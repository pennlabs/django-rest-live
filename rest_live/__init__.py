default_app_config = "rest_live.apps.RestLiveConfig"

DEFAULT_GROUP_KEY = "pk"


def get_group_name(model_label, value, key_prop) -> str:
    return f"RESOURCE-{model_label}-{key_prop}-{value}"
