from rest_framework import serializers
from rest_framework.permissions import BasePermission

from test_app.models import Todo


class TodoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Todo
        fields = ["id", "text", "done", "another_field"]


class KwargsTodoSerializer(serializers.ModelSerializer):
    message = serializers.SerializerMethodField()

    class Meta:
        model = Todo
        fields = ["message"]

    def get_message(self, *args, **kwargs):
        return self.context["view"].kwargs.get("message")


class AuthedTodoSerializer(serializers.ModelSerializer):
    auth = serializers.SerializerMethodField()

    class Meta:
        model = Todo
        fields = ["id", "text", "done", "another_field", "auth"]

    def get_auth(self, obj):
        return "ADMIN"
