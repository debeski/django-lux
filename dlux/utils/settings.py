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
from ..constants import (
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
    dlux_middleware = "dlux.middleware.DluxMiddleware"

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
    scope.setdefault("TIME_ZONE", "Etc/GMT-2")
    scope.setdefault("USE_I18N", True)
    scope.setdefault("USE_TZ", True)
    scope.setdefault("DEFAULT_CHARSET", "utf-8")

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
