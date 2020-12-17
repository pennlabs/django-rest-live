from io import BytesIO
from typing import Optional

from asgiref.sync import async_to_sync
from channels.http import AsgiRequest
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.utils.decorators import classonlymethod
from djangorestframework_camel_case.util import camelize
from rest_framework.viewsets import ModelViewSet

from rest_framework.renderers import BaseRenderer
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

    def get_model_class(self):
        assert getattr(self, "queryset", None) is not None or hasattr(
            self, "get_queryset"
        ), (
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
    def register_realtime(cls):
        viewset = cls()
        model_class = viewset.get_model_class()
        group_by_fields = list(
            set(viewset.group_by_fields + [viewset.lookup_field])
        )  # remove duplicates

        def save_callback(sender, instance, created, **kwargs):
            _send_update(
                sender, instance, CREATED if created else UPDATED, group_by_fields
            )

        post_save.connect(
            save_callback, sender=model_class, weak=False, dispatch_uid="rest-live"
        )
        return viewset._get_model_class_label()

    @classmethod
    def user_can_subscribe(cls, group_by_field, value, kwargs, user, session, scope):
        # TODO: Factor out common code
        self = cls()
        self.action_map = dict()
        self.kwargs = kwargs

        base_request = AsgiRequest(scope, BytesIO())
        request = self.initialize_request(base_request)
        self.request = request
        request.user = user
        request.session = session

        if group_by_field == self.lookup_field:
            self.action = "retrieve"
        else:
            self.action = "list"

        for permission in self.get_permissions():
            if not permission.has_permission(request, self):
                return False

        if self.action == "retrieve":
            instance = self.get_queryset().get(**{self.lookup_field: value})
            for permission in self.get_permissions():
                if not permission.has_object_permission(request, self, instance):
                    return False

        return True

    @classonlymethod
    def broadcast(cls, instance_pk, group_by_field, user, session, scope, **kwargs):
        self = cls()
        self.format_kwarg = None
        self.action_map = dict()
        base_request = AsgiRequest(scope, BytesIO())
        request = self.initialize_request(base_request)

        self.request = request

        # TODO: Run all request middleware
        request.user = user
        request.session = session

        self.args = []
        self.kwargs = kwargs
        # TODO: If group_by_field is any field with a unique=True on the model,
        if group_by_field == "pk" or group_by_field == "id":
            self.action = "retrieve"
        else:
            self.action = "list"

        model = self.get_model_class()
        try:
            instance = self.get_queryset().get(pk=instance_pk)
        except model.DoesNotExist:
            return

        # TODO: Investigate whether or not this check is erroneous
        for permission in self.get_permissions():
            # per-object permissions only checked for non-list actions.
            if self.action != "list":
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
        renderer: BaseRenderer = self.perform_content_negotiation(request)[0]

        return serializer.data, renderer
