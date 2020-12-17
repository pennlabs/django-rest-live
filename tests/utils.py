from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model

from django.test import TransactionTestCase
from djangorestframework_camel_case.util import camelize

from rest_live.testing import APICommunicator
from test_app.models import List, Todo
from test_app.serializers import TodoSerializer


User = get_user_model()
db = database_sync_to_async


class RestLiveTestCase(TransactionTestCase):
    client: APICommunicator
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
                "type": "subscribe",
                "id": request_id,
                "model": model,
                "group_by": group_by,
                "value": value,
            }
        )
        return request_id

    async def unsubscribe(self, request_id, client=None):
        if client is None:
            client = self.client
        await client.send_json_to(
            {
                "type": "unsubscribe",
                "id": request_id,
            }
        )
        self.assertTrue(await client.receive_nothing())

    async def assertResponseEquals(self, expected, client=None):
        if client is None:
            client = self.client
        response = await client.receive_json_from()
        self.assertDictEqual(response, expected)

    def make_todo_sub_response(
        self, todo, action, request_id, serializer=TodoSerializer
    ):
        return {
            "type": "broadcast",
            "id": request_id,
            "model": "test_app.Todo",
            "action": action,
            "instance": camelize(serializer(todo).data),
        }

    async def subscribe_to_list(self, client=None, error=None):
        if client is None:
            client = self.client

        request_id = await self.subscribe(
            "test_app.Todo", "list_id", self.list.pk, client
        )
        if error is None:
            self.assertTrue(await client.receive_nothing())
        else:
            msg = await client.receive_json_from()
            self.assertTrue(error, msg["code"])
        return request_id

    async def make_todo(self):
        return await db(Todo.objects.create)(list=self.list, text="test")

    async def assertReceivedUpdateForTodo(
        self, todo, action, request_id, communicator=None, serializer=TodoSerializer
    ):
        await self.assertResponseEquals(
            self.make_todo_sub_response(todo, action, request_id, serializer),
            communicator,
        )
