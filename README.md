# Django REST Live

[![CircleCI](https://circleci.com/gh/pennlabs/django-rest-live.svg?style=shield)](https://circleci.com/gh/pennlabs/django-rest-live)
[![Coverage Status](https://codecov.io/gh/pennlabs/django-rest-live/branch/master/graph/badge.svg)](https://codecov.io/gh/pennlabs/django-rest-live)
[![PyPi Package](https://img.shields.io/pypi/v/django-rest-live.svg)](https://pypi.org/project/django-rest-live/)

`django-rest-live` adds real-time subscriptions over websockets to [Django REST Framework](https://github.com/encode/django-rest-framework)
by leveraging websocket support provided by [Django Channels](https://github.com/django/channels).

## Contents
- [Inspiration and Goals](#inspiration-and-goals)
- [Dependencies](#dependencies)
- [Installation](#installation)
- [Usage](#usage)
  * [Basic Usage](#basic-usage)
    + [Server-Side](#server-side)
    + [Client-Side](#client-side)
  * [Grouped subscriptions](#grouped-subscriptions)
  * [Request objects and view keyword arguments](#request-objects-and-view-keyword-arguments)
- [Testing](#testing)
  * [setUp and tearDown](#setup-and-teardown)
  * [Authentication](#authentication)
- [Note on Django signals](#note-on-django-signals)

## Inspiration and Goals
`django-rest-live` took initial inspiration from [this article by Kit La Touche](https://www.oddbird.net/2018/12/12/channels-and-drf/).

The goal of this project is to be as close as possible to a drop-in realtime solution for projects already
using Django REST Framework. 

`django-rest-live` does not aim to supplant REST Framework for performing CRUD actions through a REST API. Instead,
it is designed to be used in conjunction with HTTP REST endpoints. Clients should still use normal REST framework
endpoints generated by ViewSets and other API views to get initial data to populate a page, as well as any write-driven
behavior (`POST`, `PATCH`, `PUT`, `DELETE`). `django-rest-live` gets rid of the need for periodic polling GET
requests to for resource updates after page load.

## Dependencies
- [Django](https://github.com/django/django/) (3.1 and up)
- [Django Channels](https://github.com/django/channels) (2.x, 3.0 not yet supported) 
- [Django REST Framework](https://github.com/encode/django-rest-framework/)
- [`channels_redis`](https://github.com/django/channels_redis) for
  [channel layer](https://channels.readthedocs.io/en/latest/topics/channel_layers.html) support in production.

## Installation

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
from rest_live.consumers import RealtimeRouter

router = RealtimeRouter()

websockets = AuthMiddlewareStack(
    URLRouter([
        path("ws/subscribe/", router.consumer, name="subscriptions"), 
        "Other routing here...",
    ])
)
application = ProtocolTypeRouter({
    "websocket": websockets
})
```

That's it! You're now ready to configure and use `django-rest-live`.

## Usage

These docs will use an example to-do app called `todolist` with the following models and serializers:
```python
# todolist/models.py
from django.db import models

class List(models.Model):
    name = models.CharField(max_length=64)

class Task(models.Model):
    text = models.CharField(max_length=140)
    done = models.BooleanField(default=False)
    list = models.ForeignKey("List", on_delete=models.CASCADE)

# todolist/serializers.py
from rest_framework import serializers

class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ["id", "text", "done"]

class TodoListSerializer(serializers.ModelSerializer):
    tasks = TaskSerializer(many=True, read_only=True)
    class Meta:
        model = List
        fields = ["id", "name", "tasks"]
```

### Basic Usage
This section describes the most basic usage of `django-rest-live`: subscribing to updates for a single model instance.
More use cases are described in sections further down.

#### Server-Side

`django-rest-live` extends the existing generic API views using a mixin called `RealtimeMixin`. In order to
designate your view as realtime-capable, add `RealtimeMixin` to its superclasses:

```python
from rest_framework.viewsets import ModelViewSet
from rest_live.mixins import RealtimeMixin

class TaskViewSet(ModelViewSet, RealtimeMixin):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
```

Note that throughout this documentation we use `ViewSet`s as our base class. It's important to note that `django-rest-live`
works just as well with any [generic view](https://www.django-rest-framework.org/api-guide/generic-views/)
that defines a [`get_serializer_class()`](https://www.django-rest-framework.org/api-guide/generic-views/#attributes)
method.

The last backend step is to register your View in the `RealtimeRouter` you defined in the first setup step:

```python
from rest_live.consumers import RealtimeRouter

router = RealtimeRouter()
router.register(TaskViewSet)  # Register all ViewSets here

websockets = AuthMiddlewareStack(
    URLRouter([
        path("ws/subscribe/", router.consumer, name="subscriptions"), 
        "Other routing here...",
    ])
```

#### Client-Side
Subscribing to model updates from a client requires opening a [WebSocket](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
connection to the URL you specified during setup. In our example case, that URL is `/ws/subscribe/`. After the connection
is established, send a JSON message (using `JSON.stringify()`) in this format:

```json5
{
  "request_id": 1337,
  "model": "todolist.Task",
  "value": 1 
}
```

You should generate the `request_id` client side. It's used to track the subscription you request throughout 
its lifetime -- we'll see that it's referenced both in error messages and broadcasts.

The model label should be in Django's standard `app.modelname` format. `value` field here is set to the value for
the [primary key](https://docs.djangoproject.com/en/3.1/topics/db/queries/#the-pk-lookup-shortcut) for the model instance
we're subscribing to. This is generally the value of the `id` field, but is equivalent to querying
for `Task.objects.filter(pk=<value>)`.

The example message above would subscribe to updates for the todo task with an primary key of 1.
As mentioned above, the client should make a GET request to get the entire list, with all its tasks and their
associated IDs, to figure out which IDs to subscribe to.

When the Task with primary key `1` updates, a message in this format will be sent over the websocket:

```json
{
    "type": "broadcast",
    "request_id": 1337,
    "model": "test_app.Todo",
    "action": "UPDATED",
    "instance": {"id": 1, "text": "test", "done": true}
}
```

Valid `action` values are `UPDATED`, `CREATED`, and `DELETED`.

### Grouped subscriptions
As mentioned above, subscriptions are "grouped" by the instance primary key by default: you send one message to the websocket to
get updates for a single Task with a given primary key. But in the todo list example, we'd generally be interested in
an entire list of tasks, including being notified of any new tasks which have been created since the page was first loaded.

Rather than subscribe all tasks individually, we want to subscribe to a list: an entire group of tasks.
`django-rest-live` allows us to specify fields we may want to group by using the `group_by_fields` property
on the View:


```python
# todolist/views.py
from rest_framework.viewsets import ModelViewSet
from rest_live.mixins import RealtimeMixin

class TaskViewSet(ModelViewSet, RealtimeMixin):
    serializer_class = TaskSerializer
    group_by_fields = ["pk", "list_id"]
```

On the client side, we now have to specify the group-by field this subscription is referring to.
In this case, we're grouping by the `list_id` of the list we'd like to get updates from, the list with id 14:

```json5
{
  "request_id": 1338,
  "model": "todolist.Task",
  "group_by": "list_id",
  "value": 14
}
```

This will subscribe you to updates for every Task in the list with ID 14.

What's important to remember here is that while the field is defined as a `ForeignKey` called `list` on the model,
the underlying integer field in the database that links together Tasks and Lists is called `list_id`. More generally,
`<fieldname>_id` for any foreign key fieldname on the model.

### Request objects and view keyword arguments
Django REST Framework makes heavy use of the [`Request`](https://www.django-rest-framework.org/api-guide/requests/)
object as a general context throughout the framework.
[permissions](https://www.django-rest-framework.org/api-guide/permissions/) are a good example: each permission check
gets passed the `request` object along with the current `view` in order to verify if
a given request has permission to view an object. 

However, broadcasts originate from database updates rather than an HTTP request, so
`django-rest-live` uses the HTTP request that establishes the websocket connection as a basis for the `request`
object accessible in views, permissions and serializers. `request.user` and `request.session`, normally populated
via middleware, are available as expected. `view.action` is `retrieve` when the group-by field is either `pk` or `id`,
and `list` otherwise.

Something that can't be
inferred, however, are [view keyword arguments](https://docs.djangoproject.com/en/3.1/ref/urls/#django.urls.path),
normally derived from the URL path to a resource in HTTP requests.
`django-rest-live` allows you to declare view arguments in your subscription request using the `arguments` key:

```json
{
  "request_id": 1339,
  "model": "todolist.Task",
  "value": 29,
  "arguments": {
    "list": 14 
  }
}
```
As a rule of thumb, if you have angle brackets in your URL pattern, like `title` in 
`path('articles/<slug:title>/', views.article)`, then you're providing your view with
keyword arguments, and you most likely need to provide those arguments to your View when requesting subscriptions too.

If you're getting an `AttributeError` in your View when receiving a broadcast but not when doing normal HTTP REST
operations, then you're probably making use of an attribute we didn't think of. In that case,
please open an issue describing your use case! It'll go a long way to making this library more useful to all. 

## Testing
As of Django 3.1, you can write asynchronous tests in Django `TestCase`s. You can set up a test case by following
the snippet below, using the test communicator provided in `rest_live.testing.APICommunicator`:

```python
from django.test import TransactionTestCase
from app.routing import application  # Replace this line with the import to your ASGI router.
from channels.db import database_sync_to_async
from rest_live.testing import APICommunicator

class MyTests(TransactionTestCase):
    async def test_subscribe(self):
        client = APICommunicator(application, "/ws/subscribe/")
        connected, _ = await self.client.connect()
        self.assertTrue(connected)
        await client.send_json_to(
            {
                "request_id": 1337,
                "model": "app.Model",
                "value": "1",
            }
        )
        self.assertTrue(await client.receive_nothing())
        await database_sync_to_async(Model.objects.create)(...)
        response = await client.receive_json_from()
        self.assertEqual(response, {
            "type": "broadcast",
            "request_id": 1337,
            "model": "app.Model",
            "instance": { "": "..." },
            "action": "CREATED",
        })
        await client.disconnect()
```

Since REST Live makes use of the database for its functionality, make sure to use `django.test.TransactionTestCase`
instead of `django.test.TestCase` so that database connections within the async test functions get cleaned up approprately.

Remember to wrap all ORM calls in the `database_sync_to_async` decorator as demonstrated in the above example. The ORM
is still fully synchronous, and the regular `sync_to_async` decorator does not properly clean up connections!

### setUp and tearDown
The normal `TestCase.setUp` and `TestCase.tearDown` methods run in different threads from the actual test itself,
and so they don't work for creating async objects like `WebsocketCommunicator`. REST Live comes with a decorator called
`@async_test` which will enable test cases to define lifecycle methods `asyncSetUp()` and `asyncTearDown()` to
run certain code before and after every test case decorated with `@async_test`. Here is an example:

```python
...
from rest_live.testing import APICommunicator, async_test
class MyTests(TransactionTestCase):
    
    async def asyncSetUp(self):
        self.client = APICommunicator(application, "/ws/subscribe/")
        connected, _ = await self.client.connect()
        self.assertTrue(connected)
    
    async def asyncTearDown(self):
        await self.client.disconnect()
        
    @async_test
    async def test_subscribe(self):
        ...  # a new connection has been opened and is accessible in `self.client`
```

### Authentication
Make sure to follow the below pattern if you use `request.user` or `request.session` anywhere in your View code.

Authentication in unit tests for django channels is a bit tricky, but the utility that `rest_live` provides
is based on this [github issue comment](https://github.com/django/channels/issues/903#issuecomment-365735926).

The `WebsocketCommunicator` class can take HTTP headers as part of its constructor. In order to open a connection
as a logged-in user, you can use `rest_live.testing.get_headers_for_user`:

```python
from rest_live.testing import get_headers_for_user

user = await database_sync_to_async(User.objects.create_user)(username="test")
headers = await get_headers_for_user(user)
client = APICommunicator(appliction, "/ws/subscribe/", headers)
...
```

## Note on Django signals
This package works by listening in on model lifecycle events sent off by Django's [signal dispatcher](https://docs.djangoproject.com/en/3.1/topics/signals/).
Specifically, the [`post_save`](https://docs.djangoproject.com/en/3.1/ref/signals/#post-save)
and [`post_delete`](https://docs.djangoproject.com/en/3.1/ref/signals/#post-delete) signals. This means that `django-rest-live`
can only pick up changes that Django knows about. Bulk operations, like `filter().update()`, `bulk_create`
and `bulk_delete` do not trigger Django's lifecycle signals, so updates will not be sent.
