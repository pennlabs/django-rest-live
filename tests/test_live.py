from channels.auth import AuthMiddlewareStack
from django.contrib.auth import get_user_model
from rest_framework.generics import GenericAPIView
from rest_framework.views import APIView

from rest_live.mixins import RealtimeMixin
from rest_live.testing import APICommunicator
from channels.db import database_sync_to_async as db

from rest_live import CREATED, UPDATED, DELETED
from rest_live.consumers import RealtimeRouter
from rest_live.testing import async_test, get_headers_for_user

from test_app.models import List, Todo
from test_app.serializers import AuthedTodoSerializer, TodoSerializer
from test_app.views import TodoViewSet, AuthedTodoViewSet, ConditionalTodoViewSet
from tests.utils import RestLiveTestCase

User = get_user_model()


class BasicTests(RestLiveTestCase):
    async def asyncSetUp(self):
        router = RealtimeRouter()
        router.register(TodoViewSet)

        self.client = APICommunicator(router.as_consumer(), "/ws/subscribe/")
        connected, _ = await self.client.connect()
        self.assertTrue(connected)
        self.list = await db(List.objects.create)(name="test list")
        # register_subscription(TodoSerializer, "list_id", None)

    async def asyncTearDown(self):
        await self.client.disconnect()

    @async_test
    async def test_list_subscribe_create(self):
        req = await self.subscribe_to_list()

        new_todo = await db(Todo.objects.create)(list=self.list, text="test")
        await self.assertReceivedUpdateForTodo(new_todo, CREATED, req)

    @async_test
    async def test_list_unsubscribe(self):
        req = await self.subscribe_to_list()

        new_todo = await self.make_todo()
        await self.assertReceivedUpdateForTodo(new_todo, CREATED, req)
        await self.unsubscribe(req)
        await self.make_todo()
        self.assertTrue(await self.client.receive_nothing())

    @async_test
    async def test_list_unsubscribe_does_stack(self):
        # Subscribe twice.
        req1 = await self.subscribe_to_list()
        req2 = await self.subscribe_to_list()

        new_todo = await self.make_todo()
        await self.assertReceivedUpdateForTodo(new_todo, CREATED, req1)
        await self.assertReceivedUpdateForTodo(new_todo, CREATED, req2)
        self.assertTrue(await self.client.receive_nothing())

        # Unsubscribe once, make sure the message is still sent on update.
        await self.unsubscribe(req1)
        new_todo.done = True
        await db(new_todo.save)()
        await self.assertReceivedUpdateForTodo(new_todo, UPDATED, req2)

        # Unsubscribe again, make sure no message is sent on update.
        await self.unsubscribe(req2)
        new_todo.text = "changed"
        await db(new_todo.save)()
        self.assertTrue(await self.client.receive_nothing())

    @async_test
    async def test_list_subscribe_update(self):
        new_todo = await self.make_todo()
        req = await self.subscribe_to_list()
        new_todo.done = True
        await db(new_todo.save)()
        await self.assertReceivedUpdateForTodo(new_todo, UPDATED, req)

    # TODO: Fix delete
    # @async_test
    # async def test_list_subscribe_delete(self):
    #     new_todo: Todo = await self.make_todo()
    #     await self.subscribe_to_list()
    #     pk = new_todo.pk
    #     await db(new_todo.delete)()
    #     new_todo.id = pk
    #     await self.assertReceivedUpdateForTodo(new_todo, DELETED)


class PermissionsTests(RestLiveTestCase):
    async def asyncSetUp(self):
        self.list = await db(List.objects.create)(name="test list")
        router = RealtimeRouter()
        router.register(AuthedTodoViewSet)
        self.client = APICommunicator(
            AuthMiddlewareStack(router.as_consumer()),
            "/ws/subscribe/",
        )
        connected, _ = await self.client.connect()
        self.assertTrue(connected)

        self.user = await db(User.objects.create_user)("test")
        headers = await get_headers_for_user(self.user)
        self.auth_client = APICommunicator(
            AuthMiddlewareStack(router.as_consumer()),
            "/ws/subscribe/",
            headers,
        )
        connected, _ = await self.auth_client.connect()
        self.assertTrue(connected)

    async def asyncTearDown(self):
        await self.client.disconnect()
        await self.auth_client.disconnect()

    @async_test
    async def test_list_sub_no_permission(self):
        await self.subscribe_to_list(error=403)
        await self.make_todo()
        self.assertTrue(await self.client.receive_nothing())

    @async_test
    async def test_list_sub_with_permission(self):
        req = await self.subscribe_to_list(self.auth_client)
        new_todo = await self.make_todo()
        await self.assertReceivedUpdateForTodo(
            new_todo, CREATED, req, communicator=self.auth_client
        )

    @async_test
    async def test_list_sub_conditional_serializers(self):
        await self.client.disconnect()
        await self.auth_client.disconnect()
        router = RealtimeRouter()
        router.register(ConditionalTodoViewSet)
        self.client = APICommunicator(
            AuthMiddlewareStack(router.as_consumer()),
            "/ws/subscribe/",
        )
        connected, _ = await self.client.connect()
        self.assertTrue(connected)

        headers = await get_headers_for_user(self.user)
        self.auth_client = APICommunicator(
            AuthMiddlewareStack(router.as_consumer()),
            "/ws/subscribe/",
            headers,
        )
        connected, _ = await self.auth_client.connect()
        self.assertTrue(connected)

        req = await self.subscribe_to_list(self.client)
        req_auth = await self.subscribe_to_list(self.auth_client)
        new_todo = await self.make_todo()

        await self.assertReceivedUpdateForTodo(
            new_todo, CREATED, req, communicator=self.client
        )
        await self.assertReceivedUpdateForTodo(
            new_todo,
            CREATED,
            req_auth,
            communicator=self.auth_client,
            serializer=AuthedTodoSerializer,
        )

        # Assert that each connection has only received a single update.
        self.assertTrue(await self.client.receive_nothing())
        self.assertTrue(await self.auth_client.receive_nothing())


class RealtimeSetupErrorTests(RestLiveTestCase):
    """
    Tests making sure that we error at registration-time
    if a view does not have all the information we need to
    use it for realtime broadcasts.
    """

    async def asyncSetUp(self):
        self.router = RealtimeRouter()

    @async_test
    async def test_view_no_mixin(self):
        class TestView(GenericAPIView):
            queryset = Todo.objects.all()
            serializer_class = TodoSerializer

        self.assertRaises(RuntimeError, self.router.register, TestView)

    @async_test
    async def test_model_has_two_views(self):
        class TestView(GenericAPIView, RealtimeMixin):
            queryset = Todo.objects.all()
            serializer_class = TodoSerializer

        self.router.register(TestView)
        self.assertRaises(RuntimeWarning, self.router.register, TestView)

    @async_test
    async def test_not_apiview(self):
        class TestView(APIView, RealtimeMixin):
            pass

        self.assertRaises(AssertionError, self.router.register, TestView)

    @async_test
    async def test_no_queryset_attribute(self):
        class TestView(GenericAPIView, RealtimeMixin):
            def get_queryset(self):
                return Todo.objects.all()

        self.assertRaises(AssertionError, self.router.register, TestView)


class APIErrorTests(RestLiveTestCase):
    """
    Tests making sure we send the right errors to the client in the
    websocket API.
    """

    async def asyncSetUp(self):
        router = RealtimeRouter()
        router.register(TodoViewSet)

        self.client = APICommunicator(router.as_consumer(), "/ws/subscribe/")
        connected, _ = await self.client.connect()
        self.assertTrue(connected)

    async def asyncTearDown(self):
        await self.client.disconnect()

    @async_test
    async def test_unsubscribe_before_subscribe(self):
        await self.client.send_json_to({"id": 1337, "type": "unsubscribe"})
        response = await self.client.receive_json_from()
        self.assertEqual("error", response["type"])
        self.assertEqual(1337, response["id"])
        self.assertEqual(404, response["code"])

    @async_test
    async def test_no_model_in_request(self):
        await self.client.send_json_to({"type": "subscribe", "id": 1337, "value": 1})
        response = await self.client.receive_json_from()
        self.assertEqual("error", response["type"])
        self.assertEqual(1337, response["id"])
        self.assertEqual(400, response["code"])

    @async_test
    async def test_no_value_in_request(self):
        await self.client.send_json_to(
            {"type": "subscribe", "id": 1337, "model": "test_app.Todo"}
        )
        response = await self.client.receive_json_from()
        self.assertEqual("error", response["type"])
        self.assertEqual(1337, response["id"])
        self.assertEqual(400, response["code"])

    @async_test
    async def test_subscribe_to_unknown_model(self):
        await self.client.send_json_to(
            {"type": "subscribe", "id": 1337, "model": "blah.Model", "value": 1}
        )
        response = await self.client.receive_json_from()
        self.assertEqual("error", response["type"])
        self.assertEqual(1337, response["id"])
        self.assertEqual(404, response["code"])
