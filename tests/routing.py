from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path

from rest_live.consumers import SubscriptionConsumer
from test_app.serializers import *  # noqa


websockets = URLRouter(
    [path("ws/subscribe/", SubscriptionConsumer, name="subscriptions")]
)
application = ProtocolTypeRouter({"websocket": websockets})
