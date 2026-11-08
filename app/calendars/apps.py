from django.apps import AppConfig


class CalendarsConfig(AppConfig):
    name = "calendars"
    verbose_name = "Google Calendar sync"

    def ready(self):
        from . import signals  # noqa: F401
