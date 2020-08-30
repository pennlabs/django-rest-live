from rest_framework import serializers

from test_app.models import Todo


class TodoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Todo
        fields = ["id", "text", "done"]
