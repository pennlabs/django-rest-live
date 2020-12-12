from typing import List, Type

from asgiref.sync import async_to_sync
from django.db.models import Model
from django.db.models.signals import post_save, post_delete
from channels.layers import get_channel_layer
from rest_framework.serializers import ModelSerializer
from rest_framework.viewsets import ModelViewSet

from rest_live import get_group_name

CREATED = "CREATED"
UPDATED = "UPDATED"
DELETED = "DELETED"


class SubscriptionSet:
    model = None
    serializer_class = None
    # TODO: Name this field. `fields`? `subscription_fields`? `subscribable_fields`? `group_fields`?
    group_by_fields = None  # Each entry in this list is a group_by_field.

    def has_subscribe_permission(
        self, user, group_by_field, field_value
    ) -> bool:  # noqa
        return True

    def has_object_permission(self, user, instance) -> bool:  # noqa
        return True

    @property
    def model_label(self):
        return self._get_model_class()._meta.label

    def _get_model_class(self) -> Type[Model]:
        assert self.model is not None, (
            f"'{self.__class__.__name__}' should include a `model` attribute."
            % self.__class__.__name__
        )
        return self.model

    def get_serializer_class(self, user, instance) -> Type[ModelSerializer]:
        assert self.serializer_class is not None, (
            f"{self.__class__.__name__} should either include a `serializer_class` attribute, "
            "or override the `get_serializer_class()` method."
        )
        return self.serializer_class

    def _get_group_by_fields(self) -> List[str]:
        if self.group_by_fields is None:
            return ["pk"]
        return self.group_by_fields

    def _send_update(self, instance, action):
        channel_layer = get_channel_layer()
        for group_by_field in self.group_by_fields:
            field_value = getattr(instance, group_by_field)
            group_name = get_group_name(self.model_label, field_value, group_by_field)
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "notify",
                    "action": action,
                    "model": self.model_label,
                    "instance_pk": instance.pk,
                    "group_by_field": group_by_field,
                    "field_value": field_value,
                },
            )

    def _save_callback(self, sender, instance, created, **kwargs):
        self._send_update(instance, CREATED if created else UPDATED)

    def _delete_callback(self, sender, instance, **kwargs):
        self._send_update(instance, DELETED)

    def register_signals(self):
        model_cls = self._get_model_class()
        post_save.connect(
            self._save_callback, sender=model_cls, dispatch_uid="rest-live"
        )
        # TODO: Fix delete
        # post_delete.connect(self._delete_callback, sender=model_cls, dispatch_uid="rest-live")
