from typing import Dict, Type

from rest_live.consumers import SubscriptionConsumer
from rest_live.mixins import RealtimeMixin


class RealtimeRouter:
    def __init__(self, uid="default"):
        self.registry: Dict[str, Type[RealtimeMixin]] = dict()
        self.uid = uid

    def register_all(self, viewsets):
        for viewset in viewsets:
            self.register(viewset)

    def register(self, viewset):
        if not hasattr(viewset, "register_realtime"):
            raise RuntimeError(
                f"View {viewset.__name__}"
                "passed to RealtimeRouter does not have RealtimeMixin applied."
            )
        label = viewset.register_realtime(self.uid)
        if label in self.registry:
            raise RuntimeWarning("You should not register two realitime views for the same model.")

        self.registry[label] = viewset

    def as_consumer(self):
        # Create a subclass of `SubscriptionConsumer` where the consumer's model
        # registry is set to this router's registry. Basically a subclass inside a closure.
        return type(
            "BoundSubscriptionConsumer",
            (SubscriptionConsumer,),
            dict(registry=self.registry),
        )
