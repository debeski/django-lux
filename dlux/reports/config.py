"""Report configuration reads and derived limits."""

from django.conf import settings
from ..utils import normalize_activity_log_model_key


REPORT_ENTRIES_ROW_LIMIT = 20000


LOG_NOISE_MODEL_NAMES = ("Trusted Device", "Known Device", "Presence Session")


def exclude_log_noise(queryset):
    """Drop operational tracking-model rows (presence/device churn) from a log queryset."""
    return queryset.exclude(model_name__in=LOG_NOISE_MODEL_NAMES)


def _reports_config():
    config = getattr(settings, "DLUX_CONFIG", {}).get("reports", {})
    return config if isinstance(config, dict) else {}


def get_reports_overview_cache_seconds():
    """Optional read-through cache TTL for the expensive report overview stats.

    Defaults to 0 to keep the overview exact out of the box. Deployments with a
    shared Django cache/Redis can set DLUX_CONFIG['reports']['overview_cache_seconds']
    to a small value to absorb repeated dashboard loads.
    """
    try:
        value = int(_reports_config().get("overview_cache_seconds", 0))
    except (TypeError, ValueError):
        value = 0
    return max(0, min(value, 3600))


def _normalized_config_set(key):
    values = _reports_config().get(key, [])
    if isinstance(values, str):
        values = [values]
    return {normalize_activity_log_model_key(value) for value in values or [] if str(value or "").strip()}


def get_report_entries_row_limit():
    """Per-model row cap for the XLSX entry export.

    Bounds worst-case workbook size/memory on a project with very large tables.
    Override with DLUX_CONFIG['reports']['entries_row_limit'].
    """
    try:
        value = int(_reports_config().get("entries_row_limit", REPORT_ENTRIES_ROW_LIMIT))
    except (TypeError, ValueError):
        value = REPORT_ENTRIES_ROW_LIMIT
    return max(1, min(value, 1000000))
