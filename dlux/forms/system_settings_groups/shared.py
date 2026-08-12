"""Helpers shared by the per-group mixins: preserved-value cleaning, asset
selection, imported-settings reads and step rendering.

Mixed into SystemSettingsForm; see dlux/forms/system_settings.py.
"""

import json
from pathlib import Path
from django.template.loader import render_to_string
from ...system.constants import (
    SETUP_STEP_IDENTITY,
    SETUP_STEP_LANGUAGES,
    SETUP_STEP_SECURITY,
    SETUP_STEP_EMAIL,
    SETUP_STEP_LOGIN,
    SETUP_STEP_SIDEBAR,
    SETUP_STEP_NAVBAR,
    SETUP_STEP_TITLEBAR,
    SETUP_STEP_NOTIFICATIONS,
    SETUP_STEP_APPEARANCE,
    SETUP_STEP_LAYOUT,
    SETUP_STEP_LOGGING,
    SETUP_STEP_PROFILE,
    SETUP_STEP_BACKUPS,
    SETUP_STEP_COUNT,
    DEFAULT_HOME_URL,
    DEFAULT_NAVBAR_MODE,
    DEFAULT_SIDEBAR_COLLAPSE_MODE,
    DEFAULT_SIDEBAR_TOGGLE_ICON,
    DEFAULT_SIDEBAR_DENSITY,
    DEFAULT_FORM_DENSITY,
    DEFAULT_MODAL_SIZE,
    DEFAULT_TABLE_DENSITY,
    FORM_DENSITY_CHOICES,
    FORM_DENSITY_VALUES,
    LAYOUT_FOOTER_TEXT_MAX_LENGTH,
    MODAL_SIZE_CHOICES,
    MODAL_SIZE_VALUES,
    OPTIONS_STYLE_CHOICES,
    OPTIONS_STYLE_VALUES,
    DEFAULT_OPTIONS_STYLE,
    THEME_PICKER_LOCATION_CHOICES,
    THEME_PICKER_LOCATION_VALUES,
    THEME_PICKER_LOCATION_TITLEBAR,
    DEFAULT_THEME_PICKER_LOCATION,
    ROW_ACTIONS_STYLE_CHOICES,
    ROW_ACTIONS_STYLE_VALUES,
    DEFAULT_ROW_ACTIONS_STYLE,
    PUBLIC_ROOT_META_DESCRIPTION_MAX_LENGTH,
    PUBLIC_ROOT_TITLE_MAX_LENGTH,
    REGISTRATION_ACTIVATION_CHOICES,
    REGISTRATION_ACTIVATION_VALUES,
    NAVBAR_MODE_CHOICES,
    NAVBAR_MODE_VALUES,
    SIDEBAR_COLLAPSE_MODE_CHOICES,
    SIDEBAR_TOGGLE_DIRECTIONAL_ICONS,
    SIDEBAR_TOGGLE_ICON_MAX_LENGTH,
    SIDEBAR_COLLAPSE_MODE_VALUES,
    SIDEBAR_DENSITY_CHOICES,
    SIDEBAR_DENSITY_VALUES,
    TABLE_DENSITY_CHOICES,
    TABLE_DENSITY_VALUES,
    TITLEBAR_ALIGN_CHOICES,
    TITLEBAR_ALIGN_VALUES,
    TITLEBAR_HEIGHT_CHOICES,
    TITLEBAR_HEIGHT_VALUES,
    TITLEBAR_HOME_SHAPE_CHOICES,
    TITLEBAR_HOME_SHAPE_VALUES,
    TITLEBAR_LOGO_TREATMENT_CHOICES,
    TITLEBAR_LOGO_TREATMENT_SHAPE_CHOICES,
    TITLEBAR_LOGO_TREATMENT_SHAPE_VALUES,
    TITLEBAR_LOGO_TREATMENT_VALUES,
    TITLEBAR_SIZE_CHOICES,
    TITLEBAR_SIZE_VALUES,
    TITLEBAR_SURFACE_CHOICES,
    TITLEBAR_SURFACE_VALUES,
    TITLEBAR_GLOBAL_SEARCH_CHOICES,
    TITLEBAR_GLOBAL_SEARCH_VALUES,
    TITLEBAR_ACTIONS_ORDER,
    TITLEBAR_USER_HUB_STYLE_ACTIONS,
    TITLEBAR_USER_HUB_STYLE_CHOICES,
    TITLEBAR_USER_HUB_STYLE_DROPDOWN,
    TITLEBAR_USER_HUB_STYLE_VALUES,
)
from ...utils import (
    CLIENT_IP_MODE_AUTO,
    CLIENT_IP_MODE_CLOUDFLARE,
    CLIENT_IP_MODE_CUSTOM,
    CLIENT_IP_MODE_REMOTE_ADDR,
    CLIENT_IP_MODE_X_FORWARDED_FOR,
    CLIENT_IP_MODE_X_REAL_IP,
    default_client_ip_config,
    default_auth_config,
    default_backup_config,
    default_log_config,
    default_profile_config,
    default_login_config,
    default_navbar_config,
    default_notification_config,
    default_titlebar_config,
    default_email_config,
    encrypt_email_secret,
    apply_system_settings_import,
    get_email_service_status,
    email_features_unlocked,
    get_system_config,
    has_section_models,
    normalize_system_settings_import_payload,
    normalize_email_config,
    normalize_client_ip_config,
    normalize_language_catalog,
    normalize_auth_config,
    normalize_backup_config,
    normalize_log_config,
    normalize_profile_config,
    normalize_login_config,
    normalize_notification_config,
    normalize_sidebar_behavior,
    normalize_sidebar_toggle_icon,
    normalize_system_names,
    normalize_titlebar_actions_order,
    normalize_titlebar_config,
    normalize_allowed_fonts,
    seed_navbar_config_from_sidebar,
)
from ...system.registry import get_setting_group
from ..assets import AssetPickerField, AssetSelection
from ...assets import adopt_stored_asset, create_managed_asset
from .._shared import FONT_CHOICES, THEME_CHOICES, _LEGACY_HOME_URL, _json_dump, logger


class PreservedValueMixin:
    def _clean_preserved_toggle(self, field_name, step_index, default):
        # Boolean toggles vanish from POST both when unchecked and when their step
        # isn't the active one, so a single-step save of another step must restore
        # the stored value rather than read the absence as False.
        if (
            self.is_bound and self.mode != 'setup' and self.single_step_mode
            and self.single_step_index != step_index
        ):
            stored = getattr(self.instance, field_name, None)
            if stored is None:
                return bool(default)
            return bool(stored)
        return bool(self.cleaned_data.get(field_name, default))

    def _clean_preserved_text(self, field_name, step_index, max_length):
        if (
            self.is_bound and self.mode != 'setup' and self.single_step_mode
            and self.single_step_index != step_index and field_name not in self.data
        ):
            value = getattr(self.instance, field_name, None)
            if value in (None, ''):
                value = self.initial.get(field_name, '')
        else:
            value = self.cleaned_data.get(field_name, '')
        return str(value or '').strip()[:max_length].rstrip()

    def _clean_preserved_choice(self, field_name, step_index, valid_values, default):
        if (
            self.is_bound and self.mode != 'setup' and self.single_step_mode
            and self.single_step_index != step_index and field_name not in self.data
        ):
            value = getattr(self.instance, field_name, None) or self.initial.get(field_name) or default
        else:
            value = self.cleaned_data.get(field_name) or default
        return value if value in valid_values else default

    def _clean_preserved_footer_string(self, field_name):
        # Footer text inputs live in the Identity step; a single-step
        # modal save of another step omits them, so keep the stored value.
        if self.is_bound and self.mode != 'setup' and self.single_step_mode and field_name not in self.data:
            value = getattr(self.instance, field_name, None)
            if value in (None, ''):
                value = self.initial.get(field_name, '')
        else:
            value = self.cleaned_data.get(field_name, '')
        return str(value or '').strip()[:LAYOUT_FOOTER_TEXT_MAX_LENGTH].rstrip()

    def _resolve_asset_selection(self, field_name, current_asset, *, legacy_file=None, commit=True):
        selection = self.cleaned_data.get(field_name)
        if not isinstance(selection, AssetSelection):
            selection = AssetSelection(omitted=True)
        if selection.upload:
            if not commit:
                return current_asset
            asset, _created = create_managed_asset(
                selection.upload,
                kind='image',
                title=Path(str(getattr(selection.upload, 'name', '') or '')).stem,
                user=self._user or getattr(self.request, 'user', None),
            )
            return asset
        if selection.asset is not None:
            return selection.asset
        if selection.clear:
            return None
        if current_asset is not None:
            return current_asset
        if commit and legacy_file:
            return adopt_stored_asset(
                legacy_file,
                user=self._user or getattr(self.request, 'user', None),
                title=Path(str(getattr(legacy_file, 'name', '') or '')).stem,
            )
        return None

    def _read_imported_settings(self):
        uploaded = self.cleaned_data.get('settings_import_file')
        if not uploaded:
            return {}
        try:
            if hasattr(uploaded, 'seek'):
                uploaded.seek(0)
            raw = uploaded.read()
            if isinstance(raw, bytes):
                raw = raw.decode('utf-8')
            parsed = json.loads(raw or '{}')
            return normalize_system_settings_import_payload(parsed)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self.add_error('settings_import_file', str(exc) or "Invalid setup import file.")
            return {}

    def _apply_schema_group_initials(self, storage_field, source, *, hidden_field=True):
        group = get_setting_group(storage_field)
        normalized = group.normalizer(source)
        if hidden_field and group.storage_field in self.fields:
            self.initial[group.storage_field] = _json_dump(normalized, ensure_ascii=False)
        for field_schema in group.fields:
            form_name = field_schema.form_name
            if form_name in self.fields:
                self.initial[form_name] = normalized.get(field_schema.storage[1], field_schema.default)
        return normalized

    def _schema_group_from_cleaned(self, storage_field, *, fallback=None):
        group = get_setting_group(storage_field)
        values = dict(fallback or {})
        for field_schema in group.fields:
            form_name = field_schema.form_name
            if form_name in self.cleaned_data:
                values[field_schema.storage[1]] = self.cleaned_data.get(form_name)
        return group.normalizer(values)

    def _step_render(self, step_index, template, context):
        """Render a heavy step-specific template block only when it will actually
        be shown. In single-step modal mode the form still builds ALL step Divs
        (hidden with CSS), so without this every step's matrices (themes, fonts,
        sidebar/navbar/log/profile builders, translation editor…) were rendered
        on every modal open — ~2 MB and many template renders per load. Now a
        step's block is built only when that step is the active one (or in the
        full setup wizard). Fields for skipped steps still exist on the form and
        are preserved on save by the step-scoped clean methods."""
        if getattr(self, 'single_step_mode', False) and self.single_step_index != step_index:
            return ''
        return render_to_string(template, context)
