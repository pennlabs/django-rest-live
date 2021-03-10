from channels.auth import AuthMiddlewareStack
from django.contrib.auth import get_user_model
from rest_framework.generics import GenericAPIView
from rest_framework.views import APIView

from rest_live.mixins import RealtimeMixin
from rest_live.testing import APICommunicator
from channels.db import database_sync_to_async as db

from rest_live import CREATED, UPDATED, DELETED
from rest_live.routers import RealtimeRouter
from rest_live.testing import async_test, get_headers_for_user

from test_app.models import List, Todo, UUIDTodo
from test_app.serializers import AuthedTodoSerializer, TodoSerializer
from test_app.views import (
    TodoViewSet,
    AuthedTodoViewSet,
    ConditionalTodoViewSet,
    KwargViewSet,
    FilteredViewSet,
    UUIDTodoViewSet,
)
from tests.utils import RestLiveTestCase

User = get_user_model()


class BasicResourceTests(RestLiveTestCase):
    """
    Basic subscription tests on single resources, retrieving by the lookup_field
    on the view.
    """

    async def asyncSetUp(self):
        router = RealtimeRouter()
        router.register(TodoViewSet)

        self.client = APICommunicator(router.as_consumer(), "/ws/subscribe/")
        connected, _ = await self.client.connect()
        self.assertTrue(connected)
        self.list = await db(List.objects.create)(name="test list")

    async def asyncTearDown(self):
        await self.client.disconnect()

    @async_test
    async def test_single_update(self):
        self.todo = await self.make_todo("test")
        other_todo = await self.make_todo("another")
        req = await self.subscribe_to_todo()

        self.todo.text = "MODIFIED"
        await db(self.todo.save)()
        await self.assertReceivedBroadcastForTodo(self.todo, UPDATED, req)

        # Modifying other instances shouldn't trigger a message
        other_todo.text = "MODIFIED TOO"
        await db(other_todo.save)()
        assert await self.client.receive_nothing()

    @async_test
    async def test_list_unsubscribe(self):
        self.todo = await self.make_todo()
        req = await self.subscribe_to_todo()
        self.todo.text = "MODIFIED"
        await db(self.todo.save)()
        await self.assertReceivedBroadcastForTodo(self.todo, UPDATED, req)
        await self.unsubscribe(req)
        self.todo.text = "MODIFIED AGAIN"
        await db(self.todo.save)()
        self.assertTrue(await self.client.receive_nothing())


class BasicListTests(RestLiveTestCase):
    """
    Basic tests on list actions based on a foreign key.
    """

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
        await self.assertReceivedBroadcastForTodo(new_todo, CREATED, req)

    @async_test
    async def test_list_unsubscribe(self):
        req = await self.subscribe_to_list()

        new_todo = await self.make_todo()
        await self.assertReceivedBroadcastForTodo(new_todo, CREATED, req)
        await self.unsubscribe(req)
        await self.make_todo()
        self.assertTrue(await self.client.receive_nothing())

    @async_test
    async def test_list_unsubscribe_does_stack(self):
        # Subscribe twice.
        req1 = await self.subscribe_to_list()
        req2 = await self.subscribe_to_list()

        new_todo = await self.make_todo()
        await self.assertReceivedBroadcastForTodo(new_todo, CREATED, req1)
        await self.assertReceivedBroadcastForTodo(new_todo, CREATED, req2)
        self.assertTrue(await self.client.receive_nothing())

        # Unsubscribe once, make sure the message is still sent on update.
        await self.unsubscribe(req1)
        new_todo.done = True
        await db(new_todo.save)()
        await self.assertReceivedBroadcastForTodo(new_todo, UPDATED, req2)
        self.assertTrue(await self.client.receive_nothing())

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
        await self.assertReceivedBroadcastForTodo(new_todo, UPDATED, req)

    # TODO: Fix delete
    # TODO: Think about adding a way to mark a field as a "conditional delete" so when it updates in the DB it
    #       sends the delete signal to the frontend
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
        await self.assertReceivedBroadcastForTodo(
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

        await self.assertReceivedBroadcastForTodo(
            new_todo, CREATED, req, communicator=self.client
        )
        await self.assertReceivedBroadcastForTodo(
            new_todo,
            CREATED,
            req_auth,
            communicator=self.auth_client,
            serializer=AuthedTodoSerializer,
        )

        # Assert that each connection has only received a single update.
        self.assertTrue(await self.client.receive_nothing())
        self.assertTrue(await self.auth_client.receive_nothing())


class ViewKwargTests(RestLiveTestCase):
    """
    Tests to ensure that view kwargs (generally URL parameters) passed along with subscriptions are
    properly handled in permissions and serializers.
    """

    async def asyncSetUp(self):
        router = RealtimeRouter()
        router.register(KwargViewSet)
        self.client = APICommunicator(router.as_consumer(), "/ws/subscribe/")
        connected, _ = await self.client.connect()
        self.assertTrue(connected)
        self.list = await db(List.objects.create)(name="test list")

    async def asyncTearDown(self):
        await self.client.disconnect()

    @async_test
    async def test_permission_with_kwargs_fails(self):
        await self.subscribe_to_list(error=403)
        new_todo = await db(Todo.objects.create)(list=self.list, text="test")
        self.assertTrue(await self.client.receive_nothing())

    @async_test
    async def test_permission_with_kwargs_succeeds(self):
        await self.subscribe_to_list(kwargs={"password": "opensesame"})

    @async_test
    async def test_permission_with_params_succeeds(self):
        await self.subscribe_to_list(params={"password": "opensesame-param"})

    @async_test
    async def test_serializer_with_kwargs(self):
        request_id = await self.subscribe_to_list(
            kwargs={"password": "opensesame", "message": "hello"}
        )
        new_todo = await db(Todo.objects.create)(list=self.list, text="test")
        response = await self.client.receive_json_from()
        self.assertDictEqual(
            {
                "type": "broadcast",
                "id": request_id,
                "model": "test_app.Todo",
                "action": CREATED,
                "instance": {"message": "hello"},
            },
            response,
        )


class QueryParamsTests(RestLiveTestCase):
    """
    Tests to ensure that query (GET) params passed along with subscriptions are
    handled properly. This ensures compatibility with DRF filter backends.
    """

    async def asyncSetUp(self):
        router = RealtimeRouter()
        router.register(TodoViewSet)
        self.client = APICommunicator(router.as_consumer(), "/ws/subscribe/")
        connected, _ = await self.client.connect()
        self.assertTrue(connected)
        self.list = await db(List.objects.create)(name="test list")

    async def asyncTearDown(self):
        await self.client.disconnect()

    @async_test
    async def test_list(self):
        request_id = await self.subscribe_to_list(params={"search": "hello"})

        todo = await self.make_todo("hello world")
        await self.assertReceivedBroadcastForTodo(todo, CREATED, request_id)

        await db(todo.save)()
        await self.assertReceivedBroadcastForTodo(todo, UPDATED, request_id)

        todo.text = "goodbye world"  # No longer matches search query
        await db(todo.save)()
        await self.assertReceivedBroadcastForTodo(todo, DELETED, request_id)

        # Make sure new ToDos that don't match the query are never broadcasted
        await self.make_todo("no match")
        self.assertTrue(await self.client.receive_nothing())


class QuerysetFetchTest(RestLiveTestCase):
    """
    Tests to make sure that subscriptions properly respect the queryset on the view.
    """

    async def asyncSetUp(self):
        router = RealtimeRouter()
        router.register(FilteredViewSet)
        self.client = APICommunicator(router.as_consumer(), "/ws/subscribe/")
        connected, _ = await self.client.connect()
        self.assertTrue(connected)
        self.list = await db(List.objects.create)(name="test list")

    async def asyncTearDown(self):
        await self.client.disconnect()

    @async_test
    async def test_empty_queryset_not_found_list(self):
        await self.subscribe_to_list()
        new_todo = await db(Todo.objects.create)(list=self.list, text="test")
        self.assertTrue(await self.client.receive_nothing())

    @async_test
    async def test_empty_queryset_not_found_individual(self):
        self.todo = await db(Todo.objects.create)(list=self.list, text="test")
        await self.subscribe_to_todo(client=self.client, error=404)

    @async_test
    async def test_filter_matches(self):
        req = await self.subscribe_to_list()
        new_todo = await self.make_todo("special")
        await self.assertReceivedBroadcastForTodo(new_todo, CREATED, req)

    @async_test
    async def test_filter_matches_then_doesnt(self):
        new_todo = await self.make_todo("special")
        req = await self.subscribe_to_list()
        new_todo.text = "not special"
        await db(new_todo.save)()
        await self.assertReceivedBroadcastForTodo(new_todo, DELETED, req)
        new_todo.text = "not special at all"
        # Make sure we only send the delete message once
        await db(new_todo.save)()
        self.assertTrue(await self.client.receive_nothing())

    @async_test
    async def test_filter_doesnt_match_then_does(self):
        new_todo = await self.make_todo("not special")
        req = await self.subscribe_to_list()
        new_todo.text = "special"
        await db(new_todo.save)()
        await self.assertReceivedBroadcastForTodo(new_todo, CREATED, req)


class PrivateRouterTests(RestLiveTestCase):
    async def asyncSetUp(self):
        self.list = await db(List.objects.create)(name="test list")
        self.router = RealtimeRouter(public=False)
        self.router.register(TodoViewSet)

    @async_test
    async def test_reject_no_auth(self):
        self.client = APICommunicator(
            AuthMiddlewareStack(self.router.as_consumer()),
            "/ws/subscribe/",
        )
        connected, code = await self.client.connect()
        self.assertFalse(connected)
        self.assertEqual(4003, code)

    @async_test
    async def test_reject_no_middleware(self):
        self.client = APICommunicator(
            self.router.as_consumer(),
            "/ws/subscribe/",
        )
        connected, code = await self.client.connect()
        self.assertFalse(connected)
        self.assertEqual(4003, code)

    @async_test
    async def test_accept_with_auth(self):
        user = await db(User.objects.create_user)("test")
        headers = await get_headers_for_user(user)
        self.client = APICommunicator(
            AuthMiddlewareStack(self.router.as_consumer()), "/ws/subscribe/", headers
        )
        connected, _ = await self.client.connect()
        self.assertTrue(connected)


class MultiRouterTests(RestLiveTestCase):
    """
    Tests to ensure that multiple routers/consumers can be stood up on
    separate domains and that they don't interfere with each other.
    """

    async def asyncSetUp(self):
        self.list = await db(List.objects.create)(name="test list")
        self.router1 = RealtimeRouter()
        self.router1.register(TodoViewSet)
        self.router2 = RealtimeRouter("auth")
        self.router2.register(AuthedTodoViewSet)

        self.user = await db(User.objects.create_user)("test")
        self.headers = await get_headers_for_user(self.user)

    async def asyncTearDown(self):
        await self.client1.disconnect()
        await self.client2.disconnect()

    @async_test
    async def test_broadcasts_one_per_router(self):
        self.client1 = APICommunicator(
            AuthMiddlewareStack(self.router1.as_consumer()),
            "/ws/subscribe/",
            self.headers,
        )
        self.assertTrue(await self.client1.connect())
        self.client2 = APICommunicator(
            AuthMiddlewareStack(self.router2.as_consumer()),
            "/ws/subscribe/auth/",
            self.headers,
        )
        self.assertTrue(await self.client2.connect())

        req1 = await self.subscribe_to_list(self.client1)
        req2 = await self.subscribe_to_list(self.client2)

        new_todo = await db(Todo.objects.create)(list=self.list, text="test")
        await self.assertReceivedBroadcastForTodo(new_todo, CREATED, req1, self.client1)
        self.assertTrue(await self.client1.receive_nothing())
        await self.assertReceivedBroadcastForTodo(new_todo, CREATED, req2, self.client2)
        self.assertTrue(await self.client2.receive_nothing())

    @async_test
    async def test_broadcasts_only_to_one(self):
        self.client1 = APICommunicator(
            AuthMiddlewareStack(self.router1.as_consumer()),
            "/ws/subscribe/",
            self.headers,
        )
        self.assertTrue(await self.client1.connect())
        self.client2 = APICommunicator(
            AuthMiddlewareStack(self.router2.as_consumer()), "/ws/subscribe/auth/"
        )
        self.assertTrue(await self.client2.connect())

        req1 = await self.subscribe_to_list(self.client1)
        req2 = await self.subscribe_to_list(self.client2, 403)

        new_todo = await db(Todo.objects.create)(list=self.list, text="test")
        await self.assertReceivedBroadcastForTodo(new_todo, CREATED, req1, self.client1)
        self.assertTrue(await self.client1.receive_nothing())
        self.assertTrue(await self.client2.receive_nothing())


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

    async def assertReceiveError(self, request_id, error_code):
        response = await self.client.receive_json_from()
        self.assertEqual("error", response["type"])
        self.assertEqual(request_id, response["id"])
        self.assertEqual(error_code, response["code"])

    @async_test
    async def test_unsubscribe_before_subscribe(self):
        await self.client.send_json_to({"id": 1337, "type": "unsubscribe"})
        await self.assertReceiveError(1337, 404)

    @async_test
    async def test_no_model_in_request(self):
        await self.client.send_json_to({"type": "subscribe", "id": 1337, "value": 1})
        await self.assertReceiveError(1337, 400)

    @async_test
    async def test_no_value_in_request(self):
        await self.client.send_json_to(
            {"type": "subscribe", "id": 1337, "model": "test_app.Todo"}
        )
        await self.assertReceiveError(1337, 400)

    @async_test
    async def test_subscribe_to_unknown_model(self):
        await self.client.send_json_to(
            {"type": "subscribe", "id": 1337, "model": "blah.Model", "value": 1}
        )
        await self.assertReceiveError(1337, 404)


class UUIDTodoTests(RestLiveTestCase):
    """
    Tests compatibility with models that use non-integer IDs
    """

    async def asyncSetUp(self):
        router = RealtimeRouter()
        router.register(UUIDTodoViewSet)
        self.client = APICommunicator(router.as_consumer(), "/ws/subscribe/")
        connected, _ = await self.client.connect()
        self.assertTrue(connected)

    async def asyncTearDown(self):
        await self.client.disconnect()

    @async_test
    async def test_list(self):
        label = UUIDTodo._meta.label
        request_id = await self.subscribe(label, "list")
        self.assertTrue(await self.client.receive_nothing())

        todo = await db(UUIDTodo.objects.create)()
        response = await self.client.receive_json_from()
        self.assertDictEqual(
            {
                "type": "broadcast",
                "id": request_id,
                "model": label,
                "action": CREATED,
                "instance": {"id": str(todo.id)},
            },
            response,
        )

        await db(todo.save)()
        response = await self.client.receive_json_from()
        self.assertDictEqual(
            {
                "type": "broadcast",
                "id": request_id,
                "model": label,
                "action": UPDATED,
                "instance": {"id": str(todo.id)},
            },
            response,
        )

        todo.included = False
        await db(todo.save)()
        response = await self.client.receive_json_from()
        self.assertDictEqual(
            {
                "type": "broadcast",
                "id": request_id,
                "model": label,
                "action": DELETED,
                "instance": {"id": str(todo.id), "pk": str(todo.id)},
            },
            response,
        )

    @async_test
    async def test_retrieve(self):
        label = UUIDTodo._meta.label
        todo = await db(UUIDTodo.objects.create)()
        request_id = await self.subscribe(label, "retrieve", str(todo.id))
        self.assertTrue(await self.client.receive_nothing())

        await db(todo.save)()
        response = await self.client.receive_json_from()
        self.assertDictEqual(
            {
                "type": "broadcast",
                "id": request_id,
                "model": label,
                "action": UPDATED,
                "instance": {"id": str(todo.id)},
            },
            response,
        )

        todo.included = False
        await db(todo.save)()
        response = await self.client.receive_json_from()
        self.assertDictEqual(
            {
                "type": "broadcast",
                "id": request_id,
                "model": label,
                "action": DELETED,
                "instance": {"id": str(todo.id), "pk": str(todo.id)},
            },
            response,
        )
