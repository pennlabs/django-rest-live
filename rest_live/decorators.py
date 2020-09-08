from typing import Optional

from django.db.models import Model
from rest_framework import serializers

from rest_live import PermissionLambda, __model_to_listeners


def __register_subscription(
    cls, group_key, check_permission: Optional[PermissionLambda]
):
    model: Model = cls.Meta.model
    label = model._meta.label  # noqa
    if label not in __model_to_listeners:
        __model_to_listeners[label] = dict()
    __model_to_listeners[label][group_key] = (cls, check_permission)


def subscribable(group_key: str = "pk", check_permission: PermissionLambda = None):
    def decorator(cls):
        if issubclass(cls, serializers.ModelSerializer):
            __register_subscription(cls, group_key, check_permission)
        return cls

    return decorator
