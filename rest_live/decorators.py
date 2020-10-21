from typing import Optional

from django.db.models import Model
from django.db.models.signals import post_delete, post_save
from rest_framework import serializers

from rest_live import PermissionLambda, __model_to_listeners
from rest_live.signals import ondelete_callback, onsave_callback


def __register_subscription(
    cls, group_key, check_permission: Optional[PermissionLambda]
):
    model: Model = cls.Meta.model
    label = model._meta.label  # noqa
    post_save.connect(onsave_callback, model, dispatch_uid="rest-live")
    post_delete.connect(ondelete_callback, model, dispatch_uid="rest-live")
    if label not in __model_to_listeners:
        __model_to_listeners[label] = dict()
    __model_to_listeners[label][group_key] = (cls, check_permission)


def subscribable(group_key: str = "pk", check_permission: PermissionLambda = None):
    def decorator(cls):
        if issubclass(cls, serializers.ModelSerializer):
            __register_subscription(cls, group_key, check_permission)
        return cls

    return decorator
