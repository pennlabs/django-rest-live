from urllib.parse import urlparse, unquote
import json

from asgiref.sync import async_to_sync
from asgiref.testing import ApplicationCommunicator
from django.conf import settings
from django.http import HttpRequest, SimpleCookie
from importlib import import_module
from channels.db import database_sync_to_async


class APICommunicator(ApplicationCommunicator):
    def __init__(self, application, path, headers=None, subprotocols=None, **extra):
        if not isinstance(path, str):
            raise TypeError("Expected str, got {}".format(type(path)))
        parsed = urlparse(path)

        self.scope = {
            "asgi": {"version": "3.0"},
            "type": "websocket",
            "scheme": "ws",
            "http_version": "1.1",
            "client": ["127.0.0.1", 0],
            "server": ("testserver", "80"),
            "path": unquote(parsed.path),
            "query_string": parsed.query.encode("utf-8"),
            "headers": headers or [],
            "subprotocols": subprotocols or [],
            **extra,
        }
        super().__init__(application, self.scope)

    async def connect(self, timeout=1):
        """
        Trigger the connection code.

        On an accepted connection, returns (True, <chosen-subprotocol>)
        On a rejected connection, returns (False, <close-code>)
        """
        await self.send_input({"type": "websocket.connect"})
        response = await self.receive_output(timeout)
        if response["type"] == "websocket.close":
            return (False, response.get("code", 1000))
        else:
            return (True, response.get("subprotocol", None))

    async def send_to(self, text_data=None, bytes_data=None):
        """
        Sends a WebSocket frame to the application.
        """
        # Make sure we have exactly one of the arguments
        assert bool(text_data) != bool(
            bytes_data
        ), "You must supply exactly one of text_data or bytes_data"
        # Send the right kind of event
        if text_data:
            assert isinstance(text_data, str), "The text_data argument must be a str"
            await self.send_input({"type": "websocket.receive", "text": text_data})
        else:
            assert isinstance(
                bytes_data, bytes
            ), "The bytes_data argument must be bytes"
            await self.send_input({"type": "websocket.receive", "bytes": bytes_data})

    async def send_json_to(self, data):
        """
        Sends JSON data as a text frame
        """
        await self.send_to(text_data=json.dumps(data))

    async def receive_from(self, timeout=1):
        """
        Receives a data frame from the view. Will fail if the connection
        closes instead. Returns either a bytestring or a unicode string
        depending on what sort of frame you got.
        """
        response = await self.receive_output(timeout)
        # Make sure this is a send message
        assert response["type"] == "websocket.send"
        # Make sure there's exactly one key in the response
        assert ("text" in response) != (
            "bytes" in response
        ), "The response needs exactly one of 'text' or 'bytes'"
        # Pull out the right key and typecheck it for our users
        if "text" in response:
            assert isinstance(response["text"], str), "Text frame payload is not str"
            return response["text"]
        else:
            assert isinstance(
                response["bytes"], bytes
            ), "Binary frame payload is not bytes"
            return response["bytes"]

    async def receive_json_from(self, timeout=1):
        """
        Receives a JSON text frame payload and decodes it
        """
        payload = await self.receive_from(timeout)
        assert isinstance(payload, str), "JSON data is not a text frame"
        return json.loads(payload)

    async def disconnect(self, code=1000, timeout=1):
        """
        Closes the socket
        """
        await self.send_input({"type": "websocket.disconnect", "code": code})
        await self.wait(timeout)


def async_test(fun):
    async def wrapped(self, *args, **kwargs):
        if hasattr(self, "asyncSetUp"):
            await self.asyncSetUp()
        ret = await fun(self, *args, **kwargs)
        if hasattr(self, "asyncTearDown"):
            await self.asyncTearDown()
        return ret

    return wrapped


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


async def get_headers_for_user(user):
    cookies = await force_login(user)
    return [(b"cookie", cookies.output(header="", sep="; ").encode())]
