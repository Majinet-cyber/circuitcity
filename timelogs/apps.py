# timelogs/apps.py
from django.apps import AppConfig


class TimelogsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "timelogs"
    verbose_name = "Time Logs"

