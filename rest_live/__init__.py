from typing import Dict, List, Tuple, Type

from rest_framework import serializers


default_app_config = "rest_live.apps.RestLiveConfig"

__label_to_serializer: Dict[
    str, List[Tuple[Type[serializers.Serializer], str]]
] = dict()
