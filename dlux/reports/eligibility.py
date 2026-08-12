"""Which models and activity rows may appear in a report."""

from django.apps import apps
from ..utils import normalize_activity_log_model_key, resolve_model_by_name

from .config import _normalized_config_set


_DLUX_REPORT_EXCLUDED_KEYS = {
    "auth",
    "authentication",
    "session",
    "sessions",
    "systemsettings",
    "system_settings",
    "scope",
    "scopesettings",
    "scope_settings",
    "profile",
    "user_profile",
    "trusteddevice",
    "trusted_device",
    "userknowndevice",
    "known_device",
    "known_devices",
    "userpresencesession",
    "presence_session",
    "presence_sessions",
    "publicregistration",
    "public_registration",
    "preferences",
    "password",
    "totp",
    "otp",
    "backup_code",
    "backup_codes",
    # Dlux-internal meta actions (not project work; classified as system interactions)
    "dlux_system_backup",
    "dlux_system_restore",
    "dlux_reports_backup",
    "reports_backup",
}


_EXCLUDED_APP_LABELS = {
    "admin",
    "auth",
    "contenttypes",
    "sessions",
    "messages",
    "staticfiles",
}


_CELERY_REPORT_APP_LABELS = {
    "celery",
    "djcelery",
    "django_celery_beat",
    "django_celery_results",
}


_CELERY_REPORT_MODEL_KEYS = {
    "task_result",
    "taskresult",
    "group_result",
    "groupresult",
    "chord_counter",
    "chordcounter",
    "periodic_task",
    "periodictask",
    "periodic_tasks",
    "periodictasks",
    "crontab_schedule",
    "crontabschedule",
    "interval_schedule",
    "intervalschedule",
    "solar_schedule",
    "solarschedule",
    "clocked_schedule",
    "clockedschedule",
    "task_meta",
    "taskmeta",
    "task_set_meta",
    "tasksetmeta",
}


def _model_keys(model):
    meta = model._meta
    values = {
        meta.label_lower,
        f"{meta.app_label}.{meta.model_name}",
        meta.model_name,
        meta.object_name,
        str(meta.verbose_name),
        str(meta.verbose_name_plural),
    }
    return {normalize_activity_log_model_key(value) for value in values if str(value or "").strip()}


def _model_is_section(model):
    marker = getattr(model, "is_section", None)
    if isinstance(marker, bool):
        return marker
    if marker is not None:
        return True
    return bool(getattr(model._meta, "is_section", False))


def _is_celery_report_identity(value):
    normalized = normalize_activity_log_model_key(value)
    return (
        normalized in _CELERY_REPORT_MODEL_KEYS
        or normalized.startswith("django_celery_beat_")
        or normalized.startswith("django_celery_results_")
        or normalized.startswith("djcelery_")
        or normalized.startswith("celery_")
    )


def _is_celery_report_model(model):
    app_label = str(model._meta.app_label or "").lower()
    return app_label in _CELERY_REPORT_APP_LABELS or app_label.startswith("django_celery_")


def is_report_eligible_model(model):
    if model is None:
        return False
    meta = model._meta
    if (
        meta.abstract
        or not meta.managed
        or getattr(meta, "auto_created", False)
        or getattr(meta, "proxy", False)
        or getattr(meta, "swapped", False)
    ):
        return False
    if _is_celery_report_model(model):
        return False
    if getattr(model, "dlux_report", None) is False:
        return False
    keys = _model_keys(model)
    if keys & _normalized_config_set("exclude_models"):
        return False
    if keys & _normalized_config_set("include_models"):
        return True
    if meta.app_label in _EXCLUDED_APP_LABELS:
        return False
    if meta.app_label == "dlux":
        return _model_is_section(model)
    return True


def is_report_eligible_activity_model_name(model_name):
    raw = str(model_name or "").strip()
    if not raw:
        return False
    # Non-ASCII verbose names (e.g. translated/Arabic model labels stored by the
    # activity logger) normalize to an empty key. Don't reject them outright — the
    # key-based checks below simply won't match, and eligibility falls through to
    # model resolution so the decision is made on the underlying model instead of
    # on whether its label happens to be ASCII.
    normalized = normalize_activity_log_model_key(raw)
    if _is_celery_report_identity(raw):
        return False
    if normalized and normalized in _DLUX_REPORT_EXCLUDED_KEYS:
        return False
    model = resolve_model_by_name(raw)
    if model is not None and not is_report_eligible_model(model):
        return False
    if normalized in _normalized_config_set("exclude_activity"):
        return False
    if normalized in _normalized_config_set("include_activity"):
        return True
    if model is not None:
        return True
    return True


def get_report_eligible_models():
    return [model for model in apps.get_models() if is_report_eligible_model(model)]
