"""Report-builder filter catalog and application.

Note: this is the reports package's own module. `dlux.filters` (the django-filter
FilterSet catalog) is a different module — import it as `..filters`."""

from django.db.models import Q
from ..utils import resolve_model_by_name, translate_activity_log_model_name

from .eligibility import get_report_eligible_models, is_report_eligible_activity_model_name
from .queries import _aggregation_queryset, activity_report_key


def _filter_values(filters, plural_key, legacy_key):
    value = filters.get(plural_key)
    if value is None:
        value = filters.get(legacy_key)
    if value is None:
        return None
    if isinstance(value, str):
        value = [value]
    return [str(item).strip() for item in value if str(item or "").strip()]


def _report_filter_catalog(activity_qs, *, strings):
    catalog = {}
    for model in get_report_eligible_models():
        key = model._meta.label_lower
        catalog[key] = {
            "key": key,
            "label": str(model._meta.verbose_name),
            "registered": True,
        }
    rows = (
        _aggregation_queryset(activity_qs)
        .values_list("model_key", "model_name")
        .distinct()
    )
    for model_key, model_name in rows:
        activity_key = activity_report_key(model_key, model_name)
        if not activity_key or not is_report_eligible_activity_model_name(activity_key):
            continue
        resolved_model = resolve_model_by_name(model_name) if not model_key else None
        key = resolved_model._meta.label_lower if resolved_model is not None else activity_key
        entry = catalog.setdefault(key, {"key": key, "registered": False})
        entry["label"] = translate_activity_log_model_name(key, strings=strings)
        entry["model_key"] = model_key or ""
        if not model_key and model_name:
            legacy_names = entry.setdefault("legacy_names", [])
            if model_name not in legacy_names:
                legacy_names.append(model_name)
    models_catalog = sorted(catalog.values(), key=lambda item: item["label"].casefold())
    operation_keys = list(
        _aggregation_queryset(activity_qs)
        .exclude(action="")
        .order_by("action")
        .values_list("action", flat=True)
        .distinct()
    )
    operations_catalog = [
        {
            "key": key,
            "label": strings.get(f"action_{str(key).lower()}", key),
        }
        for key in operation_keys
    ]
    return models_catalog, operations_catalog


def _apply_report_builder_filters(queryset, *, model_catalog, selected_models, selected_operations):
    if selected_models is not None:
        if not selected_models:
            return queryset.none()
        selected = set(selected_models)
        predicate = Q()
        for entry in model_catalog:
            if entry["key"] not in selected:
                continue
            model_key = entry.get("model_key") or (entry["key"] if "." in entry["key"] else "")
            if model_key:
                predicate |= Q(model_key=model_key)
            legacy_names = entry.get("legacy_names") or []
            if legacy_names:
                predicate |= Q(model_key__isnull=True, model_name__in=legacy_names)
                predicate |= Q(model_key="", model_name__in=legacy_names)
        if not predicate:
            return queryset.none()
        queryset = queryset.filter(predicate)
    if selected_operations is not None:
        if not selected_operations:
            return queryset.none()
        queryset = queryset.filter(action__in=selected_operations)
    return queryset
