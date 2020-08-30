from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path

from rest_live.consumers import SubscriptionConsumer


websockets = AuthMiddlewareStack(
    URLRouter([path("ws/subscribe/", SubscriptionConsumer, name="subscriptions")])
)
application = ProtocolTypeRouter({"websocket": websockets})
