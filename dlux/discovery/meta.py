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
}


CONFIGURABLE_SYSTEM_ROUTE_NAMES = {
    'manage_sections',
    'manage_users',
    'user_activity_log',
    'options_view',
    'system_backup_page',
}


HIDDEN_SIDEBAR_GROUP_KEYS = {'dlux'}


def _route_name_tokens(value):
    return [token for token in re.split(r'[_:\-]+', (value or '').lower()) if token]


def _route_leaf(url_name):
    return str(url_name or '').split(':')[-1]
