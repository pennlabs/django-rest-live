# Installation
## Dependencies
- [Django](https://github.com/django/django/) (3.1 and up)
- [Django Channels](https://github.com/django/channels) (2.x and 3.x both supported) 
- [Django REST Framework](https://github.com/encode/django-rest-framework/) (3.11 and up)
- [`channels_redis`](https://github.com/django/channels_redis) for
  [channel layer](https://channels.readthedocs.io/en/latest/topics/channel_layers.html) support in production.
  

## Set Up

If you haven't 
[installed and properly configured Django Channels](https://channels.readthedocs.io/en/latest/installation.html),
then make sure to do that before continuing on with Django REST Live.

1. Add `rest_live` to your `INSTALLED_APPS`.
```python
INSTALLED_APPS = [
    # Any other django apps
    "rest_framework",
    "channels",
    "rest_live",
]
```
    
2. Create a `RealtimeRouter` in your ASGI routing file and add `router.consumer` to the websocket routing you set up
   with Django Channels. Feel free to choose any URL path, here we've chosen `/ws/subscribe/`. 
```python
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path
from rest_live.routers import RealtimeRouter

router = RealtimeRouter()

websockets = AuthMiddlewareStack(
    URLRouter([
        path("ws/subscribe/", router.as_consumer().as_asgi(), name="subscriptions"), 
        # Other routing here...
    ])
)
application = ProtocolTypeRouter({
    "websocket": websockets
})
```

> Note: if using Channels version 2, omit the `as_asgi()` method.

That's it! You're now ready to configure and use `django-rest-live`.
