"""System checks for ``DLUX_TASK_BACKEND`` and ``DLUX_TASK_SCHEDULE``."""

from django.conf import settings
from django.core.checks import Error, register

from .config import TASK_BACKENDS, configured_task_backend
from .schedules import parse_schedule


@register()
def check_task_backend(app_configs=None, **kwargs):
    problems = []
    value = configured_task_backend()
    if value not in TASK_BACKENDS:
        problems.append(Error(
            f"DLUX_TASK_BACKEND is {value!r}; it must be one of {', '.join(TASK_BACKENDS)}.",
            id="dlux.E101",
        ))
    try:
        parse_schedule(getattr(settings, "DLUX_TASK_SCHEDULE", {}) or {})
    except ValueError as exc:
        problems.append(Error(str(exc), id="dlux.E102"))
    return problems
