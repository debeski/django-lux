"""Report-builder filter catalog and application.

Note: this is the reports package's own module. `dlux.filters` (the django-filter
FilterSet catalog) is a different module — import it as `..filters`."""

from django.db.models import Q
from ..translations import resolve_model_label

from .eligibility import get_report_eligible_models, is_report_eligible_activity_model_name
from .queries import _aggregation_queryset, activity_report_key, report_model_key, report_model_label


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
    """Models and operations the builder offers.

    One entry per report identity (``report_model_key``): an installed model's
    rows, whatever key or legacy name they were logged under, share its entry and
    its canonical label. ``model_keys``/``legacy_names`` keep the raw values so
    the selection still matches every row.
    """
    catalog = {}
    for model in get_report_eligible_models():
        key = model._meta.label_lower
        catalog[key] = {
            "key": key,
            "label": resolve_model_label(model, strings=strings),
            "registered": True,
            "model_keys": [],
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
        key = report_model_key(model_key, model_name)
        entry = catalog.setdefault(key, {
            "key": key,
            "label": report_model_label(key, strings=strings),
            "registered": False,
            "model_keys": [],
        })
        if model_key:
            if model_key not in entry["model_keys"]:
                entry["model_keys"].append(model_key)
        elif model_name:
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


def report_models_predicate(entries):
    """``Q`` matching every activity row of the given catalog entries."""
    predicate = Q()
    for entry in entries:
        model_keys = set(entry.get("model_keys") or ())
        if "." in entry["key"]:
            model_keys.add(entry["key"])
        if model_keys:
            predicate |= Q(model_key__in=model_keys)
        legacy_names = entry.get("legacy_names") or []
        if legacy_names:
            predicate |= Q(model_key__isnull=True, model_name__in=legacy_names)
            predicate |= Q(model_key="", model_name__in=legacy_names)
    return predicate


def _apply_report_builder_filters(queryset, *, model_catalog, selected_models, selected_operations):
    if selected_models is not None:
        if not selected_models:
            return queryset.none()
        selected = set(selected_models)
        predicate = report_models_predicate(entry for entry in model_catalog if entry["key"] in selected)
        if not predicate:
            return queryset.none()
        queryset = queryset.filter(predicate)
    if selected_operations is not None:
        if not selected_operations:
            return queryset.none()
        queryset = queryset.filter(action__in=selected_operations)
    return queryset
