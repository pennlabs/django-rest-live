from typing import Any, Dict, Type, List, Union, Set

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer

from rest_live import get_group_name, DELETED, UPDATED, CREATED
from rest_live.mixins import RealtimeMixin

KwargType = Dict[str, Union[int, str]]


class SubscriptionConsumer(JsonWebsocketConsumer):
    """
    Consumer that handles websocket connections, collecting subscriptions and sending broadcasts.
    Useful consumers which have a registry of views must subclass `SubscriptionConsumer` and override the `registry`
    property.

    One instance of a Consumer class communicates with exactly one client.
    """

    registry: Dict[str, Type[RealtimeMixin]] = dict()
    public = True

    def connect(self):
        if not self.public and not (
            self.scope.get("user") is not None
            and self.scope.get("user").is_authenticated
        ):
            self.close(code=4003)

        self.subscriptions: Dict[
            str, List[int]
        ] = dict()  # Maps group name to list of request IDs.
        self.actions: Dict[
            int, str
        ] = dict()  # Request ID to action (list or retrieve).
        self.kwargs: Dict[int, KwargType] = dict()  # Request ID to view kwargs.
        self.params: Dict[int, KwargType] = dict()  # Request ID to query params.
        self.visible_instance_pks: Dict[
            int, Set[int]
        ] = dict()  # set of visible instances for every request.

        self.accept()

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
        """
        Entrypoint for incoming messages from the connected client.
        """

        request_id = content.get("id", None)
        if request_id is None:
            return  # Can't send error message without request ID, so just return.
        message_type = content.get("type", None)
        if message_type == "subscribe":
            model_label = content.get("model")
            if model_label is None:
                self.send_error(request_id, 400, "No model specified.")
                return

            if model_label not in self.registry:
                self.send_error(
                    request_id,
                    404,
                    f"Model {model_label} not registered for realtime updates.",
                )
                return

            view_action = content.get("action", None)
            if view_action is None or view_action not in ["list", "retrieve"]:
                self.send_error(
                    request_id,
                    400,
                    "`action` must be present and the value must be either `list` or `retrieve`.",
                )

            lookup_value = content.get("lookup_by", None)
            view_kwargs = content.get("view_kwargs", dict())
            query_params = content.get("query_params", dict())

            view = self.registry[model_label].from_scope(
                view_action, self.scope, view_kwargs, query_params
            )
            model = view.get_model_class()

            # Check to make sure client has permissions to make this subscription.
            has_permission = True
            for permission in view.get_permissions():
                has_permission = has_permission and permission.has_permission(
                    view.request, view
                )

            # Retrieve actions must check has_object_permission as well.
            if view.action == "retrieve":
                try:
                    instance = view.get_queryset().get(
                        **{view.lookup_field: lookup_value}
                    )
                except model.DoesNotExist:
                    self.send_error(request_id, 404, "Instance not found.")
                    return

                for permission in view.get_permissions():
                    has_permission = (
                        has_permission
                        and permission.has_object_permission(
                            view.request, view, instance
                        )
                    )

            if not has_permission:
                self.send_error(
                    request_id,
                    403,
                    f"Unauthorized to subscribe to {model_label} for action {view_action}",
                )
                return

            # If we've reached this point, then the client can subscribe.
            group_name = get_group_name(model_label)
            print(f"[REST-LIVE] got subscription to {group_name}")

            self.subscriptions.setdefault(group_name, []).append(request_id)
            self.kwargs[request_id] = view_kwargs
            self.params[request_id] = query_params
            self.actions[request_id] = view_action
            self.visible_instance_pks[request_id] = set(
                [
                    instance1["pk"]
                    for instance1 in view.get_queryset().all().values("pk")
                ]
            )

            # Add subscribe to updates from channel layer: this is the "actual" subscription action.
            async_to_sync(self.channel_layer.group_add)(group_name, self.channel_name)
            self.groups.append(group_name)

        elif message_type == "unsubscribe":
            # Get the group name given the request_id
            try:
                # List comprehension is empty if the provided request_id doesn't show up for this consumer
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

            del self.actions[request_id]
            del self.kwargs[request_id]
            del self.visible_instance_pks[request_id]

            self.subscriptions[group_name].remove(request_id)
            self.groups.remove(
                group_name
            )  # Removes the first occurance of this group name.
            if (
                group_name not in self.groups
            ):  # If there are no more occurances, unsubscribe to the channel layer.
                async_to_sync(self.channel_layer.group_discard)(
                    group_name, self.channel_name
                )

            # Delete the key in the dictionary if no more subscriptions.
            if len(self.subscriptions[group_name]) == 0:
                del self.subscriptions[group_name]
        else:
            self.send_error(request_id, 400, f"unknown message type `{message_type}`.")

    def model_saved(self, event):
        channel_name = event["channel_name"]
        instance_pk = event["instance_pk"]
        model_label = event["model"]

        viewset_class = self.registry[model_label]

        for request_id in self.subscriptions[channel_name]:
            view = viewset_class.from_scope(
                self.actions[request_id],
                self.scope,
                self.kwargs[request_id],
                self.params[request_id],
            )

            model = view.get_model_class()
            renderer = view.perform_content_negotiation(view.request)[0]

            is_existing_instance = instance_pk in self.visible_instance_pks[request_id]
            try:
                instance = view.get_queryset().get(pk=instance_pk)
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
                instance_data = {
                    view.lookup_field: getattr(instance, view.lookup_field)
                }
            else:
                serializer_class = view.get_serializer_class()
                instance_data = serializer_class(
                    instance,
                    context={
                        "request": view.request,
                        "format": "json",  # TODO: change this to be general based on content negotiation
                        "view": view,
                    },
                ).data

            # We don't need to check for membership since it's implicit given broadcast_data isn't None.
            if action == DELETED:
                self.visible_instance_pks[request_id].remove(instance_pk)
            else:
                self.visible_instance_pks[request_id].add(instance_pk)
            self.send_broadcast(
                request_id, model_label, action, instance_data, renderer
            )
