"""dlux.utils.settings — Settings bootstrap, Docker secrets, app version.

Split from the original ``dlux/utils.py`` (kept intact, inert).
"""
import base64
import hashlib
import json
import os
import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import inspect
from pathlib import Path
import unicodedata
from django import forms
from django.apps import apps
from django.conf import settings
from django.contrib.messages import constants as messages
from django.db import models as dj_models
from django.db.models import ManyToManyRel, Q
from django.db.models.fields.files import FieldFile
from django.db.models.fields.related import ManyToManyField
from django.forms import modelform_factory
from django.http import JsonResponse
from django.core.mail import EmailMessage, get_connection, send_mail
from django.core.exceptions import FieldDoesNotExist
from django.utils.module_loading import import_string
from ..system.constants import (
    DEFAULT_HOME_URL,
    DEFAULT_NAVBAR_MODE,
    DEFAULT_SIDEBAR_COLLAPSE_MODE,
    DEFAULT_SIDEBAR_DENSITY,
    DEFAULT_TABLE_DENSITY,
    REGISTRATION_ACTIVATION_AUTO_LOGIN,
    REGISTRATION_ACTIVATION_VALUES,
    NAVBAR_MODE_VALUES,
    SIDEBAR_COLLAPSE_MODE_VALUES,
    SIDEBAR_DENSITY_VALUES,
    TABLE_DENSITY_VALUES,
    TITLEBAR_ALIGN_VALUES,
    TITLEBAR_HEIGHT_VALUES,
    TITLEBAR_HOME_SHAPE_VALUES,
    TITLEBAR_LOGO_TREATMENT_SHAPE_VALUES,
    TITLEBAR_LOGO_TREATMENT_VALUES,
    TITLEBAR_SIZE_VALUES,
    TITLEBAR_SURFACE_VALUES,
)
from ..fonts import DEFAULT_FONT_SLUG, get_builtin_fonts
from ..themes import is_valid_theme, normalize_allowed_themes
from ..translations import get_current_language_code, get_strings
# try-except for django_filters as it might not be installed (though likely is)
try:
    import django_filters
except ImportError:
    django_filters = None

# Settings Bootstrap - Helper normalizes mutable list settings in-place.
def _coerce_list_setting(scope, key):
    value = scope.get(key)
    if value is None:
        value = []
    elif isinstance(value, tuple):
        value = list(value)
    scope[key] = value
    return value


def _env_positive_int(key, default, *, minimum=1):
    try:
        return max(minimum, int(os.getenv(key, str(default)) or default))
    except (TypeError, ValueError):
        return default

# Settings Bootstrap - Helper inserts middleware once at a requested position.
def _insert_middleware_once(middleware, middleware_path, *, after=None, before=None):
    if middleware_path in middleware:
        middleware.remove(middleware_path)

    insert_at = 0
    if before and before in middleware:
        insert_at = middleware.index(before)
    elif after and after in middleware:
        insert_at = middleware.index(after) + 1

    middleware.insert(insert_at, middleware_path)

# Secrets - Function reads Docker secrets with environment fallback.
def get_secret(secret_name, env_var):
    """Read a Docker secret first, then fall back to an environment variable."""
    secret_path = os.path.join("/run/secrets", secret_name)
    try:
        with open(secret_path, "r", encoding="utf-8") as secret_file:
            return secret_file.read().strip()
    except OSError:
        return os.getenv(env_var)

# Settings Bootstrap - Function applies Dlux defaults to a Django settings module.
def dlux_settings(scope):
    """
    Apply the default DjangoLux settings requirements to a Django settings module.

    Intended usage from a host project's settings.py:

        from dlux.utils import dlux_settings
        dlux_settings(globals())
    """
    if not isinstance(scope, dict):
        raise TypeError("dlux_settings() expects the result of globals() from settings.py")

    installed_apps = _coerce_list_setting(scope, "INSTALLED_APPS")
    middleware = _coerce_list_setting(scope, "MIDDLEWARE")
    templates = _coerce_list_setting(scope, "TEMPLATES")

    required_apps = [
        "dlux",
        "crispy_forms",
        "crispy_bootstrap5",
        "django_filters",
        "django_tables2",
    ]
    for app_label in reversed(required_apps):
        if app_label in installed_apps:
            installed_apps.remove(app_label)
        installed_apps.insert(0, app_label)

    auth_middleware = "django.contrib.auth.middleware.AuthenticationMiddleware"
    session_middleware = "django.contrib.sessions.middleware.SessionMiddleware"
    common_middleware = "django.middleware.common.CommonMiddleware"
    locale_middleware = "django.middleware.locale.LocaleMiddleware"
    dlux_middleware = str(
        scope.get("DLUX_MIDDLEWARE", "dlux.middleware.DluxMiddleware")
        or "dlux.middleware.DluxMiddleware"
    ).strip()

    if session_middleware in middleware and common_middleware in middleware:
        session_index = middleware.index(session_middleware)
        common_index = middleware.index(common_middleware)
        if session_index < common_index:
            _insert_middleware_once(
                middleware,
                locale_middleware,
                before=common_middleware,
            )
        else:
            _insert_middleware_once(
                middleware,
                locale_middleware,
                after=session_middleware,
            )
    elif session_middleware in middleware:
        _insert_middleware_once(
            middleware,
            locale_middleware,
            after=session_middleware,
        )
    elif common_middleware in middleware:
        _insert_middleware_once(
            middleware,
            locale_middleware,
            before=common_middleware,
        )
    else:
        _insert_middleware_once(middleware, locale_middleware)

    if auth_middleware in middleware:
        _insert_middleware_once(
            middleware,
            dlux_middleware,
            after=auth_middleware,
        )
    else:
        _insert_middleware_once(middleware, dlux_middleware)

    context_proc = "dlux.context_processors.dlux_context"
    for template in templates:
        if not isinstance(template, dict):
            continue
        options = template.setdefault("OPTIONS", {})
        processors = options.setdefault("context_processors", [])
        if context_proc not in processors:
            processors.append(context_proc)

    scope.setdefault("CRISPY_ALLOWED_TEMPLATE_PACKS", "bootstrap5")
    scope.setdefault("CRISPY_TEMPLATE_PACK", "bootstrap5")
    scope.setdefault("LANGUAGE_CODE", "ar")
    scope.setdefault("TIME_ZONE", os.getenv("TIME_ZONE", "UTC"))
    scope.setdefault("USE_I18N", True)
    scope.setdefault("USE_TZ", True)
    scope.setdefault("DEFAULT_CHARSET", "utf-8")
    scope.setdefault(
        "DLUX_INLINE_UPDATES_ENABLED",
        str(os.getenv("DLUX_INLINE_UPDATES_ENABLED", "False")).strip().lower()
        in {"1", "true", "yes", "on"},
    )
    scope.setdefault(
        "DLUX_UPDATE_CHECK_INTERVAL",
        _env_positive_int("DLUX_UPDATE_CHECK_INTERVAL", 86400, minimum=300),
    )
    scope.setdefault(
        "DLUX_UPDATE_RUNTIME_ROOT",
        os.getenv("DLUX_UPDATE_RUNTIME_ROOT", "/opt/dlux-runtime"),
    )
    beat_schedule = scope.get("CELERY_BEAT_SCHEDULE")
    beat_schedule = dict(beat_schedule) if isinstance(beat_schedule, dict) else {}
    beat_schedule.setdefault(
        "dlux-scheduled-system-backup-check",
        {
            "task": "dlux.tasks.run_scheduled_system_backup",
            "schedule": 900.0,
        },
    )
    # Reliable daily update-check trigger. The task itself is a cheap no-op when
    # updates are disabled or the check is not yet due (it gates on the persisted
    # last_checked_at against DLUX_UPDATE_CHECK_INTERVAL), so an hourly poll only
    # enqueues a real check once the interval has elapsed.
    beat_schedule.setdefault(
        "dlux-update-check",
        {
            "task": "dlux.tasks.dlux_update_check",
            "schedule": 3600.0,
        },
    )
    scope["CELERY_BEAT_SCHEDULE"] = beat_schedule

    message_tags = scope.get("MESSAGE_TAGS")
    if not isinstance(message_tags, dict):
        message_tags = dict(message_tags or {})
    message_tags.setdefault(messages.ERROR, "danger")
    scope["MESSAGE_TAGS"] = message_tags

    format_module_path = scope.get("FORMAT_MODULE_PATH")
    if not format_module_path:
        scope["FORMAT_MODULE_PATH"] = ["dlux.formats"]
    elif isinstance(format_module_path, (list, tuple)):
        merged_format_module_path = list(format_module_path)
        if "dlux.formats" not in merged_format_module_path:
            merged_format_module_path.append("dlux.formats")
        scope["FORMAT_MODULE_PATH"] = merged_format_module_path
    else:
        scope["FORMAT_MODULE_PATH"] = [format_module_path, "dlux.formats"]

    # Register the dlux strong-password validator (a no-op unless the SystemSettings
    # `enforce_strong_passwords` toggle is on) so every set-password path that runs
    # Django's validate_password() honours the runtime setting.
    validators = scope.get("AUTH_PASSWORD_VALIDATORS")
    validators = list(validators) if isinstance(validators, (list, tuple)) else []
    dlux_validator = "dlux.password_validation.DluxStrongPasswordValidator"
    if not any(isinstance(v, dict) and v.get("NAME") == dlux_validator for v in validators):
        validators.append({"NAME": dlux_validator})
    scope["AUTH_PASSWORD_VALIDATORS"] = validators

    return scope

# Versioning - Function reads a package-local VERSION file.
def get_app_version(calling_file_path: str) -> str:
    """
    Reads the VERSION file from the same directory as the calling file.
    Usage: VERSION = get_app_version(__file__)
    """
    try:
        # Resolves the directory of the file that called this function
        app_dir = Path(calling_file_path).resolve().parent
        with open(app_dir / "VERSION", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "unknown"


def get_project_version(base_dir=None) -> str:
    """Read the project version from ``<base_dir>/release-manifest.json``.

    ``base_dir`` defaults to Django's configured ``BASE_DIR`` when available.
    Missing, malformed, or non-object manifests return an empty string.
    """
    if base_dir is None:
        try:
            base_dir = getattr(settings, "BASE_DIR", None)
        except Exception:
            return ""
    if not base_dir:
        return ""

    try:
        manifest = json.loads(
            (Path(base_dir) / "release-manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, TypeError):
        return ""
    if not isinstance(manifest, dict):
        return ""
    return str(manifest.get("version") or "").strip()
