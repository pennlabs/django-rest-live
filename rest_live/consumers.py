from typing import Any, Dict

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from rest_live import PermissionLambda, __model_to_listeners, DEFAULT_GROUP_KEY


def get_group_name(model_label, value, key_prop) -> str:
    return f"RESOURCE-{model_label}-{key_prop}-{value}"


@database_sync_to_async
def does_have_permission(
    user, model_label, instance_filter, check: PermissionLambda
) -> bool:
    from django.apps import apps

    model = apps.get_model(model_label)
    instance = model.objects.get(**instance_filter)
    return check(user, instance)


def get_permission_check(model_label, group_key):
    return __model_to_listeners.get(model_label, dict()).get(group_key, (None, None))[1]


def get_permissions(model_label, group_key, serializer_name):
    return __model_to_listeners[model_label][group_key][serializer_name]


class SubscriptionConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get("user", None)  # noqa
        await self.accept()

    async def notify(self, event):
        content = event["content"]
        group_key = event["group_key"]
        instance_pk = event["instance_pk"]
        serializer_name = event["serializer_name"]
        model_label = content["model"]

        try:
            _, check = get_permissions(model_label, group_key, serializer_name)
        # Some error has taken place and the global entry can't find a check.
        except KeyError:
            return

        # TODO: Make a default check in the map so that the type is no longer optional
        # and we can remove this special case.
        if check is None:
            await self.send_json(event["content"])
            return

        has_permission = await does_have_permission(
            self.user, model_label, {"id": instance_pk}, check
        )
        if has_permission:
            await self.send_json(event["content"])

    async def receive_json(self, content: Dict[str, Any], **kwargs):
        """
        Receive a subscription on this consumer.
        """

        model_label = content.get("model")
        if model_label is None:
            print("[REST-LIVE] No model")
            return
        prop = content.get("property", DEFAULT_GROUP_KEY)
        value = content.get("value", None)

        if value is None:
            print(f"[REST-LIVE] No value for prop {prop} found.")
            return

        group_name = get_group_name(model_label, value, prop)
        unsubscribe = content.get("unsubscribe", False)
        if not unsubscribe:
            print(f"[REST-LIVE] got subscription to {group_name}")
            self.groups.append(group_name)
            await self.channel_layer.group_add(group_name, self.channel_name)
        else:
            print(f"[REST-LIVE] got unsubscribe for {group_name}")
            self.groups.remove(group_name)
            if group_name not in self.groups:
                await self.channel_layer.group_discard(group_name, self.channel_name)
