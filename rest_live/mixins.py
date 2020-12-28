from io import BytesIO
from typing import Type, Set

from asgiref.sync import async_to_sync
from channels.http import AsgiRequest
from channels.layers import get_channel_layer
from django.db.models import Model
from django.db.models.signals import post_save
from django.utils.decorators import classonlymethod

from rest_framework.renderers import BaseRenderer

from rest_live import get_group_name, CREATED, UPDATED


def _send_update(sender_model, instance, action):
    model_label = sender_model._meta.label  # noqa
    channel_layer = get_channel_layer()
    group_name = get_group_name(model_label)
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "notify",
            "action": action,
            "model": model_label,
            "instance_pk": instance.pk,
            "channel_name": group_name,
        },
    )


class RealtimeMixin(object):
    # TODO: Remove if we don't need it
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

        def save_callback(sender, instance, created, **kwargs):
            _send_update(sender, instance, CREATED if created else UPDATED)

        post_save.connect(save_callback, sender=model_class, weak=False, dispatch_uid=f"rest-live")
        return viewset._get_model_class_label()

    @classonlymethod
    def from_scope(cls, viewset_action, scope, view_kwargs):
        self = cls()
        self.format_kwarg = None
        self.action_map = dict()
        self.args = []
        self.kwargs = view_kwargs
        self.action = viewset_action
        base_request = AsgiRequest(scope, BytesIO())
        request = self.initialize_request(base_request)
        self.request = request
        request.user = scope.get("user", None)
        request.session = scope.get("session", None)
        return self

    def user_can_subscribe(self, lookup_value):
        for permission in self.get_permissions():
            if not permission.has_permission(self.request, self):
                return False

        if self.action == "retrieve":
            instance = self.get_queryset().get(**{self.lookup_field: lookup_value})
            for permission in self.get_permissions():
                if not permission.has_object_permission(self.request, self, instance):
                    return False

        return True

    def get_list_pks(self) -> Set[int]:
        return set([instance["pk"] for instance in self.get_queryset().all().values("pk")])

    def get_data_to_broadcast(self, instance_pk, set_pks: Set[int]):
        model = self.get_model_class()

        try:
            instance = self.get_queryset().get(pk=instance_pk)
        except model.DoesNotExist:
            if instance_pk in set_pks:
                # TODO: Send delete action
                pass
            return None, None

        serializer_class = self.get_serializer_class()
        renderer: BaseRenderer = self.perform_content_negotiation(self.request)[0]
        serializer = serializer_class(
            instance,
            context={
                "request": self.request,
                "format": "json",  # TODO: change this to be general based on content negotiation
                "view": self,
            },
        )

        return serializer.data, renderer
