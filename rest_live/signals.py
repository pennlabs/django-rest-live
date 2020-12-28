from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from rest_live import get_group_name


def save_handler(sender, instance, *args, **kwargs):
    model_label = sender._meta.label  # noqa
    channel_layer = get_channel_layer()
    group_name = get_group_name(model_label)
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "model.saved",
            "model": model_label,
            "instance_pk": instance.pk,
            "channel_name": group_name,
        },
    )
