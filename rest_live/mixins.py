from io import BytesIO
from typing import Type

from asgiref.sync import async_to_sync
from channels.http import AsgiRequest
from channels.layers import get_channel_layer
from django.db.models import Model
from django.db.models.signals import post_save
from django.utils.decorators import classonlymethod

from rest_framework.renderers import BaseRenderer
from rest_framework.viewsets import ModelViewSet

from rest_live import get_group_name, CREATED, UPDATED


def _send_update(sender_model, instance, action, group_by_fields):
    model_label = sender_model._meta.label  # noqa
    channel_layer = get_channel_layer()
    for group_by_field in group_by_fields:
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


class RealtimeMixin(object):
    group_by_fields = []

    def get_model_class(self) -> Type[Model]:
        # TODO: Better model inference from `get_queryset` if we can.
        assert getattr(self, "queryset", None) is not None or hasattr(self, "get_queryset"), (
            f"{self.__class__.__name__} does not define a `.queryset` attribute and so no backing model could be"
            "determined. Views must provide `.queryset` attribute in order to be realtime-compatible."
        )
        assert getattr(self, "queryset", None) is not None, (
            f"{self.__class__.__name__} only defines a dynamic `.get_queryset()` method and so no backing"
            "model could be determined. Provide a 'sentinel' queryset of the form `queryset = Model.queryset.none()`"
            "to your view class in order to be realtime-compatible."
        )

        return self.queryset.model

    def _get_model_class_label(self):
        return self.get_model_class()._meta.label  # noqa

    @classmethod
    def register_realtime(cls, dispatch_uid):
        viewset = cls()
        model_class = viewset.get_model_class()
        group_by_fields = list(
            set(viewset.group_by_fields + [viewset.lookup_field])
        )  # remove duplicates

        def save_callback(sender, instance, created, **kwargs):
            _send_update(sender, instance, CREATED if created else UPDATED, group_by_fields)

        post_save.connect(save_callback, sender=model_class, weak=False, dispatch_uid=f"rest-live")
        return viewset._get_model_class_label()

    def _realtime_init(self, group_by_field, scope, view_kwargs):
        self.format_kwarg = None
        self.action_map = dict()
        self.args = []
        self.kwargs = view_kwargs

        base_request = AsgiRequest(scope, BytesIO())
        request = self.initialize_request(base_request)
        self.request = request
        request.user = scope.get("user", None)
        request.session = scope.get("session", None)

        if group_by_field == self.lookup_field:
            self.action = "retrieve"
        else:
            self.action = "list"

    @classmethod
    def user_can_subscribe(cls, group_by_field, value, scope, view_kwargs):
        self = cls()
        self._realtime_init(group_by_field, scope, view_kwargs)

        for permission in self.get_permissions():
            if not permission.has_permission(self.request, self):
                return False

        if self.action == "retrieve":
            instance = self.get_queryset().get(**{self.lookup_field: value})
            for permission in self.get_permissions():
                if not permission.has_object_permission(self.request, self, instance):
                    return False

        return True

    @classonlymethod
    def broadcast(cls, instance_pk, group_by_field, scope, view_kwargs):
        self = cls()
        self._realtime_init(group_by_field, scope, view_kwargs)

        model = self.get_model_class()
        try:
            instance = self.get_queryset().get(pk=instance_pk)
        except model.DoesNotExist:
            return None, None

        serializer_class = self.get_serializer_class()
        serializer = serializer_class(
            instance,
            context={
                "request": self.request,
                "format": "json",  # TODO: change this to be general based on content negotiation
                "view": self,
            },
        )
        renderer: BaseRenderer = self.perform_content_negotiation(self.request)[0]

        return serializer.data, renderer
