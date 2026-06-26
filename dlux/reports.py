import io
import json
import logging
import re
import shutil
import tempfile
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from io import BytesIO

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.core.serializers.json import Serializer as JsonSerializer
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import models
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from .translations import get_current_language_code, get_strings
from .utils import (
    get_user_scope,
    is_central_staff,
    is_global_staff,
    is_scope_enabled,
    log_user_action,
    normalize_activity_log_model_key,
    resolve_model_by_name,
    translate_activity_log_model_name,
)


logger = logging.getLogger("dlux")

REPORT_WINDOWS = {"week", "month", "all"}
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
    "dlux_reports_backup",
    "reports_backup",
}

# Verbose names of the high-frequency operational tracking models that are no longer
# logged (see signals.EXCLUDED_MODELS). Historical rows may still exist; use
# exclude_log_noise() to keep them out of activity feeds and reports entirely.
LOG_NOISE_MODEL_NAMES = ("Trusted Device", "Known Device", "Presence Session")


def exclude_log_noise(queryset):
    """Drop operational tracking-model rows (presence/device churn) from a log queryset."""
    return queryset.exclude(model_name__in=LOG_NOISE_MODEL_NAMES)
_EXCLUDED_APP_LABELS = {
    "admin",
    "auth",
    "contenttypes",
    "sessions",
    "messages",
    "staticfiles",
}


def normalize_report_window(value):
    value = str(value or "week").strip().lower()
    return value if value in REPORT_WINDOWS else "week"


def normalize_backup_window(value):
    """Like normalize_report_window but defaults to 'all' (the historical backup scope)."""
    value = str(value or "all").strip().lower()
    return value if value in REPORT_WINDOWS else "all"


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


def is_report_eligible_model(model):
    if model is None:
        return False
    meta = model._meta
    if meta.abstract or not meta.managed:
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
    if normalized and normalized in _DLUX_REPORT_EXCLUDED_KEYS:
        return False
    if normalized in _normalized_config_set("exclude_activity"):
        return False
    if normalized in _normalized_config_set("include_activity"):
        return True
    model = resolve_model_by_name(raw)
    if model is not None:
        return is_report_eligible_model(model)
    return True


def get_report_eligible_models():
    return [model for model in apps.get_models() if is_report_eligible_model(model)]


def _week_start_index():
    value = _reports_config().get("week_start", 0)
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 0
    return value if 0 <= value <= 6 else 0


def get_report_window_bounds(window, *, now=None):
    window = normalize_report_window(window)
    if window == "all":
        return None, None
    now = timezone.localtime(now or timezone.now())
    if window == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, None
    week_start = _week_start_index()
    start_date = now.date() - timedelta(days=(now.weekday() - week_start) % 7)
    start = timezone.make_aware(datetime.combine(start_date, time.min), timezone.get_current_timezone())
    return start, None


def get_previous_week_bounds(*, now=None):
    current_start, _ = get_report_window_bounds("week", now=now)
    previous_start = current_start - timedelta(days=7)
    return previous_start, current_start


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


def apply_report_window(queryset, window, *, now=None):
    start, end = get_report_window_bounds(window, now=now)
    if start is not None:
        queryset = queryset.filter(created_at__gte=start)
    if end is not None:
        queryset = queryset.filter(created_at__lt=end)
    return queryset


def get_visible_report_activity(actor, *, window="all", now=None):
    qs = apply_report_scope(_base_activity_queryset(), actor)
    qs = apply_report_window(qs, window, now=now)
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


def _format_actions(counter, strings):
    return [
        {
            "key": key,
            "label": strings.get(f"action_{str(key or '').lower()}", key or strings.get("user_report_unknown")),
            "count": count,
        }
        for key, count in counter.most_common()
    ]


def _format_model_actions(model_action_map, strings):
    models = []
    for model_key, action_counter in model_action_map.items():
        models.append({
            "key": model_key,
            "label": translate_activity_log_model_name(model_key, strings=strings),
            "count": sum(action_counter.values()),
            "actions": _format_actions(action_counter, strings),
        })
    models.sort(key=lambda item: item["count"], reverse=True)
    return models


def build_activity_windows(activity_qs, *, strings=None):
    strings = strings or get_strings()
    now = timezone.now()
    month_start, _ = get_report_window_bounds("month", now=now)
    week_start, _ = get_report_window_bounds("week", now=now)
    window_action = {"week": Counter(), "month": Counter(), "all": Counter()}
    window_model_action = {
        "week": defaultdict(Counter),
        "month": defaultdict(Counter),
        "all": defaultdict(Counter),
    }
    for action, row_model_key, row_model_name, created_at in activity_qs.values_list(
        "action", "model_key", "model_name", "created_at"
    ):
        report_key = activity_report_key(row_model_key, row_model_name)
        if not is_report_eligible_activity_model_name(report_key):
            continue
        group_key = report_key or strings.get("user_report_unknown")
        for window in ("all",):
            window_action[window][action] += 1
            window_model_action[window][group_key][action] += 1
        if created_at and month_start and created_at >= month_start:
            window_action["month"][action] += 1
            window_model_action["month"][group_key][action] += 1
            if week_start and created_at >= week_start:
                window_action["week"][action] += 1
                window_model_action["week"][group_key][action] += 1
    return {
        window: {
            "activity_count": sum(window_action[window].values()),
            "models": _format_model_actions(window_model_action[window], strings),
            "action_counts": _format_actions(window_action[window], strings),
        }
        for window in ("week", "month", "all")
    }


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


def _overview_cache_scope(actor):
    scope = get_user_scope(actor)
    return {
        "user_id": getattr(actor, "pk", None),
        "scope_enabled": is_scope_enabled(),
        "scope_id": getattr(scope, "pk", None),
        "superuser": bool(getattr(actor, "is_superuser", False)),
        "global": bool(is_global_staff(actor)),
        "central": bool(is_central_staff(actor)),
    }


def _overview_stats_cache_key(actor, window, filters):
    payload = {
        "scope": _overview_cache_scope(actor),
        "window": window,
        "filters": {
            "q": filters.get("q") or "",
            "model": filters.get("model") or "",
            "action": filters.get("action") or "",
        },
        "language": get_current_language_code(),
        "config": repr(_reports_config()),
    }
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    import hashlib
    return "dlux:reports:overview:%s" % hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_cache_get(key):
    try:
        return cache.get(key)
    except Exception:
        logger.warning("Report overview cache read failed", exc_info=True)
        return None


def _safe_cache_set(key, value, timeout):
    try:
        cache.set(key, value, timeout=timeout)
    except Exception:
        logger.warning("Report overview cache write failed", exc_info=True)


def _build_reports_overview_stats(current_qs, previous_qs, all_qs, *, strings):
    unknown = strings.get("user_report_unknown")

    user_counts = Counter()
    for row in _count_grouped(current_qs, "created_by__username"):
        user_counts[row["created_by__username"] or unknown] += row["count"]

    model_counts = Counter()
    for row in _count_grouped(current_qs, "model_key", "model_name"):
        key = activity_report_key(row["model_key"], row["model_name"]) or unknown
        model_counts[key] += row["count"]

    action_counts = Counter()
    for row in _count_grouped(current_qs, "action"):
        action_counts[row["action"] or unknown] += row["count"]

    day_counts = []
    day_rows = (
        _aggregation_queryset(current_qs)
        .annotate(report_day=TruncDate("created_at", tzinfo=timezone.get_current_timezone()))
        .values("report_day")
        .annotate(count=Count("pk"))
        .order_by("-report_day")
    )
    for row in day_rows:
        day = row["report_day"]
        label = day.isoformat() if day else unknown
        day_counts.append({"label": label, "count": row["count"]})

    current_total = sum(user_counts.values())
    active_days = len(day_counts)
    active_users = len(user_counts)
    previous_week_total = previous_qs.count()
    all_total = all_qs.count()

    return {
        "current_total": current_total,
        "previous_week_total": previous_week_total,
        "all_total": all_total,
        "delta": current_total - previous_week_total,
        "average_per_active_day": round(current_total / active_days, 2) if active_days else 0,
        "average_per_user": round(current_total / active_users, 2) if active_users else 0,
        "users": [
            {"label": key, "count": count}
            for key, count in user_counts.most_common()
        ],
        "models": [
            {"key": key, "label": translate_activity_log_model_name(key, strings=strings), "count": count}
            for key, count in model_counts.most_common()
        ],
        "actions": _format_actions(action_counts, strings),
        "days": day_counts,
        "available_models": list(
            _aggregation_queryset(current_qs)
            .order_by("model_name")
            .values_list("model_name", flat=True)
            .distinct()
        ),
        "available_actions": list(
            _aggregation_queryset(current_qs)
            .order_by("action")
            .values_list("action", flat=True)
            .distinct()
        ),
    }


def build_reports_overview(actor, *, window="week", filters=None):
    strings = get_strings()
    window = normalize_report_window(window)
    filters = filters or {}
    current_qs = filter_report_eligible_activity(get_visible_report_activity(actor, window=window))
    previous_start, previous_end = get_previous_week_bounds()
    previous_qs = filter_report_eligible_activity(
        apply_report_scope(_base_activity_queryset(), actor).filter(
            created_at__gte=previous_start,
            created_at__lt=previous_end,
        )
    )
    all_qs = filter_report_eligible_activity(get_visible_report_activity(actor, window="all"))

    keyword = str(filters.get("q") or "").strip()
    if keyword:
        current_qs = current_qs.filter(
            Q(created_by__username__icontains=keyword)
            | Q(created_by__first_name__icontains=keyword)
            | Q(created_by__last_name__icontains=keyword)
            | Q(action__icontains=keyword)
            | Q(model_name__icontains=keyword)
            | Q(number__icontains=keyword)
        )
    model_filter = str(filters.get("model") or "").strip()
    if model_filter:
        current_qs = current_qs.filter(model_name=model_filter)
    action_filter = str(filters.get("action") or "").strip()
    if action_filter:
        current_qs = current_qs.filter(action=action_filter)

    users = _visible_user_queryset(actor)
    stats = None
    cache_seconds = get_reports_overview_cache_seconds()
    if cache_seconds:
        cache_key = _overview_stats_cache_key(
            actor,
            window,
            {"q": keyword, "model": model_filter, "action": action_filter},
        )
        stats = _safe_cache_get(cache_key)
    else:
        cache_key = None
    if stats is None:
        stats = _build_reports_overview_stats(current_qs, previous_qs, all_qs, strings=strings)
        if cache_seconds and cache_key:
            _safe_cache_set(cache_key, stats, cache_seconds)

    return {
        "window": window,
        "filters": {"q": keyword, "model": model_filter, "action": action_filter},
        "current_total": stats["current_total"],
        "previous_week_total": stats["previous_week_total"],
        "all_total": stats["all_total"],
        "delta": stats["delta"],
        "average_per_active_day": stats["average_per_active_day"],
        "average_per_user": stats["average_per_user"],
        "users": stats["users"],
        "models": stats["models"],
        "actions": stats["actions"],
        "days": stats["days"],
        "visible_users": users,
        "recent_activity": list(current_qs[:50]),
        "available_models": stats["available_models"],
        "available_actions": stats["available_actions"],
        "activity_qs": current_qs,
    }


def build_reports_overview_xlsx(overview):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    strings = get_strings()
    wb = Workbook()

    def write_rows(ws, rows):
        for row in rows:
            ws.append(row)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for column in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in column)
            ws.column_dimensions[column[0].column_letter].width = min(max(max_len + 2, 12), 60)

    summary = wb.active
    summary.title = strings.get("reports_sheet_summary", "Summary")[:31]
    write_rows(summary, [
        [strings.get("user_report_field"), strings.get("user_report_value")],
        [strings.get("reports_window"), overview["window"]],
        [strings.get("reports_current_total"), overview["current_total"]],
        [strings.get("reports_previous_week_total"), overview["previous_week_total"]],
        [strings.get("reports_all_total"), overview["all_total"]],
        [strings.get("reports_delta"), overview["delta"]],
        [strings.get("reports_average_per_day"), overview["average_per_active_day"]],
        [strings.get("reports_average_per_user"), overview["average_per_user"]],
    ])

    for sheet_key, title_key, rows in (
        ("users", "reports_by_user", overview["users"]),
        ("models", "reports_by_model", overview["models"]),
        ("actions", "reports_by_action", overview["actions"]),
        ("days", "reports_by_day", overview["days"]),
    ):
        ws = wb.create_sheet(strings.get(title_key, sheet_key.title())[:31])
        write_rows(ws, [[strings.get("user_report_value"), strings.get("user_report_count")]] + [
            [item.get("label") or item.get("key"), item.get("count")] for item in rows
        ])

    logs = wb.create_sheet(strings.get("user_report_sheet_logs", "Logs")[:31])
    log_rows = [[
        strings.get("user_report_timestamp"),
        strings.get("user_report_username"),
        strings.get("user_report_action"),
        strings.get("user_report_model"),
        strings.get("user_report_count"),
    ]]
    for log in overview["activity_qs"][:1000]:
        created_at = timezone.localtime(log.created_at).replace(tzinfo=None) if log.created_at else None
        log_rows.append([
            created_at,
            log.created_by.get_username() if log.created_by else "",
            log.action,
            translate_activity_log_model_name(log.model_name, strings=strings),
            log.number or "",
        ])
    write_rows(logs, log_rows)

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream.getvalue()


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
_BACKUP_LABEL_FIELD_CANDIDATES = (
    "number",
    "document_number",
    "reference_number",
    "registration_number",
    "serial_number",
    "code",
    "name",
    "title",
)


def get_backup_storage_prefix():
    """Storage-relative directory where generated backup zips are kept.

    Lives under the default storage (usually MEDIA_ROOT) so web and worker
    containers can share it; deployments must block direct HTTP access to it
    (e.g. an nginx `deny all` on /media/<prefix>/) — downloads always go
    through the permission-checked Django view.
    """
    prefix = str(_reports_config().get("backup_storage_prefix") or "dlux_backups").strip("/")
    return prefix or "dlux_backups"


def _backup_label_field(model):
    configured = _reports_config().get("backup_label_fields", {})
    field_name = ""
    if isinstance(configured, dict):
        field_name = str(configured.get(model._meta.label_lower) or "").strip()
    candidates = (field_name,) if field_name else _BACKUP_LABEL_FIELD_CANDIDATES
    for candidate in candidates:
        if not candidate:
            continue
        try:
            field = model._meta.get_field(candidate)
        except Exception:
            continue
        if getattr(field, "concrete", False) and not getattr(field, "is_relation", False):
            return field.name
    return ""


def _model_natural_key_fields(model):
    """Best-effort field list composing a model's natural key, or ``[]``.

    System backups serialize foreign keys with ``use_natural_foreign_keys=True``,
    so an FK to a model that defines ``natural_key()`` is stored as that natural
    key (e.g. ``["alice"]``) rather than a PK. Only confidently-derivable cases
    are reported — currently models exposing ``USERNAME_FIELD`` (the auth user) —
    so the viewer can map such references to a label. When this returns ``[]``
    the viewer falls back to displaying the raw natural key, which is itself
    already human-readable.
    """
    if not callable(getattr(model, "natural_key", None)):
        return []
    username_field = getattr(model, "USERNAME_FIELD", None)
    if username_field:
        try:
            model._meta.get_field(username_field)
        except Exception:
            return []
        return [username_field]
    return []


def build_relation_schema(models_list):
    """Per-model relation + label metadata baked into the backup manifest.

    Lets the standalone ``.dlb`` viewer resolve FK/O2O/M2M references to readable
    labels without the originating project. Shape::

        {"app.model": {"label_field": "name",
                       "natural_key_fields": ["username"],   # omitted when empty
                       "relations": {"field": {"kind": "fk|o2o|m2m",
                                               "to": "app.target"}}}}

    Only relations that ``dumpdata`` actually serializes are recorded (concrete
    FK/O2O fields and M2M fields backed by an auto-created through table), keyed
    by the same name the serializer uses in each record's ``fields`` map.
    Defensive: any per-model failure is skipped rather than breaking the backup,
    since this is a viewer convenience, not restore data.
    """
    schema = {}
    for model in models_list:
        try:
            meta = model._meta
            relations = {}
            for field in meta.concrete_fields:
                if not field.is_relation or field.related_model is None:
                    continue
                kind = "o2o" if field.one_to_one else "fk" if field.many_to_one else ""
                if not kind:
                    continue
                relations[field.name] = {
                    "kind": kind,
                    "to": field.related_model._meta.label_lower,
                }
            for field in meta.local_many_to_many:
                if field.related_model is None:
                    continue
                # Only auto-created through tables are serialized by dumpdata.
                if not field.remote_field.through._meta.auto_created:
                    continue
                relations[field.name] = {
                    "kind": "m2m",
                    "to": field.related_model._meta.label_lower,
                }
            label_field = _backup_label_field(model)
            if not label_field:
                # User-like models rarely have a name/title field but read well
                # by their login identifier (e.g. username).
                username_field = getattr(model, "USERNAME_FIELD", None)
                if username_field:
                    try:
                        meta.get_field(username_field)
                        label_field = username_field
                    except Exception:
                        pass
            entry = {
                "label_field": label_field,
                "relations": relations,
            }
            natural_key_fields = _model_natural_key_fields(model)
            if natural_key_fields:
                entry["natural_key_fields"] = natural_key_fields
            schema[meta.label_lower] = entry
        except Exception:
            continue
    return schema


def _safe_archive_segment(value, *, max_length=80):
    value = unicodedata.normalize("NFKC", str(value or "")).strip()
    value = re.sub(r"[\\/\x00-\x1f\x7f]+", "-", value)
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"-+", "-", value).strip(" .-")
    return value[:max_length].rstrip(" .-")


def backup_record_folder(record, *, label_field=None):
    """Human-readable base folder for one report-backup record."""
    field_name = _backup_label_field(record.__class__) if label_field is None else label_field
    label = _safe_archive_segment(getattr(record, field_name, "")) if field_name else ""
    if label:
        field_label = _safe_archive_segment(field_name.replace("_", "-"), max_length=30)
        return f"{field_label}-{label}"
    object_label = _safe_archive_segment(str(record))
    if object_label and object_label != _safe_archive_segment(record.pk, max_length=80):
        return f"record-{object_label}"
    return "record"


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


def _backup_model_queryset(model, actor, window):
    qs = _scope_model_queryset(model, actor)
    start, end = get_report_window_bounds(window)
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


def _iter_queryset_by_pk(qs, chunk_size=200):
    """Yield model rows in bounded primary-key pages without server-side cursors."""
    try:
        chunk_size = int(chunk_size)
    except (TypeError, ValueError):
        chunk_size = 200
    chunk_size = max(1, chunk_size)
    pk_attname = qs.model._meta.pk.attname
    ordered = qs.order_by(pk_attname)
    last_pk = None
    while True:
        page = ordered
        if last_pk is not None:
            page = page.filter(**{f"{pk_attname}__gt": last_pk})
        batch = list(page[:chunk_size])
        if not batch:
            break
        for obj in batch:
            yield obj
        last_pk = getattr(batch[-1], pk_attname)


class _CursorlessJSONSerializer(JsonSerializer):
    """Backup serializer variant that avoids QuerySet.iterator() entirely."""

    def handle_m2m_field(self, obj, field):
        if not field.remote_field.through._meta.auto_created:
            return
        related = getattr(obj, field.name)
        if self.use_natural_foreign_keys and hasattr(
            field.remote_field.model, "natural_key"
        ):
            self._current[field.name] = [value.natural_key() for value in related.all()]
            return
        related_qs = related.select_related(None).only("pk")
        self._current[field.name] = [
            self._value_from_field(value, value._meta.pk)
            for value in related_qs
        ]


def stream_model_into_zip(
    zf,
    model,
    qs,
    manifest,
    *,
    serialize_kwargs=None,
    object_transform=None,
    human_record_folders=False,
    include_files=True,
):
    """Stream one model's records (JSON) and its file-field contents into an
    open backup ZipFile, recording everything in ``manifest``.

    Shared by the reports backup and the full system backup: the serializer
    writes straight into the zip entry and storage files are chunk-copied, so
    peak memory stays flat no matter how many records/PDFs are covered.

    ``include_files=False`` produces a data-only export: record JSON is still
    written (FileField *names* are preserved in the data), but the referenced
    media blobs are not copied into the archive. A restore then leaves existing
    media on disk untouched (``_restore_files`` only touches files the manifest
    lists). This is what the inline updater's pre-update backup uses so a quick
    code/schema update is not gated on copying gigabytes of unchanged uploads.
    """
    meta = model._meta
    model_key = meta.label_lower
    manifest["models"].append({"model": model_key, "count": qs.count()})
    def serialized_objects():
        for obj in _iter_queryset_by_pk(qs, chunk_size=200):
            yield object_transform(obj) if object_transform else obj

    with zf.open(f"data/{meta.app_label}/{meta.model_name}.json", mode="w") as raw_stream:
        text_stream = io.TextIOWrapper(raw_stream, encoding="utf-8")
        serializer = _CursorlessJSONSerializer()
        serializer.serialize(
            serialized_objects(),
            stream=text_stream,
            **(serialize_kwargs or {}),
        )
        text_stream.flush()
        text_stream.detach()
    if not include_files:
        return
    file_fields = [
        field for field in meta.get_fields()
        if isinstance(field, (models.FileField, models.ImageField))
    ]
    if not file_fields:
        return
    record_label_field = _backup_label_field(model) if human_record_folders else ""
    folder_counts = {}
    for record in _iter_queryset_by_pk(qs, chunk_size=100):
        if human_record_folders:
            base_folder = backup_record_folder(record, label_field=record_label_field)
            folder_counts[base_folder] = folder_counts.get(base_folder, 0) + 1
            occurrence = folder_counts[base_folder]
            record_folder = base_folder if occurrence == 1 else f"{base_folder}--{occurrence}"
        else:
            record_folder = str(record.pk)
        for field in file_fields:
            file_value = getattr(record, field.name, None)
            if not file_value or not getattr(file_value, "name", ""):
                continue
            archive_name = f"files/{meta.app_label}/{meta.model_name}/{record_folder}/{field.name}/{file_value.name.split('/')[-1]}"
            try:
                with default_storage.open(file_value.name, "rb") as fh, \
                        zf.open(archive_name, mode="w") as dest:
                    shutil.copyfileobj(fh, dest, 256 * 1024)
                manifest["files"].append({
                    "model": model_key,
                    "pk": record.pk,
                    "record_folder": record_folder,
                    "record_label_field": record_label_field,
                    "field": field.name,
                    "path": archive_name,
                    # Original storage name — what a restore writes the file back as.
                    "name": file_value.name,
                })
            except Exception:
                manifest["missing_files"].append({
                    "model": model_key,
                    "pk": record.pk,
                    "field": field.name,
                    "name": file_value.name,
                })


def write_backup_zip(actor, fileobj, *, window="all", progress_callback=None):
    """Stream a scope-aware, window-filtered backup zip into ``fileobj``."""
    window = normalize_backup_window(window)
    manifest = {
        "generated_at": timezone.now().isoformat(),
        "window": window,
        "models": [],
        "files": [],
        "missing_files": [],
    }
    models_to_export = get_report_eligible_models()
    total_models = max(len(models_to_export), 1)
    strings = get_strings()
    with zipfile.ZipFile(fileobj, "w", zipfile.ZIP_DEFLATED) as zf:
        for index, model in enumerate(models_to_export):
            if progress_callback:
                progress_callback(
                    5 + int((index / total_models) * 85),
                    strings.get("backup_progress_model", "Backing up {model}...").format(
                        model=str(model._meta.verbose_name),
                    ),
                )
            qs = _backup_model_queryset(model, actor, window)
            stream_model_into_zip(
                zf,
                model,
                qs,
                manifest,
                human_record_folders=True,
            )
            if progress_callback:
                progress_callback(
                    5 + int(((index + 1) / total_models) * 85),
                    strings.get("backup_progress_model_done", "Backed up {model}.").format(
                        model=str(model._meta.verbose_name),
                    ),
                )
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


def build_backup_zip(request, window="all"):
    """In-memory backup build kept for backward compatibility (small datasets only)."""
    buffer = BytesIO()
    manifest = write_backup_zip(request.user, buffer, window=window)
    buffer.seek(0)
    log_user_action(
        request,
        "EXPORT",
        model_name="Dlux Reports Backup",
        details={
            "window": manifest["window"],
            "models": len(manifest["models"]),
            "files": len(manifest["files"]),
        },
    )
    return buffer.getvalue(), manifest


# ── Background backup runs (Celery when available, synchronous fallback) ────


def _report_backup_model():
    return apps.get_model("dlux", "ReportBackup")


def report_backup_celery_available():
    """True when the backup task can actually run in the background right now:
    celery importable, broker reachable, and at least one live worker."""
    if not _reports_config().get("backup_use_celery", True):
        return False
    try:
        from .tasks import build_report_backup_task
    except Exception:
        return False
    if build_report_backup_task is None:
        return False
    try:
        app = build_report_backup_task.app
        with app.connection_for_write() as conn:
            conn.ensure_connection(max_retries=0, timeout=2)
        return bool(app.control.ping(timeout=1.0))
    except Exception:
        return False


def dispatch_report_backup(backup):
    """Queue the backup build on Celery. Returns True when queued."""
    if not report_backup_celery_available():
        return False
    from .tasks import build_report_backup_task
    try:
        build_report_backup_task.apply_async(args=[backup.pk], retry=False)
        return True
    except Exception:
        logger.exception("Failed to queue report backup pk=%s", backup.pk)
        return False


def _prune_report_backups(user, keep=3):
    ReportBackup = _report_backup_model()
    stale = list(
        ReportBackup.objects.filter(user=user, status=ReportBackup.STATUS_COMPLETED)
        .order_by("-created_at")[keep:]
    ) + list(
        ReportBackup.objects.filter(
            user=user,
            status=ReportBackup.STATUS_FAILED,
            created_at__lt=timezone.now() - timedelta(days=7),
        )
    )
    for old in stale:
        if old.file_path:
            try:
                default_storage.delete(old.file_path)
            except Exception:
                pass
        old.delete()


def run_report_backup(backup_pk):
    """Build the zip for a ReportBackup row and store it under the backup prefix.

    Runs inside the Celery worker (or inline as a last resort). Status/result
    are persisted on the row so the web process can poll over the shared DB.
    """
    ReportBackup = _report_backup_model()
    backup = ReportBackup.objects.filter(pk=backup_pk).first()
    if backup is None or backup.status not in (ReportBackup.STATUS_PENDING,):
        return backup
    logger.info(
        "Starting report backup pk=%s token=%s window=%s user_id=%s",
        backup.pk,
        backup.token,
        backup.window,
        backup.user_id,
    )
    backup.status = ReportBackup.STATUS_RUNNING
    backup.started_at = timezone.now()
    backup.save(update_fields=["status", "started_at"])
    from .backup_progress import finish_backup_progress, set_backup_progress, start_backup_progress
    start_backup_progress(backup)
    set_backup_progress(backup, 2, get_strings().get("backup_progress_preparing", "Preparing backup..."))
    try:
        with tempfile.TemporaryFile() as tmp:
            manifest = write_backup_zip(
                backup.user,
                tmp,
                window=backup.window,
                progress_callback=lambda percent, message: set_backup_progress(backup, percent, message),
            )
            size = tmp.tell()
            tmp.seek(0)
            set_backup_progress(backup, 95, get_strings().get("backup_progress_storing", "Storing backup artifact..."))
            saved_path = default_storage.save(
                f"{get_backup_storage_prefix()}/{backup.token}.zip",
                File(tmp),
            )
        backup.file_path = saved_path
        backup.file_size = size
        backup.model_count = len(manifest["models"])
        backup.file_count = len(manifest["files"])
        backup.missing_file_count = len(manifest["missing_files"])
        backup.status = ReportBackup.STATUS_COMPLETED
        backup.completed_at = timezone.now()
        backup.error = ""
        backup.save()
        finish_backup_progress(backup, success=True)
        logger.info(
            "Completed report backup pk=%s token=%s size=%s models=%s files=%s missing=%s",
            backup.pk,
            backup.token,
            backup.file_size,
            backup.model_count,
            backup.file_count,
            backup.missing_file_count,
        )
        UserActivityLog = apps.get_model("dlux", "ActivityLog")
        UserActivityLog.safe_log(
            user=backup.user,
            action="EXPORT",
            model_name="Dlux Reports Backup",
            details={
                "window": backup.window,
                "models": backup.model_count,
                "files": backup.file_count,
            },
        )
        _prune_report_backups(backup.user)
    except Exception as exc:
        logger.exception("Report backup pk=%s failed", backup_pk)
        backup.status = ReportBackup.STATUS_FAILED
        backup.completed_at = timezone.now()
        backup.error = str(exc)[:1000]
        backup.save(update_fields=["status", "completed_at", "error"])
        finish_backup_progress(backup, success=False, error=backup.error)
    return backup
