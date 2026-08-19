"""Dlux route discovery and sidebar building.

Facade over the discovery package: every name importable from the old
`dlux.discovery` module is re-exported here.
"""

from .cache import (  # noqa: F401
    SIDEBAR_CACHE_SCHEMA_VERSION,
    SIDEBAR_CACHE_TIMEOUT,
    SIDEBAR_CACHE_VERSION_KEY,
    _route_catalog_cache_key,
    _sidebar_cache_version,
    _sidebar_render_cache_key,
    _stable_hash,
    _urlconf_cache_identity,
    _user_sidebar_permission_hash,
    bump_sidebar_cache_version,
)
from .meta import (  # noqa: F401
    CONFIGURABLE_SYSTEM_ROUTE_NAMES,
    HIDDEN_SIDEBAR_GROUP_KEYS,
    SYSTEM_ROUTE_META,
    _route_leaf,
    _route_name_tokens,
)
from .inference import (  # noqa: F401
    GROUP_ICON_DEFAULTS,
    VIEW_ICON_HINTS,
    _group_label,
    _guess_group_icon,
    _guess_icon,
    _humanize,
    _infer_callback_app_label,
    _infer_group_key,
    _infer_label,
    _infer_model,
    _infer_permissions,
    _normalize_permissions,
    _normalize_sidebar_labels,
    _pick_sidebar_label,
    _plain_text,
)
from .routes import (  # noqa: F401
    _callback_looks_like_api,
    _callback_profile_opt,
    _classify_route,
    _discover_routes_uncached,
    _has_api_route_token,
    _is_api_navigation_route,
    _is_candidate,
    _is_configurable_system_url,
    _iterate_named_patterns,
    _profile_allows,
    _root_urlconf_is_loading,
    discover_routes,
    discover_routes_for,
    discover_sidebar_catalog,
    known_route_names,
)
from .sanitize import (  # noqa: F401
    _clone_sidebar_entry,
    _is_hidden_sidebar_entry,
    _is_hidden_sidebar_url,
    _sanitize_sidebar_entry,
    _sidebar_entry_id,
    _sidebar_entry_route_is_missing,
    sanitize_navbar_config,
    sanitize_sidebar_config,
)
from .merge import (  # noqa: F401
    build_default_sidebar_config,
    merge_sidebar_entries,
)
from .render import (  # noqa: F401
    _apply_sidebar_active_state,
    _is_active_path,
    _iter_render_sidebar_items,
    _normalized_active_path,
    _resolve_group_url,
    _resolve_sidebar_item,
    _user_has_sidebar_permission,
    annotate_sidebar_notification_counts,
    build_sidebar_navigation,
)
from .catalog import (  # noqa: F401
    _BASE_LOG_ACTIONS,
    _is_section_model,
    _model_log_actions,
    build_log_model_catalog,
    build_user_home_url_options,
)

__all__ = [
    'CONFIGURABLE_SYSTEM_ROUTE_NAMES',
    'GROUP_ICON_DEFAULTS',
    'HIDDEN_SIDEBAR_GROUP_KEYS',
    'SIDEBAR_CACHE_SCHEMA_VERSION',
    'SIDEBAR_CACHE_TIMEOUT',
    'SIDEBAR_CACHE_VERSION_KEY',
    'SYSTEM_ROUTE_META',
    'VIEW_ICON_HINTS',
    'annotate_sidebar_notification_counts',
    'build_default_sidebar_config',
    'build_log_model_catalog',
    'build_sidebar_navigation',
    'build_user_home_url_options',
    'bump_sidebar_cache_version',
    'discover_routes',
    'discover_routes_for',
    'discover_sidebar_catalog',
    'known_route_names',
    'merge_sidebar_entries',
    'sanitize_navbar_config',
    'sanitize_sidebar_config',
]
