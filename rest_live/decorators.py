from typing import Optional

from django.db.models import Model
from django.db.models.signals import post_delete, post_save
from rest_framework import serializers

from rest_live import PermissionLambda, __model_to_listeners, DEFAULT_GROUP_KEY
from rest_live.signals import ondelete_callback, onsave_callback


def __clear_subscriptions():
    __model_to_listeners.clear()


def __register_subscription(
    cls, group_key, check_permission: Optional[PermissionLambda], rank: int = 0
):
    model: Model = cls.Meta.model
    label = model._meta.label  # noqa
    post_save.connect(onsave_callback, model, dispatch_uid="rest-live")
    post_delete.connect(ondelete_callback, model, dispatch_uid="rest-live")
    __model_to_listeners.setdefault(label, dict()).setdefault(group_key, dict())
    if rank in __model_to_listeners[label][group_key].keys():
        print(
            "WARNING: Two registrations for the same model/key combination"
            f"have identical rank {rank} and one will be overwritten."
        )
    __model_to_listeners[label][group_key][rank] = (cls, check_permission)


def subscribable(
    group_key: str = DEFAULT_GROUP_KEY, check_permission: PermissionLambda = None, rank=0
):
    def decorator(cls):
        if issubclass(cls, serializers.ModelSerializer):
            __register_subscription(cls, group_key, check_permission, rank)
        return cls

    return decorator
