from typing import Type

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import models
from djangorestframework_camel_case.util import camelize

from rest_live import ListenerEntry, __model_to_listeners
from rest_live.consumers import get_group_name


CREATED = "CREATED"
UPDATED = "UPDATED"
DELETED = "DELETED"


def send_model_update(model: Type[models.Model], instance: models.Model, action: str):
    model_label = model._meta.label

    listeners: ListenerEntry = __model_to_listeners.get(model_label, dict())
    for group_key_prop, (serializer_class, _) in listeners.items():
        if serializer_class is None:
            return

        group_key = getattr(instance, group_key_prop)
        serializer = serializer_class(instance)
        channel_layer = get_channel_layer()
        group_name = get_group_name(model_label, group_key, group_key_prop)

        content = {
            "model": model_label,
            "instance": camelize(serializer.data),
            "action": action,
            "group_key_value": group_key,
        }

        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "notify",
                "content": content,
                "group_key": group_key_prop,
                "instance_pk": instance.pk,
            },
        )


def onsave_callback(sender: Type[models.Model], instance: models.Model, created: bool, **kwargs):
    send_model_update(sender, instance, CREATED if created else UPDATED)


def ondelete_callback(sender, instance, **kwargs):
    send_model_update(sender, instance, DELETED)
