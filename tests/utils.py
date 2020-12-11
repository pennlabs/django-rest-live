from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model

from django.test import TransactionTestCase
from djangorestframework_camel_case.util import camelize

from test_app.models import List, Todo
from test_app.serializers import TodoSerializer


User = get_user_model()
db = database_sync_to_async


def async_test(fun):
    async def wrapped(self, *args, **kwargs):
        await self.asyncSetUp()
        ret = await fun(self, *args, **kwargs)
        await self.asyncTearDown()
        return ret

    return wrapped


class RestLiveTestCase(TransactionTestCase):
    communicator: WebsocketCommunicator
    list: List

    async def subscribe(self, model, property, value, communicator=None):
        if communicator is None:
            communicator = self.communicator
        await communicator.send_json_to(
            {
                "model": model,
                "property": property,
                "value": value,
            }
        )
        self.assertTrue(await communicator.receive_nothing())

    async def unsubscribe(self, model, property, value, communicator=None):
        if communicator is None:
            communicator = self.communicator
        await communicator.send_json_to(
            {
                "unsubscribe": True,
                "model": model,
                "property": property,
                "value": value,
            }
        )
        self.assertTrue(await communicator.receive_nothing())

    async def assertResponseEquals(self, expected, communicator=None):
        if communicator is None:
            communicator = self.communicator
        response = await communicator.receive_json_from()
        self.assertDictEqual(response, expected)

    def make_todo_sub_response(
        self, todo, action, group_by_field="pk", serializer=TodoSerializer
    ):
        return {
            "model": "test_app.Todo",
            "instance": camelize(serializer(todo).data),
            "action": action,
            "group_key_value": getattr(todo, group_by_field),
        }

    async def subscribe_to_list(self, communicator=None):
        await self.subscribe("test_app.Todo", "list_id", self.list.pk, communicator)

    async def unsubscribe_from_list(self, communicator=None):
        await self.unsubscribe("test_app.Todo", "list_id", self.list.pk, communicator)

    async def make_todo(self):
        return await db(Todo.objects.create)(list=self.list, text="test")

    async def assertReceivedUpdateForTodo(
        self, todo, action, communicator=None, serializer=TodoSerializer
    ):
        await self.assertResponseEquals(
            self.make_todo_sub_response(todo, action, "list_id", serializer),
            communicator,
        )
