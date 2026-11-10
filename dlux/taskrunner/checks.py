"""System check for ``DLUX_TASK_SCHEDULE``."""

from django.conf import settings
from django.core.checks import Error, register

from .schedules import parse_schedule


@register()
def check_task_schedule(app_configs=None, **kwargs):
    try:
        parse_schedule(getattr(settings, "DLUX_TASK_SCHEDULE", {}) or {})
    except ValueError as exc:
        return [Error(str(exc), id="dlux.E102")]
    return []
