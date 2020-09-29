import pytest
from channels.testing import WebsocketCommunicator

from rest_live.decorators import __register_subscription
from rest_live.signals import CREATED
from test_app.models import Todo
from test_app.serializers import TodoSerializer
from tests.routing import application
from tests.utils import create_list, create_todo, create_user, force_login, communicator  # noqa


def auth_and_ownership_check(user, instance: Todo):
    if not user.is_authenticated:
        return False
    if instance.owner is None:
        return True

    return instance.owner == user


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_list_subscribe_permissions_fails_when_not_authed(
    communicator: WebsocketCommunicator,
):
    __register_subscription(TodoSerializer, "list_id", auth_and_ownership_check)
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
    __register_subscription(TodoSerializer, "list_id", auth_and_ownership_check)
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
        "instance": {"id": new_todo.id, "text": "test", "done": False, "anotherField": True},
        "action": CREATED,
        "group_key_value": todo_list.pk,
    }
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_list_subscribe_permissions_fails_when_not_owner(
    communicator: WebsocketCommunicator,
):
    __register_subscription(TodoSerializer, "list_id", auth_and_ownership_check)
    user = await create_user("user")
    other_user = await create_user("other")

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
    new_todo = await create_todo(todo_list, "test", owner=other_user)
    await communicator.receive_nothing()
    hey_todo = await create_todo(todo_list, "test 2", owner=user)
    response = await communicator.receive_json_from()
    assert response == {
        "model": "test_app.Todo",
        "instance": {
            "id": hey_todo.id,
            "text": hey_todo.text,
            "done": hey_todo.done,
            "anotherField": hey_todo.another_field,
        },
        "action": CREATED,
        "group_key_value": todo_list.pk,
    }
    await communicator.disconnect()
