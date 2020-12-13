from channels.auth import AuthMiddlewareStack
from django.contrib.auth import get_user_model
from rest_live.testing import APICommunicator
from channels.db import database_sync_to_async as db

from rest_live import CREATED, UPDATED, DELETED
from rest_live.consumers import RealtimeRouter
from rest_live.testing import async_test, get_headers_for_user

from test_app.models import List, Todo
from test_app.serializers import AuthedTodoSerializer
from test_app.views import TodoViewSet, AuthedTodoViewSet, ConditionalTodoViewSet
from tests.utils import RestLiveTestCase

User = get_user_model()

"""
TODO for tests
- Test inferring model class from static model serializer
- Error cases
"""


class BasicTests(RestLiveTestCase):
    async def asyncSetUp(self):
        router = RealtimeRouter()
        router.register(TodoViewSet)

        self.client = APICommunicator(router.consumer, "/ws/subscribe/")
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
            AuthMiddlewareStack(router.consumer),
            "/ws/subscribe/",
        )
        connected, _ = await self.client.connect()
        self.assertTrue(connected)

        self.user = await db(User.objects.create_user)("test")
        headers = await get_headers_for_user(self.user)
        self.auth_client = APICommunicator(
            AuthMiddlewareStack(router.consumer),
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
        await self.subscribe_to_list()
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
            AuthMiddlewareStack(router.consumer),
            "/ws/subscribe/",
        )
        connected, _ = await self.client.connect()
        self.assertTrue(connected)

        headers = await get_headers_for_user(self.user)
        self.auth_client = APICommunicator(
            AuthMiddlewareStack(router.consumer),
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
