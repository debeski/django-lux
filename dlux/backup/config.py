"""Which models a system backup covers, in dependency order."""

from django.apps import apps
from django.conf import settings
from ..system.defaults import default_backup_config
from ..system.normalizers import normalize_backup_config


_SYSTEM_BACKUP_EXCLUDED = {
    "sessions.session",
    "contenttypes.contenttype",
    "auth.permission",
    "admin.logentry",
    "dlux.reportbackup",
    "dlux.systembackup",
    "dlux.systemrestore",
    "dlux.dluxupdatestate",
    "dlux.dluxupdaterun",
}


def _backup_config():
    try:
        from ..utils import get_system_config

        config = get_system_config().get("backup_config", {})
    except Exception:
        config = getattr(settings, "DLUX_CONFIG", {}).get("backup", {})
    return normalize_backup_config(config)


def get_system_backup_storage_prefix():
    """Return the safe folder used for full-system backups in default_storage."""
    return _backup_config().get("auto_export_target") or default_backup_config()["auto_export_target"]


def _config_excluded_keys():
    values = _backup_config().get("exclude_models", [])
    if isinstance(values, str):
        values = [values]
    return {str(v or "").strip().lower() for v in values or [] if str(v or "").strip()}


def _dependency_sorted(models_list):
    """Order models so FK/M2M targets come before their referrers.

    Natural-key references (e.g. Profile.user → User by username) are resolved
    against the database at deserialize time; if the target rows aren't loaded
    yet the deserializer defers the field as NULL, which NOT NULL columns
    reject immediately. INSTALLED_APPS order gives no such guarantee (host
    projects often list dlux before django.contrib.auth), so restores must
    load in dependency order. Cycles are broken at the back-edge — deferrable
    FK constraints cover those at commit.
    """
    included = set(models_list)
    deps = {}
    for model in models_list:
        targets = set()
        for field in model._meta.concrete_fields:
            related = getattr(field, "related_model", None)
            if field.is_relation and related in included and related is not model:
                targets.add(related)
        for field in model._meta.many_to_many:
            related = field.related_model
            if related in included and related is not model:
                targets.add(related)
        deps[model] = targets
    ordered, visiting, visited = [], set(), set()

    def visit(model):
        if model in visited or model in visiting:
            return
        visiting.add(model)
        for target in sorted(deps[model], key=lambda m: m._meta.label_lower):
            visit(target)
        visiting.discard(model)
        visited.add(model)
        ordered.append(model)

    for model in models_list:
        visit(model)
    return ordered


def get_system_backup_models():
    """Every concrete managed model that belongs in a full snapshot, dependency-ordered."""
    excluded = _SYSTEM_BACKUP_EXCLUDED | _config_excluded_keys()
    result = []
    for model in apps.get_models():
        meta = model._meta
        if meta.abstract or meta.proxy or not meta.managed or meta.auto_created:
            continue
        if meta.label_lower in excluded:
            continue
        result.append(model)
    return _dependency_sorted(result)


def _system_model_queryset(model):
    manager = getattr(model, "all_objects", model._base_manager)
    queryset = manager.all()
    if model._meta.label_lower == "dlux.dluxnotification":
        queryset = queryset.exclude(
            category="backup",
            source="backup",
            metadata__backup_progress=True,
        )
    elif model._meta.label_lower == "dlux.dluxnotificationstate":
        queryset = queryset.exclude(
            notification__category="backup",
            notification__source="backup",
            notification__metadata__backup_progress=True,
        )
    return queryset


def _is_user_model(model):
    return model is apps.get_model(settings.AUTH_USER_MODEL)
