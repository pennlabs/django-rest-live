import pytest
from channels.testing import WebsocketCommunicator

from rest_live.decorators import __register_subscription
from rest_live.signals import CREATED, DELETED, UPDATED
from test_app.models import Todo
from test_app.serializers import TodoSerializer
from tests.utils import create_list, create_todo, delete_todo, update_todo, communicator  # noqa


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_list_subscribe_create(communicator):
    __register_subscription(TodoSerializer, "list_id", None)
    todo_list = await create_list("test list")
    connected, _ = await communicator.connect()
    assert connected
    await communicator.send_json_to(
        {
            "model": "test_app.Todo",
            "property": "list_id",
            "value": todo_list.pk,
        }
    )
    assert await communicator.receive_nothing()
    new_todo: Todo = await create_todo(todo_list, "test")
    response = await communicator.receive_json_from()
    assert response == {
        "model": "test_app.Todo",
        "instance": {"id": new_todo.id, "text": "test", "done": False},
        "action": CREATED,
    }

    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_list_subscribe_update(communicator):
    __register_subscription(TodoSerializer, "list_id", None)
    todo_list = await create_list("test list")
    new_todo: Todo = await create_todo(todo_list, "test")
    connected, _ = await communicator.connect()
    assert connected
    await communicator.send_json_to(
        {
            "model": "test_app.Todo",
            "property": "list_id",
            "value": todo_list.pk,
        }
    )
    assert await communicator.receive_nothing()
    await update_todo(new_todo, done=True)
    response = await communicator.receive_json_from()
    assert response == {
        "model": "test_app.Todo",
        "instance": {"id": new_todo.id, "text": "test", "done": True},
        "action": UPDATED,
    }

    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_list_subscribe_delete(communicator):
    __register_subscription(TodoSerializer, "list_id", None)
    todo_list = await create_list("test list")
    new_todo: Todo = await create_todo(todo_list, "test")
    connected, _ = await communicator.connect()
    assert connected
    await communicator.send_json_to(
        {
            "model": "test_app.Todo",
            "property": "list_id",
            "value": todo_list.pk,
        }
    )
    assert await communicator.receive_nothing()
    pk = new_todo.id
    await delete_todo(new_todo)
    response = await communicator.receive_json_from()
    assert response == {
        "model": "test_app.Todo",
        "instance": {"id": pk, "text": "test", "done": False},
        "action": DELETED,
    }

    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_list_subscribe_permissions_fails(communicator: WebsocketCommunicator):
    """
    This permissions check should never allow a notification to be sent.
    """
    __register_subscription(TodoSerializer, "list_id", lambda u, i: False)
    todo_list = await create_list("test list")
    connected, _ = await communicator.connect()
    assert connected
    await communicator.send_json_to(
        {
            "model": "test_app.Todo",
            "property": "list_id",
            "value": todo_list.pk,
        }
    )
    assert await communicator.receive_nothing()
    await create_todo(todo_list, "test")
    assert await communicator.receive_nothing()
    await communicator.disconnect()
