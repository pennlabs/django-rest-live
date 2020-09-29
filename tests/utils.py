from importlib import import_module

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpRequest, SimpleCookie

from test_app.models import List, Todo
from tests.routing import application


User = get_user_model()


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
def login(**credentials):
    from django.contrib.auth import authenticate

    user = authenticate(**credentials)
    if user:
        return _login(user)
    else:
        return SimpleCookie()


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


@pytest.fixture
def communicator():
    from test_app import serializers  # noqa

    return WebsocketCommunicator(application, "/ws/subscribe/")


@database_sync_to_async
def create_list(name):
    return List.objects.create(name=name)


@database_sync_to_async
def create_todo(todolist, text, owner=None):
    return Todo.objects.create(list=todolist, text=text, owner=owner)


@database_sync_to_async
def update_todo(todo, **kwargs):
    for k, v in kwargs.items():
        setattr(todo, k, v)
    return todo.save()


@database_sync_to_async
def delete_todo(todo):
    todo.delete()


@database_sync_to_async
def create_user(username):
    return User.objects.create_user(username)
