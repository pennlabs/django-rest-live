import pytest
from channels.testing import WebsocketCommunicator

from rest_live.decorators import __register_subscription, __clear_subscriptions
from rest_live.signals import CREATED
from test_app.serializers import TodoSerializer, AuthedTodoSerializer
from tests.routing import application
from tests.utils import (
    create_list,
    create_todo,
    create_user,
    force_login,
    communicator,
)  # noqa


def teardown_function():
    __clear_subscriptions()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_list_subscribe_permissions_fails_when_not_authed(
    communicator: WebsocketCommunicator,
):
    __register_subscription(TodoSerializer, "list_id", lambda u, i: u.is_authenticated)
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


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_list_subscribe_permissions_succeeds_when_authed(
    communicator: WebsocketCommunicator,
):
    __register_subscription(TodoSerializer, "list_id", lambda u, i: u.is_authenticated)
    user = await create_user("user")

    cookies = await force_login(user)
    headers = [(b"cookie", cookies.output(header="", sep="; ").encode())]
    communicator = WebsocketCommunicator(application, "/ws/subscribe/", headers)

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
    new_todo = await create_todo(todo_list, "test")
    response = await communicator.receive_json_from()
    assert response == {
        "model": "test_app.Todo",
        "instance": {
            "id": new_todo.id,
            "text": "test",
            "done": False,
            "anotherField": True,
        },
        "action": CREATED,
        "group_key_value": todo_list.pk,
    }
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_list_subscribe_permissions_multiple_serializers_by_auth(
    communicator: WebsocketCommunicator,
):
    __register_subscription(
        TodoSerializer, "list_id", lambda u, i: not u.is_authenticated, rank=1
    )
    __register_subscription(
        AuthedTodoSerializer, "list_id", lambda u, i: u.is_authenticated, rank=0
    )
    user = await create_user("user")
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

    new_todo = await create_todo(todo_list, "test")
    response = await communicator.receive_json_from()
    assert response == {
        "model": "test_app.Todo",
        "instance": {
            "id": new_todo.id,
            "text": "test",
            "done": False,
            "anotherField": True,
        },
        "action": CREATED,
        "group_key_value": todo_list.pk,
    }
    await communicator.disconnect()

    cookies = await force_login(user)
    headers = [(b"cookie", cookies.output(header="", sep="; ").encode())]
    communicator = WebsocketCommunicator(application, "/ws/subscribe/", headers)

    connected, _ = await communicator.connect()
    assert connected
    await communicator.send_json_to(
        {
            "model": "test_app.Todo",
            "property": "list_id",
            "value": todo_list.pk,
        }
    )
    new_todo = await create_todo(todo_list, "test")
    response = await communicator.receive_json_from()
    assert response == {
        "model": "test_app.Todo",
        "instance": {
            "id": new_todo.id,
            "text": "test",
            "done": False,
            "anotherField": True,
            "auth": "ADMIN",
        },
        "action": CREATED,
        "group_key_value": todo_list.pk,
    }
    await communicator.disconnect()
