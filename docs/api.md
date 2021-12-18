# Websocket API
## General format
Messages are sent from over the websocket connection
as JSON strings. The easiest way to generate these is to construct an object
in JavaScript and pass it to `JSON.stringify`. Incoming messages can be parsed with `JSON.parse`.

All messages have a `type` property which determines all other properties
accessible on the message
and a `id` which specifies which request it pertains to. It's
important to remember that this is an asynchronous API, and so responses
may arrive out-of-order – clients should rely on the `id` property to
match requests and responses. The details of each type are explained below.

### Errors
Errors have the following form:

- `type` (_string_) – Always `"error"`.
- `id` (_string_) – The request ID from the message which prompted the error.
- `code` (_number_) – Code identifying the error message. Generally modeled after HTTP status codes.
- `message` (_string_) – Description of the error.

An error with code `400` will be sent if an unknown message `type` is sent.

## Subscription Request
Subscription requests are sent from the client over the websocket connection with the server.
It has the following properties:

- `type` (_string_) – Designates a message as a subscription request; should always be `"subscribe"`.
- `id` (_number_) – Identifier for this subscription request. Should be unique
per-connection. Broadcasts from the server, unsubscribe requests, and error messages
all refer to this request ID.
- `model` (_string_) – The Django model you want to subscribe to, in standard
`appname.ModelName` format.
- `action` (_string_) – The viewset action you'd like to subscribe to;
Must be either `"retrieve"` or `"list"`.
    * `"retrieve"` subscriptions only broadcast updates for a single model instance.
    * `"list"` subscriptions will broadcast updates for every instance within the queryset
    specified in the view's `get_queryset()` method or `queryset` property.
- `lookup_by` (_string or number_) – Only defined on `retrieve` subscriptions. The value of the `lookup_field`
on the instance to be subscribed to.
- `view_kwargs` (_object_) – View keyword arguments to be passed along to the view when processing
subscriptions. See [here](https://docs.djangoproject.com/en/3.1/topics/http/urls/#how-django-processes-a-request)
for information on keyword arguments. Optional; defaults to `{}`.
  
– `query_params` (_object_) – `GET` parameters to be accessible on the view.
See [Django documentation](https://docs.djangoproject.com/en/3.1/ref/request-response/#django.http.HttpRequest.GET) 
and [DRF documentation](https://www.django-rest-framework.org/api-guide/requests/#query_params).
Optional; defaults to `{}`. Note that parameters must be URL serializable.

### Error Codes
- `400`: Some required field is missing or not properly specified in the request.
Example: no `model` field, or a non-standard `action`.
- `403`: Unauthorized to perform subscription based on
[permissions](https://www.django-rest-framework.org/api-guide/permissions/) on the view.
- `404`: Resource not found. Could either be that no view is registered for a given model,
or no model instance found with the `lookup_by` field in the view's queryset.


## Broadcast
Broadcasts are sent from the server when model instances update.

- `type` (_string_) – Always `"broadcast"`
- `id` (_string_) – ID of the request which subscribed to this broadcast.
- `model`: (_string_) – Model label for model this broadcast refers to.
- `action`: (_string_) – One of `"CREATED"`, `"UPDATED"`, or `"DELETED"`.
New objects and objects which are updated so that they enter the queryset
are marked as `"CREATED"`, and objects which are updated so that they leave
the queryset are marked as `"DELETED"`.
- `instance`: (_object_) – The serialized model instance that this broadcast
refers to. Only present with `CREATED` and `UPDATED` actions. Serializer
determined from `get_serializer_class()` on the view.


## Unsubscribe
Unsubscribe requests are sent from the client.

- `type` (_string_) – Always `"unsubscribe"`.
- `id` (_number_) – Original request ID for the subscription to unsubscribe from.

### Error Codes
- `404`: No subscription with the provided request ID could be found.
