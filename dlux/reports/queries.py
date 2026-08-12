"""Report querysets: scoping, windowing, aggregation and pk-paged iteration."""

from django.apps import apps
from django.conf import settings
from django.db import models
from django.db.models import Count, Q
from ..utils.common import _iter_queryset_by_pk  # re-exported: generic pagination
from ..utils import get_user_scope, is_central_staff, is_global_staff, is_scope_enabled

from ._shared import REPORT_ACTIVITY_CATEGORY
from .config import _reports_config
from .eligibility import is_report_eligible_activity_model_name
from .windows import get_report_window_bounds


def _base_activity_queryset():
    ActivityLog = apps.get_model("dlux", "ActivityLog")
    manager = getattr(ActivityLog, "all_objects", ActivityLog._default_manager)
    qs = manager.filter(deleted_at__isnull=True) if hasattr(ActivityLog, "deleted_at") else manager.all()
    return qs.select_related("created_by", "created_by__profile__scope", "scope")


def apply_report_scope(queryset, actor):
    if not is_scope_enabled():
        return queryset
    if getattr(actor, "is_superuser", False) or is_global_staff(actor):
        return queryset
    if is_central_staff(actor):
        return queryset.filter(scope__isnull=True)
    actor_scope = get_user_scope(actor)
    if actor_scope is not None:
        return queryset.filter(scope=actor_scope)
    return queryset.none()


def apply_report_window(queryset, window, *, now=None, custom_start=None, custom_end=None):
    start, end = get_report_window_bounds(
        window,
        now=now,
        custom_start=custom_start,
        custom_end=custom_end,
    )
    if start is not None:
        queryset = queryset.filter(created_at__gte=start)
    if end is not None:
        queryset = queryset.filter(created_at__lt=end)
    return queryset


def get_visible_report_activity(actor, *, window="all", now=None, custom_start=None, custom_end=None):
    qs = apply_report_scope(_base_activity_queryset(), actor)
    qs = apply_report_window(
        qs,
        window,
        now=now,
        custom_start=custom_start,
        custom_end=custom_end,
    )
    return qs.order_by("-created_at")


def activity_report_key(model_key, model_name):
    """Locale-independent identity for an activity row.

    Prefer the stable ``app_label.model_name`` key; fall back to the (possibly
    translated) display label for legacy rows and non-model events. Grouping and
    eligibility must run on this, never on the raw ``model_name`` label, which
    changes with the active language.
    """
    key = str(model_key or "").strip()
    if key:
        return key
    return str(model_name or "").strip()


def log_report_key(log):
    """``activity_report_key`` for a UserActivityLog instance."""
    return activity_report_key(getattr(log, "model_key", None), getattr(log, "model_name", None))


def filter_report_eligible_activity(queryset):
    queryset = queryset.filter(category=REPORT_ACTIVITY_CATEGORY)
    eligible_keys = set()
    eligible_legacy_names = set()
    identity_rows = queryset.select_related(None).order_by().values_list("model_key", "model_name").distinct()
    for model_key, model_name in identity_rows:
        report_key = activity_report_key(model_key, model_name)
        if not report_key or not is_report_eligible_activity_model_name(report_key):
            continue
        if model_key:
            eligible_keys.add(model_key)
        else:
            eligible_legacy_names.add(model_name)
    if not eligible_keys and not eligible_legacy_names:
        return queryset.none()
    predicate = Q()
    if eligible_keys:
        predicate |= Q(model_key__in=eligible_keys)
    if eligible_legacy_names:
        predicate |= Q(model_key__isnull=True, model_name__in=eligible_legacy_names)
    return queryset.filter(predicate)


def _visible_user_queryset(actor):
    User = apps.get_model(settings.AUTH_USER_MODEL)
    qs = User._default_manager.select_related("profile__scope").order_by("username")
    if getattr(actor, "is_superuser", False) or is_global_staff(actor) or not is_scope_enabled():
        return qs
    if is_central_staff(actor):
        return qs.filter(profile__scope__isnull=True)
    actor_scope = get_user_scope(actor)
    if actor_scope is not None:
        return qs.filter(profile__scope=actor_scope)
    return qs.none()


def _aggregation_queryset(queryset):
    """Strip ordering/joins before grouped count queries."""
    return queryset.select_related(None).order_by()


def _count_grouped(queryset, *fields):
    return (
        _aggregation_queryset(queryset)
        .values(*fields)
        .annotate(count=Count("pk"))
        .order_by("-count")
    )


def _scope_model_queryset(model, actor):
    manager = getattr(model, "all_objects", model._default_manager)
    qs = manager.all()
    if hasattr(model, "deleted_at"):
        qs = qs.filter(deleted_at__isnull=True)
    if not is_scope_enabled():
        return qs
    field_names = {field.name for field in model._meta.get_fields()}
    if "scope" not in field_names:
        return qs
    if getattr(actor, "is_superuser", False) or is_global_staff(actor):
        return qs
    if is_central_staff(actor):
        return qs.filter(scope__isnull=True)
    actor_scope = get_user_scope(actor)
    if actor_scope is not None:
        return qs.filter(scope=actor_scope)
    return qs.none()


_BACKUP_TIMESTAMP_CANDIDATES = ("created_at", "created", "created_on", "date_created", "timestamp")


def _backup_timestamp_field(model):
    """Field used to window-filter a model's rows, or None to include all rows."""
    config_map = _reports_config().get("backup_window_fields", {})
    if isinstance(config_map, dict) and model._meta.label_lower in config_map:
        configured = str(config_map.get(model._meta.label_lower) or "").strip()
        return configured or None
    names = {
        field.name
        for field in model._meta.get_fields()
        if isinstance(field, (models.DateTimeField, models.DateField))
    }
    for candidate in _BACKUP_TIMESTAMP_CANDIDATES:
        if candidate in names:
            return candidate
    return None


def _backup_model_queryset(model, actor, window, *, custom_start=None, custom_end=None):
    qs = _scope_model_queryset(model, actor)
    start, end = get_report_window_bounds(
        window,
        custom_start=custom_start,
        custom_end=custom_end,
    )
    if start is None and end is None:
        return qs
    field = _backup_timestamp_field(model)
    if not field:
        # No timestamp to filter on: include everything rather than silently dropping rows.
        return qs
    if start is not None:
        qs = qs.filter(**{f"{field}__gte": start})
    if end is not None:
        qs = qs.filter(**{f"{field}__lt": end})
    return qs


