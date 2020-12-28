from io import BytesIO
from typing import Type, Set, Tuple, Dict, Any, Optional

from channels.http import AsgiRequest
from django.db.models import Model
from django.db.models.signals import post_save
from django.utils.decorators import classonlymethod

from rest_framework.renderers import BaseRenderer

from rest_live import CREATED, UPDATED, DELETED
from rest_live.signals import save_handler


class RealtimeMixin(object):
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
            save_handler(sender, instance)

        post_save.connect(save_callback, sender=model_class, weak=False, dispatch_uid=f"rest-live")
        return viewset._get_model_class_label()

    @classonlymethod
    def from_scope(cls, viewset_action, scope, view_kwargs):
        self = cls()

        self.format_kwarg = None
        self.action_map = dict()
        self.args = []
        self.kwargs = view_kwargs
        self.action = viewset_action  # TODO: custom subscription actions?

        base_request = AsgiRequest(scope, BytesIO())
        # TODO: Run other middleware?
        base_request.user = scope.get("user", None)
        base_request.session = scope.get("session", None)

        self.request = self.initialize_request(base_request)
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

    def get_data_to_broadcast(
        self, instance_pk, owned_instance_pks: Set[int]
    ) -> Optional[Tuple[Dict[Any, Any], BaseRenderer, str]]:
        model = self.get_model_class()
        renderer: BaseRenderer = self.perform_content_negotiation(self.request)[0]

        is_existing_instance = instance_pk in owned_instance_pks
        try:
            instance = self.get_queryset().get(pk=instance_pk)
            action = UPDATED if is_existing_instance else CREATED
        except model.DoesNotExist:
            if not is_existing_instance:
                # If the model doesn't exist in the queryset now, and also is not in the set of PKs that we've seen,
                # then we truly don't have permission to see it.
                return None

            # If the instance has been seen, then we should get it from the database to serialize and send the delete
            # message.
            instance = model.objects.get(pk=instance_pk)
            action = DELETED

        if action == DELETED:
            # If an object's deleted from a user's queryset, there's no guarantee that the user still
            # has permission to see the contents of the instance, so the instance just returns the lookup_field.
            payload = {self.lookup_field: getattr(instance, self.lookup_field)}
        else:
            serializer_class = self.get_serializer_class()
            payload = serializer_class(
                instance,
                context={
                    "request": self.request,
                    "format": "json",  # TODO: change this to be general based on content negotiation
                    "view": self,
                },
            ).data

        return payload, renderer, action
