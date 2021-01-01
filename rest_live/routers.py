from typing import Dict, Type

from rest_live.consumers import SubscriptionConsumer
from rest_live.mixins import RealtimeMixin


class RealtimeRouter:
    """
    This router collects views/model pairs that are registered as realtime-capable, and generates
    a Django Channels Consumer to handle subscriptions for those models.
    """

    def __init__(self, public=True, uid="default"):
        self.registry: Dict[str, Type[RealtimeMixin]] = dict()
        self.uid = uid
        self.public = public

    def register_all(self, views):
        for viewset in views:
            self.register(viewset)

    def register(self, view):
        if not hasattr(view, "register_signal_handler"):
            raise RuntimeError(
                f"View {view.__name__}"
                "passed to RealtimeRouter does not have RealtimeMixin applied."
            )
        label = view.register_signal_handler(self.uid)
        if label in self.registry:
            raise RuntimeWarning(
                "You should not register two realitime views for the same model."
            )

        self.registry[label] = view

    def as_consumer(self):
        # Create a subclass of `SubscriptionConsumer` where the consumer's model
        # registry is set to this router's registry. Basically a subclass inside a closure.
        return type(
            "BoundSubscriptionConsumer",
            (SubscriptionConsumer,),
            dict(registry=self.registry, public=self.public),
        )
