from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.utils.decorators import classonlymethod
from djangorestframework_camel_case.util import camelize
from rest_framework.permissions import AllowAny
from rest_framework.viewsets import ModelViewSet

from rest_live import get_group_name, CREATED, UPDATED


def _send_update(sender_model, instance, action, broadcast_fields):
    model_label = sender_model._meta.label  # noqa
    channel_layer = get_channel_layer()
    for group_by_field in broadcast_fields:
        field_value = getattr(instance, group_by_field)
        group_name = get_group_name(model_label, group_by_field, field_value)
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "notify",
                "action": action,
                "model": model_label,
                "instance_pk": instance.pk,
                "group_by_field": group_by_field,
                "field_value": field_value,
                "channel_name": group_name,
            },
        )


class FakeRequest:
    def __init__(self, user, **kwargs):
        self.user = user
        for k, v in kwargs.items():
            setattr(self, k, v)


class RealtimeMixin(object):
    model_class = None
    group_by_fields = ["id"]
    _broadcast_actions = None

    def get_model_class(self):
        if self.model_class is not None:
            return self.model_class

        if self.serializer_class is not None:
            return self.serializer_class.Meta.model
        else:
            raise AssertionError("model cannot be inferred from dynamic get_serializer_class."
                                 "Either explicitliy define model_class or serializer_class on the ViewSet.")

    def _get_model_class_label(self):
        return self.get_model_class()._meta.label  # noqa

    def _get_broadcast_actions(self):
        if self._broadcast_actions is None:
            self._broadcast_actions = []
            if "pk" in self.group_by_fields:
                self._broadcast_actions += ["retrieve"]
            if len([f for f in self.group_by_fields if f != "pk"]):
                self._broadcast_actions += ["list"]
        return self._broadcast_actions

    @classmethod
    def register_realtime(cls):
        viewset = cls()
        model_class = viewset.model_class
        broadcast_fields = viewset.group_by_fields

        def save_callback(sender, instance, created, **kwargs):
            _send_update(
                sender, instance, CREATED if created else UPDATED, broadcast_fields
            )
        post_save.connect(
            save_callback, sender=model_class, weak=False, dispatch_uid="rest-live"
        )
        return viewset._get_model_class_label()

    @classonlymethod
    def as_broadcast(cls, **initkwargs):
        def broadcast(instance_pk, group_by_field, user, session, **kwargs):
            self = cls(**initkwargs)
            model = self.get_model_class()
            try:
                instance = model.objects.get(pk=instance_pk)
            except model.DoesNotExist:
                return

            request = FakeRequest(user, session=session, method="GET", content_type="application/json", GET=dict(), query_params=dict())

            self.request = request
            self.args = []
            self.kwargs = kwargs

            # TODO: If group_by_field is any field with a unique=True on the model,
            if group_by_field == "pk" or group_by_field == "id":
                viewset_action = "retrieve"
            else:
                viewset_action = "list"

            self.action = viewset_action
            for permission in self.get_permissions():
                # per-object permissions only checked for non-list actions.
                if viewset_action != "list":
                    if not permission.has_object_permission(request, self, instance):
                        return None
                if not permission.has_permission(request, self):
                    return None

            serializer_class = self.get_serializer_class()
            serializer = serializer_class(
                instance,
                context={
                    "request": request,
                    "format": "json",
                    "view": self,
                },
            )

            return camelize(serializer.data)

        return broadcast
