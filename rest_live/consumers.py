from typing import Any, Dict, Type, List

from channels.consumer import AsyncConsumer
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from djangorestframework_camel_case.util import camelize

from rest_live import DEFAULT_GROUP_KEY, get_group_name
from rest_live.subscriptionsets import SubscriptionSet


def make_consumer(
    subscription_sets: List[Type[SubscriptionSet]],
) -> Type[AsyncConsumer]:
    from django.apps import apps

    subscriptions = {sub.model_label: sub for sub in [s() for s in subscription_sets]}

    for sub in subscriptions.values():
        sub.register_signals()

    class SubscriptionConsumer(AsyncJsonWebsocketConsumer):
        async def connect(self):
            self.user = self.scope.get("user", None)  # noqa
            await self.accept()

        async def receive_json(self, content: Dict[str, Any], **kwargs):
            """
            Receive a subscription on this consumer.
            """

            model_label = content.get("model")
            if model_label is None:
                print("[REST-LIVE] No model")  # TODO: Error message
                return

            prop = content.get("property", DEFAULT_GROUP_KEY)
            value = content.get("value", None)

            if value is None:
                print(f"[REST-LIVE] No value for prop {prop} found.")  # TODO: Error
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
                    await self.channel_layer.group_discard(
                        group_name, self.channel_name
                    )

        async def notify(self, event):
            group_by_field = event["group_by_field"]
            field_value = event["field_value"]
            instance_pk = event["instance_pk"]
            action = event["action"]
            model_label = event["model"]

            subscription_set: SubscriptionSet = subscriptions.get(model_label)
            if subscription_set is None:
                return  # Error: subscription set not found

            model = apps.get_model(model_label)
            instance = await database_sync_to_async(model.objects.get)(
                **{"pk": instance_pk}
            )
            has_permission = await database_sync_to_async(
                subscription_set.has_object_permission
            )(self.user, instance)
            if not has_permission:
                return

            serializer_class = subscription_set.get_serializer_class(
                self.user, instance
            )
            serialized = await database_sync_to_async(
                lambda: serializer_class(instance).data
            )()
            await self.send_json(
                {
                    "model": model_label,
                    "action": action,
                    "group_key_value": field_value,
                    "instance": camelize(serialized),
                }
            )

    return SubscriptionConsumer
