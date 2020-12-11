from typing import Optional

from django.db.models import Model
from django.db.models.signals import post_delete, post_save
from rest_framework import serializers

from rest_live import PermissionLambda, __model_to_listeners, DEFAULT_GROUP_KEY
from rest_live.signals import ondelete_callback, onsave_callback


def __clear_subscriptions():
    __model_to_listeners.clear()


def __register_subscription(
    cls, group_key, check_permission: Optional[PermissionLambda]
):
    model: Model = cls.Meta.model
    label = model._meta.label  # noqa
    post_save.connect(onsave_callback, model, dispatch_uid="rest-live")
    post_delete.connect(ondelete_callback, model, dispatch_uid="rest-live")
    __model_to_listeners.setdefault(label, dict()).setdefault(group_key, dict())
    serializer_name = cls.__qualname__
    if serializer_name in __model_to_listeners[label][group_key].keys():
        print(
            "WARNING: Two registrations for the same model/key/serializer combination"
            f"({label}/{group_key}/{serializer_name}) and one will be overwritten."
        )
    __model_to_listeners[label][group_key][serializer_name] = (cls, check_permission)


def subscribable(
    group_key: str = DEFAULT_GROUP_KEY,
    check_permission: PermissionLambda = None,
    rank=0,
):
    def decorator(cls):
        if issubclass(cls, serializers.ModelSerializer):
            __register_subscription(cls, group_key, check_permission, rank)
        return cls

    return decorator
