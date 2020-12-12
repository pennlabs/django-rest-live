from rest_live.subscriptionsets import SubscriptionSet

from test_app.models import Todo
from test_app.serializers import TodoSerializer, AuthedTodoSerializer


class TodoSubscription(SubscriptionSet):
    model = Todo
    serializer_class = TodoSerializer
    group_by_fields = ["pk", "list_id"]


class ConditionalTodoSubscription(SubscriptionSet):
    model = Todo
    group_by_fields = ["pk", "list_id"]

    def get_serializer_class(self, user, instance):
        if user.is_authenticated:
            return AuthedTodoSerializer
        else:
            return TodoSerializer


class PermissionTodoSubscription(SubscriptionSet):
    model = Todo
    group_by_fields = ["pk", "list_id"]
    serializer_class = TodoSerializer

    def has_object_permission(self, user, instance) -> bool:
        return user.is_authenticated
