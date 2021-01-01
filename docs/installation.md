# Installation
## Dependencies
- [Django](https://github.com/django/django/) (3.1 and up)
- [Django Channels](https://github.com/django/channels) (2.x, 3.0 not yet supported) 
- [Django REST Framework](https://github.com/encode/django-rest-framework/)
- [`channels_redis`](https://github.com/django/channels_redis) for
  [channel layer](https://channels.readthedocs.io/en/latest/topics/channel_layers.html) support in production.
  

## Set Up

If your project already uses REST framework, but this is the first realtime component,
then make sure to install and properly configure Django Channels before continuing.

You can find details in [the Channels documentation](https://channels.readthedocs.io/en/2.x/installation.html).

1. Add `rest_live` to your `INSTALLED_APPS`
```python
INSTALLED_APPS = [
    # Any other django apps
    "rest_framework",
    "channels",
    "rest_live",
]
```
    
2. Create a `RealtimeRouter` in your ASGI routing file and add Add `router.consumer` to your websocket routing. Feel'
free to choose any URL path, here we've chosen `/ws/subscribe/`. 
```python
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path
from rest_live.routers import RealtimeRouter

router = RealtimeRouter()

websockets = AuthMiddlewareStack(
    URLRouter([
        path("ws/subscribe/", router.as_consumer(), name="subscriptions"), 
        "Other routing here...",
    ])
)
application = ProtocolTypeRouter({
    "websocket": websockets
})
```

That's it! You're now ready to configure and use `django-rest-live`.
