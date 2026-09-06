"""dlux.utils.settings — Settings bootstrap, Docker secrets, app version.

Split from the original ``dlux/utils.py`` (kept intact, inert).
"""
import base64
import hashlib
import json
import os
import re
import sys
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
from django.core.exceptions import ImproperlyConfigured
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


def _is_test_process():
    argv = [str(value).strip().lower() for value in sys.argv]
    executable = Path(argv[0]).name if argv else ""
    return "test" in argv[1:] or executable.startswith(("pytest", "py.test"))

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

def scanlink_enabled():
    """Is the ScanLink desktop helper integration turned on for this deployment?

    Off unless asked for. ScanLink talks to a tray app on the operator's own
    machine over ``localhost:5443``/``:5000``; on every deployment without that
    app installed the probe is a connection the browser refuses and logs, and no
    ``catch`` in our code can suppress that log. So the whole integration —
    scripts and buttons alike — is opt-in, and a deployment that never enables it
    ships no ScanLink code to the page at all.

    Stored in ``SystemSettings.extra_config['scanlink']['enabled']`` and edited
    from the Extra Features settings step, like every other dlux system setting.
    """
    from .config import get_system_config

    extra = get_system_config().get("extra_config") or {}
    scanlink = extra.get("scanlink") if isinstance(extra, dict) else None
    if not isinstance(scanlink, dict):
        return False
    return bool(scanlink.get("enabled", False))

#: Keys that mean "nobody set one". Signing sessions and password-reset tokens
#: with any of these makes them forgeable, and swapping between two of them logs
#: every user out — which is how an unset key usually announces itself.
PLACEHOLDER_SECRET_KEYS = frozenset({
    "local_secret",
    "changeme",
    "secret",
    "insecure-temporary-dev-only-key-change-me-now",
})


def _reject_placeholder_secret_key(scope):
    """Refuse to boot a non-DEBUG deployment on a placeholder ``SECRET_KEY``.

    Both scaffold layers fall back silently — compose to ``local_secret``,
    settings to its own dev key — so a restart that loses the secrets file comes
    up signing with a different key than the one that signed the live session
    cookies. Every user is logged out, and nothing is logged to say why.

    Only a settings module that actually defines ``SECRET_KEY`` is judged. A
    scope without one is a programmatic caller, not a deployment, and Django
    raises its own error the moment the setting is read.

    Set ``DLUX_ALLOW_INSECURE_SECRET_KEY = True`` to opt out (CI, throwaway
    stacks); DEBUG deployments are never affected.
    """
    if "SECRET_KEY" not in scope:
        return
    if scope.get("DEBUG", False) or scope.get("DLUX_ALLOW_INSECURE_SECRET_KEY", False):
        return
    key = str(scope.get("SECRET_KEY") or "").strip()
    if key and key not in PLACEHOLDER_SECRET_KEYS:
        return
    detail = "is empty" if not key else "is a placeholder"
    raise ImproperlyConfigured(
        f"SECRET_KEY {detail}, so every session cookie and password-reset token "
        "signed by this deployment is forgeable, and the next restart that "
        "resolves a different key will sign every user out. Set "
        "DJANGO_SECRET_KEY in .secrets/.env (50+ random characters). Set "
        "DLUX_ALLOW_INSECURE_SECRET_KEY = True to allow it anyway."
    )


def dlux_settings(scope):
    """
    Apply the default DjangoLux settings requirements to a Django settings module.

    Intended usage from a host project's settings.py:

        from dlux.utils import dlux_settings
        dlux_settings(globals())
    """
    if not isinstance(scope, dict):
        raise TypeError("dlux_settings() expects the result of globals() from settings.py")

    _reject_placeholder_secret_key(scope)

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
    scope.setdefault("DLUX_ISOLATE_TEST_CACHE", True)
    if scope["DLUX_ISOLATE_TEST_CACHE"] and _is_test_process():
        scope["CACHES"] = {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": f"dlux-test-cache-{os.getpid()}",
            }
        }
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
    # The DjangoLux write-side loop. Since 1.8.0 Composer executes updates, so
    # what remains is writing small JSON state files — this replaced the
    # dedicated `dlux-updater` service's worker loop. Short interval because the
    # update panel reflects the transitions it publishes; the task is a cheap
    # no-op when there is nothing queued.
    beat_schedule.setdefault(
        "dlux-state-tick",
        {
            "task": "dlux.tasks.dlux_state_tick",
            "schedule": 5.0,
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
    dlux_validator = "dlux.auth.password_validation.DluxStrongPasswordValidator"
    # The module moved to dlux.auth in 1.8.0 and the old path was NOT kept as an
    # alias, so rewriting a hand-pinned legacy entry is the only thing standing
    # between such a project and an unresolvable validator at startup. It also
    # avoids appending the new path beside the old one, which would run the
    # validator twice and duplicate its messages.
    legacy_validator = "dlux.password_validation.DluxStrongPasswordValidator"
    validators = [
        {**v, "NAME": dlux_validator}
        if isinstance(v, dict) and v.get("NAME") == legacy_validator else v
        for v in validators
    ]
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
