default_app_config = "rest_live.apps.RestLiveConfig"

DEFAULT_GROUP_BY_FIELD = "pk"


def get_group_name(model_label, broadcast_field, field_value) -> str:
    return f"RESOURCE-{model_label}-{broadcast_field}-{field_value}"


CREATED = "CREATED"
UPDATED = "UPDATED"
DELETED = "DELETED"
