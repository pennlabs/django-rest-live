import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from rest_live.signals import CREATED, DELETED, UPDATED
from test_app.models import List, Todo
from tests.routing import application


@pytest.fixture
def communicator():
    return WebsocketCommunicator(application, "/ws/subscribe/")


@database_sync_to_async
def create_list(name):
    return List.objects.create(name=name)


@database_sync_to_async
def create_todo(todolist, text):
    return Todo.objects.create(list=todolist, text=text)


@database_sync_to_async
def update_todo(todo, **kwargs):
    for k, v in kwargs.items():
        setattr(todo, k, v)
    return todo.save()


@database_sync_to_async
def delete_todo(todo):
    todo.delete()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_list_subscribe_create(communicator):
    todo_list = await create_list("test list")
    connected, _ = await communicator.connect()
    assert connected
    await communicator.send_json_to(
        {
            "model": "test_app.Todo",
            "list_id": todo_list.pk,
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
    todo_list = await create_list("test list")
    new_todo: Todo = await create_todo(todo_list, "test")
    connected, _ = await communicator.connect()
    assert connected
    await communicator.send_json_to(
        {
            "model": "test_app.Todo",
            "list_id": todo_list.pk,
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
    todo_list = await create_list("test list")
    new_todo: Todo = await create_todo(todo_list, "test")
    connected, _ = await communicator.connect()
    assert connected
    await communicator.send_json_to(
        {
            "model": "test_app.Todo",
            "list_id": todo_list.pk,
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
