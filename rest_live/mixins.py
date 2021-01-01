from io import BytesIO
from typing import Type, Set, Tuple, Dict, Any, Optional

from channels.http import AsgiRequest
from django.db.models import Model
from django.db.models.signals import post_save
from django.utils.decorators import classonlymethod
from django.utils.http import urlencode
from rest_framework.generics import GenericAPIView
from rest_live.signals import save_handler


class RealtimeMixin(object):
    """
    This mixin marks a DRF Generic APIView as realtime capable. It contains utility methods
    used internally for initializing the view class based on a ASGI websocket scope and subscription
    metadata rather than an HTTP request.
    """

    def get_model_class(self) -> Type[Model]:
        """
        Get the model class from the `queryset` property on the view class. This method can be called
        when a viewset hasn't been properly initialized, as long as there is a static `queryset` property.
        """

        # TODO: Better model inference from `get_queryset` if we can.
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

    @classmethod
    def register_signal_handler(cls, dispatch_uid):
        """
        Register post_save signal handler for the view's model.
        """
        viewset = cls()
        model_class = viewset.get_model_class()

        post_save.connect(save_handler, sender=model_class, dispatch_uid=f"rest-live")
        return viewset.get_model_class()._meta.label

    @classonlymethod
    def from_scope(cls, viewset_action, scope, view_kwargs, query_params):
        """
        "This is the magic."
        (reference: https://github.com/encode/django-rest-framework/blob/1e383f/rest_framework/viewsets.py#L47)

        This method initializes a view properly so that calls to methods like get_queryset() and get_serializer_class(),
        and permission checks have all the properties set, like self.kwargs and self.request, that they would expect.

        The production of a Django HttpRequest object from a base websocket asgi scope, rather than an actual HTTP
        request, is probably the largest "hack" in this project. By inspection of the ASGI spec, however,
        the only difference between websocket and HTTP scopes is the existence of an HTTP method
        (https://asgi.readthedocs.io/en/latest/specs/www.html).

        This is because websocket connections are established over an HTTP connection, and so headers and everything
        else are set just as they would be in a normal HTTP request. Therefore, the base of the request object for
        every broadcast is the initial HTTP request. Subscriptions are retrieval operations, so the method is hard-coded
        as GET.
        """
        self = cls()

        self.format_kwarg = None
        self.action_map = dict()
        self.args = []
        self.kwargs = view_kwargs
        self.action = viewset_action  # TODO: custom subscription actions?

        base_request = AsgiRequest(
            {**scope, "method": "GET", "query_string": urlencode(query_params)},
            BytesIO(),
        )
        # TODO: Run other middleware?
        base_request.user = scope.get("user", None)
        base_request.session = scope.get("session", None)

        self.request = self.initialize_request(base_request)
        return self
