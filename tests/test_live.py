from channels.auth import AuthMiddlewareStack
from django.contrib.auth import get_user_model
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async as db

from rest_live.consumers import SubscriptionConsumer
from rest_live.decorators import __register_subscription, __clear_subscriptions
from rest_live.signals import CREATED, DELETED, UPDATED
from rest_live.testing import async_test, get_headers_for_user

from test_app.models import List, Todo
from test_app.serializers import TodoSerializer, AuthedTodoSerializer
from tests.utils import RestLiveTestCase

User = get_user_model()


def clear_subs():
    __clear_subscriptions()


def register_subscription(*args, **kwargs):
    return __register_subscription(*args, **kwargs)


class BasicTests(RestLiveTestCase):
    async def asyncSetUp(self):
        self.communicator = WebsocketCommunicator(
            SubscriptionConsumer, "/ws/subscribe/"
        )
        connected, _ = await self.communicator.connect()
        self.assertTrue(connected)
        self.list = await db(List.objects.create)(name="test list")
        register_subscription(TodoSerializer, "list_id", None)

    async def asyncTearDown(self):
        await self.communicator.disconnect()
        clear_subs()

    @async_test
    async def test_list_subscribe_create(self):
        await self.subscribe_to_list()

        new_todo = await db(Todo.objects.create)(list=self.list, text="test")
        await self.assertReceivedUpdateForTodo(new_todo, CREATED)

    @async_test
    async def test_list_unsubscribe(self):
        await self.subscribe_to_list()

        new_todo = await self.make_todo()
        await self.assertReceivedUpdateForTodo(new_todo, CREATED)
        await self.unsubscribe_from_list()
        await self.make_todo()
        self.assertTrue(await self.communicator.receive_nothing())

    @async_test
    async def test_list_unsubscribe_does_stack(self):
        # Subscribe twice.
        await self.subscribe_to_list()
        await self.subscribe_to_list()

        # Make a new instance and assert that only one response is sent to the client.
        new_todo = await self.make_todo()
        await self.assertReceivedUpdateForTodo(new_todo, CREATED)
        self.assertTrue(await self.communicator.receive_nothing())

        # Unsubscribe once, make sure the message is still sent on update.
        await self.unsubscribe_from_list()
        new_todo.done = True
        await db(new_todo.save)()
        await self.assertReceivedUpdateForTodo(new_todo, UPDATED)

        # Unsubscribe again, make sure no message is sent on update.
        await self.unsubscribe_from_list()
        new_todo.text = "changed"
        await db(new_todo.save)()
        self.assertTrue(await self.communicator.receive_nothing())

    @async_test
    async def test_list_subscribe_update(self):
        new_todo = await self.make_todo()
        await self.subscribe_to_list()
        new_todo.done = True
        await db(new_todo.save)()
        await self.assertReceivedUpdateForTodo(new_todo, UPDATED)

    @async_test
    async def test_list_subscribe_delete(self):
        new_todo: Todo = await self.make_todo()
        await self.subscribe_to_list()
        pk = new_todo.pk
        await db(new_todo.delete)()
        new_todo.id = pk
        await self.assertReceivedUpdateForTodo(new_todo, DELETED)


class PermissionsTests(RestLiveTestCase):
    async def asyncSetUp(self):
        register_subscription(
            TodoSerializer, "list_id", lambda u, i: u.is_authenticated
        )
        self.list = await db(List.objects.create)(name="test list")
        self.communicator = WebsocketCommunicator(
            AuthMiddlewareStack(SubscriptionConsumer), "/ws/subscribe/"
        )
        connected, _ = await self.communicator.connect()
        self.assertTrue(connected)

        self.user = await db(User.objects.create_user)("test")
        headers = await get_headers_for_user(self.user)
        self.auth_communicator = WebsocketCommunicator(
            AuthMiddlewareStack(SubscriptionConsumer), "/ws/subscribe/", headers
        )
        connected, _ = await self.auth_communicator.connect()
        self.assertTrue(connected)

    async def asyncTearDown(self):
        await self.communicator.disconnect()
        await self.auth_communicator.disconnect()

        clear_subs()

    @async_test
    async def test_list_sub_no_permission(self):
        await self.subscribe_to_list()
        await self.make_todo()
        self.assertTrue(await self.communicator.receive_nothing())

    @async_test
    async def test_list_sub_with_permission(self):
        await self.subscribe_to_list(self.auth_communicator)
        new_todo = await self.make_todo()
        await self.assertReceivedUpdateForTodo(
            new_todo, CREATED, self.auth_communicator
        )

    @async_test
    async def test_list_sub_conditional_serializers(self):
        clear_subs()
        register_subscription(
            TodoSerializer, "list_id", lambda u, i: not u.is_authenticated
        )
        register_subscription(
            AuthedTodoSerializer, "list_id", lambda u, i: u.is_authenticated
        )
        await self.subscribe_to_list(self.communicator)
        await self.subscribe_to_list(self.auth_communicator)
        new_todo = await self.make_todo()

        await self.assertReceivedUpdateForTodo(new_todo, CREATED, self.communicator)
        await self.assertReceivedUpdateForTodo(
            new_todo, CREATED, self.auth_communicator, serializer=AuthedTodoSerializer
        )

        # Assert that each connection has only received a single update.
        self.assertTrue(await self.communicator.receive_nothing())
        self.assertTrue(await self.auth_communicator.receive_nothing())
