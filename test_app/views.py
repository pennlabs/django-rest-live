from rest_framework import viewsets
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated, DjangoModelPermissions, BasePermission

from rest_live.mixins import RealtimeMixin
from test_app.models import Todo

from test_app.serializers import TodoSerializer, AuthedTodoSerializer, KwargsTodoSerializer


class TodoViewSet(GenericAPIView, RealtimeMixin):
    queryset = Todo.objects.all()
    serializer_class = TodoSerializer
    group_by_fields = ["pk", "list_id"]


class EmptyTodoViewSet(GenericAPIView, RealtimeMixin):
    queryset = Todo.objects.none()
    serializer_class = TodoSerializer
    group_by_fields = ["pk", "list_id"]


class KwargPermission(BasePermission):
    def has_permission(self, request, view):
        return view.kwargs.get("password", "") == "opensesame"


class KwargViewSet(GenericAPIView, RealtimeMixin):
    queryset = Todo.objects.all()
    serializer_class = KwargsTodoSerializer
    permission_classes = [KwargPermission]
    group_by_fields = ["pk", "list_id"]


class ConditionalTodoViewSet(viewsets.ModelViewSet, RealtimeMixin):
    queryset = Todo.objects.all()
    group_by_fields = ["pk", "list_id"]

    def get_serializer_class(self):
        if self.request.user.is_authenticated:
            return AuthedTodoSerializer
        else:
            return TodoSerializer


class AuthedTodoViewSet(viewsets.ModelViewSet, RealtimeMixin):
    queryset = Todo.objects.all()
    serializer_class = TodoSerializer
    permission_classes = [IsAuthenticated]
    group_by_fields = ["pk", "list_id"]
