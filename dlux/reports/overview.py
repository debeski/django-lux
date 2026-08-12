"""The reports overview page: stats, cached aggregates and activity windows."""

import json
from collections import Counter, defaultdict
from django.core.cache import cache
from django.db import models
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from ..translations import get_current_language_code, get_strings
from ..utils import (
    get_user_scope,
    is_central_staff,
    is_global_staff,
    is_scope_enabled,
    translate_activity_log_model_name,
)

from ._shared import logger
from .config import _reports_config, get_reports_overview_cache_seconds
from .eligibility import is_report_eligible_activity_model_name
from .filters import _apply_report_builder_filters, _filter_values, _report_filter_catalog
from .queries import _aggregation_queryset, _base_activity_queryset, _count_grouped, _visible_user_queryset, activity_report_key, apply_report_scope, apply_report_window, filter_report_eligible_activity
from .windows import _report_period_details, get_previous_period_bounds, get_report_window_bounds, normalize_report_window


REPORT_OVERVIEW_CACHE_SCHEMA_VERSION = 2


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
        "schema": REPORT_OVERVIEW_CACHE_SCHEMA_VERSION,
        "scope": _overview_cache_scope(actor),
        "window": window,
        "filters": {
            "q": filters.get("q") or "",
            "custom_start": filters.get("custom_start") or "",
            "custom_end": filters.get("custom_end") or "",
            "models": sorted(filters.get("models") or []),
            "operations": sorted(filters.get("operations") or []),
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
    previous_period_total = previous_qs.count() if previous_qs is not None else 0
    all_total = all_qs.count()

    return {
        "current_total": current_total,
        "previous_period_total": previous_period_total,
        "previous_week_total": previous_period_total,
        "all_total": all_total,
        "delta": current_total - previous_period_total,
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
    }


def build_reports_overview(actor, *, window="week", filters=None, now=None):
    strings = get_strings()
    window = normalize_report_window(window)
    filters = filters or {}
    now = now or timezone.now()
    period = _report_period_details(
        window,
        filters.get("custom_start"),
        filters.get("custom_end"),
        now=now,
    )
    base_qs = filter_report_eligible_activity(
        apply_report_scope(_base_activity_queryset(), actor)
    )
    model_catalog, operation_catalog = _report_filter_catalog(base_qs, strings=strings)
    model_keys = {item["key"] for item in model_catalog}
    operation_keys = {item["key"] for item in operation_catalog}
    requested_models = _filter_values(filters, "models", "model")
    requested_operations = _filter_values(filters, "operations", "action")
    explicit_builder = str(filters.get("builder") or "") == "1"
    if requested_models is None and not explicit_builder:
        selected_models = sorted(model_keys)
    else:
        selected_models = [key for key in (requested_models or []) if key in model_keys]
    if requested_operations is None and not explicit_builder:
        selected_operations = sorted(operation_keys)
    else:
        selected_operations = [key for key in (requested_operations or []) if key in operation_keys]

    filtered_qs = _apply_report_builder_filters(
        base_qs,
        model_catalog=model_catalog,
        selected_models=selected_models,
        selected_operations=selected_operations,
    )

    keyword = str(filters.get("q") or "").strip()
    if keyword:
        filtered_qs = filtered_qs.filter(
            Q(created_by__username__icontains=keyword)
            | Q(created_by__first_name__icontains=keyword)
            | Q(created_by__last_name__icontains=keyword)
            | Q(action__icontains=keyword)
            | Q(model_name__icontains=keyword)
            | Q(number__icontains=keyword)
        )
    all_qs = filtered_qs
    current_qs = apply_report_window(
        filtered_qs,
        window,
        now=now,
        custom_start=period["custom_start"],
        custom_end=period["custom_end"],
    ).order_by("-created_at")
    previous_start, previous_end = get_previous_period_bounds(
        window,
        now=now,
        custom_start=period["custom_start"],
        custom_end=period["custom_end"],
    )
    previous_qs = None
    if previous_start is not None:
        previous_qs = filtered_qs.filter(
            created_at__gte=previous_start,
            created_at__lt=previous_end,
        )

    users = _visible_user_queryset(actor)
    stats = None
    cache_seconds = get_reports_overview_cache_seconds()
    if cache_seconds:
        cache_key = _overview_stats_cache_key(
            actor,
            window,
            {
                "q": keyword,
                "custom_start": period["custom_start"],
                "custom_end": period["custom_end"],
                "models": selected_models,
                "operations": selected_operations,
            },
        )
        stats = _safe_cache_get(cache_key)
    else:
        cache_key = None
    if stats is None:
        stats = _build_reports_overview_stats(current_qs, previous_qs, all_qs, strings=strings)
        if cache_seconds and cache_key:
            _safe_cache_set(cache_key, stats, cache_seconds)

    criteria = {
        "window": window,
        "q": keyword,
        "custom_start": period["custom_start"],
        "custom_end": period["custom_end"],
        "models": selected_models,
        "operations": selected_operations,
        "builder": "1",
    }
    selected_model_set = set(selected_models)
    selected_operation_set = set(selected_operations)
    for item in model_catalog:
        item["selected"] = item["key"] in selected_model_set
    for item in operation_catalog:
        item["selected"] = item["key"] in selected_operation_set
    return {
        "window": window,
        "filters": criteria,
        "criteria": criteria,
        "period": period,
        "current_total": stats["current_total"],
        "previous_period_total": stats["previous_period_total"],
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
        "available_models": model_catalog,
        "available_actions": operation_catalog,
        "selected_model_count": len(selected_models),
        "selected_operation_count": len(selected_operations),
        "activity_qs": current_qs,
    }
