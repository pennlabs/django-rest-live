from typing import Any, Dict, Type, List

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from django.db.models import Model

from rest_live import DEFAULT_GROUP_BY_FIELD, get_group_name
from rest_live.mixins import RealtimeMixin


class SubscriptionConsumer(JsonWebsocketConsumer):
    registry: Dict[str, Type[RealtimeMixin]] = dict()

    def connect(self):
        self.scope["method"] = "GET"
        self.user = self.scope.get("user", None)
        self.session = self.scope.get("session", dict())
        self.subscriptions = dict()
        self.kwargs = dict()
        self.accept()

    def add_subscription(self, group_name, request_id, **kwargs):
        print(f"[REST-LIVE] got subscription to {group_name}")
        self.subscriptions.setdefault(group_name, []).append(request_id)
        self.groups.append(group_name)
        self.kwargs[request_id] = kwargs
        async_to_sync(self.channel_layer.group_add)(group_name, self.channel_name)

    def remove_subscription(self, request_id):
        try:
            group_name = [k for k, v in self.subscriptions.items() if request_id in v][0]
        except IndexError:
            self.send_error(
                request_id,
                404,
                "Attempted to unsubscribe for request ID before subscribing.",
            )
            return
        if group_name not in self.subscriptions:
            return

        self.subscriptions[group_name].remove(request_id)
        self.groups.remove(group_name)
        if group_name not in self.groups:
            async_to_sync(self.channel_layer.group_discard)(group_name, self.channel_name)
        if len(self.subscriptions[group_name]) == 0:
            del self.subscriptions[group_name]

    def send_error(self, request_id, code, message):
        self.send_json(
            {
                "type": "error",
                "id": request_id,
                "code": code,
                "message": message,
            }
        )

    def send_broadcast(self, request_id, model_label, action, instance_data, renderer):
        # https://www.django-rest-framework.org/api-guide/content-negotiation/
        self.send(
            text_data=renderer.render(
                {
                    "type": "broadcast",
                    "id": request_id,
                    "model": model_label,
                    "action": action,
                    "instance": instance_data,
                }
            ).decode("utf-8")
        )

    def receive_json(self, content: Dict[str, Any], **kwargs):
        request_id = content.get("id", None)
        if request_id is None:
            return  # Can't send error message without request ID.
        message_type = content.get("type", None)
        if message_type == "subscribe":
            model_label = content.get("model")
            if model_label is None:
                self.send_error(request_id, 400, "No model specified")
                return

            # TODO: Switch from PK to lookup field for the viewset.
            # TODO: These fields go unused as of now.
            group_by_field = content.get("group_by", DEFAULT_GROUP_BY_FIELD)
            value = content.get("value", None)

            if value is None:
                self.send_error(request_id, 400, f"No value specified in subscription")
                return

            if model_label not in self.registry:
                self.send_error(
                    request_id,
                    404,
                    f"Model {model_label} not registered for realtime updates.",
                )
                return

            kwargs = content.get("kwargs", dict())
            # TODO: Use the global app registry here instead of the viewset get_model_class()
            model = self.registry[model_label]().get_model_class()
            try:
                has_permission = self.registry[model_label].user_can_subscribe(
                    group_by_field, value, self.scope, kwargs
                )
            except model.DoesNotExist:
                self.send_error(request_id, 404, "Instance not found.")
                return

            if not has_permission:
                self.send_error(
                    request_id,
                    403,
                    f"Unauthorized to subscribe to {model_label} by field {group_by_field}",
                )
                return

            group_name = get_group_name(model_label, group_by_field, value)
            # TODO: Clean up to remove group_by_field and value
            # group_name = get_group_name(model_label, "", "")
            self.add_subscription(group_name, request_id, **kwargs)
            self.pks = self.registry[model_label].get_list_pks(group_by_field, self.scope, kwargs)
        elif message_type == "unsubscribe":
            self.remove_subscription(request_id)
        else:
            self.send_error(request_id, 400, f"unknown message type `{message_type}`.")

    def notify(self, event):
        channel_name = event["channel_name"]
        group_by_field = event["group_by_field"]
        instance_pk = event["instance_pk"]
        action = event["action"]
        model_label = event["model"]

        viewset = self.registry[model_label]

        for request_id in self.subscriptions[channel_name]:
            kwargs = self.kwargs.get(request_id, dict())
            instance_data, renderer = viewset.prepare_broadcast(
                instance_pk,
                group_by_field,
                self.scope,
                kwargs,
                self.pks
            )
            if instance_data is not None:
                self.pks.add(instance_pk)
                self.send_broadcast(request_id, model_label, action, instance_data, renderer)
            else:
                # TODO: Send delete action if we get the right signal from `viewset.broadcast`
                if instance_pk in self.pks:
                    self.pks.remove(instance_pk)
                pass


class RealtimeRouter:
    def __init__(self, uid="default"):
        self.registry: Dict[str, Type[RealtimeMixin]] = dict()
        self.uid = uid

    def register_all(self, viewsets):
        for viewset in viewsets:
            self.register(viewset)

    def register(self, viewset):
        if not hasattr(viewset, "register_realtime"):
            raise RuntimeError(
                f"View {viewset.__name__}"
                "passed to RealtimeRouter does not have RealtimeMixin applied."
            )
        label = viewset.register_realtime(self.uid)
        if label in self.registry:
            raise RuntimeWarning("You should not register two realitime views for the same model.")

        self.registry[label] = viewset

    def as_consumer(self):
        # Create a subclass of `SubscriptionConsumer` where the consumer's model
        # registry is set to this router's registry. Basically a subclass inside a closure.
        return type(
            "BoundSubscriptionConsumer",
            (SubscriptionConsumer,),
            dict(registry=self.registry),
        )
