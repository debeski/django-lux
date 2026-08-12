"""Dlux JSON endpoints served under ``sys/api/``.

Facade over the api package: every name that was importable from the old
`dlux.api` module is re-exported here, so `from dlux import api` and
`api.<view>` in `urls.py` keep working.

Split by what the code guards, not by size:

* :mod:`~dlux.api.introspection` — the generic model reader, where an
  authenticated caller supplies the ``app_label``/``model_name``. The
  permission check, scope narrowing and sensitive-field stripping all live
  there together.
* :mod:`~dlux.api.preferences` — per-user profile writes.
* :mod:`~dlux.api.system_config` — project-wide config writes, superuser only.
* :mod:`~dlux.api.notifications` — the caller's own notifications.
"""

from ._shared import _SAFE_NAMESPACE, logger  # noqa: F401
from .introspection import (  # noqa: F401
    _can_view_model,
    _has_scope_field,
    _is_sensitive_api_field,
    _scope_filter_queryset,
    _serialize_instance,
    _visible_queryset,
    get_last_entry,
    get_model_details,
)
from .notifications import (  # noqa: F401
    notification_dismiss,
    notification_mark_read,
    notifications_clear_all,
    notifications_list,
    notifications_mark_all_read,
)
from .preferences import (  # noqa: F401
    _coerce_prefs_dict,
    _max_preferences_bytes,
    _merge_app_namespace,
    _prefs_within_cap,
    reset_dialog_prompts,
    reset_preferences,
    update_app_preference,
    update_preferences,
)
from .system_config import update_app_system_config  # noqa: F401
