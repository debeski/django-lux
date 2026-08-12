"""dlux.utils.navigation — Sidebar and navbar configuration + sidebar runtime toggle.

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

# ── intra-package imports (shared + feature deps) ──
from ..system.defaults import (
    default_navbar_config as _system_default_navbar_config,
    default_sidebar_config as _system_default_sidebar_config,
)
from ..system.normalizers import (
    normalize_navbar_config as _system_normalize_navbar_config,
    normalize_sidebar_behavior as _system_normalize_sidebar_behavior,
    normalize_sidebar_toggle_icon as _system_normalize_sidebar_toggle_icon,
)
from .localization import _normalize_language_code

# Sidebar Config - Helper removes duplicate sidebar entries by route key.
def _dedupe_sidebar_entries(entries):
    seen = set()
    deduped = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = entry.get('id') or entry.get('url_name') or entry.get('label')
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped

# Sidebar Config - Function returns default sidebar structure and behavior.
def default_sidebar_config():
    return _system_default_sidebar_config()

# Sidebar Config - Function validates sidebar behavior flags.
def normalize_sidebar_behavior(sidebar_config):
    return _system_normalize_sidebar_behavior(sidebar_config)


def normalize_sidebar_toggle_icon(value):
    return _system_normalize_sidebar_toggle_icon(value)

# Navbar Config - Function returns default navbar structure and mode settings.
def default_navbar_config():
    return _system_default_navbar_config()

# Navbar Config - Helper validates translated navbar labels.
def _normalize_navbar_labels(value):
    if not isinstance(value, dict):
        return {}
    labels = {}
    for raw_code, raw_label in value.items():
        code = _normalize_language_code(raw_code)
        label = str(raw_label or '').strip()
        if code and label:
            labels[code] = label
    return labels

# Navbar Config - Helper validates recursive navbar nodes.
def _normalize_navbar_nodes(value, depth=0):
    if not isinstance(value, list) or depth > 6:
        return []

    nodes = []
    for raw_node in value:
        if not isinstance(raw_node, dict):
            continue
        kind = 'route' if raw_node.get('kind') == 'route' else 'manual'
        node_id = str(raw_node.get('id') or '').strip()
        if not node_id:
            continue
        node = {
            'kind': kind,
            'id': node_id[:180],
            'children': _normalize_navbar_nodes(raw_node.get('children'), depth + 1),
        }
        labels = _normalize_navbar_labels(raw_node.get('labels'))
        if labels:
            node['labels'] = labels
        url = str(raw_node.get('url') or '').strip()
        if url:
            node['url'] = url[:500]
        if kind == 'route':
            url_name = str(raw_node.get('url_name') or node_id).strip()
            if not url_name:
                continue
            node['url_name'] = url_name[:255]
        nodes.append(node)
    return nodes

# Navbar Config - Function validates navbar modes, labels, and hierarchy.
def normalize_navbar_config(navbar_config):
    return _system_normalize_navbar_config(navbar_config)

# Navbar Config - Function builds a default navbar hierarchy from sidebar config.
def seed_navbar_config_from_sidebar(navbar_config, sidebar_config, lang_code='en'):
    navbar = normalize_navbar_config(navbar_config)
    if not navbar.get('enabled'):
        return navbar
    if navbar.get('hierarchy', {}).get('nodes'):
        return navbar

    sidebar = normalize_sidebar_behavior(sidebar_config)
    language_code = _normalize_language_code(lang_code) or 'en'

    # Navbar Config - Helper resolves entry labels across configured languages.
    def labels_for(entry):
        label = str((entry or {}).get('label') or '').strip()
        return {language_code: label} if label else {}

    # Navbar Config - Helper derives stable navbar node identifiers.
    def node_id(prefix, entry, index):
        return str(
            (entry or {}).get('url_name')
            or (entry or {}).get('id')
            or (entry or {}).get('url')
            or f'{prefix}-{index}'
        ).strip()

    # Navbar Config - Helper converts sidebar entries into navbar nodes.
    def convert_entry(entry, index=0):
        if not isinstance(entry, dict):
            return None

        kind = entry.get('kind') or 'item'
        if kind == 'group':
            children = [
                child_node
                for child_index, child in enumerate(entry.get('items') or [])
                for child_node in [convert_entry(child, child_index)]
                if child_node
            ]
            if not children:
                return None
            url_name = str(entry.get('url_name') or '').strip()
            node = {
                'kind': 'route' if url_name else 'manual',
                'id': node_id('sidebar-group', entry, index),
                'children': children,
            }
            if url_name:
                node['url_name'] = url_name
            url = str(entry.get('url') or '').strip()
            if url:
                node['url'] = url
            labels = labels_for(entry)
            if labels:
                node['labels'] = labels
            return node

        url_name = str(entry.get('url_name') or '').strip()
        url = str(entry.get('url') or '').strip()
        if not url_name and not url:
            return None
        node = {
            'kind': 'route' if url_name else 'manual',
            'id': node_id('sidebar-item', entry, index),
            'children': [],
        }
        if url_name:
            node['url_name'] = url_name
        if url:
            node['url'] = url
        labels = labels_for(entry)
        if labels:
            node['labels'] = labels
        return node

    nodes = [
        node
        for index, entry in enumerate(sidebar.get('entries') or [])
        for node in [convert_entry(entry, index)]
        if node
    ]
    if nodes:
        navbar['hierarchy'] = {'nodes': nodes}
    return normalize_navbar_config(navbar)

# Sidebar Config - Function resolves user sidebar density under system policy.
def resolve_sidebar_density_preference(user_prefs, config):
    prefs = dict(user_prefs or {})
    sidebar_config = normalize_sidebar_behavior(config.get('sidebar', {}))
    if not sidebar_config.get('allow_user_density', True):
        prefs.pop('sidebar_density', None)
        prefs['sidebar_density'] = sidebar_config.get('density', DEFAULT_SIDEBAR_DENSITY)
        return prefs

    if prefs.get('sidebar_density') not in SIDEBAR_DENSITY_VALUES:
        prefs['sidebar_density'] = sidebar_config.get('density', DEFAULT_SIDEBAR_DENSITY)
    return prefs

# Sidebar Config - Function resolves sidebar collapsed state under lock policy.
def resolve_sidebar_collapsed_preference(user_prefs, config, session_collapsed=False):
    prefs = dict(user_prefs or {})
    collapse_mode = normalize_sidebar_behavior(config.get('sidebar', {})).get('collapse_mode', DEFAULT_SIDEBAR_COLLAPSE_MODE)
    if collapse_mode == 'locked_expanded':
        prefs.pop('sidebar_collapsed', None)
        return False, prefs

    raw_value = prefs.get('sidebar_collapsed', session_collapsed)
    if isinstance(raw_value, str):
        raw_value = raw_value.lower() == 'true'
    return bool(raw_value), prefs

# Sidebar Runtime - Function toggles collapsed sidebar state in the session.
