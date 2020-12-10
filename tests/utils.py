from importlib import import_module

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpRequest, SimpleCookie
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

    def make_todo_sub_response(self, todo, action, group_by_field="pk", serializer=TodoSerializer):
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

    async def assertReceivedUpdateForTodo(self, todo, action, communicator=None, serializer=TodoSerializer):
        await self.assertResponseEquals(
            self.make_todo_sub_response(todo, action, "list_id", serializer),
            communicator
        )


def _login(user, backend=None):
    from django.contrib.auth import login

    engine = import_module(settings.SESSION_ENGINE)

    # Create a fake request to store login details.
    request = HttpRequest()
    request.session = engine.SessionStore()
    login(request, user, backend)

    # Save the session values.
    request.session.save()

    # Create a cookie to represent the session.
    session_cookie = settings.SESSION_COOKIE_NAME
    cookies = SimpleCookie()
    cookies[session_cookie] = request.session.session_key
    cookie_data = {
        "max-age": None,
        "path": "/",
        "domain": settings.SESSION_COOKIE_DOMAIN,
        "secure": settings.SESSION_COOKIE_SECURE or None,
        "expires": None,
    }
    cookies[session_cookie].update(cookie_data)
    return cookies


@database_sync_to_async
def force_login(user, backend=None):
    def get_backend():
        from django.contrib.auth import load_backend

        for backend_path in settings.AUTHENTICATION_BACKENDS:
            backend = load_backend(backend_path)
            if hasattr(backend, "get_user"):
                return backend_path

    if backend is None:
        backend = get_backend()
    user.backend = backend
    return _login(user, backend)

