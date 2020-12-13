from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from rest_live.mixins import RealtimeMixin
from test_app.models import Todo

from test_app.serializers import TodoSerializer, AuthedTodoSerializer


class TodoViewSet(viewsets.ModelViewSet, RealtimeMixin):
    serializer_class = TodoSerializer
    model_class = Todo
    broadcast_fields = ["pk", "list_id"]


class ConditionalTodoViewSet(viewsets.ModelViewSet, RealtimeMixin):
    model_class = Todo
    broadcast_fields = ["pk", "list_id"]

    def get_serializer_class(self):
        if self.request.user.is_authenticated:
            return AuthedTodoSerializer
        else:
            return TodoSerializer


class AuthedTodoViewSet(viewsets.ModelViewSet, RealtimeMixin):
    model_class = Todo
    broadcast_fields = ["pk", "list_id"]
    serializer_class = TodoSerializer
    permission_classes = [IsAuthenticated]
