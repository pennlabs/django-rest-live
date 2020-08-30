from typing import Any, Dict, List

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from rest_live import __label_to_serializer


def get_group_name(model_label, key, key_prop) -> str:
    return f"RESOURCE-{model_label}-{key_prop}-{key}"


def get_associated_properties(model_label) -> List[str]:
    return [prop for _, prop in __label_to_serializer.get(model_label, [])]


class SubscriptionConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        # TODO: Confirm that the user has permissions
        print("[LIVE] Connected!")
        await self.accept()

    async def notify(self, event):
        await self.send_json(event["content"])

    async def receive_json(self, content: Dict[str, Any], **kwargs):
        """
        Receive a subscription on this consumer.
        """

        model_label = content.get("model")
        if model_label is None:
            print("[LIVE] No model")
            return
        props = get_associated_properties(model_label)

        key = None
        prop = None
        for potential_prop in props:
            key = content.get(potential_prop)
            if key is not None:
                prop = potential_prop
                break

        if key is None:
            print("[LIVE] No accepted key prop found.")
            return

        group_name = get_group_name(model_label, key, prop)
        print(f"[REST-LIVE] got subscription to {group_name}")
        self.groups.append(group_name)
        await self.channel_layer.group_add(group_name, self.channel_name)
