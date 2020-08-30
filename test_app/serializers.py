from rest_framework import serializers

from rest_live.decorators import subscribable
from test_app.models import Todo


@subscribable()
@subscribable("list_id")
class TodoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Todo
        fields = ["id", "text", "done"]
