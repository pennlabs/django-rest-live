from django.db.models import Model
from rest_framework import serializers

from rest_live import __label_to_serializer


def subscribable(group_key: str = "pk"):
    def decorator(cls):
        if issubclass(cls, serializers.Serializer):
            model: Model = cls.Meta.model
            label = model._meta.label
            if label not in __label_to_serializer:
                __label_to_serializer[label] = list()
            __label_to_serializer[label].append((cls, group_key))
        return cls

    return decorator
