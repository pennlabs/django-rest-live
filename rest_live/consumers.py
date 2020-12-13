from typing import Any, Dict, Type, List

from rest_framework.generics import GenericAPIView
from rest_framework.request import Request

from asgiref.sync import async_to_sync
from channels.generic.websocket import AsyncJsonWebsocketConsumer, JsonWebsocketConsumer

from rest_live import DEFAULT_GROUP_BY_FIELD, get_group_name
from rest_live.mixins import RealtimeMixin


class RealtimeRouter:
    def __init__(self):
        self.registry: Dict[str, Type[RealtimeMixin]] = dict()

    def register_all(self, viewsets):
        for viewset in viewsets:
            self.register(viewset)

    def register(self, viewset):
        if not hasattr(viewset, "register_realtime"):
            raise RuntimeError(
                f"View {viewset.__name__}"
                "passed to RealtimeRouter does not have RealtimeMixin applied."
            )
        label = viewset.register_realtime()
        if label in self.registry:
            raise RuntimeWarning(
                "You should not register two realitime views for the same model."
            )

        self.registry[label] = viewset

    @property
    def consumer(self):
        router = self

        class SubscriptionConsumer(JsonWebsocketConsumer):
            def connect(self):
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
                async_to_sync(self.channel_layer.group_add)(
                    group_name, self.channel_name
                )

            def remove_subscription(self, request_id):
                try:
                    group_name = [
                        k for k, v in self.subscriptions.items() if request_id in v
                    ][0]
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
                    async_to_sync(self.channel_layer.group_discard)(
                        group_name, self.channel_name
                    )
                if len(self.subscriptions[group_name]) == 0:
                    del self.subscriptions[group_name]

            def send_error(self, request_id, code, message):
                self.send_json(
                    {
                        "type": "error",
                        "request_id": request_id,
                        "code": code,
                        "message": message,
                    }
                )

            def send_broadcast(self, request_id, model_label, action, instance_data):
                self.send_json(
                    {
                        "type": "broadcast",
                        "request_id": request_id,
                        "model": model_label,
                        "action": action,
                        "instance": instance_data,
                    }
                )

            def receive_json(self, content: Dict[str, Any], **kwargs):
                request_id = content.get("request_id", None)
                if request_id is None:
                    return  # Can't send error message without request ID.
                unsubscribe = content.get("unsubscribe", False)
                if not unsubscribe:
                    model_label = content.get("model")
                    if model_label is None:
                        self.send_error(request_id, 400, "No model specified")
                        return

                    group_by_field = content.get("group_by", DEFAULT_GROUP_BY_FIELD)
                    value = content.get("value", None)

                    if value is None:
                        self.send_error(
                            request_id, 400, f"No value specified in subscription"
                        )
                        return

                    if model_label not in router.registry:
                        self.send_error(
                            request_id,
                            404,
                            f"Model {model_label} not registered for realtime updates.",
                        )

                    group_name = get_group_name(model_label, group_by_field, value)
                    kwargs = content.get("kwargs", dict())
                    self.add_subscription(group_name, request_id, **kwargs)
                else:
                    self.remove_subscription(request_id)

            def notify(self, event):
                channel_name = event["channel_name"]
                group_by_field = event["group_by_field"]
                instance_pk = event["instance_pk"]
                action = event["action"]
                model_label = event["model"]

                viewset = router.registry[model_label]

                for request_id in self.subscriptions[channel_name]:
                    kwargs = self.kwargs.get(request_id, dict())
                    instance_data = viewset.broadcast(
                        instance_pk,
                        group_by_field,
                        self.user,
                        self.session,
                        self.scope,
                        **kwargs,
                    )
                    if instance_data is not None:
                        self.send_broadcast(
                            request_id, model_label, action, instance_data
                        )

        return SubscriptionConsumer
