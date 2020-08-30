from typing import Type

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import models

from rest_live import __label_to_serializer
from rest_live.consumers import get_group_name


CREATED = "CREATED"
UPDATED = "UPDATED"
DELETED = "DELETED"


async def send_model_update(
    model: Type[models.Model], instance: models.Model, action: str
):
    model_label = model._meta.label

    for serializer_class, group_key_prop in __label_to_serializer.get(model_label, []):
        if serializer_class is None:
            return

        group_key = getattr(instance, group_key_prop)
        serializer = serializer_class(instance)
        channel_layer = get_channel_layer()
        group_name = get_group_name(model_label, group_key, group_key_prop)

        content = {"model": model_label, "payload": serializer.data, "action": action}

        await channel_layer.group_send(
            group_name, {"type": "notify", "content": content}
        )


def onsave_callback(
    sender: Type[models.Model], instance: models.Model, created: bool, **kwargs
):
    async_to_sync(send_model_update)(sender, instance, CREATED if created else UPDATED)


def ondelete_callback(sender, instance, **kwargs):
    async_to_sync(send_model_update)(sender, instance, DELETED)
