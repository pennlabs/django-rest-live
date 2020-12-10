from rest_framework import serializers

from test_app.models import Todo


class TodoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Todo
        fields = ["id", "text", "done", "another_field"]


class AuthedTodoSerializer(serializers.ModelSerializer):
    auth = serializers.SerializerMethodField()

    class Meta:
        model = Todo
        fields = ["id", "text", "done", "another_field", "auth"]

    def get_auth(self, obj):
        return "ADMIN"
