import json
from pathlib import Path


# Single source of truth for the DjangoLux version: the release manifest. The
# manifest already ships inside the wheel (remote updaters read it to verify a
# downloaded release), so sourcing the version from it keeps the package version,
# the updater's compatibility checks, and the release tag in lockstep from one file.
_MANIFEST_FILE = Path(__file__).with_name("release-manifest.json")


def get_version():
    return str(json.loads(_MANIFEST_FILE.read_text(encoding="utf-8"))["version"]).strip()


__version__ = get_version()


def log_activity(action, target=None, *, model=None, details=None, number=None, category=None):
    """Zero-boilerplate activity logging for deployed projects.

    Example::

        from dlux import log_activity
        log_activity("APPROVE", obj)          # instance form
        log_activity("EXPORT", pk, model="documents.decree")  # pk + model form

    ``target`` is a model instance (model_key/name/pk resolved automatically) or a primary
    key (pass ``model`` as a class or "app_label.model" string). The actor, scope, IP and
    user-agent are resolved from the current request. ``category`` defaults to ``'user'``
    (dev-invoked work); the call honours the ``log_config`` per-model/per-action gating, so
    the action surfaces as a toggle in System Settings once seen. Returns the created
    ``ActivityLog`` row, or ``None`` if logging is disabled for that model/action.
    """
    from django.apps import apps
    from .middleware import get_current_request
    from .utils.activity_log import (
        get_active_log_config,
        is_model_logging_enabled,
        log_user_action,
    )

    instance = None
    object_id = None
    model_name = None
    model_key = None

    if target is not None and hasattr(target, '_meta'):
        instance = target
        model_key = target._meta.label_lower
    else:
        object_id = target
        resolved = model
        if isinstance(resolved, str):
            try:
                resolved = apps.get_model(resolved)
            except Exception:
                resolved = None
        if resolved is not None and hasattr(resolved, '_meta'):
            model_name = str(resolved._meta.verbose_name)
            model_key = resolved._meta.label_lower

    resolved_category = category or 'user'
    if model_key:
        if not is_model_logging_enabled(resolved_category, model_key, str(action), get_active_log_config()):
            return None

    return log_user_action(
        get_current_request(), str(action),
        instance=instance, model_name=model_name, model_key=model_key,
        object_id=object_id, details=details, number=number,
        category=resolved_category,
    )
