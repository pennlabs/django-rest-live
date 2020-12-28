from typing import Any, Dict, Type, List, Union, Set

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer

from rest_live import get_group_name, DELETED, UPDATED, CREATED
from rest_live.mixins import RealtimeMixin

KwargType = Dict[str, Union[int, str]]


class SubscriptionConsumer(JsonWebsocketConsumer):
    registry: Dict[str, Type[RealtimeMixin]] = dict()

    def connect(self):
        self.scope["method"] = "GET"
        self.subscriptions: Dict[str, List[int]] = dict()  # Maps group name to list of request IDs
        self.actions: Dict[int, str] = dict()  # Request ID to action (list or retrieve)
        self.kwargs: Dict[int, KwargType] = dict()  # Request ID to view kwargs
        self.owned_instance_pks: Dict[int, Set[int]] = dict()
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

            if model_label not in self.registry:
                self.send_error(
                    request_id,
                    404,
                    f"Model {model_label} not registered for realtime updates.",
                )
                return

            viewset_action = content.get("action", None)
            if viewset_action is None or viewset_action not in ["list", "retrieve"]:
                self.send_error(
                    request_id,
                    400,
                    "action must be present and the value must be either `list` or `retrieve`.",
                )

            lookup_value = content.get("lookup_by", None)

            kwargs = content.get("kwargs", dict())
            # TODO: Use the global app registry here instead of the view get_model_class()
            view = self.registry[model_label].from_scope(viewset_action, self.scope, kwargs)
            model = view.get_model_class()
            # Check permissions from the view.

            has_permission = True
            for permission in view.get_permissions():
                has_permission = has_permission and permission.has_permission(
                    view.request, view
                )

            if view.action == "retrieve":
                try:
                    instance = view.get_queryset().get(**{view.lookup_field: lookup_value})
                except model.DoesNotExist:
                    self.send_error(request_id, 404, "Instance not found.")
                    return

                for permission in view.get_permissions():
                    has_permission = has_permission and permission.has_object_permission(
                        view.request, view, instance
                    )

            if not has_permission:
                self.send_error(
                    request_id,
                    403,
                    f"Unauthorized to subscribe to {model_label} for action {viewset_action}",
                )
                return

            group_name = get_group_name(model_label)
            self.add_subscription(group_name, request_id, **kwargs)
            self.actions[request_id] = viewset_action
            self.owned_instance_pks[request_id] = set(
                [instance1["pk"] for instance1 in view.get_queryset().all().values("pk")]
            )
        elif message_type == "unsubscribe":
            self.remove_subscription(request_id)
        else:
            self.send_error(request_id, 400, f"unknown message type `{message_type}`.")

    def model_saved(self, event):
        channel_name = event["channel_name"]
        instance_pk = event["instance_pk"]
        model_label = event["model"]

        viewset_class = self.registry[model_label]

        for request_id in self.subscriptions[channel_name]:
            viewset = viewset_class.from_scope(
                self.actions[request_id], self.scope, self.kwargs[request_id]
            )

            model = viewset.get_model_class()
            renderer = viewset.perform_content_negotiation(viewset.request)[0]

            is_existing_instance = instance_pk in self.owned_instance_pks[request_id]
            try:
                instance = viewset.get_queryset().get(pk=instance_pk)
                action = UPDATED if is_existing_instance else CREATED
            except model.DoesNotExist:
                if not is_existing_instance:
                    # If the model doesn't exist in the queryset now, and also is not in the set of PKs that we've seen,
                    # then we truly don't have permission to see it.
                    return

                # If the instance has been seen, then we should get it from the database to serialize and
                # send the delete message.
                instance = model.objects.get(pk=instance_pk)
                action = DELETED

            if action == DELETED:
                # If an object's deleted from a user's queryset, there's no guarantee that the user still
                # has permission to see the contents of the instance, so the instance just returns the lookup_field.
                instance_data = {viewset.lookup_field: getattr(instance, viewset.lookup_field)}
            else:
                serializer_class = viewset.get_serializer_class()
                instance_data = serializer_class(
                    instance,
                    context={
                        "request": viewset.request,
                        "format": "json",  # TODO: change this to be general based on content negotiation
                        "view": viewset,
                    },
                ).data

            # We don't need to check for membership since it's implicit given broadcast_data isn't None.
            if action == DELETED:
                self.owned_instance_pks[request_id].remove(instance_pk)
            else:
                self.owned_instance_pks[request_id].add(instance_pk)
            self.send_broadcast(request_id, model_label, action, instance_data, renderer)
