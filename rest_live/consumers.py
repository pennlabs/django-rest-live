from typing import Any, Dict, Type, List, Union, Set
from dataclasses import dataclass

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from django.http import Http404
from rest_framework.exceptions import NotAuthenticated, PermissionDenied

from rest_live import get_group_name, DELETED, UPDATED, CREATED
from rest_live.mixins import RealtimeMixin

KwargType = Dict[str, Union[int, str]]


@dataclass
class Subscription:
    """
    Data representing a subscription request from the client. See documentation for explanation
    of what each field does.
    """

    request_id: int
    action: str
    view_kwargs: Dict[str, Union[int, str]]
    query_params: Dict[str, Union[int, str]]

    # To determine if an instance should be considered "created" or "deleted", we need
    # to keep track of all the instances that a given subscription currently considers
    # visible. This map keeps track of that and will additionally map the primary keys of
    # each instance to the lookup field. This will probably be the main resource bottleneck
    # in django-rest-live
    pks_to_lookup_in_queryset: Dict[int, object]


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

        self.subscriptions: Dict[str, List[Subscription]] = dict()
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

            # Check to make sure client has permissions to make this subscription.
            has_permission = True
            for permission in view.get_permissions():
                has_permission = has_permission and permission.has_permission(
                    view.request, view
                )

            # Retrieve actions use get_object() to check object permissions as well.
            if view.action == "retrieve":
                view.kwargs.setdefault(view.lookup_field, lookup_value)
                try:
                    view.get_object()
                except Http404:
                    self.send_error(
                        request_id,
                        404,
                        "Instance not found. Make sure 'lookup_by' is set to a valid ID",
                    )
                    return
                except (NotAuthenticated, PermissionDenied):
                    has_permission = False

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

            self.subscriptions.setdefault(group_name, []).append(
                Subscription(
                    request_id,
                    action=view_action,
                    view_kwargs=view_kwargs,
                    query_params=query_params,
                    pks_to_lookup_in_queryset=dict(
                        {
                            inst["pk"]: inst[view.lookup_field]
                            for inst in view.get_queryset().all().values("pk", view.lookup_field)
                        }
                    ),
                )
            )

            # Add subscribe to updates from channel layer: this is the "actual" subscription action.
            async_to_sync(self.channel_layer.group_add)(group_name, self.channel_name)
            self.groups.append(group_name)

        elif message_type == "unsubscribe":
            # Get the group name given the request_id
            try:
                # List comprehension is empty if the provided request_id doesn't show up for this consumer
                group_name = [
                    k
                    for k, v in self.subscriptions.items()
                    if request_id in [s.request_id for s in v]
                ][0]
            except IndexError:
                self.send_error(
                    request_id,
                    404,
                    "Attempted to unsubscribe for request ID before subscribing.",
                )
                return

            self.subscriptions[group_name] = [
                sub
                for sub in self.subscriptions[group_name]
                if sub.request_id != request_id
            ]
            self.groups.remove(
                group_name
            )  # Removes the first occurrence of this group name.
            if (
                group_name not in self.groups
            ):  # If there are no more occurrences, unsubscribe to the channel layer.
                async_to_sync(self.channel_layer.group_discard)(
                    group_name, self.channel_name
                )

            # Delete the key in the dictionary if no more subscriptions.
            if len(self.subscriptions[group_name]) == 0:
                del self.subscriptions[group_name]
        else:
            self.send_error(request_id, 400, f"unknown message type `{message_type}`.")

    def model_saved(self, event):
        channel_name: str = event["channel_name"]
        instance_pk: int = event["instance_pk"]
        model_label: str = event["model"]

        viewset_class = self.registry[model_label]

        for subscription in self.subscriptions[channel_name]:
            view = viewset_class.from_scope(
                subscription.action,
                self.scope,
                subscription.view_kwargs,
                subscription.query_params,
            )

            model = view.get_model_class()
            renderer = view.perform_content_negotiation(view.request)[0]

            is_existing_instance = instance_pk in subscription.pks_to_lookup_in_queryset
            try:
                instance = view.filter_queryset(view.get_queryset()).get(pk=instance_pk)
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

            serializer_class = view.get_serializer_class()
            instance_data = serializer_class(
                instance,
                context={
                    "request": view.request,
                    "format": "json",  # TODO: change this to be general based on content negotiation
                    "view": view,
                },
            ).data

            if action == DELETED:
                # If an object's deleted from a user's queryset, there's no guarantee that the user still
                # has permission to see the contents of the instance, so the instance just returns the lookup_field.
                # TODO: clients might expect `id` as well as `pk`, since django defaults to `id`.
                if view.lookup_field == "pk" and "id" in instance_data:
                    instance_data = {
                        view.lookup_field: getattr(instance, view.lookup_field),
                        "id": instance_data["id"],
                    }
                else:
                    instance_data = {
                        view.lookup_field: getattr(instance, view.lookup_field)
                    }

            # We don't need to check for membership since it's implicit given broadcast_data isn't None.
            if action == DELETED:
                del subscription.pks_to_lookup_in_queryset[instance_pk]
            else:
                subscription.pks_to_lookup_in_queryset[instance_pk] = getattr(
                    instance, view.lookup_field
                )
            self.send_broadcast(
                subscription.request_id, model_label, action, instance_data, renderer
            )

    def model_deleted(self, event):
        channel_name: str = event["channel_name"]
        instance_pk: int = event["instance_pk"]
        model_label: str = event["model"]

        viewset_class = self.registry[model_label]

        for subscription in self.subscriptions[channel_name]:
            view = viewset_class.from_scope(
                subscription.action,
                self.scope,
                subscription.view_kwargs,
                subscription.query_params,
            )
            renderer = view.perform_content_negotiation(view.request)[0]
            is_existing_instance = instance_pk in subscription.pks_to_lookup_in_queryset

            if is_existing_instance:
                instance_data = {
                    view.lookup_field: subscription.pks_to_lookup_in_queryset[
                        instance_pk
                    ],
                    "id": instance_pk,
                }
                del subscription.pks_to_lookup_in_queryset[instance_pk]
                self.send_broadcast(
                    subscription.request_id,
                    model_label,
                    DELETED,
                    instance_data,
                    renderer,
                )
