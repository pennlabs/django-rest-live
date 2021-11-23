# Usage

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

## Server-side setup

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
that defines a `queryset` attribute along with either a `serializer_class` atttribute or a
[`get_serializer_class()`](https://www.django-rest-framework.org/api-guide/generic-views/#attributes) method.

Just like [parts of REST Framework](https://www.django-rest-framework.org/api-guide/permissions/#using-with-views-that-do-not-include-a-queryset-attribute)
which require knowledge of a backing model for a view, `RealtimeMixin` requires that you have a `queryset` attribute
defined on your view, even if you have overridden the `get_queryset()` method. The DRF solution, recommended here as
well, is to define an empty "sentinel" queryset on the view that `RealtimeMixin` can use to determine the model:

```python
from rest_framework.viewsets import ModelViewSet
from rest_live.mixins import RealtimeMixin

class FilteredTaskViewSet(ModelViewSet, RealtimeMixin):
    serializer_class = TaskSerializer
    queryset = Task.objects.none()  # Empty queryset indicating the backing model for this view

    def get_queryset(self):  # Actual queryset for the view
        return Task.objects.filter(user=self.request.user)
```

The last backend step is to register your View in the `RealtimeRouter` you defined in the first setup step:

```python
from rest_live.routers import RealtimeRouter

router = RealtimeRouter()
router.register(TaskViewSet)  # Register all ViewSets here

websockets = AuthMiddlewareStack(
    URLRouter([
        path("ws/subscribe/", router.as_consumer().as_asgi(), name="subscriptions"), 
        "Other routing here...",
    ])
```

> Note: if using Channels version 2, omit the `as_asgi()` method.
 
## Subscribing to single instances
Subscribing to a single model's updates from a client requires opening a [WebSocket](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
connection to the URL you specified during setup. In our example case, that URL is `/ws/subscribe/`. After the connection
is established, send a JSON message (using `JSON.stringify()`) in this format:

```json
{
  "type": "subscribe",
  "id": 1337,
  "model": "todolist.Task",
  "action": "retrieve",
  "lookup_by": 1 
}
```

You should generate the `id` client side. It's used to track the subscription you request throughout 
its lifetime -- we'll see that it's referenced both in error messages and broadcasts.

The model label should be in Django's standard `app.modelname` format. `lookup_by` should be the value of the
[lookup field](https://www.django-rest-framework.org/api-guide/generic-views/#attributes) for the model instance
we're subscribing to. Since this defaults to  [`pk`](https://docs.djangoproject.com/en/3.1/topics/db/queries/#the-pk-lookup-shortcut),
it's the conceptual equivalent of subscribing to the instance which would be returned from
`Task.objects.filter(pk=<value>)`.

As mentioned above, the client should make RESTful HTTP requests for resources to determine which IDs it wants to
subscribe to; there's no capability for querying models built in to the Websocket API, just subscriptions and broadcasts.

When the Task with primary key `1` updates, a message in this format will be sent over the websocket:

```json
{
    "type": "broadcast",
    "id": 1337,
    "model": "test_app.Todo",
    "action": "UPDATED",
    "instance": {"id": 1, "text": "test", "done": true}
}
```

Valid `action` values are `UPDATED`, `CREATED`, and `DELETED`. `instance` is the JSON-serialized model instance
using the serializer defined in the view's `serializer_class` attribute or returned from the `get_serializer_class`
method.

Unsubscribing is even simpler – simply pass the original request `id` along in a websocket message:
```json
{
    "type": "unsubscribe",
    "id": 1337
}
```

## Subscribing to lists
Being attached to a generic view with a `get_queryset()` method, you can also subscribe to updates for all instances
that would be returned from the view's `list` action. The subscription looks like this:


```json
{
  "id": 1338,
  "type": "subscription",
  "model": "todolist.Task",
  "action": "list"
}
```

Note that `lookup_by` isn't used here since we're referring to the whole queryset. You'll receive broadcasts in the same
format as shown above.

`CREATE` and `DELETE` actions are not the actual create and delete actions in the database, but are relative to their
inclusion in the view's queryset. If an instance is created, or is modified such that it is now included in the queryset
when it wasn't before, the action in the broadcast will be `CREATED`. If the instance is modified so that it is no
longer included in the queryset, the action in the broadcast will be `DELETED`.

Note that `DELETED` actions can't be triggered from actual deletions from the database at this time.


## `request.user` and `request.session`
Django REST Framework makes heavy use of the [`Request`](https://www.django-rest-framework.org/api-guide/requests/)
object as a general context throughout the framework.
[Permissions](https://www.django-rest-framework.org/api-guide/permissions/) are a good example: each permission check
gets passed the `request` object along with the current `view` in order to verify if
a given request has permission to view an object. 

However, broadcasts originate from database updates rather than an HTTP request, so
`django-rest-live` uses the HTTP request that establishes the websocket connection as a basis for the `request`
object accessible in views, permissions and serializers. `request.user` and `request.session`, normally populated
via middleware, are available as expected.


## Passing parameters to subscriptions
Views are often filtered in some way, using parameters in the URL
passed as keyword arguments to the view, or as GET parameters after the `?`
in the URL. These arguments can be passed to DRF through extra fields
on the initial subscription request to filter the queryset appropriately
for a given subscription.

### `view.kwargs`
Something that can't be
inferred from the initial request are [view keyword arguments](https://docs.djangoproject.com/en/3.1/ref/urls/#django.urls.path),
normally derived from the URL path to a resource in HTTP requests.
`django-rest-live` allows you to declare view arguments in your subscription request using the `view_kwargs` key:

```json
{
  "type": "subscribe",
  "id": 1339,
  "model": "todolist.Task",
  "action": "retrieve",
  "lookup_by": 29,
  "view_kwargs": {
    "list": 14 
  }
}
```
As a rule of thumb, if you have angle brackets in your URL pattern, like `title` in 
`path('articles/<slug:title>/', views.article)`, then you're providing your view with
keyword arguments, and you most likely need to provide those arguments to your View when requesting subscriptions too.

### `request.query_params`
If you use `request.query_params` in your view at all, potentially from
[filters](https://www.django-rest-framework.org/api-guide/filtering/#filtering-against-query-parameters) on your queryset,
you can also pass in query parameters to your subscription with the `query_params` key:
```json
{
  "type": "subscribe",
  "id": 1340,
  "model": "todolist.Task",
  "action": "list",
  "query_params": {
    "active": true
  }
}
```

If you're getting an `AttributeError` in your View when receiving a broadcast but not when doing normal HTTP REST
operations, then you're probably making use of an attribute we didn't think of. In that case,
please open an issue describing your use case! It'll go a long way to making this library more useful to all. 
