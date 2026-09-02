"""Static route metadata and route-name primitives.

Below both `inference` and `routes`: inference reads SYSTEM_ROUTE_META to label a
known system route, and routes reads it while classifying. Keeping it here is
what makes those two modules an acyclic pair."""

import re


SYSTEM_ROUTE_META = {
    'manage_sections': {
        'label_key': 'manage_sections',
        'icon': 'bi-diagram-3',
        'permissions': ['__dlux_sections_view__'],
        'group_key': 'dlux',
    },
    'manage_users': {
        'label_key': 'manage_users',
        'icon': 'bi-people',
        'permissions': ['__dlux_user_directory__'],
        'group_key': 'dlux',
    },
    'user_activity_log': {
        'label_key': 'activity_log',
        'icon': 'bi-clock-history',
        'permissions': ['__dlux_activity_log__'],
        'group_key': 'dlux',
    },
    'user_profile': {
        'label_key': 'profile',
        'icon': 'bi-person-badge',
        'permissions': ['__dlux_authenticated__'],
        'group_key': 'dlux',
    },
    'options_view': {
        'label_key': 'options_title',
        'icon': 'bi-gear',
        'permissions': ['__dlux_authenticated__'],
        'group_key': 'dlux',
    },
    'system_backup_page': {
        'label_key': 'sysbackup_title',
        'icon': 'bi-safe2-fill',
        'permissions': ['is_superuser'],
        'group_key': 'dlux',
        'breadcrumb_parent': 'options_view',
    },
    'reports_overview': {
        'label_key': 'reports_title',
        'icon': 'bi-graph-up-arrow',
        'permissions': ['__dlux_reports__'],
        'group_key': 'dlux',
    },
    'pending_registrations': {
        'label_key': 'pending_registrations',
        'icon': 'bi-person-plus',
        'permissions': ['is_superuser'],
        'group_key': 'dlux',
    },
    'control_panel': {
        'label_key': 'control_link_title',
        'icon': 'bi-hdd-network',
        'permissions': ['is_superuser'],
        'group_key': 'dlux',
    },
    # Described here, deliberately absent from CONFIGURABLE_SYSTEM_ROUTE_NAMES
    # below: these are modal managers, not pages to sit in a sidebar, but a ribbon
    # button can open them. Metadata and configurability are separate questions —
    # `is_system` reads only the list below.
    'manage_groups': {
        'label_key': 'tut_users_groups_title',
        'icon': 'bi-people-fill',
        'permissions': ['is_superuser'],
        'group_key': 'dlux',
    },
    'manage_assets': {
        'label_key': 'asset_manager_title',
        'icon': 'bi-images',
        'permissions': ['is_superuser'],
        'group_key': 'dlux',
    },
    'manage_scopes': {
        'label_key': 'tut_users_scopes_title',
        'icon': 'bi-diagram-2',
        'permissions': ['is_superuser'],
        'group_key': 'dlux',
    },
    # Modal managers. Described only so they read as themselves in a destination
    # picker instead of a humanised route name ("Scanlink Releases Modal").
    'modal_user': {
        'label_key': 'manage_users',
        'icon': 'bi-person-lines-fill',
        'permissions': ['__dlux_user_directory__'],
        'group_key': 'dlux',
    },
    'scanlink_releases_modal': {
        'label_key': 'scanlink_releases_title',
        'icon': 'bi-upc-scan',
        'permissions': ['is_superuser'],
        'group_key': 'dlux',
    },
}


# The dlux-owned pages an admin may place in the sidebar, navbar or a ribbon
# button. Everything else in the hidden `dlux` group is machinery. A name here
# must also carry SYSTEM_ROUTE_META, or it arrives with no label, icon or
# permission and reads as its raw route name.
CONFIGURABLE_SYSTEM_ROUTE_NAMES = {
    'manage_sections',
    'manage_users',
    'user_activity_log',
    'options_view',
    'system_backup_page',
    'user_profile',
    'reports_overview',
    'pending_registrations',
    'control_panel',
}


HIDDEN_SIDEBAR_GROUP_KEYS = {'dlux'}


def _route_name_tokens(value):
    return [token for token in re.split(r'[_:\-]+', (value or '').lower()) if token]


def _route_leaf(url_name):
    return str(url_name or '').split(':')[-1]
