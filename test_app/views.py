from django.db.models.functions import Length

from rest_framework import viewsets, filters
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import (
    IsAuthenticated,
    BasePermission,
)

from rest_live.mixins import RealtimeMixin
from test_app.models import Todo

from test_app.serializers import (
    TodoSerializer,
    AuthedTodoSerializer,
    KwargsTodoSerializer,
)


class TodoViewSet(GenericAPIView, RealtimeMixin):
    queryset = Todo.objects.all()
    serializer_class = TodoSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["text"]


class ConditionalTodoViewSet(viewsets.ModelViewSet, RealtimeMixin):
    queryset = Todo.objects.all()

    def get_serializer_class(self):
        if self.request.user.is_authenticated:
            return AuthedTodoSerializer
        else:
            return TodoSerializer


class AuthedTodoViewSet(viewsets.ModelViewSet, RealtimeMixin):
    queryset = Todo.objects.all()
    serializer_class = TodoSerializer
    permission_classes = [IsAuthenticated]


class LookupTodoViewSet(viewsets.ModelViewSet, RealtimeMixin):
    queryset = Todo.objects.all()
    serializer_class = TodoSerializer
    lookup_field = "text"


class KwargPermission(BasePermission):
    def has_permission(self, request, view):
        return view.kwargs.get("password", "") == "opensesame"


class ParamPermission(BasePermission):
    def has_permission(self, request, view):
        return request.query_params.get("password", "") == "opensesame-param"


class KwargViewSet(GenericAPIView, RealtimeMixin):
    queryset = Todo.objects.all()
    serializer_class = KwargsTodoSerializer
    permission_classes = [KwargPermission | ParamPermission]


class FilteredViewSet(GenericAPIView, RealtimeMixin):
    queryset = Todo.objects.filter(text="special")
    serializer_class = TodoSerializer


class AnnotatedTodoViewSet(GenericAPIView, RealtimeMixin):
    queryset = Todo.objects.all()
    serializer_class = TodoSerializer

    def get_queryset(self):
        return super().get_queryset().annotate(text_length=Length("text"))
