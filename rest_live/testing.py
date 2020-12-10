from django.conf import settings
from django.http import HttpRequest, SimpleCookie
from importlib import import_module
from channels.db import database_sync_to_async


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
