## Django REST Live

[![Documentation](https://readthedocs.org/projects/django-rest-live/badge/?version=latest)](https://django-rest-live.readthedocs.io/en/latest/?badge=latest)
[![CircleCI](https://circleci.com/gh/pennlabs/django-rest-live.svg?style=shield)](https://circleci.com/gh/pennlabs/django-rest-live)
[![Coverage Status](https://codecov.io/gh/pennlabs/django-rest-live/branch/master/graph/badge.svg)](https://codecov.io/gh/pennlabs/django-rest-live)
[![PyPi Package](https://img.shields.io/pypi/v/django-rest-live.svg)](https://pypi.org/project/django-rest-live/)

Django REST Live enables clients which use an API built with [Django REST Framework](https://github.com/encode/django-rest-framework) to receive a stream of updates for querysets and model instances over a websocket connection managed by [Django Channels](https://github.com/django/channels). There had been plans for real-time websocket support in REST Framework on a few occasions ([2016](https://www.django-rest-framework.org/community/mozilla-grant/#realtime-apis), [2018](https://groups.google.com/g/django-rest-framework/c/3-QNn3SYlZI/m/Gwx6rFr4BQAJ?pli=1)), but at the time, async support in Django was in the early planning stages and Channels was being [rewritten with breaking API changes](https://channels.readthedocs.io/en/2.x/one-to-two.html).

This plugin aims to bridge that gap between Channels and REST Framework while being as generic and boilerplate-free as possible. Clients are be able to subscribe to real-time updates for any queryset that's exposed through a [Generic API View](https://www.django-rest-framework.org/api-guide/generic-views/#genericapiview) or any of its subclasses, including [Model ViewSet](https://www.django-rest-framework.org/api-guide/viewsets/#modelviewset), with just one mixin!

Check out [the full tutorial and reference documentation](https://django-rest-live.readthedocs.io) for specifics.

### Dependencies

- [Django](https://github.com/django/django/) (3.1 and up)
- [Django Channels](https://github.com/django/channels) (2.x and 3.x both supported)
- [Django REST Framework](https://github.com/encode/django-rest-framework/) (3.11 and up)
- [`channels_redis`](https://github.com/django/channels_redis) for
  [channel layer](https://channels.readthedocs.io/en/latest/topics/channel_layers.html) support in production. Channel layers is what allows a Django signal to broadcast an update to all websocket clients.

### Installation and Setup

Make sure to [install and properly set up Django Channels](https://channels.readthedocs.io/en/latest/installation.html) before installing `django-rest-live`.

```
pip install django-rest-live
```

Add `rest_live` to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    "rest_framework",
    "channels",
    "rest_live",
]
```

Create a `RealtimeRouter` in your ASGI routing file (generally `asgi.py`) and add the router's consumer to the websocket routing you set up with Django Channels. Feel free to choose any URL endpoint for the websocket, here we've chosen `/ws/subscribe/`.

```python
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path
from django.core.asgi import get_asgi_application
from rest_live.routers import RealtimeRouter

router = RealtimeRouter()

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
    URLRouter([
        path("ws/subscribe/", router.as_consumer().as_asgi(), name="subscriptions"),
    ])
),
})
```

### Configuration

> Check out the [Tutorial](https://django-rest-live.readthedocs.io/en/latest/usage/) for an in-depth example.

To allow subscriptions to a queryset, add the `RealtimeMixin` to a GenericAPIView or ModelViewSet that exposes that queryset. Then, register the view with the `RealtimeRouter` instance you created during setup.

```python
...
router = RealtimeRouter()
router.register(TaskViewSet)  # Register all ViewSets here
...
```

### Client-Side

Subscribing to a updates equires opening a [WebSocket](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
on the client connection to the URL you specified during setup. Feel free to use any frontend web framework you'd like. Below is a simple example in vanilla JavaScript which logs updates to the console.

```javascript
const socket = new WebSocket("ws://<django_domain_here>/ws/subscribe");

socket.addEventListener("message", function (event) {
  console.log("Update received:", JSON.parse(event.data));
});

// Subscribe to updates for the model instance with the ID of 1.
socket.send(
  JSON.stringify({
    id: 1337,
    type: "subscribe",
    model: "appname.ModelName",
    action: "retrieve",
    lookup_by: 1,
  })
);

// Subscribe to updates for every model in the queryset.
socket.send(
  JSON.stringify({
    id: 1338,
    type: "subscribe",
    model: "appname.ModelName",
    action: "list",
  })
);

// After 5 seconds, unsubscribe from updates for the single model instance with ID 1.
setTimeout(5 * 1000, () =>
  socket.sent(
    JSON.stringify({
      type: "unsubscribe",
      id: 1337,
    })
  )
);
```

Broadcast updates will be sent from the server in this format:

```json
{
  "type": "broadcast",
  "id": 1337,
  "model": "appname.ModelName",
  "action": "UPDATED",
  "instance": { "id": 1, "field1": "value1", "field2": "value2" }
}
```

This is only a basic example. For more details, including how to send arguments and parameters along with subscriptions, read the [Tutorial](https://django-rest-live.readthedocs.io/en/latest/usage/) and the [Websocket API Reference](https://django-rest-live.readthedocs.io/en/latest/api/).

### Closing Notes

`django-rest-live` took initial inspiration from [this article by Kit La Touche](https://www.oddbird.net/2018/12/12/channels-and-drf/).
Differently from projects like [`djangochannelsrestframework`](https://github.com/hishnash/djangochannelsrestframework),
`django-rest-live` does not aim to supplant REST Framework for performing CRUD actions through a REST API. Instead,
it is designed to be used in conjunction with HTTP REST endpoints. Clients should still use normal REST framework
endpoints generated by ViewSets and other API views to get initial data to populate a page, as well as any write-driven
behavior (`POST`, `PATCH`, `PUT`, `DELETE`). `django-rest-live` gets rid of the need for periodic polling GET
requests to for resource updates after page load.
