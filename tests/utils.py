from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model

from django.test import TransactionTestCase
from djangorestframework_camel_case.util import camelize

from test_app.models import List, Todo
from test_app.serializers import TodoSerializer


User = get_user_model()
db = database_sync_to_async


class RestLiveTestCase(TransactionTestCase):
    client: WebsocketCommunicator
    list: List

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.counter = 0

    async def subscribe(self, model, group_by, value, client=None):
        self.counter += 1
        request_id = self.counter

        if client is None:
            client = self.client
        await client.send_json_to(
            {
                "request_id": request_id,
                "model": model,
                "group_by": group_by,
                "value": value,
            }
        )
        self.assertTrue(await client.receive_nothing())
        return request_id

    async def unsubscribe(self, request_id, client=None):
        if client is None:
            client = self.client
        await client.send_json_to(
            {
                "request_id": request_id,
                "unsubscribe": True,
            }
        )
        self.assertTrue(await client.receive_nothing())

    async def assertResponseEquals(self, expected, communicator=None):
        if communicator is None:
            communicator = self.client
        response = await communicator.receive_json_from()
        self.assertDictEqual(response, expected)

    def make_todo_sub_response(
        self, todo, action, request_id, serializer=TodoSerializer
    ):
        return {
            "type": "broadcast",
            "request_id": request_id,
            "model": "test_app.Todo",
            "action": action,
            "instance": camelize(serializer(todo).data),
        }

    async def subscribe_to_list(self, communicator=None):
        return await self.subscribe(
            "test_app.Todo", "list_id", self.list.pk, communicator
        )

    async def make_todo(self):
        return await db(Todo.objects.create)(list=self.list, text="test")

    async def assertReceivedUpdateForTodo(
        self, todo, action, request_id, communicator=None, serializer=TodoSerializer
    ):
        await self.assertResponseEquals(
            self.make_todo_sub_response(todo, action, request_id, serializer),
            communicator,
        )
