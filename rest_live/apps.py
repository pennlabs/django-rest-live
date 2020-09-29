from django.apps import AppConfig
from django.db.models.signals import pre_delete, post_save

from rest_live.signals import ondelete_callback, onsave_callback


class RestLiveConfig(AppConfig):
    name = "rest_live"

    def ready(self):
        post_save.connect(onsave_callback)
        # pre_delete.connect(ondelete_callback)
