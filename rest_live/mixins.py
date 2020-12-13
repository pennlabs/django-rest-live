from io import BytesIO

from asgiref.sync import async_to_sync
from channels.http import AsgiRequest
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.utils.decorators import classonlymethod
from djangorestframework_camel_case.util import camelize

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
    group_by_fields = ["pk"]

    def get_model_class(self):
        qs = self.get_queryset()
        return qs.model

    def _get_model_class_label(self):
        return self.get_model_class()._meta.label  # noqa

    @classmethod
    def register_realtime(cls):
        viewset = cls()
        model_class = viewset.get_model_class()
        group_by_fields = viewset.group_by_fields

        def save_callback(sender, instance, created, **kwargs):
            _send_update(
                sender, instance, CREATED if created else UPDATED, group_by_fields
            )

        post_save.connect(
            save_callback, sender=model_class, weak=False, dispatch_uid="rest-live"
        )
        return viewset._get_model_class_label()

    @classonlymethod
    def as_broadcast(cls, **initkwargs):
        def broadcast(instance_pk, group_by_field, user, session, scope, **kwargs):
            self = cls(**initkwargs)

            self.action_map = dict()
            base_request = AsgiRequest(scope, BytesIO())
            request = self.initialize_request(base_request)

            self.request = request

            # TODO: Run all request middleware
            request.user = user
            request.session = session

            self.args = []
            self.kwargs = kwargs

            model = self.get_model_class()
            try:
                instance = self.get_queryset().get(pk=instance_pk)
            except model.DoesNotExist:
                return

            # TODO: If group_by_field is any field with a unique=True on the model,
            if group_by_field == "pk" or group_by_field == "id":
                self.action = "retrieve"
            else:
                self.action = "list"

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

            return camelize(serializer.data)

        return broadcast
