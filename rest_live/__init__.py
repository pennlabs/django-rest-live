from typing import Callable, Dict, Optional, Tuple, Type

from django.conf import settings
from django.db.models import Model
from rest_framework import serializers


default_app_config = "rest_live.apps.RestLiveConfig"

DEFAULT_GROUP_KEY = "pk"

User = settings.AUTH_USER_MODEL

PermissionLambda = Callable[[User, Model], bool]
SerializerClass = Type[serializers.Serializer]
ListenerEntry = Dict[str, Dict[str, Tuple[SerializerClass, Optional[PermissionLambda]]]]

__model_to_listeners: Dict[str, ListenerEntry] = dict()
