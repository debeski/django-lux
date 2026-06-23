# Imports of the required python modules and libraries
######################################################
import os
import json
import re
from types import MethodType, SimpleNamespace

from django import forms
from django.contrib.auth.models import Permission as Permissions
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, UserChangeForm, PasswordChangeForm, SetPasswordForm
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Div, HTML, Submit, Row
from crispy_forms.bootstrap import FormActions
from PIL import Image
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.html import conditional_escape
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from django.db.models import Q
from django.apps import apps
from django.forms.widgets import ChoiceWidget
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from .system.constants import (
    DEFAULT_HOME_URL,
    DEFAULT_NAVBAR_MODE,
    DEFAULT_SIDEBAR_COLLAPSE_MODE,
    DEFAULT_SIDEBAR_DENSITY,
    DEFAULT_TABLE_DENSITY,
    REGISTRATION_ACTIVATION_CHOICES,
    REGISTRATION_ACTIVATION_VALUES,
    NAVBAR_MODE_CHOICES,
    NAVBAR_MODE_VALUES,
    SIDEBAR_COLLAPSE_MODE_CHOICES,
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
    TITLEBAR_ACTIONS_ORDER,
    TITLEBAR_USER_HUB_STYLE_ACTIONS,
    TITLEBAR_USER_HUB_STYLE_CHOICES,
    TITLEBAR_USER_HUB_STYLE_DROPDOWN,
    TITLEBAR_USER_HUB_STYLE_VALUES,
)
from .translations import build_translation_matrix_groups, discover_translation_languages, get_strings, get_current_language_code
from .themes import get_theme_choices, get_theme_options, is_valid_theme, normalize_allowed_themes
from .utils import (
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
    get_user_management_tier_state,
    get_user_scope,
    has_section_models,
    is_central_staff,
    is_global_staff,
    normalize_system_settings_import_payload,
    normalize_email_config,
    normalize_client_ip_config,
    normalize_language_catalog,
    LOGIN_STYLE_VALUES,
    normalize_auth_config,
    normalize_backup_config,
    normalize_log_config,
    normalize_profile_config,
    normalize_login_config,
    normalize_navbar_config,
    normalize_notification_config,
    normalize_sidebar_behavior,
    normalize_system_names,
    normalize_titlebar_actions_order,
    normalize_titlebar_config,
    normalize_allowed_fonts,
    seed_navbar_config_from_sidebar,
)
from .system.registry import get_setting_group
from .widgets import DluxChoiceSelectorWidget

User = get_user_model()

_LEGACY_HOME_URL = '/sys/'

DLUX_PERMISSION_HELP_TEXTS = {
    'view_reports': (
        'help_perm_view_reports',
        'Allows viewing the reports overview and exporting report summaries.',
    ),
    'download_backup': (
        'help_perm_download_backup',
        'Allows building and downloading report backup ZIP archives.',
    ),
    'view_sections': (
        'help_perm_view_sections',
        'Allows opening the Sections screen and viewing the section hierarchy.',
    ),
    'manage_sections': (
        'help_perm_manage_sections',
        'Allows creating, editing, reordering, and deleting sections and subsections.',
    ),
    'view_activitylog': (
        'help_perm_view_activitylog',
        'Allows viewing activity-log pages and activity detail modals.',
    ),
    'manage_staff': (
        'help_perm_manage_staff',
        'Lets this staff user assign staff access to other users. It does not widen their own scope.',
    ),
    'manage_scopes': (
        'help_perm_manage_scopes',
        'Creates Global Staff access only when the user has no assigned scope.',
    ),
}

THEME_CHOICES = get_theme_choices()
from .fonts import get_font_choices
FONT_CHOICES = get_font_choices()
PERMISSION_UI_EXCLUDED_APP_LABELS = [
    'admin',
    'contenttypes',
    'sessions',
    'django_celery_beat',
    'health_check',
    'db',
    'corsheaders',
    'csp',
]


def get_assignable_permissions_queryset():
    return Permissions.objects.exclude(
        Q(codename__regex=r'^(delete_)') |
        Q(content_type__app_label__in=PERMISSION_UI_EXCLUDED_APP_LABELS) |
        (Q(content_type__app_label='dlux') & ~Q(codename__in=['manage_staff', 'manage_scopes', 'view_activitylog', 'view_reports', 'download_backup']) & ~Q(content_type__model='section')) |
        Q(content_type__app_label='auth', content_type__model__in=['group', 'user', 'permission'])
    )


def _get_assignable_permission_ids_for_user(user):
    if not user or getattr(user, 'is_superuser', False):
        return None

    cache_attr = '_dlux_assignable_permission_ids'
    if hasattr(user, cache_attr):
        return getattr(user, cache_attr)

    permission_ids = list(
        Permissions.objects.filter(
            Q(user=user) | Q(group__user=user)
        ).values_list('id', flat=True).distinct()
    )
    setattr(user, cache_attr, permission_ids)
    return permission_ids


def _apply_assignable_permission_filter(form, user):
    if not user or getattr(user, 'is_superuser', False):
        return
    permission_ids = _get_assignable_permission_ids_for_user(user)
    filtered_qs = form.fields['permissions'].queryset.filter(id__in=permission_ids)
    form.fields['permissions'].queryset = filtered_qs
    form.fields['permissions'].widget._filtered_queryset = filtered_qs


class DluxAuthenticationForm(AuthenticationForm):
    """
    Preserve normal username login while allowing verified public-registration
    projects to accept email in the username field.
    """

    def clean(self):
        raw_username = self.cleaned_data.get('username')
        if raw_username and '@' in raw_username:
            from .registration import public_registration_config

            if public_registration_config().get('enabled'):
                match = User._default_manager.filter(email__iexact=str(raw_username).strip()).first()
                if match:
                    self.cleaned_data['username'] = match.get_username()
        return super().clean()


class PublicRegistrationForm(forms.Form):
    email = forms.EmailField(
        label=_("Email"),
        max_length=254,
        widget=forms.EmailInput(attrs={'autocomplete': 'email'}),
    )
    password1 = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    password2 = forms.CharField(
        label=_("Confirm password"),
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    first_name = forms.CharField(
        label=_("First name"),
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={'autocomplete': 'given-name'}),
    )
    last_name = forms.CharField(
        label=_("Last name"),
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={'autocomplete': 'family-name'}),
    )
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'autocomplete': 'off', 'tabindex': '-1'}),
    )

    def clean_email(self):
        return str(self.cleaned_data['email']).strip().lower()

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get('password1')
        password2 = cleaned.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', _("The two password fields did not match."))
        if password1:
            validate_password(password1)
        return cleaned


def _json_dump(value, **kwargs):
    return json.dumps(value, cls=DjangoJSONEncoder, **kwargs)


def _extract_permission_codenames(permissions):
    codenames = set()
    for permission in permissions or []:
        codename = getattr(permission, 'codename', None)
        if codename:
            codenames.add(str(codename))
    return codenames


def _build_staff_tier_preview_catalog(strings):
    tier_examples = {
        'regular_user': get_user_management_tier_state(
            is_superuser=False,
            is_staff=False,
            scope=None,
            permission_codenames=set(),
        ),
        'superuser': get_user_management_tier_state(
            is_superuser=True,
            is_staff=True,
            scope=None,
            permission_codenames={'manage_scopes', 'manage_staff'},
        ),
        'global_staff': get_user_management_tier_state(
            is_superuser=False,
            is_staff=True,
            scope=None,
            permission_codenames={'manage_scopes'},
        ),
        'central_staff': get_user_management_tier_state(
            is_superuser=False,
            is_staff=True,
            scope=None,
            permission_codenames=set(),
        ),
        'scoped_staff': get_user_management_tier_state(
            is_superuser=False,
            is_staff=True,
            scope=SimpleNamespace(name=strings.get('form_scope', 'Scope')),
            permission_codenames=set(),
        ),
    }
    return {
        'preview_title': strings.get('staff_tier_preview', 'Staff Tier Preview'),
        'preview_caption': strings.get(
            'staff_tier_preview_caption',
            'Read-only summary based on staff access, scope, and selected permissions.',
        ),
        'delegation_badge_label': strings.get('tier_delegate_badge', 'Can Assign Staff Roles'),
        'tiers': {
            key: {
                'title': state['title'],
                'description': state['description'],
                'badge_classes': state['badge_classes'],
                'icon': state['icon'],
                'capabilities': state['capabilities'],
            }
            for key, state in tier_examples.items()
        },
        'warnings': {
            'needs_staff': strings.get(
                'tier_warning_needs_staff',
                'Staff-related permissions are selected, but staff access is not enabled yet.',
            ),
            'scoped_manage_scopes_conflict': strings.get(
                'tier_warning_scoped_manage_scopes',
                'Global Staff access is ineffective while a scope is assigned.',
            ),
        },
    }


def _configure_staff_tier_preview(form, *, fixed_scope=None, scope_locked=False):
    perm_field = form.fields.get('permissions')
    if not perm_field or not isinstance(perm_field.widget, GroupedPermissionWidget):
        return

    strings = getattr(perm_field.widget, 'translations', get_strings())
    instance = getattr(form, 'instance', None)
    initial_permissions = perm_field.initial
    if initial_permissions is None and instance is not None and getattr(instance, 'pk', None):
        initial_permissions = getattr(instance, 'user_permissions', None)
        if initial_permissions is not None:
            initial_permissions = initial_permissions.all()

    is_staff_value = bool(
        form.initial.get('is_staff')
        if 'is_staff' in getattr(form, 'initial', {})
        else getattr(getattr(form, 'instance', None), 'is_staff', getattr(form.fields.get('is_staff'), 'initial', False))
    )

    if fixed_scope is None and 'scope' in form.fields:
        fixed_scope = form.fields['scope'].initial

    preview_state = get_user_management_tier_state(
        is_superuser=bool(getattr(instance, 'is_superuser', False)),
        is_staff=is_staff_value,
        scope=fixed_scope,
        permission_codenames=_extract_permission_codenames(initial_permissions),
    )
    preview_config = {
        'catalog': _build_staff_tier_preview_catalog(strings),
        'initial_state': preview_state,
        'forced_superuser': bool(getattr(instance, 'is_superuser', False)),
        'scope_field_name': 'scope' if 'scope' in form.fields else '',
        'fixed_scope_active': bool(fixed_scope is not None),
        'fixed_scope_label': getattr(fixed_scope, 'name', '') if fixed_scope is not None else '',
        'scope_locked': bool(scope_locked),
    }
    perm_field.widget.staff_tier_preview = {
        'config_json': _json_dump(preview_config),
    }


def _system_settings_sidebar_tools_available(cleaned_data):
    allowed_themes = cleaned_data.get('allowed_themes') or []
    theme_picker_enabled = bool(cleaned_data.get('allow_user_theme_override', True)) and len(allowed_themes) > 1
    density_picker_enabled = bool(cleaned_data.get('sidebar_allow_user_density', True))
    reorder_enabled = bool(cleaned_data.get('sidebar_enable_reorder', True))
    return bool(theme_picker_enabled or density_picker_enabled or reorder_enabled or has_section_models())


def _bind_choice_selector_widget(field, widget):
    widget.choices = field.choices
    field.widget = widget




def _attach_is_staff_permission(form, widget_id=None):
    perm_field = form.fields.get('permissions')
    staff_field = form.fields.get('is_staff')
    if not perm_field or not staff_field:
        return
    if not isinstance(perm_field.widget, GroupedPermissionWidget):
        return

    try:
        app_config = apps.get_app_config('dlux')
        app_name = app_config.verbose_name
    except LookupError:
        app_name = 'dlux'

    current_value = False
    if getattr(form, 'instance', None) is not None and getattr(form.instance, 'pk', None):
        current_value = bool(getattr(form.instance, 'is_staff', False))
    elif 'is_staff' in form.initial:
        current_value = bool(form.initial.get('is_staff'))
    else:
        current_value = bool(getattr(staff_field, 'initial', False))

    field_id = widget_id or 'id_permissions'
    option_id = f"{field_id}_is_staff"

    # helper to check translations on widget
    s = getattr(perm_field.widget, 'translations', get_strings())

    option = {
        'name': 'is_staff',
        'value': 'on',
        'label': staff_field.label or s.get('form_is_staff', "Staff"),
        'selected': current_value,
        'help_text': staff_field.help_text,
        'attrs': {
            'id': option_id,
            'data_action': 'other',
            'data_model': 'staff',
            'data_codename': 'is_staff',
            'disabled': bool(getattr(staff_field, 'disabled', False)),
        }
    }

    perm_field.widget.add_extra_group(
        app_label='dlux',
        app_name=app_name,
        model_key='staff_access',
        model_name=s.get('perm_staff_access', 'Staff Permissions'),
        option=option,
    )


def _get_ui_direction():
    return 'rtl' if get_current_language_code().startswith('ar') else 'ltr'


def _build_cancel_button_html(strings):
    return f"""
    <button type="button" class="btn btn-danger rounded-pill" data-bs-dismiss="modal">
        <i class="bi bi-x-circle text-light me-1 h4"></i> {strings.get('btn_cancel', 'Cancel')}
    </button>
    """


def _wrap_modal_action_buttons(*buttons):
    direction = _get_ui_direction()
    button_html = ''.join(buttons)
    return FormActions(
        HTML(
            f"""
            <div class="d-flex flex-wrap justify-content-end gap-2 dlux-modal-form-actions" dir="{direction}">
                {button_html}
            </div>
            """
        )
    )


def _build_wizard_actions(strings, submit_label, submit_icon):
    direction = _get_ui_direction()
    prev_icon = 'bi-arrow-right-circle' if direction == 'rtl' else 'bi-arrow-left-circle'
    next_icon = 'bi-arrow-left-circle' if direction == 'rtl' else 'bi-arrow-right-circle'

    return _wrap_modal_action_buttons(
        _build_cancel_button_html(strings),
        f"""
        <button type="button" class="btn btn-secondary rounded-pill dlux-btn-prev d-none">
            <i class="bi {prev_icon} text-light me-1 h4"></i> {strings.get('btn_prev', 'Previous')}
        </button>
        """,
        f"""
        <button type="button" class="btn btn-primary rounded-pill dlux-btn-next">
            {strings.get('btn_next', 'Next')} <i class="bi {next_icon} text-light ms-1 h4"></i>
        </button>
        """,
        f"""
        <button type="submit" class="btn btn-success rounded-pill dlux-btn-submit d-none">
            <i class="bi {submit_icon} text-light me-1 h4"></i> {submit_label}
        </button>
        """,
    )


def _build_submit_actions(strings, submit_label, submit_icon, submit_class='btn btn-success rounded-pill'):
    return _wrap_modal_action_buttons(
        _build_cancel_button_html(strings),
        f"""
        <button type="submit" class="{submit_class}">
            <i class="bi {submit_icon} text-light me-1 h4"></i> {submit_label}
        </button>
        """,
    )

class ProfileImageWidget(forms.ClearableFileInput):
    template_name = 'dlux/users/profile_image_widget.html'


def _apply_autocomplete_attrs(form, mapping):
    for field_name, autocomplete in mapping.items():
        field = form.fields.get(field_name)
        if field is None or not autocomplete:
            continue
        field.widget.attrs['autocomplete'] = autocomplete


def _build_archive_file_widget(field_label="", show_scan=False, attrs=None):
    widget = forms.ClearableFileInput(attrs=attrs or {})
    widget.template_name = 'dlux/forms/file_input.html'

    widget_attrs = dict(widget.attrs or {})
    existing_class = str(widget_attrs.get('class', '') or '').strip()
    widget_attrs['class'] = f"{existing_class} archive-file-input".strip()
    widget.attrs = widget_attrs

    def _get_context(self, name, value, attrs):
        context = forms.ClearableFileInput.get_context(self, name, value, attrs)
        data = context["widget"]
        data["field_label"] = field_label
        data["show_scan"] = show_scan

        if value and hasattr(value, "url"):
            data["file_url"] = value.url
            data["display_name"] = getattr(value, "name", "").split("/")[-1] or str(value)
            display_name = data["display_name"].lower()
            if display_name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico")):
                data["icon_class"] = "bi bi-file-earmark-image-fill"
            else:
                data["icon_class"] = "bi bi-file-earmark-fill"
        else:
            data["file_url"] = ""
            data["display_name"] = ""
            data["icon_class"] = "bi bi-file-earmark-arrow-up-fill"

        return context

    widget.get_context = MethodType(_get_context, widget)
    return widget


def build_archive_file_field(field_name, css_class=None):
    field_kwargs = {'template': 'dlux/forms/crispy_file_field.html'}
    if css_class:
        field_kwargs['css_class'] = css_class
    return Field(field_name, **field_kwargs)


def _boolean_field_checked(form, field_name):
    field = form.fields[field_name]
    if form.is_bound:
        return bool(field.widget.value_from_datadict(form.data, form.files, form.add_prefix(field_name)))
    if field_name in form.initial:
        return bool(form.initial.get(field_name))
    return bool(field.initial)


def build_settings_toggle_field(form, field_name, css_class=None, attrs=None):
    bound_field = form[field_name]
    field = bound_field.field
    label = conditional_escape(field.label or field_name.replace('_', ' ').title())
    help_text = str(field.help_text or '').strip()
    help_html = (
        f"<div class='dlux-settings-toggle-field__help small text-muted mt-1'>{conditional_escape(help_text)}</div>"
        if help_text else
        ""
    )
    checked_attr = ' checked' if _boolean_field_checked(form, field_name) else ''
    disabled_attr = ' disabled' if bool(getattr(field, 'disabled', False)) else ''
    wrapper_html = mark_safe(
        f"<div class='dlux-settings-toggle-field d-flex justify-content-between align-items-start gap-3 p-3 border rounded bg-light mb-2 h-100' "
        f"data-dlux-settings-toggle-field='{conditional_escape(field_name)}'>"
        f"<div class='dlux-settings-toggle-field__content flex-grow-1'>"
        f"<div class='dlux-settings-toggle-field__label fw-semibold'>{label}</div>"
        f"{help_html}"
        f"</div>"
        f"<div class='dlux-settings-toggle-field__control form-switch'>"
        f"<input class='form-check-input dlux-settings-toggle-field__input' type='checkbox' id='{conditional_escape(bound_field.auto_id)}' "
        f"name='{conditional_escape(bound_field.html_name)}' aria-label='{label}'{checked_attr}{disabled_attr}>"
        f"</div>"
        f"</div>"
    )
    if css_class:
        return Div(HTML(wrapper_html), css_class=css_class, **(attrs or {}))
    return HTML(wrapper_html)


def build_email_toggle_field(form, field_name, css_class=None, attrs=None):
    bound_field = form[field_name]
    field = bound_field.field
    label = conditional_escape(field.label or field_name.replace('_', ' ').title())
    help_text = str(field.help_text or '').strip()
    help_html = (
        f"<div class='dlux-email-toggle-field__help small text-muted mt-1'>{conditional_escape(help_text)}</div>"
        if help_text else
        ""
    )
    checked_attr = ' checked' if _boolean_field_checked(form, field_name) else ''
    disabled_attr = ' disabled' if bool(getattr(field, 'disabled', False)) else ''
    wrapper_html = mark_safe(
        f"<div class='dlux-email-toggle-field border rounded bg-light px-3 py-2 h-100' "
        f"data-dlux-email-toggle-field='{conditional_escape(field_name)}'>"
        f"<div class='dlux-email-toggle-field__row d-flex align-items-center justify-content-between gap-3'>"
        f"<div class='dlux-email-toggle-field__label fw-semibold'>{label}</div>"
        f"<input class='form-check-input dlux-email-toggle-field__input' type='checkbox' id='{conditional_escape(bound_field.auto_id)}' "
        f"name='{conditional_escape(bound_field.html_name)}' aria-label='{label}'{checked_attr}{disabled_attr}>"
        f"</div>"
        f"{help_html}"
        f"</div>"
    )
    if css_class:
        return Div(HTML(wrapper_html), css_class=css_class, **(attrs or {}))
    return HTML(wrapper_html)


_TITLEBAR_ACTION_META = {
    'notifications': ('bi-bell-fill', 'notifications', 'Notifications'),
    'home': ('bi-house-fill', 'btn_home', 'Home'),
    'profile': ('bi-person-bounding-box', 'profile', 'Profile'),
    'help': ('bi-question-circle-fill', 'help', 'Help'),
    'users': ('bi-people-fill', 'manage_users', 'Users'),
    'activity': ('bi-clock-history', 'activity_log', 'Activity'),
    'reports': ('bi-bar-chart-fill', 'reports_title', 'Reports'),
    'settings': ('bi-gear-fill', 'options_title', 'Settings'),
    'auth': ('bi-box-arrow-right', 'logout', 'Login / Logout'),
}


def build_titlebar_actions_order_builder(order, strings, *, visible=True):
    if isinstance(order, str):
        try:
            order = json.loads(order)
        except (TypeError, ValueError, json.JSONDecodeError):
            order = []
    normalized_order = normalize_titlebar_actions_order(order)
    items_html = []
    for action_key in normalized_order:
        icon, label_key, fallback = _TITLEBAR_ACTION_META.get(action_key, ('bi-app', action_key, action_key.title()))
        label = conditional_escape(strings.get(label_key, fallback))
        key = conditional_escape(action_key)
        items_html.append(
            "<div class='dlux-titlebar-action-order-item' "
            f"data-titlebar-action-order-item data-action-key='{key}'>"
            "<span class='dlux-titlebar-action-order-handle'><i class='bi bi-grip-vertical' aria-hidden='true'></i></span>"
            f"<span class='dlux-titlebar-action-order-icon'><i class='bi {conditional_escape(icon)}' aria-hidden='true'></i></span>"
            f"<span class='dlux-titlebar-action-order-label'>{label}</span>"
            "<span class='dlux-titlebar-action-order-controls'>"
            "<button type='button' class='btn btn-sm btn-light' data-titlebar-action-move='-1' aria-label='Move up'>"
            "<i class='bi bi-arrow-up-short' aria-hidden='true'></i>"
            "</button>"
            "<button type='button' class='btn btn-sm btn-light' data-titlebar-action-move='1' aria-label='Move down'>"
            "<i class='bi bi-arrow-down-short' aria-hidden='true'></i>"
            "</button>"
            "</span>"
            "</div>"
        )

    hidden_class = '' if visible else ' d-none'
    title = conditional_escape(strings.get('titlebar_actions_order_title', 'Titlebar action order'))
    help_text = conditional_escape(
        strings.get(
            'titlebar_actions_order_help',
            'Choose the right-side titlebar button order for the Titlebar Actions layout.',
        )
    )
    return mark_safe(
        f"<div class='dlux-titlebar-actions-order-builder border rounded bg-light p-3 mb-3{hidden_class}' "
        "data-titlebar-actions-order-builder>"
        "<div class='d-flex align-items-start justify-content-between gap-3 mb-2'>"
        f"<div><div class='fw-semibold'>{title}</div><div class='small text-muted'>{help_text}</div></div>"
        "</div>"
        "<div class='dlux-titlebar-actions-order-list' data-titlebar-actions-order-list>"
        f"{''.join(items_html)}"
        "</div>"
        "</div>"
    )


class GroupedPermissionWidget(ChoiceWidget):
    template_name = 'dlux/users/grouped_permissions.html'
    allow_multiple_selected = True

    def add_extra_group(self, app_label, app_name, model_key, model_name, option):
        if not hasattr(self, 'extra_groups') or self.extra_groups is None:
            self.extra_groups = {}
        group = self.extra_groups.setdefault(app_label, {'name': app_name, 'models': {}})
        if app_name and not group.get('name'):
            group['name'] = app_name
        model_group = group['models'].setdefault(model_key, {'name': model_name, 'permissions': []})
        model_group['permissions'].append(option)

    def value_from_datadict(self, data, files, name):
        if hasattr(data, 'getlist'):
            return data.getlist(name)
        return data.get(name)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        s = getattr(self, 'translations', get_strings())
        
        # Get current selected values (as strings/ints)
        if value is None:
            value = []
        str_values = set(str(v) for v in value)
        
        # Access the queryset directly - prioritize field's current queryset over cached choices
        qs = None
        if hasattr(self, '_filtered_queryset'):
            # Use the explicitly set filtered queryset from the form
            qs = self._filtered_queryset.select_related('content_type').order_by('content_type__app_label', 'codename')
        elif hasattr(self.choices, 'queryset'):
            qs = self.choices.queryset.select_related('content_type').order_by('content_type__app_label', 'codename')
        else:
             choices = list(self.choices)
             choice_ids = [c[0] for c in choices if c[0]]
             qs = Permissions.objects.filter(id__in=choice_ids).select_related('content_type').order_by('content_type__app_label', 'codename')

        grouped_perms = {}
        
        for perm in qs:
            app_label = perm.content_type.app_label
            model_name = perm.content_type.model
            codename = perm.codename

            # Keep staff-delegation permissions together in the dedicated staff-access UI.
            if app_label == 'dlux' and codename in {'manage_staff', 'manage_scopes'}:
                model_name = 'staff_access'
                # Force model_verbose_name to match what _attach_is_staff_permission uses
                # "perm_staff_access" string usually "Staff Permissions"
                
            model_label_key = None
            model_label_fallback = None
            if app_label == 'dlux' and model_name == 'staff_access':
                model_label_key = 'perm_staff_access'
                model_label_fallback = "Staff Permissions"
            elif app_label == 'dlux' and model_name == 'profile':
                model_label_key = 'model_user'

            model_class = perm.content_type.model_class()
            if model_class is None and not (
                app_label == 'dlux' and model_name in {'staff_access', 'profile'}
            ):
                continue
            if model_class:
                # prefer plural verbose name if possible, or just verbose name
                # But here we want to use our translation keys if available
                default_verbose = str(model_class._meta.verbose_name)
            else:
                default_verbose = perm.content_type.name
            
            if model_label_key:
                model_verbose_name = s.get(model_label_key, model_label_fallback or default_verbose)
            else:
                # Try translation key 'model_modelname' (e.g. model_user)
                model_verbose_name = s.get(f"model_{model_name}", default_verbose)
            
            # Fetch verbose app name
            try:
                app_config = apps.get_app_config(app_label)
                default_app_verbose = app_config.verbose_name
            except LookupError:
                default_app_verbose = app_label.title()
            
            # Try translation key 'app_applabel' (e.g. app_dlux)
            app_verbose_name = s.get(f"app_{app_label}", default_app_verbose)

            action = 'other'
            codename = perm.codename
            if codename.startswith('view_'): action = 'view'
            elif codename.startswith('add_'): action = 'add'
            elif codename.startswith('change_'): action = 'change'
            elif codename.startswith('delete_'): action = 'delete'
            
            # Build option dict
            current_id = attrs.get('id', 'id_permissions') if attrs else 'id_permissions'

            # Translate permission label if possible
            # We use str(perm) to respect the dynamic translations 
            # applied in apps.py (which overrides Permission.__str__)
            perm_label = s.get(f"perm_{codename}", str(perm))

            # Dlux-owned permissions carry concise descriptions in the grouped UI.
            help_text = ""
            help_config = DLUX_PERMISSION_HELP_TEXTS.get(codename) if app_label == 'dlux' else None
            if help_config:
                help_key, help_default = help_config
                help_text = s.get(help_key, help_default)

            option = {
                'name': name,
                'value': perm.pk,
                'label': perm_label,
                'codename': codename,
                'selected': str(perm.pk) in str_values,
                'help_text': help_text,
                'attrs': {
                    'id': f"{current_id}_{perm.pk}",
                    'data_action': action,
                    'data_model': model_name,
                    'data_codename': codename,
                }
            }
            
            if app_label not in grouped_perms:
                grouped_perms[app_label] = {
                    'name': app_verbose_name,
                    'models': {}
                }
            
            if model_name not in grouped_perms[app_label]['models']:
                grouped_perms[app_label]['models'][model_name] = {
                    'name': model_verbose_name.title(),
                    'permissions': []
                }
            
            grouped_perms[app_label]['models'][model_name]['permissions'].append(option)
        
        action_order = {'view': 1, 'add': 2, 'change': 3, 'delete': 4, 'other': 5}
        for app_label, app_data in grouped_perms.items():
            for model_name, model_data in app_data['models'].items():
                model_data['permissions'].sort(
                    key=lambda x: action_order.get(x['attrs']['data_action'], 99)
                )

        extra_groups = getattr(self, 'extra_groups', None)
        if isinstance(extra_groups, dict):
            for app_label, app_data in extra_groups.items():
                if app_label not in grouped_perms:
                    grouped_perms[app_label] = {
                        'name': app_data.get('name', app_label.title()),
                        'models': {},
                    }

                target_app = grouped_perms[app_label]
                if app_data.get('name'):
                    # Check for translation override to prevent overwriting with hardcoded AppConfig name
                    translated_app = s.get(f"app_{app_label}")
                    if translated_app:
                        target_app['name'] = translated_app
                    else:
                        target_app['name'] = app_data['name']

                for model_name, model_data in app_data.get('models', {}).items():
                    target_model = target_app['models'].setdefault(
                        model_name,
                        {'name': model_data.get('name', model_name), 'permissions': []}
                    )

                    existing_ids = {
                        p.get('attrs', {}).get('id') for p in target_model['permissions']
                    }
                    for option in model_data.get('permissions', []):
                        opt_id = option.get('attrs', {}).get('id')
                        if opt_id and opt_id in existing_ids:
                            continue
                        target_model['permissions'].append(option)
            
        context['widget']['grouped_perms'] = grouped_perms
        context['widget']['staff_tier_preview'] = getattr(self, 'staff_tier_preview', None)
        context['DLUX_STRINGS'] = s  # Pass translations to template
        return context

    def render(self, name, value, attrs=None, renderer=None):
        from django.template.loader import render_to_string
        from django.utils.safestring import mark_safe
        
        context = self.get_context(name, value, attrs)
        return mark_safe(render_to_string(self.template_name, context))



# Custom User Creation form layout
class CustomUserCreationForm(UserCreationForm):
    handles_save = True
    refresh_parent = True

    # Added fields from Profile
    phone = forms.CharField(max_length=15, required=False)
    scope = forms.ModelChoiceField(queryset=None, required=False, label="Scope")
    force_password_change = forms.BooleanField(required=False, initial=False)
    
    permissions = forms.ModelMultipleChoiceField(
        queryset=get_assignable_permissions_queryset(),
        required=False,
        widget=GroupedPermissionWidget,
        label="Permissions"
    )

    class Meta:
        model = User
        fields = ["username", "password1", "password2", "first_name", "last_name", "email", "is_staff", "is_active"]

    def __init__(self, *args, **kwargs):
        self.user_context = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        Scope = apps.get_model('dlux', 'Scope')
        self.fields['scope'].queryset = Scope.objects.all()

        # Permission check: Non-superusers can only assign permissions they already have
        _apply_assignable_permission_filter(self, self.user_context)

        lock_scope = bool(
            self.user_context
            and not self.user_context.is_superuser
            and hasattr(self.user_context, 'profile')
            and self.user_context.profile.scope
        )

        if lock_scope:
            # Security Fix: Hide manage_staff
            filtered_qs = self.fields['permissions'].queryset.exclude(codename='manage_staff')
            self.fields['permissions'].queryset = filtered_qs
            self.fields['permissions'].widget._filtered_queryset = filtered_qs
        
        # Central Staff restrictions: cannot assign scopes, cannot see manage_scopes permission
        # Also apply to any non-superuser without manage_scopes permission
        if self.user_context and not self.user_context.is_superuser:
            if not self.user_context.has_perm('dlux.manage_scopes'):
                # Hide scope field completely - Central Staff can only create scopeless users
                self.fields['scope'].widget = forms.HiddenInput()
                self.fields['scope'].required = False
                self.fields['scope'].initial = None
                self.fields['scope'].queryset = Scope.objects.none()
                # Hide manage_scopes permission - only superusers can create Global Staff
                filtered_qs = self.fields['permissions'].queryset.exclude(codename='manage_scopes')
                self.fields['permissions'].queryset = filtered_qs
                # Store filtered queryset for widget to use
                self.fields['permissions'].widget._filtered_queryset = filtered_qs
        
        self.fields["email"].required = False

        # can_manage_staff logic
        if self.user_context and not self.user_context.is_superuser:
            if not self.user_context.has_perm('dlux.manage_staff'):
                self.fields['is_staff'].disabled = True
                self.fields['is_staff'].initial = False
                self.fields['is_staff'].help_text = "You don't have permission to assign this user as staff."

        # Load translations
        s = get_strings()
        self.modal_heading = s.get('add_user', 'Add New User')
        
        # Inject translations into widget
        self.fields['permissions'].widget.translations = s

        self.fields["username"].label = s.get('form_username', "Username")
        self.fields["email"].label = s.get('form_email', "Email")
        self.fields["first_name"].label = s.get('form_firstname', "First Name")
        self.fields["last_name"].label = s.get('form_lastname', "Last Name")
        self.fields["is_staff"].label = s.get('form_is_staff', "Enable Staff Access")
        self.fields["password1"].label = s.get('form_password', "Password")
        self.fields["password2"].label = s.get('form_password_confirm', "Confirm Password")
        self.fields["is_active"].label = s.get('form_is_active', "Active")
        self.fields["force_password_change"].label = s.get('form_force_password_change', "Require password change on first login")
        self.fields["phone"].label = s.get('form_phone', "Phone Number")
        self.fields["scope"].label = s.get('form_scope', "Scope")
        self.fields["permissions"].label = s.get('form_permissions', "Permissions")

        # Help Texts
        self.fields["username"].help_text = s.get('help_username', "Username must be unique. 150 characters or fewer. Letters, digits and @/./+/-/_ only.")
        self.fields["email"].help_text = s.get('help_email', "Enter a valid email address (optional).")
        self.fields["is_active"].help_text = s.get('help_is_active', "Designates whether this user should be treated as active.")
        self.fields["force_password_change"].help_text = s.get('help_force_password_change', "The new user must change this password before using the system.")
        self.fields["is_staff"].help_text = s.get('help_is_staff', "Enables staff access. The final tier depends on scope and selected permissions.")
        self.fields["password1"].help_text = s.get('help_password_common', "Your password can't be too similar to your other personal information.")
        self.fields["password2"].help_text = s.get('help_password_match', "Enter the same password as before, for verification.")
        self.fields["phone"].help_text = s.get('help_phone', "Enter a valid phone number (optional).")
        _apply_autocomplete_attrs(
            self,
            {
                'username': 'username',
                'password1': 'new-password',
                'password2': 'new-password',
                'first_name': 'given-name',
                'last_name': 'family-name',
                'email': 'email',
                'phone': 'tel',
            },
        )

        # can_manage_staff logic message update
        if self.user_context and not self.user_context.is_superuser:
            if not self.user_context.has_perm('dlux.manage_staff'):
                 # ... existing disabled logic ...
                 self.fields['is_staff'].help_text = s.get('help_is_staff_no_perm', "You don't have permission to assign this user as staff.")

        _attach_is_staff_permission(self, self.fields['permissions'].widget.attrs.get('id'))
        fixed_scope = None
        scope_locked = False
        if self.user_context and not self.user_context.is_superuser:
            actor_scope = get_user_scope(self.user_context)
            if actor_scope is not None:
                fixed_scope = actor_scope
                scope_locked = True
        _configure_staff_tier_preview(self, fixed_scope=fixed_scope, scope_locked=scope_locked)


        self.helper = FormHelper()
        self.helper.form_tag = False
        
        from dlux.utils import is_scope_enabled
        scope_visible = 'scope' in self.fields and getattr(self.fields['scope'].widget, 'input_type', '') != 'hidden' and is_scope_enabled()

        step_1_fields = [
            Row(Field("username", css_class="form-control")),
            Row(Field("password1", css_class="form-control")),
            Row(Field("password2", css_class="form-control")),
            HTML("<hr>"),
            Row(
                Div(Field("first_name", css_class="form-control"), css_class="col-md-6"),
                Div(Field("last_name", css_class="form-control"), css_class="col-md-6"),
                css_class="row"
            ),
            Row(
                Div(Field("phone", css_class="form-control"), css_class="col-md-6"),
                Div(Field("email", css_class="form-control"), css_class="col-md-6"),
                css_class="row"
            ),
            Field("is_active"),
            Field("force_password_change"),
        ]
        
        if scope_visible:
            step_1_fields.append(Row(Field("scope", css_class="form-control")))
            
        step_1_div = Div(*step_1_fields, css_class="wizard-step wizard-step-1")
        
        step_2_fields = [
            HTML("<hr>"),
            Field("permissions", css_class="col-12")
        ]
        step_2_div = Div(*step_2_fields, css_class="wizard-step wizard-step-2 d-none")

        actions = _build_wizard_actions(
            s,
            submit_label=s.get('btn_add', 'Add'),
            submit_icon='bi-person-plus-fill',
        )

        self.helper.layout = Layout(step_1_div, step_2_div, actions)

    def save(self, commit=True):
        user = super().save(commit=False)
        # We need to save the user first to get an ID for the OneToOne relationship
        if commit:
            user.save()
            # Manually set permissions
            permissions = list(self.cleaned_data["permissions"])
            
            # Auto-grant auth.view_user permission when user is staff
            if user.is_staff:
                from django.contrib.auth.models import Permission
                try:
                    view_user_perm = Permission.objects.get(
                        content_type__app_label='auth',
                        codename='view_user'
                    )
                    if view_user_perm not in permissions:
                        permissions.append(view_user_perm)
                except Permission.DoesNotExist:
                    pass
            
            user.user_permissions.set(permissions)
            
            # Save Profile fields
            Profile = apps.get_model('dlux', 'Profile')
            # Check if profile already exists (via signal) or create it
            profile, created = Profile.all_objects.get_or_create(user=user)
            profile.phone = self.cleaned_data.get('phone')
            user_scope = get_user_scope(self.user_context)
            if self.user_context and not self.user_context.is_superuser and user_scope:
                profile.scope = user_scope
            elif self.cleaned_data.get('scope'):
                profile.scope = self.cleaned_data.get('scope')
            # If empty scope, we do not overwrite since signal may have auto-assigned one
            preferences = dict(profile.preferences or {})
            if self.cleaned_data.get('force_password_change'):
                preferences['force_password_change'] = True
            else:
                preferences.pop('force_password_change', None)
            profile.preferences = preferences
            profile.save()
            
        return user


# Custom User Editing form layout
class CustomUserChangeForm(UserChangeForm):
    handles_save = True
    refresh_parent = True

    phone = forms.CharField(max_length=15, required=False)
    scope = forms.ModelChoiceField(queryset=None, required=False, label="Scope")

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]

    def __init__(self, *args, **kwargs):
        self.user_context = kwargs.pop('user', None)
        user_instance = kwargs.get('instance')
        super().__init__(*args, **kwargs)
        
        Scope = apps.get_model('dlux', 'Scope')
        self.fields['scope'].queryset = Scope.objects.all()

        # Initialize Profile Fields
        if user_instance and hasattr(user_instance, 'profile'):
            self.fields['phone'].initial = user_instance.profile.phone
            self.fields['scope'].initial = user_instance.profile.scope

        # Labels
        s = get_strings()
        self.modal_heading = s.get('edit_user_label', 'Edit User')

        self.fields["username"].label = s.get('form_username', "Username")
        self.fields["email"].label = s.get('form_email', "Email")
        self.fields["first_name"].label = s.get('form_firstname', "First Name")
        self.fields["last_name"].label = s.get('form_lastname', "Last Name")
        self.fields["is_active"].label = s.get('form_is_active', "Active")
        self.fields["phone"].label = s.get('form_phone', "Phone Number")
        self.fields["scope"].label = s.get('form_scope', "Scope")
        
        self.fields["username"].help_text = s.get('help_username', "Username must be unique. 150 characters or fewer. Letters, digits and @/./+/-/_ only.")
        self.fields["email"].help_text = s.get('help_email', "Enter a valid email address (optional).")
        self.fields["is_active"].help_text = s.get('help_is_active', "Designates whether this user should be treated as active.")
        self.fields["phone"].help_text = s.get('help_phone', "Enter a valid phone number (optional).")
        self.fields["scope"].help_text = ""
        _apply_autocomplete_attrs(
            self,
            {
                'username': 'username',
                'first_name': 'given-name',
                'last_name': 'family-name',
                'email': 'email',
                'phone': 'tel',
            },
        )

        if self.user_context and not self.user_context.is_superuser:
            if self.user_context == user_instance:
                if self.user_context.is_staff:
                    self.fields['scope'].disabled = True
                    self.fields['is_active'].disabled = True
                    self.fields['scope'].help_text = s.get('help_scope_self', "You cannot change your own scope to prevent removing your own admin access.")
            
            # Central Staff: cannot edit scope of any user (can only edit scopeless users)
            if is_central_staff(self.user_context):
                target_scope = getattr(user_instance.profile, 'scope', None) if user_instance and hasattr(user_instance, 'profile') else None
                if target_scope is not None:
                    # Cannot edit scoped users at all - hide scope field
                    self.fields['scope'].widget = forms.HiddenInput()
                else:
                    # Can edit scopeless user but cannot assign a scope - hide scope field
                    self.fields['scope'].widget = forms.HiddenInput()
                    self.fields['scope'].initial = None

        self.fields["email"].required = False

        self.helper = FormHelper()
        self.helper.form_tag = False
        
        from dlux.utils import is_scope_enabled
        scope_visible = 'scope' in self.fields and getattr(self.fields['scope'].widget, 'input_type', '') != 'hidden' and is_scope_enabled()
        
        layout_fields = [
            Row(Field("username", css_class="form-control")),            
            HTML("<hr>"),
            Row(
                Div(Field("first_name", css_class="form-control"), css_class="col-md-6"),
                Div(Field("last_name", css_class="form-control"), css_class="col-md-6"),
                css_class="row"
            ),
            Row(
                Div(Field("phone", css_class="form-control"), css_class="col-md-6"),
                Div(Field("email", css_class="form-control"), css_class="col-md-6"),
                css_class="row"
            ),
            Field("is_active")
        ]
        
        if scope_visible:
            layout_fields.append(Row(Field("scope", css_class="form-control")))

        actions = _build_submit_actions(
            s,
            submit_label=s.get('btn_update', 'Update'),
            submit_icon='bi-person-check-fill',
        )
        
        self.helper.layout = Layout(*layout_fields, actions)

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            
            # Save Profile fields
            Profile = apps.get_model('dlux', 'Profile')
            profile, created = Profile.all_objects.get_or_create(user=user)
            profile.phone = self.cleaned_data.get('phone')
            user_scope = get_user_scope(self.user_context)
            if self.user_context and not self.user_context.is_superuser and user_scope:
                profile.scope = user_scope
            else:
                if 'scope' in self.changed_data:
                    profile.scope = self.cleaned_data.get('scope')
            profile.save()
            
        return user


class CustomUserPermissionsForm(UserChangeForm):
    handles_save = True
    refresh_parent = True

    permissions = forms.ModelMultipleChoiceField(
        queryset=get_assignable_permissions_queryset(),
        required=False,
        widget=GroupedPermissionWidget,
        label="Permissions"
    )

    class Meta:
        model = User
        fields = ["is_staff", "permissions"]

    def __init__(self, *args, **kwargs):
        self.user_context = kwargs.pop('user', None)
        user_instance = kwargs.get('instance')
        super().__init__(*args, **kwargs)

        s = get_strings()
        self.modal_heading = s.get('edit_permissions_label', 'Edit Permissions')
        self.fields['permissions'].widget.translations = s

        _apply_assignable_permission_filter(self, self.user_context)

        self.fields["is_staff"].label = s.get('form_is_staff', "Enable Staff Access")
        self.fields["is_staff"].help_text = s.get('help_is_staff', "Enables staff access. The final tier depends on scope and selected permissions.")
        self.fields["permissions"].label = s.get('form_permissions', "Permissions")

        if user_instance:
            self.fields["permissions"].initial = user_instance.user_permissions.all()

        lock_scope = bool(
            self.user_context
            and not self.user_context.is_superuser
            and hasattr(self.user_context, 'profile')
            and self.user_context.profile.scope
        )

        if self.user_context and not self.user_context.is_superuser:
            if self.user_context == user_instance and self.user_context.is_staff:
                self.fields['is_staff'].disabled = True
                filtered_qs = self.fields['permissions'].queryset.exclude(codename='manage_staff')
                self.fields['permissions'].queryset = filtered_qs
                self.fields['permissions'].widget._filtered_queryset = filtered_qs

            if not self.user_context.has_perm('dlux.manage_staff'):
                self.fields['is_staff'].disabled = True
                self.fields['is_staff'].help_text = s.get(
                    'help_is_staff_no_perm',
                    "You don't have permission to change this user's staff status.",
                )

        if lock_scope:
            filtered_qs = self.fields['permissions'].queryset.exclude(codename='manage_staff')
            self.fields['permissions'].queryset = filtered_qs
            self.fields['permissions'].widget._filtered_queryset = filtered_qs
        
        # Central Staff (and any non-superuser without manage_scopes): cannot assign manage_scopes permission
        # Only superusers can create Global Staff by assigning manage_scopes
        if self.user_context and not self.user_context.is_superuser:
            if not self.user_context.has_perm('dlux.manage_scopes'):
                filtered_qs = self.fields['permissions'].queryset.exclude(codename='manage_scopes')
                self.fields['permissions'].queryset = filtered_qs
                # Store filtered queryset for widget to use
                self.fields['permissions'].widget._filtered_queryset = filtered_qs

        _attach_is_staff_permission(self, self.fields['permissions'].widget.attrs.get('id'))
        preview_scope = getattr(getattr(user_instance, 'profile', None), 'scope', None)
        _configure_staff_tier_preview(self, fixed_scope=preview_scope, scope_locked=True)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("permissions", css_class="col-12"),
            _build_submit_actions(
                s,
                submit_label=s.get('btn_update', 'Update'),
                submit_icon='bi-shield-check',
            ),
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            permissions = list(self.cleaned_data["permissions"])
            
            # Central Staff cannot assign manage_scopes permission
            if self.user_context and is_central_staff(self.user_context):
                from dlux.utils import strip_manage_scopes_permissions
                permissions = strip_manage_scopes_permissions(permissions)
            
            # Auto-grant auth.view_user permission when user is staff
            if user.is_staff:
                from django.contrib.auth.models import Permission
                try:
                    view_user_perm = Permission.objects.get(
                        content_type__app_label='auth',
                        codename='view_user'
                    )
                    if view_user_perm not in permissions:
                        permissions.append(view_user_perm)
                except Permission.DoesNotExist:
                    pass
            
            user.user_permissions.set(permissions)
        return user


class UserModalForm:
    """
    Smart proxy form for the Dynamic Modal system.
    Delegates to CustomUserCreationForm (create) or CustomUserChangeForm (edit)
    based on whether an instance with a PK is provided.
    """
    handles_save = True  # Tells DynamicModalManagerView to call save(commit=True) directly
    refresh_parent = True # Tells dynamic_modals.js to reload the page on success

    def __new__(cls, *args, user=None, **kwargs):
        instance = kwargs.get('instance')

        if instance and instance.pk:
            # Edit mode — use change form
            form_cls = CustomUserChangeForm
        else:
            # Create mode — use creation form
            form_cls = CustomUserCreationForm
            # Remove instance for creation form (UserCreationForm doesn't expect it)
            kwargs.pop('instance', None)

        kwargs['user'] = user
        form = form_cls(*args, **kwargs)
        form.handles_save = True
        # Ensure no <form> tag in modal context (modal template provides it)
        if hasattr(form, 'helper'):
            form.helper.form_tag = False
        return form


class DluxPasswordMustChangeMixin:
    unchanged_password_error_code = 'password_unchanged'

    def clean(self):
        cleaned_data = super().clean()
        password = self.cleaned_data.get('new_password2')
        user = getattr(self, 'user', None)
        if password and user is not None and user.check_password(password):
            s = get_strings()
            self.add_error(
                'new_password2',
                ValidationError(
                    s.get('err_password_unchanged', 'New password must be different from the current password.'),
                    code=self.unchanged_password_error_code,
                ),
            )
        return cleaned_data


# Custom User Reset Password form layout
class ResetPasswordForm(DluxPasswordMustChangeMixin, SetPasswordForm):
    username = forms.CharField(label="Username", widget=forms.TextInput(attrs={"readonly": "readonly"}))

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        s = get_strings()
        self.fields['username'].initial = user.username
        self.fields['username'].label = s.get('form_username', "Username")
        
        self.helper = FormHelper()
        self.fields["new_password1"].label = s.get('form_new_password', "New Password")
        self.fields['new_password1'].help_text = mark_safe(s.get('help_password_common', "Password should not be similar to..."))

        self.fields["new_password2"].label = s.get('form_confirm_new_password', "Confirm New Password")
        self.fields['new_password2'].help_text = s.get('help_password_match', "Enter the same password as...")
        _apply_autocomplete_attrs(
            self,
            {
                'username': 'username',
                'new_password1': 'new-password',
                'new_password2': 'new-password',
            },
        )
        self.helper.layout = Layout(
            Div(
                Field('username', css_class='col-md-12'),
                Field('new_password1', css_class='col-md-12'),
                Field('new_password2', css_class='col-md-12'),
                css_class='row'
            ),
            Submit('submit', s.get('btn_change_password', 'Change Password'), css_class='btn btn-danger rounded-pill'),
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
        return user


class UserProfileEditForm(forms.ModelForm):
    # Add fields from profile
    phone = forms.CharField(max_length=15, required=False, label="Phone Number")
    profile_picture = forms.ImageField(required=False, label="Profile Picture")

    handles_save = True  # Indicate to DynamicModalManagerView to call save(commit=True) directly
    refresh_parent = True # Force page reload on success

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']

    def __init__(self, *args, user=None, **kwargs):
        # Extract instance and pop 'user' before super().__init__
        user_instance = kwargs.get('instance')
        self.user_context = user
        super().__init__(*args, **kwargs)
        
        s = get_strings()

        if user_instance and hasattr(user_instance, 'profile'):
            self.fields['phone'].initial = user_instance.profile.phone
            self.fields['profile_picture'].initial = user_instance.profile.profile_picture

        self.fields['username'].disabled = True
        self.fields['username'].label = s.get('form_username', "Username")
        self.fields['first_name'].label = s.get('form_firstname', "First Name")
        self.fields['last_name'].label = s.get('form_lastname', "Last Name")
        self.fields['email'].label = s.get('form_email', "Email")
        self.fields['phone'].label = s.get('form_phone', "Phone Number")
        self.fields['profile_picture'].label = s.get('form_profile_pic', "Profile Picture")
        self.fields['profile_picture'].widget = _build_archive_file_widget(
            attrs={'accept': 'image/*'},
            field_label=self.fields['profile_picture'].label,
        )

        
        self.fields["email"].required = False
        _apply_autocomplete_attrs(
            self,
            {
                'username': 'username',
                'first_name': 'given-name',
                'last_name': 'family-name',
                'email': 'email',
                'phone': 'tel',
            },
        )

        self.helper = FormHelper()
        self.helper.form_tag = False
        
        layout_blocks = [
            build_archive_file_field("profile_picture"),
            Row(Field("username", css_class="form-control")),            
            HTML("<hr>"),
            Row(
                Div(Field("first_name", css_class="form-control"), css_class="col-md-6"),
                Div(Field("last_name", css_class="form-control"), css_class="col-md-6"),
                css_class="row"
            ),
            Row(
                Div(Field("phone", css_class="form-control"), css_class="col-md-6"),
                Div(Field("email", css_class="form-control"), css_class="col-md-6"),
                css_class="row"
            ),
            HTML("<hr>"),
            FormActions(
                HTML(
                    f"""
                    <button type="submit" class="btn btn-success rounded-pill">
                        <i class="bi bi-save text-light me-1 h4"></i>
                        {s.get('btn_update', 'Update')}
                    </button>
                    """
                ),
                HTML(
                    f"""
                    <button type="button" class="btn btn-danger rounded-pill" data-bs-dismiss="modal">
                        <i class="bi bi-x-circle text-light me-1 h4"></i> {s.get('btn_cancel', 'Cancel')}
                    </button>
                    """
                )
            )
        ]
        
        self.helper.layout = Layout(*layout_blocks)

    def clean_profile_picture(self):
        profile_picture = self.cleaned_data.get('profile_picture')
        if profile_picture:
            try:
                # Just check if it can be opened by Pillow
                img = Image.open(profile_picture)
                # No need to verify() and raise error for size anymore
                # as the model handles resizing automatically.
                # However, we must reset the file pointer for further use.
                if hasattr(profile_picture, 'seek'):
                    profile_picture.seek(0)
            except Exception:
                raise ValidationError("Invalid image file.")
        return profile_picture

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            
            Profile = apps.get_model('dlux', 'Profile')
            profile, created = Profile.all_objects.get_or_create(user=user)
            
            profile.phone = self.cleaned_data.get('phone')
            if self.cleaned_data.get('profile_picture'):
                profile.profile_picture = self.cleaned_data.get('profile_picture')
            profile.save()
            
        return user


class CustomPasswordChangeForm(DluxPasswordMustChangeMixin, PasswordChangeForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        s = get_strings()
        
        # Current Password
        self.fields['old_password'].label = s.get('form_old_password', "Current Password")
        self.fields['old_password'].widget.attrs.pop('dir', None) # Remove fixed RTL 
        
        # New Password 1
        self.fields['new_password1'].label = s.get('form_new_password', "New Password")
        self.fields['new_password1'].help_text = mark_safe(s.get('help_password_common', "Password should not be similar to..."))
        self.fields['new_password1'].widget.attrs.pop('dir', None)

        # New Password 2
        self.fields['new_password2'].label = s.get('form_confirm_new_password', "Confirm New Password")
        self.fields['new_password2'].help_text = s.get('help_password_match', "Enter the same password as...")
        self.fields['new_password2'].widget.attrs.pop('dir', None)
        _apply_autocomplete_attrs(
            self,
            {
                'old_password': 'current-password',
                'new_password1': 'new-password',
                'new_password2': 'new-password',
            },
        )

class ScopeForm(forms.ModelForm):
    class Meta:
        model = apps.get_model('dlux', 'Scope')
        fields = ['name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        s = get_strings()
        # But scope form often used in modals?
        # If we have request in kwargs we can use it, but typically ModelForms don't get request.
        # Fallback to default is okay for now or we can inject request if needed.
        self.fields['name'].label = s.get('form_scope_name', "Scope Name")
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field('name', css_class='col-12'),
        )


class SystemSettingsForm(forms.ModelForm):
    _SCHEMA_SIMPLE_CONFIG_GROUPS = (
        'auth_config',
        'registration_config',
        'public_root_config',
        'layout_config',
        'client_ip_config',
        'backup_config',
    )

    home_url_discovered = forms.ChoiceField(
        required=False,
        choices=(),
    )
    public_root_url_discovered = forms.ChoiceField(
        required=False,
        choices=(),
    )
    settings_import_file = forms.FileField(
        required=False,
    )
    settings_import_processed = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.HiddenInput(),
    )
    default_language = forms.CharField(
        required=True,
        widget=forms.HiddenInput(),
    )
    system_names = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    default_theme = forms.ChoiceField(
        required=True,
        choices=[(value, value) for value, _, _ in THEME_CHOICES],
        widget=forms.HiddenInput(),
    )
    allowed_themes = forms.MultipleChoiceField(
        required=False,
        choices=[(value, value) for value, _, _ in THEME_CHOICES],
    )
    allow_user_theme_override = forms.BooleanField(
        required=False,
        initial=True,
    )
    allow_user_language_override = forms.BooleanField(
        required=False,
        initial=True,
    )
    allowed_fonts = forms.MultipleChoiceField(
        required=False,
        choices=FONT_CHOICES,
    )
    allow_user_font_override = forms.BooleanField(
        required=False,
        initial=True,
    )
    default_fonts = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    default_table_density = forms.ChoiceField(
        required=True,
        choices=TABLE_DENSITY_CHOICES,
        widget=forms.HiddenInput(),
    )
    languages = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    translations_override = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    email_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    email_config_transport = forms.ChoiceField(
        required=False,
        choices=(
            ('relay', 'Internal SMTP relay'),
            ('direct', 'Direct SMTP from web service'),
        ),
    )
    email_config_secret_storage = forms.ChoiceField(
        required=False,
        choices=(
            ('encrypted_db', 'Encrypted database secret'),
            ('env', 'Environment / secrets'),
        ),
    )
    email_config_provider_preset = forms.ChoiceField(
        required=False,
        choices=(
            ('custom', 'Custom / manual'),
            ('gmail', 'Gmail'),
            ('outlook', 'Outlook / Office 365'),
            ('ses', 'Amazon SES'),
            ('mailgun', 'Mailgun'),
            ('relay', 'Internal relay'),
        ),
    )
    email_config_host = forms.CharField(required=False, max_length=255)
    email_config_port = forms.IntegerField(required=False, min_value=1, max_value=65535)
    email_config_use_tls = forms.BooleanField(required=False, initial=True)
    email_config_use_ssl = forms.BooleanField(required=False, initial=False)
    email_config_username = forms.CharField(required=False, max_length=255)
    email_config_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
    )
    email_config_default_from_email = forms.EmailField(required=False)
    email_config_failure_recipients = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
    )
    email_config_test_recipient = forms.EmailField(required=False)
    sidebar_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    navbar_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    log_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    profile_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    backup_config = forms.CharField(widget=forms.HiddenInput(), required=False)
    backup_scheduled_enabled = forms.BooleanField(required=False, initial=False)
    backup_schedule_interval_hours = forms.IntegerField(required=False, min_value=1, max_value=8760, initial=24)
    backup_retention_days = forms.IntegerField(required=False, min_value=0, max_value=3650, initial=0)
    backup_max_backups_to_keep = forms.IntegerField(required=False, min_value=0, max_value=10000, initial=0)
    backup_auto_export_target = forms.CharField(required=False, max_length=180, initial='dlux_backups')
    sidebar_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )
    sidebar_enable_reorder = forms.BooleanField(
        required=False,
        initial=True,
    )
    sidebar_enable_toolbar = forms.BooleanField(
        required=False,
        initial=True,
    )
    sidebar_show_icons = forms.BooleanField(
        required=False,
        initial=True,
    )
    sidebar_density = forms.ChoiceField(
        required=False,
        choices=SIDEBAR_DENSITY_CHOICES,
        widget=forms.HiddenInput(),
    )
    sidebar_allow_user_density = forms.BooleanField(
        required=False,
        initial=True,
    )
    sidebar_collapse_mode = forms.ChoiceField(
        required=False,
        choices=SIDEBAR_COLLAPSE_MODE_CHOICES,
        initial=DEFAULT_SIDEBAR_COLLAPSE_MODE,
    )
    navbar_enabled = forms.BooleanField(
        required=False,
        initial=False,
    )
    navbar_default_mode = forms.ChoiceField(
        required=False,
        choices=NAVBAR_MODE_CHOICES,
        initial=DEFAULT_NAVBAR_MODE,
    )
    navbar_allow_user_mode_override = forms.BooleanField(
        required=False,
        initial=True,
    )
    titlebar_show_logo = forms.BooleanField(
        required=False,
        initial=True,
    )
    titlebar_show_title = forms.BooleanField(
        required=False,
        initial=True,
    )
    titlebar_show_home_button = forms.BooleanField(
        required=False,
        initial=True,
    )
    titlebar_hide_on_public_unauthenticated_index = forms.BooleanField(
        required=False,
        initial=False,
    )
    titlebar_home_shape = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_HOME_SHAPE_CHOICES,
        initial='circle',
    )
    titlebar_user_hub_style = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_USER_HUB_STYLE_CHOICES,
        initial=TITLEBAR_USER_HUB_STYLE_DROPDOWN,
    )
    titlebar_actions_order = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )
    titlebar_title_align = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_ALIGN_CHOICES,
        initial='start',
    )
    titlebar_title_size = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_SIZE_CHOICES,
        initial='md',
    )
    titlebar_height = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_HEIGHT_CHOICES,
        initial='balanced',
    )
    titlebar_surface = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_SURFACE_CHOICES,
        initial='default',
    )
    titlebar_logo_treatment = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_LOGO_TREATMENT_CHOICES,
        initial='none',
    )
    titlebar_logo_treatment_shape = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_LOGO_TREATMENT_SHAPE_CHOICES,
        initial='soft',
    )
    notification_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    notifications_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )
    notification_flash_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )
    notification_flash_position = forms.ChoiceField(
        required=False,
        choices=(
            ('top_center', 'Top center'),
            ('top_start', 'Top start'),
            ('top_end', 'Top end'),
            ('titlebar_end', 'Titlebar end'),
            ('bottom_start', 'Bottom start'),
            ('bottom_end', 'Bottom end'),
        ),
        initial='top_center',
    )
    notification_flash_size = forms.ChoiceField(
        required=False,
        choices=(
            ('compact', 'Compact'),
            ('balanced', 'Balanced'),
            ('prominent', 'Prominent'),
        ),
        initial='balanced',
    )
    notification_flash_text_size = forms.ChoiceField(
        required=False,
        choices=(
            ('sm', 'Small'),
            ('md', 'Medium'),
            ('lg', 'Large'),
        ),
        initial='md',
    )
    notification_flash_timeout_ms = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=60000,
        initial=3200,
    )
    notification_flash_max_visible = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10,
        initial=3,
    )
    notification_drawer_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )
    notification_badge_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )
    notification_bridge_enabled = forms.BooleanField(
        required=False,
        initial=False,
    )
    notification_email_enabled = forms.BooleanField(
        required=False,
        initial=False,
    )
    notification_email_default = forms.BooleanField(
        required=False,
        initial=False,
    )
    notification_auto_crud_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )
    notification_auto_create = forms.BooleanField(
        required=False,
        initial=True,
    )
    notification_auto_update = forms.ChoiceField(
        required=False,
        choices=(
            ('off', 'Off'),
            ('summary', 'Summary'),
            ('full', 'Full'),
        ),
        initial='summary',
    )
    notification_auto_delete = forms.BooleanField(
        required=False,
        initial=True,
    )
    login_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    login_style = forms.ChoiceField(
        required=False,
        choices=(
            ('split', ''),
            ('centered', ''),
            ('minimal', ''),
            ('fullpage', ''),
        ),
        initial='split',
    )
    login_show_logo = forms.BooleanField(
        required=False,
        initial=True,
    )
    login_banner_color = forms.CharField(
        required=False,
        initial='',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '#2b3035',
            'pattern': r'^(#[0-9a-fA-F]{3,8}|[a-z]+)?$',
            'spellcheck': 'false',
        }),
    )
    login_logo_treatment = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_LOGO_TREATMENT_CHOICES,
        initial='none',
    )
    login_logo_treatment_shape = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_LOGO_TREATMENT_SHAPE_CHOICES,
        initial='soft',
    )
    # login_hero_message_{lang} fields are added dynamically per language in __init__
    email_2fa = forms.BooleanField(
        required=False,
        initial=False,
    )
    prevent_multiple_active_sessions = forms.BooleanField(
        required=False,
        initial=False,
    )
    login_lockout_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )
    enforce_strong_passwords = forms.BooleanField(
        required=False,
        initial=False,
    )
    auth_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    client_ip_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    client_ip_mode = forms.ChoiceField(
        required=False,
        choices=(),
    )
    client_ip_trusted_proxy_hops = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=8,
    )
    client_ip_custom_header = forms.CharField(
        required=False,
        max_length=255,
    )
    public_root = forms.BooleanField(
        required=False,
        initial=False,
    )
    public_root_split_enabled = forms.BooleanField(
        required=False,
        initial=False,
    )
    public_root_url = forms.CharField(
        required=False,
        max_length=255,
    )
    public_registration_enabled = forms.BooleanField(
        required=False,
        initial=False,
    )
    registration_activation_mode = forms.ChoiceField(
        required=False,
        choices=REGISTRATION_ACTIVATION_CHOICES,
    )
    registration_throttle_enabled = forms.BooleanField(
        required=False,
        initial=True,
    )

    class Meta:
        model = apps.get_model('dlux', 'SystemSettings')
        fields = [
            'system_names',
            'logo',
            'favicon',
            'home_url',
            'default_language',
            'default_theme',
            'allowed_themes',
            'allow_user_theme_override',
            'allowed_fonts',
            'allow_user_font_override',
            'default_fonts',
            'allow_user_language_override',
            'default_table_density',
            'auth_config',
            'client_ip_config',
            'public_root',
            'public_root_split_enabled',
            'public_root_url',
            'public_registration_enabled',
            'registration_activation_mode',
            'registration_throttle_enabled',
            'email_config',
            'languages',
            'translations_override',
            'sidebar_config',
            'navbar_config',
            'log_config',
            'profile_config',
            'backup_config',
            'titlebar_config',
            'notification_config',
            'login_config',
        ]

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

    def __init__(self, *args, request=None, user=None, mode='modal', **kwargs):
        self.request = request if request is not None else kwargs.pop('request', None)
        self._user = user if user is not None else kwargs.pop('user', None)
        self.mode = mode if mode is not None else kwargs.pop('mode', 'modal')
        super().__init__(*args, **kwargs)
        self.refresh_parent = True
        self.extra_form_class = 'dlux-system-setup-form'
        self.single_step_mode = False
        self.single_step_index = None
        s = get_strings()
        if hasattr(self, 'translations') and self.translations:
            s = self.translations

        if self.mode != 'setup' and self.request is not None:
            raw_step = self.request.GET.get('step')
            try:
                parsed_step = int(raw_step)
            except (TypeError, ValueError):
                parsed_step = None
            if parsed_step in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11):
                self.single_step_mode = True
                self.single_step_index = parsed_step
        if self.mode != 'setup' and self.single_step_mode:
            # Single-step modal posts can legitimately omit values owned by
            # another wizard step; field-level required validation must not fire
            # before the step-preservation cleaners get a chance to restore them.
            self.fields['default_theme'].required = False
            self.fields['default_table_density'].required = False

        from dlux.discovery import discover_sidebar_catalog, sanitize_sidebar_config
        from dlux.utils import get_system_config

        config = get_system_config()
        current_languages = normalize_language_catalog(config.get('languages', {}))
        if isinstance(getattr(self.instance, 'languages', None), dict):
            current_languages = normalize_language_catalog(current_languages, self.instance.languages)
        discovered_theme_choices = [(value, value) for value, _, _ in get_theme_choices()]
        self.fields['default_theme'].choices = discovered_theme_choices
        self.fields['allowed_themes'].choices = discovered_theme_choices

        self.fields['system_names'].label = s.get('form_sys_system_names', "System names")
        self.fields['settings_import_file'].label = s.get('form_sys_import_config', "Import system setup file")
        self.fields['settings_import_file'].help_text = s.get(
            'help_sys_import_config',
            'Optional: choose a Dlux-exported JSON setup file to populate these settings.',
        )
        self.fields['settings_import_file'].widget = _build_archive_file_widget(
            attrs={
                'accept': 'application/json,.json',
                'data-settings-import-file': 'true',
            },
            field_label=self.fields['settings_import_file'].label,
        )
        self.fields['languages'].label = s.get('form_sys_languages', "Available languages")
        self.fields['translations_override'].label = s.get('form_sys_translations', "Translation overrides")
        self.fields['home_url'].required = False
        self.fields['home_url'].label = s.get('form_sys_home_url', "Home URL")
        self.fields['home_url'].help_text = s.get(
            'help_sys_home_url',
            'Choose the main Home URL. It remains the authenticated home destination and login redirect even when anonymous public-root traffic is split elsewhere.',
        )
        self.fields['home_url'].widget.attrs.update({
            'class': 'form-control glass-input',
            'dir': 'ltr',
            'placeholder': DEFAULT_HOME_URL,
        })
        self.fields['home_url_discovered'].label = s.get('form_sys_home_url_discovered', "Select from discovered pages")
        self.fields['home_url_discovered'].help_text = s.get(
            'help_sys_home_url_discovered',
            'Optional: select a discovered page to auto-fill the Home URL, or leave it blank and enter a custom URL.',
        )
        self.fields['home_url_discovered'].widget.attrs.update({
            'class': 'form-select glass-input',
        })
        self.fields['public_root_url'].required = False
        self.fields['public_root_url'].label = s.get('form_sys_public_root_url', 'Anonymous Public Root URL')
        self.fields['public_root_url'].help_text = s.get(
            'help_sys_public_root_url',
            'Optional: when separate public-root mode is enabled, anonymous users landing on `/` are redirected here instead of the main Home URL.',
        )
        self.fields['public_root_url'].widget.attrs.update({
            'class': 'form-control glass-input',
            'dir': 'ltr',
            'placeholder': '/',
        })
        self.fields['public_root_url_discovered'].label = s.get(
            'form_sys_public_root_url_discovered',
            'Choose anonymous public root from discovered pages',
        )
        self.fields['public_root_url_discovered'].help_text = s.get(
            'help_sys_public_root_url_discovered',
            'Optional: select a discovered page to auto-fill the anonymous public-root destination, or leave it blank and enter a custom URL.',
        )
        self.fields['public_root_url_discovered'].widget.attrs.update({
            'class': 'form-select glass-input',
        })
        self.fields['default_language'].label = s.get('form_sys_default_lang', "Default Language")
        self.fields['default_theme'].label = s.get('form_sys_default_theme', "Default Theme")
        self.fields['allowed_themes'].label = s.get('form_sys_allowed_themes', 'Allowed themes')
        self.fields['allowed_themes'].help_text = s.get(
            'help_sys_allowed_themes',
            'Choose which themes are available in this project. The default theme must remain enabled.',
        )
        self.fields['allow_user_theme_override'].label = s.get('form_sys_allow_user_theme_override', 'Allow user theme override')
        self.fields['allow_user_theme_override'].help_text = s.get(
            'help_sys_allow_user_theme_override',
            'Allow users to switch between the allowed themes at runtime from Options and the sidebar toolbar.',
        )
        self.fields['allow_user_language_override'].label = s.get('form_sys_allow_user_language_override', 'Allow user language override')
        self.fields['allow_user_language_override'].help_text = s.get(
            'help_sys_allow_user_language_override',
            'Allow users to change their display language from Options. When disabled, the system default language is enforced.',
        )
        self.fields['allowed_fonts'].label = s.get('form_sys_allowed_fonts', 'Allowed fonts')
        self.fields['allowed_fonts'].help_text = s.get(
            'help_sys_allowed_fonts',
            'Choose which fonts are available in this project. The default fonts for each language must remain enabled.',
        )
        self.fields['allow_user_font_override'].label = s.get('form_sys_allow_user_font_override', 'Allow user font override')
        self.fields['allow_user_font_override'].help_text = s.get(
            'help_sys_allow_user_font_override',
            'Allow users to switch between the allowed fonts at runtime from Options.',
        )
        self.fields['default_fonts'].label = s.get('form_sys_default_fonts', 'Default fonts by language')
        self.fields['default_table_density'].label = s.get('form_sys_default_table_density', "Default Table Density")
        self.fields['default_table_density'].help_text = s.get(
            'help_sys_default_table_density',
            'Choose the default table density for new users; each user can still override it later from Options.',
        )
        self.fields['default_table_density'].choices = (
            ('dense', s.get('table_density_dense', 'Dense')),
            (DEFAULT_TABLE_DENSITY, s.get('table_density_balanced', 'Balanced')),
            ('roomy', s.get('table_density_roomy', 'Roomy')),
        )
        self.fields['logo'].label = s.get('form_sys_logo', "System Logo (Logo)")
        self.fields['favicon'].label = s.get('form_sys_favicon', "Site Icon (Favicon)")
        self.fields['logo'].widget = _build_archive_file_widget(
            attrs={'accept': 'image/*'},
            field_label=self.fields['logo'].label,
        )
        self.fields['favicon'].widget = _build_archive_file_widget(
            attrs={'accept': 'image/*'},
            field_label=self.fields['favicon'].label,
        )
        self.fields['sidebar_config'].label = s.get('form_sys_sidebar', "Sidebar Configuration")
        self.fields['sidebar_enabled'].label = s.get('form_sys_sidebar_enabled', 'Enable sidebar')
        self.fields['sidebar_enabled'].help_text = s.get(
            'help_sys_sidebar_enabled',
            'Show the runtime sidebar. When disabled, content expands and sidebar toolbar controls are ignored.',
        )
        self.fields['sidebar_enable_reorder'].label = s.get('form_sys_sidebar_enable_reorder', 'Enable sidebar reorder')
        self.fields['sidebar_enable_reorder'].help_text = s.get(
            'help_sys_sidebar_enable_reorder',
            'Show the quick reorder control in the sidebar toolbar so users can rearrange sidebar items from the UI.',
        )
        self.fields['sidebar_enable_toolbar'].label = s.get('form_sys_sidebar_enable_toolbar', 'Enable sidebar toolbar')
        self.fields['sidebar_enable_toolbar'].help_text = s.get(
            'help_sys_sidebar_enable_toolbar',
            'Show the sidebar toolbar that contains the quick theme picker, reorder toggle, and dynamic section manager shortcut.',
        )
        self.fields['sidebar_show_icons'].label = s.get('form_sys_sidebar_show_icons', 'Show sidebar icons')
        self.fields['sidebar_show_icons'].help_text = s.get(
            'help_sys_sidebar_show_icons',
            'Show icons beside sidebar items and folders in the expanded sidebar.',
        )
        self.fields['sidebar_density'].label = s.get('form_sys_sidebar_density', 'Sidebar density')
        self.fields['sidebar_density'].help_text = s.get(
            'help_sys_sidebar_density',
            'Choose the default row density for the sidebar.',
        )
        self.fields['sidebar_density'].choices = (
            ('dense', s.get('table_density_dense', 'Dense')),
            (DEFAULT_SIDEBAR_DENSITY, s.get('table_density_balanced', 'Balanced')),
            ('roomy', s.get('table_density_roomy', 'Roomy')),
        )
        self.fields['sidebar_allow_user_density'].label = s.get('form_sys_sidebar_allow_user_density', 'Allow user sidebar density override')
        self.fields['sidebar_allow_user_density'].help_text = s.get(
            'help_sys_sidebar_allow_user_density',
            'Allow users to change sidebar density from the sidebar toolbar at runtime.',
        )
        self.fields['sidebar_collapse_mode'].label = s.get('form_sys_sidebar_collapse_mode', 'Desktop collapse mode')
        self.fields['sidebar_collapse_mode'].help_text = s.get(
            'help_sys_sidebar_collapse_mode',
            'Choose how the sidebar behaves when collapsed on large screens.',
        )
        self.fields['sidebar_collapse_mode'].choices = (
            ('icons', s.get('sidebar_collapse_icons', 'Icons only')),
            ('hidden', s.get('sidebar_collapse_hidden', 'Hide completely')),
            ('locked_expanded', s.get('sidebar_collapse_locked_expanded', 'Always expanded')),
        )
        self.fields['navbar_config'].label = s.get('form_sys_navbar', '')
        self.fields['log_config'].label = s.get('form_sys_log', 'Logging Configuration')
        self.fields['profile_config'].label = s.get('form_sys_profile', 'Profile Page Configuration')
        self.fields['backup_config'].label = s.get('form_sys_backup', 'Backup Configuration')
        self.fields['backup_scheduled_enabled'].label = s.get('form_sys_backup_scheduled_enabled', 'Enable scheduled backups')
        self.fields['backup_scheduled_enabled'].help_text = s.get('help_sys_backup_scheduled_enabled', 'Create full encrypted system backups automatically through Celery beat.')
        self.fields['backup_schedule_interval_hours'].label = s.get('form_sys_backup_schedule_interval_hours', 'Backup interval (hours)')
        self.fields['backup_schedule_interval_hours'].help_text = s.get('help_sys_backup_schedule_interval_hours', 'How often a scheduled backup becomes due. The scheduler checks every 15 minutes.')
        self.fields['backup_retention_days'].label = s.get('form_sys_backup_retention_days', 'Retention age (days)')
        self.fields['backup_retention_days'].help_text = s.get('help_sys_backup_retention_days', 'Delete completed backups older than this many days. Use 0 to keep them indefinitely.')
        self.fields['backup_max_backups_to_keep'].label = s.get('form_sys_backup_max_backups_to_keep', 'Maximum backups to keep')
        self.fields['backup_max_backups_to_keep'].help_text = s.get('help_sys_backup_max_backups_to_keep', 'Keep only the newest completed backups after each successful backup. Use 0 for no count limit.')
        self.fields['backup_auto_export_target'].label = s.get('form_sys_backup_auto_export_target', 'Automatic export target')
        self.fields['backup_auto_export_target'].help_text = s.get('help_sys_backup_auto_export_target', 'Storage-relative folder in Django default storage, for example dlux_backups or protected/dlux.')
        self.fields['navbar_enabled'].label = s.get('form_sys_navbar_enabled', '')
        self.fields['navbar_enabled'].help_text = s.get('help_sys_navbar_enabled', '')
        self.fields['navbar_default_mode'].label = s.get('form_sys_navbar_default_mode', '')
        self.fields['navbar_default_mode'].help_text = s.get('help_sys_navbar_default_mode', '')
        self.fields['navbar_default_mode'].choices = (
            ('hierarchy', s.get('navbar_mode_hierarchy', '')),
            ('history', s.get('navbar_mode_history', '')),
        )
        self.fields['navbar_allow_user_mode_override'].label = s.get(
            'form_sys_navbar_allow_user_mode_override',
            '',
        )
        self.fields['navbar_allow_user_mode_override'].help_text = s.get(
            'help_sys_navbar_allow_user_mode_override',
            '',
        )
        self.fields['titlebar_show_title'].label = s.get('form_sys_titlebar_show_title', 'Show titlebar title')
        self.fields['titlebar_show_logo'].label = s.get('form_sys_titlebar_show_logo', 'Show titlebar logo')
        self.fields['titlebar_show_home_button'].label = s.get('form_sys_titlebar_show_home_button', 'Show titlebar home button')
        self.fields['titlebar_hide_on_public_unauthenticated_index'].label = s.get(
            'form_sys_titlebar_hide_on_public_unauthenticated_index',
            'Hide titlebar on anonymous public home/index',
        )
        self.fields['titlebar_home_shape'].label = s.get('form_sys_titlebar_home_shape', 'Titlebar buttons shape')
        self.fields['titlebar_user_hub_style'].label = s.get('form_sys_titlebar_user_hub_style', 'Titlebar and user hub style')
        self.fields['titlebar_actions_order'].label = s.get('form_sys_titlebar_actions_order', 'Titlebar action order')
        self.fields['titlebar_title_align'].label = s.get('form_sys_titlebar_title_align', 'Title alignment')
        self.fields['titlebar_title_size'].label = s.get('form_sys_titlebar_title_size', 'Title size')
        self.fields['titlebar_height'].label = s.get('form_sys_titlebar_height', 'Titlebar height')
        self.fields['titlebar_surface'].label = s.get('form_sys_titlebar_surface', 'Titlebar surface')
        self.fields['titlebar_logo_treatment'].label = s.get('form_sys_titlebar_logo_treatment', 'Logo treatment')
        self.fields['titlebar_logo_treatment_shape'].label = s.get(
            'form_sys_titlebar_logo_treatment_shape',
            'Logo treatment shape',
        )
        self.fields['titlebar_show_title'].help_text = s.get(
            'help_sys_titlebar_show_title',
            'Show the system title in the titlebar.',
        )
        self.fields['titlebar_show_logo'].help_text = s.get(
            'help_sys_titlebar_show_logo',
            'Show the configured branding logo beside the title.',
        )
        self.fields['titlebar_show_home_button'].help_text = s.get(
            'help_sys_titlebar_show_home_button',
            'Show the quick Home button in the titlebar.',
        )
        self.fields['titlebar_hide_on_public_unauthenticated_index'].help_text = s.get(
            'help_sys_titlebar_hide_on_public_unauthenticated_index',
            'Hide the titlebar when an anonymous user opens the public root/home page.',
        )
        self.fields['titlebar_logo_treatment'].help_text = s.get(
            'help_sys_titlebar_logo_treatment',
            'Choose how Dlux visually assists the logo on mixed theme surfaces.',
        )
        self.fields['titlebar_logo_treatment_shape'].help_text = s.get(
            'help_sys_titlebar_logo_treatment_shape',
            'Choose the plate silhouette when the Plate treatment is active.',
        )
        self.fields['titlebar_user_hub_style'].help_text = s.get(
            'help_sys_titlebar_user_hub_style',
            'Choose whether user shortcuts stay in the user hub dropdown or move into orderable titlebar action buttons.',
        )
        self.fields['titlebar_home_shape'].choices = (
            ('circle', s.get('titlebar_home_shape_circle', 'Circle')),
            ('square', s.get('titlebar_home_shape_square', 'Square')),
            ('squircle', s.get('titlebar_home_shape_squircle', 'Squircle')),
        )
        self.fields['titlebar_user_hub_style'].choices = (
            (TITLEBAR_USER_HUB_STYLE_DROPDOWN, s.get('titlebar_user_hub_style_dropdown', 'Dropdown')),
            (TITLEBAR_USER_HUB_STYLE_ACTIONS, s.get('titlebar_user_hub_style_actions', 'Titlebar Actions')),
        )
        self.fields['titlebar_title_align'].choices = (
            ('start', s.get('titlebar_align_start', 'Start')),
            ('center', s.get('titlebar_align_center', 'Center')),
            ('end', s.get('titlebar_align_end', 'End')),
        )
        self.fields['titlebar_title_size'].choices = (
            ('sm', s.get('titlebar_size_sm', 'Small')),
            ('md', s.get('titlebar_size_md', 'Medium')),
            ('lg', s.get('titlebar_size_lg', 'Large')),
        )
        self.fields['titlebar_height'].choices = (
            ('dense', s.get('titlebar_height_dense', 'Dense')),
            ('balanced', s.get('titlebar_height_balanced', 'Balanced')),
            ('roomy', s.get('titlebar_height_roomy', 'Roomy')),
        )
        self.fields['titlebar_surface'].choices = (
            ('default', s.get('titlebar_surface_default', 'Default')),
            ('muted', s.get('titlebar_surface_muted', 'Muted')),
            ('glass', s.get('titlebar_surface_glass', 'Glass')),
        )
        self.fields['titlebar_logo_treatment'].choices = (
            ('none', s.get('titlebar_logo_treatment_none', 'None')),
            ('plate', s.get('titlebar_logo_treatment_plate', 'Plate')),
            ('halo', s.get('titlebar_logo_treatment_halo', 'Halo')),
            ('contrast', s.get('titlebar_logo_treatment_contrast', 'Contrast')),
        )
        self.fields['titlebar_logo_treatment_shape'].choices = (
            ('soft', s.get('titlebar_logo_treatment_shape_soft', 'Soft')),
            ('pill', s.get('titlebar_logo_treatment_shape_pill', 'Pill')),
            ('square', s.get('titlebar_logo_treatment_shape_square', 'Square')),
        )
        self.fields['notification_config'].label = s.get('form_sys_notification_config', 'Notification configuration')
        self.fields['notifications_enabled'].label = s.get('form_sys_notifications_enabled', 'Enable notifications')
        self.fields['notifications_enabled'].help_text = s.get(
            'help_sys_notifications_enabled',
            'Master switch for the entire notification subsystem. When off, flash notices, the titlebar drawer/badge, emails, automatic CRUD notifications, and notify(...) are all suppressed.',
        )
        self.fields['notification_flash_enabled'].label = s.get('form_sys_notification_flash_enabled', 'Show flash notices')
        self.fields['notification_flash_enabled'].help_text = s.get(
            'help_sys_notification_flash_enabled',
            'Show short-lived notices for user-facing events.',
        )
        self.fields['notification_flash_position'].label = s.get('form_sys_notification_flash_position', 'Flash position')
        self.fields['notification_flash_size'].label = s.get('form_sys_notification_flash_size', 'Flash size')
        self.fields['notification_flash_text_size'].label = s.get('form_sys_notification_flash_text_size', 'Flash text size')
        self.fields['notification_flash_timeout_ms'].label = s.get('form_sys_notification_flash_timeout', 'Flash timeout (ms)')
        self.fields['notification_flash_max_visible'].label = s.get('form_sys_notification_flash_max_visible', 'Max visible flash notices')
        self.fields['notification_drawer_enabled'].label = s.get('form_sys_notification_drawer_enabled', 'Enable titlebar notification drawer')
        self.fields['notification_drawer_enabled'].help_text = s.get(
            'help_sys_notification_drawer_enabled',
            'Store user-facing notifications under the titlebar icon for authenticated users.',
        )
        self.fields['notification_badge_enabled'].label = s.get('form_sys_notification_badge_enabled', 'Show unread badge')
        self.fields['notification_bridge_enabled'].label = s.get('form_sys_notification_bridge_enabled', 'Import legacy Django messages')
        self.fields['notification_bridge_enabled'].help_text = s.get(
            'help_sys_notification_bridge_enabled',
            'Drain host-project Django messages into Dlux flash notices when enabled.',
        )
        notification_email_status = get_email_service_status()
        self.notification_email_available = bool(notification_email_status.get('available'))
        notification_email_reason = str(notification_email_status.get('reason') or '').replace('_', ' ')
        self.fields['notification_email_enabled'].label = s.get('form_sys_notification_email_enabled', 'Enable notification email channel')
        self.fields['notification_email_enabled'].help_text = s.get(
            'help_sys_notification_email_enabled',
            'Master gate for notification emails. Requires configured Dlux email delivery; when off, rules and notify(..., email=True) cannot send mail.',
        )
        self.fields['notification_email_default'].label = s.get('form_sys_notification_email_default', 'Email by default')
        self.fields['notification_email_default'].help_text = s.get(
            'help_sys_notification_email_default',
            'After the email channel is allowed, send eligible persisted notifications by email unless a rule or notify(...) call overrides delivery.',
        )
        if not self.notification_email_available:
            unavailable_help = s.get(
                'help_sys_notification_email_unavailable',
                'Disabled until Dlux email delivery is configured.',
            )
            if notification_email_reason:
                unavailable_help = f"{unavailable_help} ({notification_email_reason})"
            self.fields['notification_email_enabled'].help_text = unavailable_help
            self.fields['notification_email_default'].help_text = unavailable_help
            self.fields['notification_email_enabled'].disabled = True
            self.fields['notification_email_default'].disabled = True
        self.fields['notification_auto_crud_enabled'].label = s.get('form_sys_notification_auto_crud', 'Enable automatic ScopedModel CRUD notifications')
        self.fields['notification_auto_crud_enabled'].help_text = s.get(
            'help_sys_notification_auto_crud',
            'Master switch for automatic notifications emitted by ScopedModel create, update, and delete events.',
        )
        self.fields['notification_auto_create'].label = s.get('form_sys_notification_auto_create', 'Automatic create notifications')
        self.fields['notification_auto_create'].help_text = s.get(
            'help_sys_notification_auto_create',
            'When automatic CRUD notifications are enabled, emit notifications for new ScopedModel records.',
        )
        self.fields['notification_auto_update'].label = s.get('form_sys_notification_auto_update', 'Automatic update mode')
        self.fields['notification_auto_update'].help_text = s.get(
            'help_sys_notification_auto_update',
            'Off suppresses update notifications; Summary emits quiet changed-field summaries; Full emits update notifications with full metadata.',
        )
        self.fields['notification_auto_delete'].label = s.get('form_sys_notification_auto_delete', 'Automatic delete notifications')
        self.fields['notification_auto_delete'].help_text = s.get(
            'help_sys_notification_auto_delete',
            'When automatic CRUD notifications are enabled, emit notifications for deleted ScopedModel records.',
        )
        self.fields['notification_flash_position'].choices = (
            ('top_center', s.get('notification_position_top_center', 'Top center')),
            ('top_start', s.get('notification_position_top_start', 'Top start')),
            ('top_end', s.get('notification_position_top_end', 'Top end')),
            ('titlebar_end', s.get('notification_position_titlebar_end', 'Titlebar end')),
            ('bottom_start', s.get('notification_position_bottom_start', 'Bottom start')),
            ('bottom_end', s.get('notification_position_bottom_end', 'Bottom end')),
        )
        self.fields['notification_flash_size'].choices = (
            ('compact', s.get('notification_size_compact', 'Compact')),
            ('balanced', s.get('notification_size_balanced', 'Balanced')),
            ('prominent', s.get('notification_size_prominent', 'Prominent')),
        )
        self.fields['notification_flash_text_size'].choices = (
            ('sm', s.get('titlebar_size_sm', 'Small')),
            ('md', s.get('titlebar_size_md', 'Medium')),
            ('lg', s.get('titlebar_size_lg', 'Large')),
        )
        self.fields['notification_auto_update'].choices = (
            ('off', s.get('notification_update_off', 'Off')),
            ('summary', s.get('notification_update_summary', 'Summary')),
            ('full', s.get('notification_update_full', 'Full')),
        )
        for field_name in ('notification_flash_timeout_ms', 'notification_flash_max_visible'):
            self.fields[field_name].widget.attrs.update({'class': 'form-control glass-input'})
        self.fields['login_style'].label = s.get('form_sys_login_style', 'Login Layout Style')
        self.fields['login_style'].help_text = ''
        self.fields['login_style'].choices = (
            ('split', s.get('login_style_split', 'Split (form + banner)')),
            ('centered', s.get('login_style_centered', 'Centered card')),
            ('minimal', s.get('login_style_minimal', 'Floating with background')),
            ('fullpage', s.get('login_style_fullpage', 'Full-page split')),
        )
        self.fields['login_show_logo'].label = s.get('form_sys_login_show_logo', 'Show Logo')
        self.fields['login_show_logo'].help_text = s.get(
            'help_sys_login_show_logo',
            'Show the logo on the login screen. When off, the logo is hidden across all login styles.',
        )
        self.fields['login_banner_color'].label = s.get('form_sys_login_banner_color', 'Banner Colour')
        self.fields['login_banner_color'].help_text = s.get(
            'help_sys_login_banner_color',
            'Optional — enter a CSS colour (hex, rgb, named). Leave empty for the theme default.',
        )
        self.fields['login_logo_treatment'].label = s.get('form_sys_login_logo_treatment', 'Login Logo Treatment')
        self.fields['login_logo_treatment'].help_text = ''
        self.fields['login_logo_treatment'].choices = (
            ('none', s.get('titlebar_logo_treatment_none', 'None')),
            ('plate', s.get('titlebar_logo_treatment_plate', 'Plate')),
            ('halo', s.get('titlebar_logo_treatment_halo', 'Halo')),
            ('contrast', s.get('titlebar_logo_treatment_contrast', 'Contrast')),
        )
        self.fields['login_logo_treatment_shape'].label = s.get('form_sys_login_logo_treatment_shape', 'Treatment Shape')
        self.fields['login_logo_treatment_shape'].choices = (
            ('soft', s.get('titlebar_logo_treatment_shape_soft', 'Soft')),
            ('pill', s.get('titlebar_logo_treatment_shape_pill', 'Pill')),
            ('square', s.get('titlebar_logo_treatment_shape_square', 'Square')),
        )
        initial_login_config = normalize_login_config(
            getattr(self.instance, 'login_config', None) or config.get('login', {})
        )
        initial_hero = initial_login_config.get('hero_message', {})
        if not isinstance(initial_hero, dict):
            initial_hero = {}
        self._login_hero_lang_fields = []
        for lang_code, lang_meta in current_languages.items():
            field_name = f'login_hero_message_{lang_code}'
            lang_label = lang_meta.get('name', lang_code) if isinstance(lang_meta, dict) else str(lang_meta)
            lang_dir = lang_meta.get('dir', 'ltr') if isinstance(lang_meta, dict) else 'ltr'
            placeholder = s.get('login_hero_placeholder', 'Welcome! Sign in to continue.')
            self.fields[field_name] = forms.CharField(
                required=False,
                initial=initial_hero.get(lang_code, ''),
                label=lang_label,
                widget=forms.Textarea(attrs={
                    'rows': 5,
                    'class': 'form-control font-monospace',
                    'dir': lang_dir,
                    'placeholder': placeholder,
                }),
            )
            self._login_hero_lang_fields.append((lang_code, lang_label, field_name))
        _bind_choice_selector_widget(
            self.fields['login_style'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'split': {'icon': 'bi-layout-split'},
                    'centered': {'icon': 'bi-credit-card-2-front'},
                    'minimal': {'icon': 'bi-window-fullscreen'},
                    'fullpage': {'icon': 'bi-layout-text-sidebar-reverse'},
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['login_logo_treatment'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'none': {'icon': 'bi-slash-circle'},
                    'plate': {'icon': 'bi-badge-ad'},
                    'halo': {'icon': 'bi-brightness-high'},
                    'contrast': {'icon': 'bi-circle-half'},
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['login_logo_treatment_shape'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'soft': {'icon': 'bi-app'},
                    'pill': {'icon': 'bi-capsule'},
                    'square': {'icon': 'bi-square'},
                },
            ),
        )
        self.fields['email_2fa'].label = s.get('form_sys_email_2fa', 'Enable Email 2FA')
        self.fields['email_2fa'].help_text = s.get(
            'help_sys_email_2fa',
            'Allow users to enable two-factor authentication via email. Requires Dlux email delivery to be ready.',
        )
        self.fields['prevent_multiple_active_sessions'].label = s.get('form_sys_prevent_multiple_active_sessions')
        self.fields['prevent_multiple_active_sessions'].help_text = s.get('help_sys_prevent_multiple_active_sessions')
        self.fields['login_lockout_enabled'].label = s.get('form_sys_login_lockout', 'Enable Login Lockout')
        self.fields['login_lockout_enabled'].help_text = s.get(
            'help_sys_login_lockout',
            'Temporarily block sign-in after repeated failed password attempts from the same IP or username.',
        )
        self.fields['enforce_strong_passwords'].label = s.get('form_sys_enforce_strong_passwords', 'Enforce strong passwords')
        self.fields['enforce_strong_passwords'].help_text = s.get(
            'help_sys_enforce_strong_passwords',
            'Require new passwords to be at least 12 characters with upper and lower case letters, a digit, and a symbol.',
        )
        self.fields['client_ip_mode'].label = s.get('form_sys_client_ip_mode')
        self.fields['client_ip_mode'].help_text = s.get('help_sys_client_ip_mode')
        self.fields['client_ip_mode'].choices = (
            (CLIENT_IP_MODE_AUTO, s.get('client_ip_mode_auto', 'Auto-detect')),
            (CLIENT_IP_MODE_X_FORWARDED_FOR, s.get('client_ip_mode_x_forwarded_for')),
            (CLIENT_IP_MODE_REMOTE_ADDR, s.get('client_ip_mode_remote_addr')),
            (CLIENT_IP_MODE_X_REAL_IP, s.get('client_ip_mode_x_real_ip')),
            (CLIENT_IP_MODE_CLOUDFLARE, s.get('client_ip_mode_cloudflare')),
            (CLIENT_IP_MODE_CUSTOM, s.get('client_ip_mode_custom')),
        )
        self.fields['client_ip_mode'].widget.attrs.update({
            'class': 'form-select glass-input',
            'data-client-ip-mode-input': 'true',
        })
        self.fields['client_ip_trusted_proxy_hops'].label = s.get('form_sys_client_ip_hops')
        self.fields['client_ip_trusted_proxy_hops'].help_text = s.get('help_sys_client_ip_hops')
        self.fields['client_ip_trusted_proxy_hops'].widget.attrs.update({
            'class': 'form-control glass-input',
            'min': '0',
            'max': '8',
        })
        self.fields['client_ip_custom_header'].label = s.get('form_sys_client_ip_custom_header')
        self.fields['client_ip_custom_header'].help_text = s.get('help_sys_client_ip_custom_header')
        self.fields['client_ip_custom_header'].widget.attrs.update({
            'class': 'form-control glass-input',
            'placeholder': s.get('client_ip_custom_header_placeholder'),
            'dir': 'ltr',
        })
        self.fields['email_config'].label = s.get('form_sys_email_config', 'Email delivery configuration')
        self.fields['email_config_transport'].label = s.get('form_sys_email_transport', 'Delivery path')
        self.fields['email_config_secret_storage'].label = s.get('form_sys_email_secret_storage', 'Secret storage')
        self.fields['email_config_host'].label = s.get('form_sys_email_host', 'Provider SMTP host')
        self.fields['email_config_port'].label = s.get('form_sys_email_port', 'Provider SMTP port')
        self.fields['email_config_use_tls'].label = s.get('form_sys_email_use_tls', 'Provider STARTTLS')
        self.fields['email_config_use_ssl'].label = s.get('form_sys_email_use_ssl', 'Provider SSL')
        self.fields['email_config_username'].label = s.get('form_sys_email_username', 'Provider SMTP username')
        self.fields['email_config_password'].label = s.get('form_sys_email_password', 'Provider SMTP password')
        self.fields['email_config_default_from_email'].label = s.get('form_sys_email_default_from', 'Default from email')
        self.fields['email_config_provider_preset'].label = s.get('form_sys_email_provider_preset', 'Provider preset')
        self.fields['email_config_provider_preset'].help_text = s.get(
            'help_sys_email_provider_preset',
            'Prefills SMTP host/port/encryption for common providers. Choose Custom to enter values manually.',
        )
        self.fields['email_config_failure_recipients'].label = s.get(
            'form_sys_email_failure_recipients', 'Failure alert recipients'
        )
        self.fields['email_config_failure_recipients'].help_text = s.get(
            'help_sys_email_failure_recipients',
            'Comma or newline separated emails warned in-app when transactional mail fails to send. Requires notifications enabled.',
        )
        self.fields['email_config_test_recipient'].label = s.get('form_sys_email_test_recipient', 'Send a test email to')
        self.fields['email_config_test_recipient'].help_text = s.get(
            'help_sys_email_test_recipient',
            'Sends a one-off message using the saved configuration. Save the form before testing.',
        )
        for field_name in (
            'email_config_host',
            'email_config_username',
            'email_config_password',
            'email_config_default_from_email',
            'email_config_failure_recipients',
            'email_config_test_recipient',
        ):
            self.fields[field_name].widget.attrs.update({'class': 'form-control glass-input'})
        self.fields['email_config_port'].widget.attrs.update({'class': 'form-control glass-input'})
        self.fields['email_config_provider_preset'].widget.attrs.update({
            'class': 'form-select glass-input',
            'data-email-provider-preset': '',
        })
        self.fields['email_config_test_recipient'].widget.attrs.update({'data-email-test-recipient': ''})
        self.fields['public_root'].label = s.get('form_sys_public_root', 'Public Root Access')
        self.fields['public_root'].help_text = s.get(
            'help_sys_public_root',
            'Allow anonymous (non-logged-in) users to access the root URL (/). When enabled, the system will not force-redirect to login.',
        )
        self.fields['public_root_split_enabled'].label = s.get(
            'form_sys_public_root_split_enabled',
            'Separate anonymous public root from Home URL',
        )
        self.fields['public_root_split_enabled'].help_text = s.get(
            'help_sys_public_root_split_enabled',
            'When enabled, anonymous users can be redirected to a separate Public Root URL while authenticated users still use the main Home URL.',
        )
        email_status = get_email_service_status()
        smtp_label = s.get('form_sys_email_status_ready', 'ready') if email_status.get('available') else s.get('form_sys_email_status_not_ready', 'not ready')
        self.fields['public_registration_enabled'].label = s.get('form_sys_public_registration', 'Enable Public Registration')
        self.fields['public_registration_enabled'].help_text = s.get(
            'help_sys_public_registration',
            'Allow anonymous users to request an account. Email verification is mandatory and SMTP/email delivery must be configured.',
        ) + f" Email service: {smtp_label}."
        self.fields['registration_activation_mode'].label = s.get('form_sys_registration_activation_mode', 'Registration Activation Mode')
        self.fields['registration_activation_mode'].help_text = s.get(
            'help_sys_registration_activation_mode',
            'Choose whether verified users become active immediately or wait for superuser approval.',
        )
        self.fields['registration_throttle_enabled'].label = s.get('form_sys_registration_throttle', 'Enable Registration Throttles')
        self.fields['registration_throttle_enabled'].help_text = s.get(
            'help_sys_registration_throttle',
            'Use cache-based IP/email throttles and resend cooldowns for public registration.',
        )
        self.sidebar_sections_manager_available = bool(has_section_models())
        _bind_choice_selector_widget(
            self.fields['default_table_density'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'dense': {
                        'icon': 'bi-list',
                        'description': s.get('table_density_dense_desc', 'Fits more rows on screen with tighter spacing.'),
                    },
                    'balanced': {
                        'icon': 'bi-table',
                        'description': s.get('table_density_balanced_desc', 'Comfortable default for everyday admin work.'),
                    },
                    'roomy': {
                        'icon': 'bi-layout-text-window-reverse',
                        'description': s.get('table_density_roomy_desc', 'Uses larger rows and more breathing room.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['sidebar_density'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'dense': {
                        'icon': 'bi-list-ul',
                        'description': s.get('sidebar_density_dense_desc', 'Tighter rows and spacing for a denser sidebar.'),
                    },
                    'balanced': {
                        'icon': 'bi-layout-sidebar-inset',
                        'description': s.get('sidebar_density_balanced_desc', 'The default balance between density and readability.'),
                    },
                    'roomy': {
                        'icon': 'bi-distribute-vertical',
                        'description': s.get('sidebar_density_roomy_desc', 'Larger row height and spacing for a more relaxed sidebar.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['sidebar_collapse_mode'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'icons': {
                        'icon': 'bi-layout-sidebar-inset',
                        'description': s.get('sidebar_collapse_icons_desc', 'Collapse to an icon rail on desktop.'),
                    },
                    'hidden': {
                        'icon': 'bi-eye-slash',
                        'description': s.get('sidebar_collapse_hidden_desc', 'Collapse to a fully hidden desktop sidebar.'),
                    },
                    'locked_expanded': {
                        'icon': 'bi-lock',
                        'description': s.get('sidebar_collapse_locked_expanded_desc', 'Disable desktop collapsing and keep the sidebar open.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_home_shape'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'circle': {
                        'icon': 'bi-circle',
                        'description': s.get('titlebar_home_shape_circle_desc', 'Round button silhouette.'),
                    },
                    'square': {
                        'icon': 'bi-square',
                        'description': s.get('titlebar_home_shape_square_desc', 'Sharp square edges.'),
                    },
                    'squircle': {
                        'icon': 'bi-app-indicator',
                        'description': s.get('titlebar_home_shape_squircle_desc', 'Soft rounded square edges.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_user_hub_style'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    TITLEBAR_USER_HUB_STYLE_DROPDOWN: {
                        'icon': 'bi-person-lines-fill',
                        'description': s.get(
                            'titlebar_user_hub_style_dropdown_desc',
                            'Keep user shortcuts inside the current user hub dropdown.',
                        ),
                    },
                    TITLEBAR_USER_HUB_STYLE_ACTIONS: {
                        'icon': 'bi-ui-checks-grid',
                        'description': s.get(
                            'titlebar_user_hub_style_actions_desc',
                            'Render user shortcuts as orderable titlebar action buttons.',
                        ),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_title_align'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'start': {
                        'icon': 'bi-text-left',
                        'description': s.get('titlebar_align_start_desc', 'Pin the title to the start side.'),
                    },
                    'center': {
                        'icon': 'bi-text-center',
                        'description': s.get('titlebar_align_center_desc', 'Keep the title visually centered.'),
                    },
                    'end': {
                        'icon': 'bi-text-right',
                        'description': s.get('titlebar_align_end_desc', 'Pin the title to the end side.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_title_size'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'sm': {
                        'surface_label': 'S',
                        'description': s.get('titlebar_size_sm_desc', 'Compact title sizing.'),
                    },
                    'md': {
                        'surface_label': 'M',
                        'description': s.get('titlebar_size_md_desc', 'Balanced default title sizing.'),
                    },
                    'lg': {
                        'surface_label': 'L',
                        'description': s.get('titlebar_size_lg_desc', 'Larger, more prominent title sizing.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_height'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'dense': {
                        'surface_label': 'D',
                        'description': s.get('titlebar_height_dense_desc', 'Tighter vertical titlebar spacing.'),
                    },
                    'balanced': {
                        'surface_label': 'B',
                        'description': s.get('titlebar_height_balanced_desc', 'Default titlebar spacing.'),
                    },
                    'roomy': {
                        'surface_label': 'R',
                        'description': s.get('titlebar_height_roomy_desc', 'More breathing room inside the titlebar.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_surface'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'default': {
                        'surface_label': 'Df',
                        'description': s.get('titlebar_surface_default_desc', 'Standard titlebar surface styling.'),
                    },
                    'muted': {
                        'surface_label': 'Mu',
                        'description': s.get('titlebar_surface_muted_desc', 'Lower-contrast titlebar surface.'),
                    },
                    'glass': {
                        'surface_label': 'Gl',
                        'description': s.get('titlebar_surface_glass_desc', 'Blurred glass-style surface effect.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_logo_treatment'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'none': {
                        'icon': 'bi-slash-circle',
                        'description': s.get('titlebar_logo_treatment_none_desc', 'Leave the logo as uploaded.'),
                    },
                    'plate': {
                        'icon': 'bi-badge-ad',
                        'description': s.get('titlebar_logo_treatment_plate_desc', 'Place the logo on an adaptive material plate.'),
                    },
                    'halo': {
                        'icon': 'bi-brightness-high',
                        'description': s.get('titlebar_logo_treatment_halo_desc', 'Add a subtle adaptive glow behind the logo.'),
                    },
                    'contrast': {
                        'icon': 'bi-circle-half',
                        'description': s.get('titlebar_logo_treatment_contrast_desc', 'Apply contrast and shadow assistance for simple logos.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_logo_treatment_shape'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'soft': {
                        'icon': 'bi-app',
                        'description': s.get('titlebar_logo_treatment_shape_soft_desc', 'A modern rounded plate.'),
                    },
                    'pill': {
                        'icon': 'bi-capsule',
                        'description': s.get('titlebar_logo_treatment_shape_pill_desc', 'A fully rounded capsule plate.'),
                    },
                    'square': {
                        'icon': 'bi-square',
                        'description': s.get('titlebar_logo_treatment_shape_square_desc', 'A sharper compact plate.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['navbar_default_mode'],
            DluxChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'hierarchy': {
                        'icon': 'bi-diagram-3',
                        'description': s.get('navbar_mode_hierarchy_desc', ''),
                    },
                    'history': {
                        'icon': 'bi-clock-history',
                        'description': s.get('navbar_mode_history_desc', ''),
                    },
                },
            ),
        )
        project_config = getattr(settings, 'DLUX_CONFIG', {})
        instance_system_names = normalize_system_names(getattr(self.instance, 'system_names', {}))
        if not instance_system_names:
            instance_system_names = normalize_system_names(
                project_config.get('system_names', config.get('system_names', {}))
            )
        self.initial['system_names'] = _json_dump(instance_system_names, ensure_ascii=False)
        if not self.instance.default_language:
             self.instance.default_language = config.get('default_language', 'en')
        self.initial['default_language'] = self.instance.default_language or config.get('default_language', 'en')
        if not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False):
            self.instance.default_theme = config.get('default_theme', 'light')
        elif not getattr(self.instance, 'default_theme', None):
            self.instance.default_theme = config.get('default_theme', 'light')
        self.initial['default_theme'] = self.instance.default_theme or config.get('default_theme', 'light')
        initial_allowed_themes = normalize_allowed_themes(
            (
                config.get('allowed_themes')
                if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
                else getattr(self.instance, 'allowed_themes', None)
            ) or config.get('allowed_themes')
        )
        self.initial['allowed_themes'] = list(initial_allowed_themes)
        self.initial['allow_user_theme_override'] = bool(
            config.get('allow_user_theme_override', True)
            if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
            else getattr(self.instance, 'allow_user_theme_override', config.get('allow_user_theme_override', True))
        )
        self.initial['allow_user_font_override'] = bool(
            config.get('allow_user_font_override', True)
            if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
            else getattr(self.instance, 'allow_user_font_override', config.get('allow_user_font_override', True))
        )
        initial_allowed_fonts = normalize_allowed_fonts(
            (
                config.get('allowed_fonts')
                if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
                else getattr(self.instance, 'allowed_fonts', None)
            ) or config.get('allowed_fonts')
        )
        self.initial['allowed_fonts'] = list(initial_allowed_fonts)
        instance_default_fonts = getattr(self.instance, 'default_fonts', {}) or {}
        if not instance_default_fonts:
             instance_default_fonts = config.get('default_fonts', {})
        self.initial['default_fonts'] = _json_dump(instance_default_fonts, ensure_ascii=False)
        self.initial['allow_user_language_override'] = bool(
            config.get('allow_user_language_override', True)
            if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
            else getattr(self.instance, 'allow_user_language_override', config.get('allow_user_language_override', True))
        )
        if (
            not getattr(self.instance, 'pk', None)
            and not getattr(self.instance, 'is_configured', False)
        ) or getattr(self.instance, 'default_table_density', None) not in TABLE_DENSITY_VALUES:
            self.instance.default_table_density = config.get('default_table_density', DEFAULT_TABLE_DENSITY)
        self.initial['default_table_density'] = self.instance.default_table_density or config.get('default_table_density', DEFAULT_TABLE_DENSITY)
        instance_home_url = str(self.instance.home_url or '').strip()
        if (
            not getattr(self.instance, 'is_configured', False)
            and instance_home_url == _LEGACY_HOME_URL
        ):
            instance_home_url = ''

        current_home_url = (
            instance_home_url
            or config.get('home_url', '')
            or project_config.get('home_url', '')
            or DEFAULT_HOME_URL
        )
        self.initial['home_url'] = current_home_url
        instance_public_root_url = str(getattr(self.instance, 'public_root_url', '') or '').strip()
        current_public_root_url = (
            instance_public_root_url
            or config.get('public_root_url', '')
            or project_config.get('public_root_url', '')
        )
        self.initial['public_root_url'] = current_public_root_url

        if self.instance and self.instance.pk:
            if isinstance(self.instance.languages, dict):
                self.initial['languages'] = _json_dump(self.instance.languages, ensure_ascii=False, indent=2)
            if isinstance(self.instance.translations_override, dict):
                self.initial['translations_override'] = _json_dump(self.instance.translations_override, ensure_ascii=False, indent=2)
        if isinstance(getattr(self.instance, 'sidebar_config', None), dict) and self.instance.sidebar_config:
            sidebar_config = sanitize_sidebar_config(self.instance.sidebar_config, allow_system_items=True)
            sidebar_config['home_url_name'] = None
            self.initial['sidebar_config'] = _json_dump(sidebar_config, ensure_ascii=False)
        initial_navbar_config = normalize_navbar_config(
            (
                config.get('navbar', {})
                if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
                else getattr(self.instance, 'navbar_config', None)
            ) or config.get('navbar', {})
        )
        self.initial['navbar_config'] = _json_dump(initial_navbar_config, ensure_ascii=False)
        initial_log_config = normalize_log_config(
            (
                config.get('log', {})
                if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
                else getattr(self.instance, 'log_config', None)
            ) or config.get('log', {})
        )
        self.initial['log_config'] = _json_dump(initial_log_config, ensure_ascii=False)
        self._initial_log_config = initial_log_config
        initial_profile_config = normalize_profile_config(
            (
                config.get('profile', {})
                if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
                else getattr(self.instance, 'profile_config', None)
            ) or config.get('profile', {})
        )
        self.initial['profile_config'] = _json_dump(initial_profile_config, ensure_ascii=False)
        self._initial_profile_config = initial_profile_config
        self._apply_schema_group_initials(
            'backup_config',
            getattr(self.instance, 'backup_config', None) or config.get('backup_config') or config.get('backup') or {},
        )
        initial_titlebar_config = normalize_titlebar_config(
            (
                config.get('titlebar', {})
                if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
                else getattr(self.instance, 'titlebar_config', None)
            ) or config.get('titlebar', {})
        )

        if not self.initial.get('languages'):
            self.initial['languages'] = _json_dump(config.get('languages', {}), ensure_ascii=False, indent=2)
        if not self.initial.get('translations_override'):
            self.initial['translations_override'] = _json_dump({}, ensure_ascii=False, indent=2)
        if not self.initial.get('default_language'):
            self.initial['default_language'] = config.get('default_language', 'en')
        if not self.initial.get('default_theme'):
            self.initial['default_theme'] = config.get('default_theme', 'light')
        if not self.initial.get('allowed_themes'):
            self.initial['allowed_themes'] = list(normalize_allowed_themes(config.get('allowed_themes')))
        if self.initial.get('default_table_density') not in TABLE_DENSITY_VALUES:
            self.initial['default_table_density'] = config.get('default_table_density', DEFAULT_TABLE_DENSITY)
        self._apply_schema_group_initials(
            'layout_config',
            {'default_table_density': self.initial.get('default_table_density')},
            hidden_field=False,
        )
        self._apply_schema_group_initials(
            'auth_config',
            getattr(self.instance, 'auth_config', None) or config.get('auth_config') or config
        )
        initial_login_config = normalize_login_config(
            getattr(self.instance, 'login_config', None) or config.get('login', {})
        )
        self.initial['login_config'] = _json_dump(initial_login_config, ensure_ascii=False)
        self.initial['login_style'] = initial_login_config.get('style', 'split')
        self.initial['login_show_logo'] = initial_login_config.get('show_logo', True)
        self.initial['login_banner_color'] = initial_login_config.get('banner_color', '')
        self.initial['login_logo_treatment'] = initial_login_config.get('logo_treatment', 'none')
        self.initial['login_logo_treatment_shape'] = initial_login_config.get('logo_treatment_shape', 'soft')
        # per-language hero message initial values set dynamically in __init__ above
        self._apply_schema_group_initials(
            'client_ip_config',
            (
                getattr(self.instance, 'client_ip_config', None)
                if isinstance(getattr(self.instance, 'client_ip_config', None), dict) and getattr(self.instance, 'client_ip_config', None)
                else config.get('client_ip', {})
            )
        )
        self._apply_schema_group_initials(
            'public_root_config',
            {
                'public_root': (
                    getattr(self.instance, 'public_root', False)
                    or config.get('public_root', False)
                ),
                'public_root_split_enabled': (
                    config.get('public_root_split_enabled', False)
                    if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
                    else getattr(self.instance, 'public_root_split_enabled', config.get('public_root_split_enabled', False))
                ),
                'public_root_url': current_public_root_url,
            },
            hidden_field=False,
        )
        registration_activation_mode = (
            getattr(self.instance, 'registration_activation_mode', None)
            or config.get('registration_activation_mode')
        )
        self._apply_schema_group_initials(
            'registration_config',
            {
                'public_registration_enabled': (
                    getattr(self.instance, 'public_registration_enabled', False)
                    or config.get('public_registration_enabled', False)
                ),
                'registration_activation_mode': registration_activation_mode,
                'registration_throttle_enabled': (
                    getattr(self.instance, 'registration_throttle_enabled', True)
                    if hasattr(self.instance, 'registration_throttle_enabled')
                    else config.get('registration_throttle_enabled', True)
                ),
            },
            hidden_field=False,
        )
        initial_email_config = normalize_email_config(
            (
                getattr(self.instance, 'email_config', None)
                if isinstance(getattr(self.instance, 'email_config', None), dict) and getattr(self.instance, 'email_config', None)
                else config.get('email_config', {})
            )
        )
        self.initial['email_config'] = _json_dump(normalize_email_config(initial_email_config, redact_secret=True), ensure_ascii=False)
        self.initial['email_config_transport'] = initial_email_config.get('transport', 'direct')
        self.initial['email_config_secret_storage'] = initial_email_config.get('secret_storage', 'env')
        self.initial['email_config_provider_preset'] = initial_email_config.get('provider_preset', 'custom')
        self.initial['email_config_host'] = initial_email_config.get('host', '')
        self.initial['email_config_port'] = initial_email_config.get('port', 587)
        self.initial['email_config_use_tls'] = bool(initial_email_config.get('use_tls', True))
        self.initial['email_config_use_ssl'] = bool(initial_email_config.get('use_ssl', False))
        self.initial['email_config_username'] = initial_email_config.get('username', '')
        self.initial['email_config_default_from_email'] = initial_email_config.get('default_from_email', '')
        self.initial['email_config_failure_recipients'] = '\n'.join(
            initial_email_config.get('failure_notification_recipients', []) or []
        )
        if not self.initial.get('sidebar_config'):
            sidebar_config = sanitize_sidebar_config(config.get('sidebar', {}), allow_system_items=True)
            if not isinstance(sidebar_config, dict):
                sidebar_config = normalize_sidebar_behavior({
                    'home_url_name': None,
                    'entries': [],
                })
            sidebar_config.setdefault('entries', [])
            sidebar_config = normalize_sidebar_behavior(sidebar_config)
            sidebar_config['home_url_name'] = None
            self.initial['sidebar_config'] = _json_dump(sidebar_config, ensure_ascii=False)

        initial_sidebar_config = self.initial.get('sidebar_config') or {}
        if isinstance(initial_sidebar_config, str):
            try:
                initial_sidebar_config = json.loads(initial_sidebar_config)
            except (TypeError, ValueError, json.JSONDecodeError):
                initial_sidebar_config = {}

        self.initial['sidebar_enabled'] = bool(initial_sidebar_config.get('enabled', True))
        self.initial['sidebar_enable_reorder'] = bool(initial_sidebar_config.get('enable_reorder', True))
        self.initial['sidebar_enable_toolbar'] = bool(initial_sidebar_config.get('show_toolbar', True))
        self.initial['sidebar_show_icons'] = bool(initial_sidebar_config.get('show_icons', True))
        self.initial['sidebar_density'] = initial_sidebar_config.get('density', DEFAULT_SIDEBAR_DENSITY)
        self.initial['sidebar_allow_user_density'] = bool(initial_sidebar_config.get('allow_user_density', True))
        self.initial['sidebar_collapse_mode'] = initial_sidebar_config.get('collapse_mode', DEFAULT_SIDEBAR_COLLAPSE_MODE)
        if self.mode == 'setup' and not getattr(self.instance, 'is_configured', False):
            initial_navbar_config = seed_navbar_config_from_sidebar(
                initial_navbar_config,
                initial_sidebar_config,
                lang_code=self.initial.get('default_language') or 'en',
            )
            self.initial['navbar_config'] = _json_dump(initial_navbar_config, ensure_ascii=False)
        self.initial['navbar_enabled'] = bool(initial_navbar_config.get('enabled', False))
        self.initial['navbar_default_mode'] = initial_navbar_config.get('default_mode', DEFAULT_NAVBAR_MODE)
        self.initial['navbar_allow_user_mode_override'] = bool(
            initial_navbar_config.get('allow_user_mode_override', True)
        )
        self.initial['titlebar_show_title'] = bool(initial_titlebar_config.get('show_title', True))
        self.initial['titlebar_show_logo'] = bool(initial_titlebar_config.get('show_logo', True))
        self.initial['titlebar_show_home_button'] = bool(initial_titlebar_config.get('show_home_button', True))
        self.initial['titlebar_hide_on_public_unauthenticated_index'] = bool(
            initial_titlebar_config.get('hide_on_public_unauthenticated_index', False)
        )
        self.initial['titlebar_home_shape'] = initial_titlebar_config.get(
            'buttons_shape',
            initial_titlebar_config.get('home_shape', 'circle'),
        )
        self.initial['titlebar_user_hub_style'] = initial_titlebar_config.get(
            'user_hub_style',
            TITLEBAR_USER_HUB_STYLE_DROPDOWN,
        )
        self.initial['titlebar_actions_order'] = _json_dump(
            normalize_titlebar_actions_order(initial_titlebar_config.get('actions_order')),
            ensure_ascii=False,
        )
        self.initial['titlebar_title_align'] = initial_titlebar_config.get('title_align', 'start')
        self.initial['titlebar_title_size'] = initial_titlebar_config.get('title_size', 'md')
        self.initial['titlebar_height'] = initial_titlebar_config.get('height', 'balanced')
        self.initial['titlebar_surface'] = initial_titlebar_config.get('surface', 'default')
        self.initial['titlebar_logo_treatment'] = initial_titlebar_config.get('logo_treatment', 'none')
        self.initial['titlebar_logo_treatment_shape'] = initial_titlebar_config.get('logo_treatment_shape', 'soft')
        initial_notification_config = normalize_notification_config(
            (
                config.get('notifications', {})
                if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
                else getattr(self.instance, 'notification_config', None)
            ) or config.get('notifications', {})
        )
        self.initial['notification_config'] = _json_dump(initial_notification_config, ensure_ascii=False)
        flash_config = initial_notification_config.get('flash', {})
        drawer_config = initial_notification_config.get('drawer', {})
        bridge_config = initial_notification_config.get('bridge', {})
        email_notification_config = initial_notification_config.get('email', {})
        automatic_config = initial_notification_config.get('automatic', {})
        self.initial['notifications_enabled'] = bool(initial_notification_config.get('enabled', True))
        self.initial['notification_flash_enabled'] = bool(flash_config.get('enabled', True))
        self.initial['notification_flash_position'] = flash_config.get('position', 'top_center')
        self.initial['notification_flash_size'] = flash_config.get('size', 'balanced')
        self.initial['notification_flash_text_size'] = flash_config.get('text_size', 'md')
        self.initial['notification_flash_timeout_ms'] = flash_config.get('timeout_ms', 3200)
        self.initial['notification_flash_max_visible'] = flash_config.get('max_visible', 3)
        self.initial['notification_drawer_enabled'] = bool(drawer_config.get('enabled', True))
        self.initial['notification_badge_enabled'] = bool(drawer_config.get('badge_enabled', True))
        self.initial['notification_bridge_enabled'] = bool(bridge_config.get('django_messages_enabled', False))
        self.initial['notification_email_enabled'] = bool(email_notification_config.get('enabled', False))
        self.initial['notification_email_default'] = bool(email_notification_config.get('default', False))
        if not getattr(self, 'notification_email_available', False):
            self.initial['notification_email_enabled'] = False
            self.initial['notification_email_default'] = False
        self.initial['notification_auto_crud_enabled'] = bool(automatic_config.get('scoped_model_crud', True))
        self.initial['notification_auto_create'] = bool(automatic_config.get('create', True))
        self.initial['notification_auto_update'] = automatic_config.get('update', 'summary')
        self.initial['notification_auto_delete'] = bool(automatic_config.get('delete', True))

        catalog_lang = self.initial.get('default_language') or self.instance.default_language or config.get('default_language', 'en')
        public_sidebar_catalog = discover_sidebar_catalog(lang_code=catalog_lang, include_system_items=False)
        self.sidebar_catalog = discover_sidebar_catalog(lang_code=catalog_lang, include_system_items=True)
        self.sidebar_catalog_fallback = discover_sidebar_catalog(lang_code='en', include_system_items=True)
        seen_home_urls = set()
        home_url_choices = [('', s.get('form_sys_home_url_custom', 'Use a custom URL'))]
        home_url_option_meta = {
            '': {
                'description': s.get('home_url_custom_desc', 'Keep a custom titlebar home URL instead of a discovered page.'),
            }
        }
        for entry in public_sidebar_catalog:
            url_name = entry.get('url_name')
            if not url_name:
                continue
            try:
                resolved_url = reverse(url_name)
            except NoReverseMatch:
                continue
            if resolved_url in seen_home_urls:
                continue
            seen_home_urls.add(resolved_url)
            entry_label = str(entry.get('label') or entry.get('group_label') or url_name).strip()
            home_url_choices.append((resolved_url, entry_label))
            home_url_option_meta[resolved_url] = {
                'description': str(entry.get('group_label') or '').strip(),
                'secondary': url_name,
                'search_text': f"{entry_label} {url_name} {resolved_url}",
            }
        self.fields['home_url_discovered'].choices = home_url_choices
        self.fields['home_url_discovered'].widget.option_meta = home_url_option_meta
        self.initial['home_url_discovered'] = current_home_url if current_home_url in seen_home_urls else ''
        self.fields['public_root_url_discovered'].choices = home_url_choices
        self.fields['public_root_url_discovered'].widget.option_meta = home_url_option_meta
        self.initial['public_root_url_discovered'] = current_public_root_url if current_public_root_url in seen_home_urls else ''

        initial_languages = (
            self.data.get('languages')
            if self.is_bound and 'languages' in self.data
            else self.initial.get('languages')
        ) or {}
        if isinstance(initial_languages, str):
            try:
                initial_languages = json.loads(initial_languages)
            except (TypeError, ValueError, json.JSONDecodeError):
                initial_languages = {}
        current_languages = normalize_language_catalog(initial_languages)
        self.initial['languages'] = _json_dump(current_languages, ensure_ascii=False)
        initial_default_language = (
            self.data.get('default_language')
            if self.is_bound and 'default_language' in self.data
            else self.initial.get('default_language')
        )
        initial_default_language = str(initial_default_language or '').strip().lower().replace('_', '-')
        if initial_default_language in current_languages:
            self.initial['default_language'] = initial_default_language
        else:
            self.initial['default_language'] = 'en' if 'en' in current_languages else next(iter(current_languages), 'en')

        initial_system_names = (
            self.data.get('system_names')
            if self.is_bound and 'system_names' in self.data
            else self.initial.get('system_names')
        ) or {}
        if isinstance(initial_system_names, str):
            try:
                initial_system_names = json.loads(initial_system_names)
            except (TypeError, ValueError, json.JSONDecodeError):
                initial_system_names = {}
        initial_system_names = normalize_system_names(initial_system_names)
        self.initial['system_names'] = _json_dump(initial_system_names, ensure_ascii=False)

        initial_translation_overrides = (
            self.data.get('translations_override')
            if self.is_bound and 'translations_override' in self.data
            else self.initial.get('translations_override')
        ) or {}
        if isinstance(initial_translation_overrides, str):
            try:
                initial_translation_overrides = json.loads(initial_translation_overrides)
            except (TypeError, ValueError, json.JSONDecodeError):
                initial_translation_overrides = {}
        if not isinstance(initial_translation_overrides, dict):
            initial_translation_overrides = {}
        suggested_languages = [
            code for code in discover_translation_languages(config.get('translations', {}), initial_translation_overrides)
            if code not in current_languages
        ]

        self.language_catalog_html = render_to_string(
            'dlux/includes/language_catalog_editor.html',
            {
                'language_rows': [
                    {
                        'code': code,
                        'name': payload.get('name', code),
                        'dir': payload.get('dir', 'ltr'),
                        'flag': payload.get('flag', ''),
                        'system_name': initial_system_names.get(code, ''),
                    }
                    for code, payload in current_languages.items()
                ],
                'default_language': self.initial.get('default_language', 'en'),
                'suggested_languages': suggested_languages,
                'DLUX_STRINGS': s,
            },
        )
        self.system_names_html = render_to_string(
            'dlux/includes/system_names_editor.html',
            {
                'language_rows': [
                    {
                        'code': code,
                        'name': payload.get('name', code),
                        'system_name': initial_system_names.get(code, ''),
                    }
                    for code, payload in current_languages.items()
                ],
                'DLUX_STRINGS': s,
            },
        )
        translation_groups = build_translation_matrix_groups(current_languages, initial_translation_overrides)
        for group in translation_groups:
            if group.get('id') == 'project':
                group['label'] = s.get('translation_matrix_group_project', group.get('label') or 'Project translations')
            elif group.get('id') == 'runtime':
                group['label'] = s.get('translation_matrix_group_runtime', group.get('label') or 'Settings overrides')
        self.translation_matrix_html = render_to_string(
            'dlux/includes/translation_matrix_editor.html',
            {
                'languages': current_languages,
                'translation_groups': translation_groups,
                'DLUX_STRINGS': s,
            },
        )

        self.theme_picker_html = render_to_string(
            'dlux/includes/theme_settings_matrix.html',
            {
                'selected_theme': self.initial.get('default_theme', 'light'),
                'picker_mode': 'setup',
                'input_id': 'id_default_theme',
                'allowed_input_name': 'allowed_themes',
                'allowed_themes': set(self.initial.get('allowed_themes') if isinstance(self.initial.get('allowed_themes'), (list, tuple, set)) else []),
                'DLUX_STRINGS': s,
                'DLUX_THEMES': get_theme_options(s),
                'label': self.fields['default_theme'].label,
                'help_text': self.fields['allowed_themes'].help_text,
            },
        )
        
        from .fonts import get_builtin_fonts
        self.font_picker_html = render_to_string(
            'dlux/includes/font_settings_matrix.html',
            {
                'picker_mode': 'setup',
                'input_id': 'id_allowed_fonts',
                'allowed_input_name': 'allowed_fonts',
                'allowed_fonts': set(self.initial.get('allowed_fonts') if isinstance(self.initial.get('allowed_fonts'), (list, tuple, set)) else []),
                'DLUX_STRINGS': s,
                'DLUX_FONTS': get_builtin_fonts(),
                'label': self.fields['allowed_fonts'].label,
                'help_text': self.fields['allowed_fonts'].help_text,
            },
        )
        
        default_fonts_data = self.initial.get('default_fonts') or {}
        if isinstance(default_fonts_data, str):
            try:
                default_fonts_data = json.loads(default_fonts_data)
            except (TypeError, ValueError, json.JSONDecodeError):
                default_fonts_data = {}

        self.language_fonts_editor_html = render_to_string(
            'dlux/includes/language_fonts_editor.html',
            {
                'current_languages': current_languages,
                'default_fonts': default_fonts_data,
                'DLUX_FONTS': get_builtin_fonts(),
                'DLUX_STRINGS': s,
            },
        )

        self.sidebar_builder_html = render_to_string(
            'dlux/includes/sidebar_builder.html',
            {
                'sidebar_catalog': self.sidebar_catalog,
                'sidebar_catalog_json': _json_dump(self.sidebar_catalog, ensure_ascii=False),
                'sidebar_catalog_fallback_json': _json_dump(self.sidebar_catalog_fallback, ensure_ascii=False),
                'sidebar_config_json': _json_dump(self.initial.get('sidebar_config', {}), ensure_ascii=False),
                'mode': self.mode,
                'DLUX_STRINGS': s,
            },
        )
        self.navbar_builder_html = render_to_string(
            'dlux/includes/navbar_builder.html',
            {
                'navbar_catalog_json': _json_dump(self.sidebar_catalog, ensure_ascii=False),
                'navbar_config_json': _json_dump(initial_navbar_config, ensure_ascii=False),
                'languages_json': _json_dump(current_languages, ensure_ascii=False),
                'mode': self.mode,
                'DLUX_STRINGS': s,
            },
        )
        from dlux.discovery import build_log_model_catalog
        log_catalog = build_log_model_catalog()

        def _log_action_label(key):
            base = {
                'create': s.get('action_create', 'Create'),
                'update': s.get('action_update', 'Update'),
                'delete': s.get('action_delete', 'Delete'),
            }
            return base.get(key) or s.get(f'action_{key}', key.replace('_', ' ').title())

        for _bucket in ('user', 'system'):
            for _item in log_catalog[_bucket]:
                _item['display_actions'] = [
                    {'key': a, 'label': _log_action_label(a)}
                    for a in _item.get('actions') or ('create', 'update', 'delete')
                ]

        self.log_builder_html = render_to_string(
            'dlux/includes/log_builder.html',
            {
                'log_config_json': _json_dump(initial_log_config, ensure_ascii=False),
                'sections': [
                    {'key': 'user', 'title': s.get('form_sys_log_user', 'User activity (project)'), 'models': log_catalog['user']},
                    {'key': 'system', 'title': s.get('form_sys_log_system', 'System activity (dlux)'), 'models': log_catalog['system']},
                ],
                'actions': [
                    {'key': 'create', 'label': s.get('action_create', 'Create')},
                    {'key': 'update', 'label': s.get('action_update', 'Update')},
                    {'key': 'delete', 'label': s.get('action_delete', 'Delete')},
                ],
                'audit_events': [
                    {'key': key, 'label': s.get(f'form_sys_log_audit_{key}', key.replace('_', ' ').title())}
                    for key in initial_log_config.get('audit', {}).get('events', {}).keys()
                ],
                'DLUX_STRINGS': s,
            },
        )
        self.profile_builder_html = render_to_string(
            'dlux/includes/profile_builder.html',
            {
                'profile_config_json': _json_dump(initial_profile_config, ensure_ascii=False),
                'page_toggles': [
                    {'key': 'show_completion_widget', 'label': s.get('profile_show_completion', 'Show profile completion widget')},
                    {'key': 'show_session_device_cards', 'label': s.get('profile_show_devices', 'Show session/device cards')},
                    {'key': 'show_activity_feed', 'label': s.get('profile_show_activity', 'Show activity feed')},
                    {'key': 'allow_user_home_url', 'label': s.get('profile_allow_user_home_url', 'Allow users to set their landing page')},
                ],
                'nudge_options': [
                    {'key': 'off', 'label': s.get('nudge_off', 'Off')},
                    {'key': 'subtle', 'label': s.get('nudge_subtle', 'Subtle')},
                    {'key': 'persistent', 'label': s.get('nudge_persistent', 'Persistent')},
                ],
                'onboarding_toggles': [
                    {'key': 'theme', 'label': s.get('options_theme', 'Theme')},
                    {'key': 'language', 'label': s.get('options_language', 'Language')},
                    {'key': 'fonts', 'label': s.get('options_font', 'Font')},
                ],
                'DLUX_STRINGS': s,
            },
        )
        self.titlebar_actions_order_html = build_titlebar_actions_order_builder(
            initial_titlebar_config.get('actions_order'),
            s,
            visible=self.initial.get('titlebar_user_hub_style') == TITLEBAR_USER_HUB_STYLE_ACTIONS,
        )

        modal_desc = s.get('system_settings_modal_desc', 'حدّث العلامة التجارية واللغات والشريط الجانبي من نافذة الإعدادات.')
        intro_html = ''
        if self.mode != 'setup':
            intro_html = (
                f"<div class='dlux-system-settings-intro mb-4'>"
                f"<p class='text-muted mb-0'>{modal_desc}</p>"
                f"</div>"
            )

        self.helper = FormHelper()
        self.helper.form_tag = False

        def _step_css_class(index):
            classes = ['wizard-step']
            if self.single_step_mode and self.single_step_index != index:
                classes.append('d-none')
            elif not self.single_step_mode and index > 0:
                classes.append('d-none')
            return ' '.join(classes)

        email_password_field_class = 'col-lg-4 dlux-email-config-password-field'
        if self.initial.get('email_config_secret_storage') != 'encrypted_db':
            email_password_field_class += ' d-none'

        # Build step 1 fields dynamically - import only shown in initial setup
        step_1_fields = [
            HTML(f"<div class='mb-3'><span class='badge rounded-pill text-bg-primary'>{s.get('system_setup_step1', 'Step 1: Identity')}</span></div>"),
        ]
        if self.mode == 'setup':
            step_1_fields.append(build_archive_file_field('settings_import_file'))
            step_1_fields.append(Field('settings_import_processed'))
            step_1_fields.append(HTML(
                "<div class='dlux-import-finish-cta d-none' data-settings-import-finish>"
                f"<div><strong>{s.get('system_setup_import_finish', 'Finish setup from imported config')}</strong>"
                f"<small>{s.get('system_setup_import_finish_desc', 'Save the imported setup now, or keep editing first.')}</small></div>"
                f"<button type='submit' class='btn btn-primary'>{s.get('system_setup_import_finish_button', 'Finish setup')}</button>"
                "</div>"
            ))
        step_1_fields.extend([
            HTML(self.system_names_html),
            Field('system_names'),
            Row(
                Div(build_archive_file_field('logo', css_class='col-md-6'), css_class='col-md-6'),
                Div(build_archive_file_field('favicon', css_class='col-md-6'), css_class='col-md-6'),
                css_class='row'
            ),
        ])

        self.helper.layout = Layout(
            HTML(
                (
                    f"<div class='dlux-system-settings-shell mode-{self.mode}'>"
                    f"{intro_html}"
                )
            ),
            Div(
                *step_1_fields,
                css_class=_step_css_class(0),
            ),
            Div(
                HTML(f"<div class='mb-3'><span class='badge rounded-pill text-bg-primary'>{s.get('system_setup_step2', 'Step 2: Languages')}</span></div>"),
                HTML(self.language_catalog_html),
                Row(
                    Div(Field('default_language'), css_class='d-none'),
                    build_settings_toggle_field(self, 'allow_user_language_override', css_class='col-lg-12'),
                    css_class='mb-3',
                ),
                HTML(self.translation_matrix_html),
                Field('languages'),
                Field('translations_override'),
                css_class=_step_css_class(1),
            ),
            Div(
                HTML(f"<div class='mb-3'><span class='badge rounded-pill text-bg-primary'>{s.get('system_setup_step3', 'Step 3: Security')}</span></div>"),
                HTML(
                    f"<div class='dlux-email-config-section' data-email-config-section>"
                    f"<h6 class='fw-bold my-3'>{s.get('email_delivery_settings_title', 'Email Delivery')}</h6>"
                    f"<p class='small text-muted mb-3'>"
                    f"{s.get('email_delivery_settings_desc', 'Visible when public signup or email 2FA is enabled. If the web service is isolated, choose Internal SMTP relay and enter the upstream SMTP server below; the generated relay reads this UI config and handles internet egress. If the web service can reach SMTP directly, choose Direct SMTP from web service. Use Encrypted database secret for UI-managed passwords, or Environment / secrets when deployers intentionally keep mail secrets outside the UI.')}"
                    f"</p>"
                ),
                Row(
                    Div(Field('email_config_transport'), css_class='col-lg-3'),
                    Div(Field('email_config_provider_preset'), css_class='col-lg-3'),
                    Div(Field('email_config_secret_storage'), css_class='col-lg-3'),
                    Div(Field('email_config_default_from_email'), css_class='col-lg-3'),
                ),
                Row(
                    Div(Field('email_config_host'), css_class='col-lg-4'),
                    Div(Field('email_config_port'), css_class='col-lg-2'),
                    build_email_toggle_field(self, 'email_config_use_tls', css_class='col-lg-2'),
                    build_email_toggle_field(self, 'email_config_use_ssl', css_class='col-lg-2'),
                    Div(Field('email_config_username'), css_class='col-lg-2'),
                ),
                Row(
                    Div(Field('email_config_password'), css_class=email_password_field_class),
                ),
                Row(
                    Div(Field('email_config_failure_recipients'), css_class='col-lg-12'),
                ),
                Field('email_config'),
                HTML(
                    f"<div class='alert alert-info small' data-autoclose='false'>"
                    f"Email service: {get_email_service_status().get('reason', 'unknown')}."
                    f"</div>"
                ),
                Row(
                    Div(Field('email_config_test_recipient'), css_class='col-lg-8'),
                    Div(
                        HTML(
                            "<button type='button' class='btn btn-outline-primary w-100' "
                            "data-email-send-test "
                            f"data-email-send-test-url='{reverse('email_send_test')}'>"
                            f"{s.get('email_send_test_button', 'Send test email')}</button>"
                        ),
                        css_class='col-lg-4 d-flex align-items-end',
                    ),
                    css_class='align-items-end',
                ),
                HTML("<div class='small mt-2' data-email-send-test-result aria-live='polite'></div>"),
                HTML("</div>"),
                HTML(f"<h6 class='fw-bold my-3'>{s.get('access_security_settings_title', s.get('system_settings_security', 'Access & Security'))}</h6>"),
                Row(
                    build_settings_toggle_field(self, 'public_root', css_class='col-lg-6'),
                    build_settings_toggle_field(self, 'email_2fa', css_class='col-lg-6'),
                    build_settings_toggle_field(self, 'prevent_multiple_active_sessions', css_class='col-lg-6'),
                    build_settings_toggle_field(self, 'login_lockout_enabled', css_class='col-lg-6'),
                    build_settings_toggle_field(self, 'enforce_strong_passwords', css_class='col-lg-6'),
                    css_class='g-3 mb-3',
                ),
                Field('auth_config'),
                HTML(f"<h6 class='fw-bold my-3'>{s.get('client_ip_settings_title')}</h6>"),
                HTML(
                    f"<p class='small text-muted mb-3'>"
                    f"{s.get('client_ip_settings_desc')}"
                    f"</p>"
                ),
                Row(
                    Div(Field('client_ip_mode'), css_class='col-lg-4'),
                    Div(
                        Field('client_ip_trusted_proxy_hops'),
                        css_class=(
                            "col-lg-4 dlux-client-ip-hops-field"
                            f"{' d-none' if self.initial.get('client_ip_mode') != CLIENT_IP_MODE_X_FORWARDED_FOR else ''}"
                        ),
                        data_client_ip_hops='true',
                        aria_hidden='false' if self.initial.get('client_ip_mode') == CLIENT_IP_MODE_X_FORWARDED_FOR else 'true',
                    ),
                    Div(
                        Field('client_ip_custom_header'),
                        css_class=(
                            "col-lg-4 dlux-client-ip-custom-header-field"
                            f"{' d-none' if self.initial.get('client_ip_mode') != CLIENT_IP_MODE_CUSTOM else ''}"
                        ),
                        data_client_ip_custom_header='true',
                        aria_hidden='false' if self.initial.get('client_ip_mode') == CLIENT_IP_MODE_CUSTOM else 'true',
                    ),
                ),
                Field('client_ip_config'),
                HTML(f"<h6 class='fw-bold my-3'>{s.get('root_home_settings_title', 'Home & Public Root Destinations')}</h6>"),
                Row(
                    Div(Field('home_url_discovered'), css_class='col-lg-6'),
                    Div(Field('home_url', dir='ltr'), css_class='col-lg-6'),
                ),
                Row(
                    build_settings_toggle_field(
                        self,
                        'public_root_split_enabled',
                        css_class=f"col-lg-12 dlux-public-root-dependent{' d-none' if not self.initial.get('public_root', False) else ''}",
                        attrs={
                            'data_public_root_dependent': 'true',
                            'aria_hidden': 'false' if self.initial.get('public_root', False) else 'true',
                        },
                    ),
                    css_class='g-3 mb-3',
                ),
                Row(
                    Div(
                        Field('public_root_url_discovered'),
                        css_class=(
                            "col-lg-6 dlux-public-root-split-dependent"
                            f"{' d-none' if not (self.initial.get('public_root', False) and self.initial.get('public_root_split_enabled', False)) else ''}"
                        ),
                        data_public_root_split_dependent='true',
                        aria_hidden='false' if (self.initial.get('public_root', False) and self.initial.get('public_root_split_enabled', False)) else 'true',
                    ),
                    Div(
                        Field('public_root_url', dir='ltr'),
                        css_class=(
                            "col-lg-6 dlux-public-root-split-dependent"
                            f"{' d-none' if not (self.initial.get('public_root', False) and self.initial.get('public_root_split_enabled', False)) else ''}"
                        ),
                        data_public_root_split_dependent='true',
                        aria_hidden='false' if (self.initial.get('public_root', False) and self.initial.get('public_root_split_enabled', False)) else 'true',
                    ),
                ),
                Row(
                    build_settings_toggle_field(self, 'public_registration_enabled', css_class='col-lg-12'),
                    css_class='g-3 mb-3',
                ),
                Row(
                    Div(
                        Field('registration_activation_mode'),
                        css_class=f"col-lg-6 dlux-public-registration-dependent{' d-none' if not self.initial.get('public_registration_enabled', False) else ''}",
                        data_public_registration_dependent='true',
                        aria_hidden='false' if self.initial.get('public_registration_enabled', False) else 'true',
                    ),
                    build_settings_toggle_field(
                        self,
                        'registration_throttle_enabled',
                        css_class=f"col-lg-6 dlux-public-registration-dependent{' d-none' if not self.initial.get('public_registration_enabled', False) else ''}",
                        attrs={
                            'data_public_registration_dependent': 'true',
                            'aria_hidden': 'false' if self.initial.get('public_registration_enabled', False) else 'true',
                        },
                    ),
                    css_class='g-3',
                ),
                css_class=_step_css_class(2),
            ),
            Div(
                HTML(f"<div class='mb-3'><span class='badge rounded-pill text-bg-primary'>{s.get('system_setup_step4', 'Step 4: Login Page')}</span></div>"),
                HTML(f"<h6 class='fw-bold my-3'>{s.get('login_page_settings_title', 'Login Page Settings')}</h6>"),
                HTML(f"<p class='small text-muted mb-3'>{s.get('login_page_settings_desc', 'Choose the login page layout and customise the side banner and logo treatment.')}</p>"),
                # Row 1: layout style — full width, as-is
                Field('login_style'),
                # Logo visibility toggle
                Row(
                    build_settings_toggle_field(self, 'login_show_logo', css_class='col-12'),
                    css_class='g-3 mt-1 mb-2',
                ),
                # Row 2: hero message textareas — one column per language
                Div(
                    HTML(
                        f"<h6 class='fw-bold mt-4 mb-2'>{s.get('form_sys_login_hero_message', 'Hero Message')}</h6>"
                        f"<p class='small text-muted mb-3'>{s.get('help_sys_login_hero_message', 'Text shown on the start half. Supports Markdown: **bold**, *italic*, # Heading, [link](url), lists.')}</p>"
                    ),
                    Row(
                        *[
                            Div(
                                Field(field_name),
                                css_class=(
                                    'col-lg-6' if len(getattr(self, '_login_hero_lang_fields', [])) == 2
                                    else 'col-lg-4' if len(getattr(self, '_login_hero_lang_fields', [])) == 3
                                    else 'col-lg-3' if len(getattr(self, '_login_hero_lang_fields', [])) >= 4
                                    else 'col-12'
                                ),
                            )
                            for _lang_code, _lang_label, field_name in getattr(self, '_login_hero_lang_fields', [])
                        ],
                        css_class='g-3',
                    ),
                    css_class=(
                        "dlux-login-hero-field"
                        f"{' d-none' if self.initial.get('login_style', 'split') != 'fullpage' else ''}"
                    ),
                    data_login_hero_field='true',
                    aria_hidden='false' if self.initial.get('login_style', 'split') == 'fullpage' else 'true',
                ),
                # Row 3: logo treatment + plate shape side by side
                # col-lg-7 (4 tiles) vs col-lg-5 (3 tiles) gives near-equal tile widths:
                # 7/12÷4 ≈ 14.6%  vs  5/12÷3 ≈ 13.9% — visually uniform.
                # align-items-stretch ensures both grids share the same row height.
                HTML(f"<h6 class='fw-bold mt-4 mb-2'>{s.get('form_sys_login_logo_treatment', 'Logo Treatment')}</h6>"),
                Row(
                    Div(
                        Field('login_logo_treatment'),
                        css_class=(
                            "col-lg-7 d-flex flex-column dlux-logo-treatment-primary dlux-login-logo-treatment-primary"
                            f"{' dlux-logo-treatment-primary--wide' if self.initial.get('login_logo_treatment', 'none') != 'plate' else ''}"
                        ),
                    ),
                    Div(
                        Field('login_logo_treatment_shape'),
                        css_class=(
                            "col-lg-5 d-flex flex-column dlux-login-plate-shape-field"
                            f"{' d-none' if self.initial.get('login_logo_treatment', 'none') != 'plate' else ''}"
                        ),
                        data_login_plate_shape='true',
                        aria_hidden='false' if self.initial.get('login_logo_treatment', 'none') == 'plate' else 'true',
                    ),
                    css_class='g-3 align-items-stretch',
                ),
                # Row 4: optional banner colour (transparent by default)
                Row(
                    Div(Field('login_banner_color'), css_class='col-lg-4'),
                    css_class='g-3 mt-2 mb-3',
                ),
                Field('login_config'),
                css_class=_step_css_class(3),
            ),
            Div(
                HTML(f"<div class='mb-3'><span class='badge rounded-pill text-bg-primary'>{s.get('system_setup_step5', 'Step 5: Sidebar')}</span></div>"),
                Row(
                    build_settings_toggle_field(self, 'sidebar_enabled', css_class='col-lg-12'),
                    css_class='g-3 mb-3',
                ),
                HTML(
                    f"<div class='alert alert-warning small mb-3{' d-none' if self.initial.get('sidebar_enabled', True) else ''}' "
                    f"data-sidebar-disabled-note>"
                    f"{s.get('sidebar_disabled_navigation_note', 'Disabling the sidebar can leave the app without built-in navigation. You will need to rely on dashboards and modals, or add your own back buttons and navigation entries in forms, lists, and dashboards. As of v2.2.0, Dynamic Sections Manager is only available through the sidebar, so add a dashboard button or custom entry if you need access. This warning will be updated if a built-in workaround is added later.')}"
                    f"</div>"
                ),
                HTML("<div class='dlux-sidebar-dependent-settings' data-sidebar-dependent>"),
                HTML(
                    f"<div class='d-none' data-sidebar-tooling-state "
                    f"data-sections-manager-available=\"{'true' if self.sidebar_sections_manager_available else 'false'}\"></div>"
                ),
                Row(
                    build_settings_toggle_field(self, 'sidebar_enable_reorder', css_class='col-lg-6'),
                    build_settings_toggle_field(self, 'sidebar_enable_toolbar', css_class='col-lg-6'),
                    css_class='g-3 mb-3',
                ),
                Row(
                    build_settings_toggle_field(self, 'sidebar_show_icons', css_class='col-lg-6'),
                    build_settings_toggle_field(self, 'sidebar_allow_user_density', css_class='col-lg-6'),
                    css_class='g-3 mb-3',
                ),
                HTML(
                    f"<div class='alert alert-warning small mb-3{' d-none' if self.initial.get('sidebar_enable_toolbar', True) else ''}' "
                    f"data-sidebar-toolbar-note>"
                    f"{s.get('sidebar_toolbar_disable_note', 'Disabling the sidebar toolbar also removes the only built-in shortcut to Dynamic Sections Manager. If you still want UI access, enable system items in the sidebar builder and add Section Management to your sidebar.')}"
                    f"</div>"
                ),
                Row(
                    Div(Field('sidebar_density'), css_class='col-lg-6'),
                    Div(Field('sidebar_collapse_mode'), css_class='col-lg-6'),
                ),
                HTML(self.sidebar_builder_html),
                HTML("</div>"),
                Field('sidebar_config'),
                css_class=_step_css_class(4),
            ),
            Div(
                HTML(f"<div class='mb-3'><span class='badge rounded-pill text-bg-primary'>{s.get('system_setup_step6', 'Step 6: Nav Bar')}</span></div>"),
                HTML(f"<h6 class='fw-bold my-3'>{s.get('navbar_settings_title', '')}</h6>"),

                Row(
                    build_settings_toggle_field(self, 'navbar_enabled', css_class='col-lg-12'),
                    css_class='g-3 mb-3',
                ),
                HTML(
                    f"<div class='dlux-navbar-dependent-settings{' d-none' if not self.initial.get('navbar_enabled', False) else ''}' "
                    f"data-navbar-dependent>"
                ),
                Row(
                    build_settings_toggle_field(self, 'navbar_allow_user_mode_override', css_class='col-lg-12'),
                    css_class='g-3 mb-3',
                ),
                Div(Field('navbar_default_mode'), css_class='mb-3'),
                HTML(self.navbar_builder_html),
                HTML("</div>"),
                Field('navbar_config'),
                css_class=_step_css_class(5),
            ),
            Div(
                HTML(f"<div class='mb-3'><span class='badge rounded-pill text-bg-primary'>{s.get('system_setup_step7', 'Step 7: Titlebar')}</span></div>"),
                HTML(f"<h6 class='fw-bold my-3'>{s.get('titlebar_settings_title', 'Titlebar Settings')}</h6>"),
                Row(
                    build_settings_toggle_field(self, 'titlebar_show_title', css_class='col-lg-6 col-xl-3'),
                    build_settings_toggle_field(self, 'titlebar_show_logo', css_class='col-lg-6 col-xl-3'),
                    build_settings_toggle_field(self, 'titlebar_show_home_button', css_class='col-lg-6 col-xl-3'),
                    build_settings_toggle_field(self, 'titlebar_hide_on_public_unauthenticated_index', css_class='col-lg-6 col-xl-3'),
                    css_class='g-3 mb-3'
                ),
                Row(
                    Div(Field('titlebar_title_align'), css_class='col-lg-6'),
                    Div(Field('titlebar_title_size'), css_class='col-lg-6'),
                ),
                Row(
                    Div(Field('titlebar_home_shape'), css_class='col-lg-6'),
                    Div(Field('titlebar_height'), css_class='col-lg-6'),
                ),
                Row(
                    Div(Field('titlebar_user_hub_style'), css_class='col-lg-12'),
                    css_class='g-3 mb-3',
                ),
                HTML(self.titlebar_actions_order_html),
                Field('titlebar_actions_order'),
                Row(
                    Div(Field('titlebar_surface'), css_class='col-lg-12'),
                ),
                Row(
                    Div(
                        Field('titlebar_logo_treatment'),
                        css_class=(
                            "col-lg-8 dlux-logo-treatment-primary dlux-titlebar-logo-dependent dlux-titlebar-logo-treatment-primary"
                            f"{' d-none' if not self.initial.get('titlebar_show_logo', True) else ''}"
                            f"{' dlux-logo-treatment-primary--wide' if self.initial.get('titlebar_show_logo', True) and self.initial.get('titlebar_logo_treatment', 'none') != 'plate' else ''}"
                        ),
                        aria_hidden='false' if self.initial.get('titlebar_show_logo', True) else 'true',
                    ),
                    Div(
                        Field('titlebar_logo_treatment_shape'),
                        css_class=(
                            "col-lg-4 dlux-titlebar-logo-plate-dependent"
                            f"{' d-none' if not (self.initial.get('titlebar_show_logo', True) and self.initial.get('titlebar_logo_treatment', 'none') == 'plate') else ''}"
                        ),
                        aria_hidden='false' if (
                            self.initial.get('titlebar_show_logo', True)
                            and self.initial.get('titlebar_logo_treatment', 'none') == 'plate'
                        ) else 'true',
                    ),
                    css_class='g-3 mb-3',
                ),
                css_class=_step_css_class(6),
            ),
            Div(
                HTML(f"<div class='mb-3'><span class='badge rounded-pill text-bg-primary'>{s.get('system_setup_step8', 'Step 8: Notifications')}</span></div>"),
                HTML(f"<h6 class='fw-bold my-3'>{s.get('notification_settings_title', 'Notifications')}</h6>"),
                Row(
                    build_settings_toggle_field(self, 'notifications_enabled', css_class='col-lg-12'),
                    css_class='g-3 mb-3',
                ),
                HTML(
                    f"<div class='dlux-notifications-dependent-settings{' d-none' if not self.initial.get('notifications_enabled', True) else ''}' "
                    f"data-notifications-dependent>"
                ),
                Row(
                    build_settings_toggle_field(self, 'notification_flash_enabled', css_class='col-lg-6 col-xl-3'),
                    build_settings_toggle_field(self, 'notification_drawer_enabled', css_class='col-lg-6 col-xl-3'),
                    build_settings_toggle_field(self, 'notification_badge_enabled', css_class='col-lg-6 col-xl-3'),
                    build_settings_toggle_field(self, 'notification_bridge_enabled', css_class='col-lg-6 col-xl-3'),
                    css_class='g-3 mb-3',
                ),
                Row(
                    Div(Field('notification_flash_position'), css_class='col-lg-4'),
                    Div(Field('notification_flash_size'), css_class='col-lg-4'),
                    Div(Field('notification_flash_text_size'), css_class='col-lg-4'),
                    css_class='g-3',
                ),
                Row(
                    Div(Field('notification_flash_timeout_ms'), css_class='col-lg-4'),
                    Div(Field('notification_flash_max_visible'), css_class='col-lg-4'),
                    Div(Field('notification_auto_update'), css_class='col-lg-4'),
                    css_class='g-3 mb-3',
                ),
                Row(
                    build_settings_toggle_field(self, 'notification_auto_crud_enabled', css_class='col-lg-4'),
                    build_settings_toggle_field(self, 'notification_auto_create', css_class='col-lg-4'),
                    build_settings_toggle_field(self, 'notification_auto_delete', css_class='col-lg-4'),
                    css_class='g-3 mb-3',
                ),
                Row(
                    build_settings_toggle_field(self, 'notification_email_enabled', css_class='col-lg-6'),
                    build_settings_toggle_field(self, 'notification_email_default', css_class='col-lg-6'),
                    css_class='g-3 mb-3',
                ),
                HTML("</div>"),
                Field('notification_config'),
                css_class=_step_css_class(7),
            ),
            Div(
                HTML(f"<div class='mb-3'><span class='badge rounded-pill text-bg-primary'>{s.get('system_setup_step9', 'Step 9: Themes & Typography')}</span></div>"),
                Row(
                    Div(
                        HTML(self.theme_picker_html),
                        Field('default_theme'),
                        css_class='mb-3'
                    ),
                ),
                Row(
                    build_settings_toggle_field(self, 'allow_user_theme_override', css_class='col-12')
                ),
                HTML(f"<h6 class='fw-bold my-3'>{s.get('typography_settings_title', 'Typography Settings')}</h6>"),
                HTML(self.font_picker_html),
                # Field('allowed_fonts'),
                build_settings_toggle_field(self, 'allow_user_font_override', css_class='col-12 mt-2'),
                HTML(self.language_fonts_editor_html),
                Field('default_fonts'),
                HTML(f"<h6 class='fw-bold my-3'>{s.get('tables_settings_title', 'Tables Settings')}</h6>"),
                Row(
                    Div(Field('default_table_density'), css_class='col'),
                    css_class='mb-3'
                ),
                css_class=_step_css_class(8),
            ),
            Div(
                HTML(f"<div class='mb-3'><span class='badge rounded-pill text-bg-primary'>{s.get('system_setup_step10', 'Step 10: Logging')}</span></div>"),
                HTML(f"<h6 class='fw-bold my-3'>{s.get('log_settings_title', 'Activity Logging')}</h6>"),
                HTML(self.log_builder_html),
                Field('log_config'),
                css_class=_step_css_class(9),
            ),
            Div(
                HTML(f"<div class='mb-3'><span class='badge rounded-pill text-bg-primary'>{s.get('system_setup_step11', 'Step 11: Profile Page')}</span></div>"),
                HTML(f"<h6 class='fw-bold my-3'>{s.get('profile_settings_title', 'Profile Page & Onboarding')}</h6>"),
                HTML(self.profile_builder_html),
                Field('profile_config'),
                css_class=_step_css_class(10),
            ),
            Div(
                HTML(f"<div class='mb-3'><span class='badge rounded-pill text-bg-primary'>{s.get('system_setup_step12', 'Step 12: Backups')}</span></div>"),
                HTML(f"<h6 class='fw-bold my-3'>{s.get('backup_settings_title', 'System Backup Policy')}</h6>"),
                HTML(f"<div class='alert alert-info'>{s.get('backup_settings_update_notice', 'Inline updates and rollbacks always create and verify a full system backup before maintenance. An update is stopped if that backup fails.')}</div>"),
                build_settings_toggle_field(self, 'backup_scheduled_enabled', css_class='col-12'),
                Row(
                    Div(Field('backup_schedule_interval_hours', css_class='form-control'), css_class='col-12 col-lg-4'),
                    Div(Field('backup_retention_days', css_class='form-control'), css_class='col-12 col-lg-4'),
                    Div(Field('backup_max_backups_to_keep', css_class='form-control'), css_class='col-12 col-lg-4'),
                    css_class='g-3',
                ),
                Field('backup_auto_export_target', css_class='form-control font-monospace', dir='ltr'),
                Field('backup_config'),
                css_class=_step_css_class(11),
            ),
            FormActions(
                HTML(
                    f"<div class='d-flex flex-wrap justify-content-end align-items-center gap-2 mt-4 dlux-setup-wizard-actions' dir='{_get_ui_direction()}'>"
                    f"<button type='submit' name='submit' class='btn btn-primary px-5 rounded-pill fw-bold dlux-btn-submit'>"
                    f"{s.get('btn_save', 'Save')}</button>"
                    f"</div>"
                )
            ) if self.single_step_mode else FormActions(
                HTML(
                    f"<div class='d-flex flex-wrap justify-content-end align-items-center gap-2 mt-4 dlux-setup-wizard-actions' dir='{_get_ui_direction()}'>"
                    f"<button type='button' class='btn btn-outline-secondary rounded-pill px-4 dlux-btn-prev'>"
                    f"{s.get('btn_prev', 'Previous')}</button>"
                    f"<button type='button' class='btn btn-outline-primary rounded-pill px-4 dlux-btn-next'>"
                    f"{s.get('btn_next', 'Next')}</button>"
                    f"<button type='submit' name='submit' class='btn btn-primary px-5 rounded-pill fw-bold dlux-btn-submit'>"
                    f"{s.get('btn_save', 'Save')}</button>"
                    f"</div>"
                )
            ),
            HTML("</div>")
        )

    def clean_system_names(self):
        data = self.cleaned_data.get('system_names')
        if not data:
            return {}
        try:
            parsed = json.loads(data) if isinstance(data, str) else data
        except json.JSONDecodeError:
            raise ValidationError("Invalid system names JSON format.")
        if not isinstance(parsed, dict):
            raise ValidationError("System names must be a valid JSON object.")
        return normalize_system_names(parsed)

    def clean_languages(self):
        data = self.cleaned_data.get('languages')
        if not data:
            return normalize_language_catalog()
        try:
            parsed = json.loads(data) if isinstance(data, str) else data
            if not isinstance(parsed, dict):
                raise ValidationError("Must be a valid JSON dictionary.")
            return normalize_language_catalog(parsed)
        except json.JSONDecodeError:
            raise ValidationError("Invalid JSON format.")

    def clean_translations_override(self):
        data = self.cleaned_data.get('translations_override')
        if not data:
            return {}
        try:
            parsed = json.loads(data) if isinstance(data, str) else data
            if not isinstance(parsed, dict):
                raise ValidationError("Must be a valid JSON dictionary.")
            cleaned = {}
            for lang, values in parsed.items():
                if not isinstance(values, dict):
                    continue
                lang_values = {}
                for key, value in values.items():
                    text = str(value or '').strip()
                    if key and text:
                        lang_values[str(key)] = text
                if lang_values:
                    cleaned[str(lang).split('-')[0].lower()] = lang_values
            return cleaned
        except json.JSONDecodeError:
            raise ValidationError("Invalid JSON format.")

    def clean_default_language(self):
        return str(self.cleaned_data.get('default_language') or 'en').strip().lower().replace('_', '-')

    def clean_allowed_fonts(self):
        if self.is_bound and self.mode != 'setup' and self.single_step_mode and 'allowed_fonts' not in self.data:
            preserved = getattr(self.instance, 'allowed_fonts', None)
            if preserved in (None, ''):
                preserved = self.initial.get('allowed_fonts')
            return list(normalize_allowed_fonts(preserved))
        data = self.cleaned_data.get('allowed_fonts')
        if not data:
            return []
        return list(data)

    def clean_default_fonts(self):
        if self.is_bound and self.mode != 'setup' and self.single_step_mode and 'default_fonts' not in self.data:
            preserved = getattr(self.instance, 'default_fonts', None)
            if preserved in (None, ''):
                preserved = self.initial.get('default_fonts')
            if isinstance(preserved, str):
                try:
                    preserved = json.loads(preserved)
                except json.JSONDecodeError:
                    preserved = {}
            return preserved if isinstance(preserved, dict) else {}
        data = self.cleaned_data.get('default_fonts')
        if not data:
            return {}
        try:
            parsed = json.loads(data) if isinstance(data, str) else data
            if not isinstance(parsed, dict):
                return {}
            return parsed
        except json.JSONDecodeError:
            return {}

    def clean_default_theme(self):
        if self.is_bound and self.mode != 'setup' and self.single_step_mode and 'default_theme' not in self.data:
            value = (
                getattr(self.instance, 'default_theme', None)
                or self.initial.get('default_theme')
                or 'light'
            )
        else:
            value = self.cleaned_data.get('default_theme') or 'light'
        if not is_valid_theme(value):
            raise ValidationError("Invalid theme choice.")
        return value

    def clean_allowed_themes(self):
        if self.is_bound and self.mode != 'setup' and self.single_step_mode and 'allowed_themes' not in self.data:
            values = getattr(self.instance, 'allowed_themes', None)
            if not values:
                values = self.initial.get('allowed_themes')
            normalized = list(normalize_allowed_themes(values))
            if not normalized:
                raise ValidationError("At least one theme must remain enabled.")
            return normalized
        values = self.cleaned_data.get('allowed_themes') or []
        if not values:
            raise ValidationError("At least one theme must remain enabled.")
        normalized = list(normalize_allowed_themes(values))
        if not normalized:
            raise ValidationError("At least one theme must remain enabled.")
        return normalized

    def clean_default_table_density(self):
        if self.is_bound and self.mode != 'setup' and self.single_step_mode and 'default_table_density' not in self.data:
            value = (
                getattr(self.instance, 'default_table_density', None)
                or self.initial.get('default_table_density')
                or DEFAULT_TABLE_DENSITY
            )
        else:
            value = self.cleaned_data.get('default_table_density') or DEFAULT_TABLE_DENSITY
        if value not in TABLE_DENSITY_VALUES:
            raise ValidationError("Invalid table density choice.")
        return value

    def _auth_toggle_clean(self, key, default):
        # The auth toggles now live in the auth_config JSON field. In a non-setup
        # single-step modal post that doesn't own the security step (index 2), the
        # checkbox is omitted; preserve the stored value instead of reading it as
        # an unchecked False.
        if (
            self.is_bound
            and self.mode != 'setup'
            and self.single_step_mode
            and self.single_step_index != 2
            and key not in self.data
        ):
            existing = normalize_auth_config(getattr(self.instance, 'auth_config', None) or {})
            return bool(existing.get(key, default))
        return bool(self.cleaned_data.get(key, default))

    def clean_email_2fa(self):
        return self._auth_toggle_clean('email_2fa', False)

    def clean_prevent_multiple_active_sessions(self):
        return self._auth_toggle_clean('prevent_multiple_active_sessions', False)

    def clean_login_lockout_enabled(self):
        return self._auth_toggle_clean('login_lockout_enabled', True)

    def clean_enforce_strong_passwords(self):
        return self._auth_toggle_clean('enforce_strong_passwords', False)

    def clean_sidebar_density(self):
        value = self.cleaned_data.get('sidebar_density') or DEFAULT_SIDEBAR_DENSITY
        if value not in SIDEBAR_DENSITY_VALUES:
            raise ValidationError("Invalid sidebar density choice.")
        return value

    def clean_sidebar_collapse_mode(self):
        value = self.cleaned_data.get('sidebar_collapse_mode') or DEFAULT_SIDEBAR_COLLAPSE_MODE
        if value not in SIDEBAR_COLLAPSE_MODE_VALUES:
            raise ValidationError("Invalid sidebar collapse mode.")
        return value

    def clean_titlebar_home_shape(self):
        value = self.cleaned_data.get('titlebar_home_shape') or 'circle'
        if value not in TITLEBAR_HOME_SHAPE_VALUES:
            raise ValidationError("Invalid titlebar home shape.")
        return value

    def clean_titlebar_user_hub_style(self):
        value = self.cleaned_data.get('titlebar_user_hub_style') or TITLEBAR_USER_HUB_STYLE_DROPDOWN
        if value not in TITLEBAR_USER_HUB_STYLE_VALUES:
            raise ValidationError("Invalid titlebar and user hub style.")
        return value

    def clean_titlebar_actions_order(self):
        value = self.cleaned_data.get('titlebar_actions_order')
        if isinstance(value, str):
            value = value.strip()
            if value:
                try:
                    value = json.loads(value)
                except (TypeError, ValueError, json.JSONDecodeError):
                    value = []
            else:
                value = []
        return normalize_titlebar_actions_order(value)

    def clean_titlebar_title_align(self):
        value = self.cleaned_data.get('titlebar_title_align') or 'start'
        if value not in TITLEBAR_ALIGN_VALUES:
            raise ValidationError("Invalid title alignment.")
        return value

    def clean_titlebar_title_size(self):
        value = self.cleaned_data.get('titlebar_title_size') or 'md'
        if value not in TITLEBAR_SIZE_VALUES:
            raise ValidationError("Invalid title size.")
        return value

    def clean_titlebar_height(self):
        value = self.cleaned_data.get('titlebar_height') or 'balanced'
        if value not in TITLEBAR_HEIGHT_VALUES:
            raise ValidationError("Invalid titlebar height.")
        return value

    def clean_titlebar_surface(self):
        value = self.cleaned_data.get('titlebar_surface') or 'default'
        if value not in TITLEBAR_SURFACE_VALUES:
            raise ValidationError("Invalid titlebar surface.")
        return value

    def clean_titlebar_logo_treatment(self):
        value = self.cleaned_data.get('titlebar_logo_treatment') or 'none'
        if value not in TITLEBAR_LOGO_TREATMENT_VALUES:
            raise ValidationError("Invalid titlebar logo treatment.")
        return value

    def clean_titlebar_logo_treatment_shape(self):
        value = self.cleaned_data.get('titlebar_logo_treatment_shape') or 'soft'
        if value not in TITLEBAR_LOGO_TREATMENT_SHAPE_VALUES:
            raise ValidationError("Invalid titlebar logo treatment shape.")
        return value

    def clean_home_url(self):
        value = str(self.cleaned_data.get('home_url') or '').strip()
        discovered_value = str(self.cleaned_data.get('home_url_discovered') or '').strip()
        if self.is_bound and 'home_url' not in self.data and 'home_url_discovered' not in self.data:
            return (
                str(getattr(self.instance, 'home_url', '') or '').strip()
                or str(self.initial.get('home_url') or '').strip()
                or getattr(settings, 'DLUX_CONFIG', {}).get('home_url')
                or DEFAULT_HOME_URL
            )
        return value or discovered_value or getattr(settings, 'DLUX_CONFIG', {}).get('home_url') or DEFAULT_HOME_URL

    def clean_public_root_url(self):
        value = str(self.cleaned_data.get('public_root_url') or '').strip()
        discovered_value = str(self.cleaned_data.get('public_root_url_discovered') or '').strip()
        home_url = str(self.cleaned_data.get('home_url') or '').strip()
        if self.is_bound and 'public_root_url' not in self.data and 'public_root_url_discovered' not in self.data:
            return (
                str(getattr(self.instance, 'public_root_url', '') or '').strip()
                or str(self.initial.get('public_root_url') or '').strip()
                or str(getattr(settings, 'DLUX_CONFIG', {}).get('public_root_url') or '').strip()
                or home_url
                or getattr(settings, 'DLUX_CONFIG', {}).get('home_url')
                or DEFAULT_HOME_URL
            )
        return (
            value
            or discovered_value
            or str(getattr(settings, 'DLUX_CONFIG', {}).get('public_root_url') or '').strip()
            or home_url
            or getattr(settings, 'DLUX_CONFIG', {}).get('home_url')
            or DEFAULT_HOME_URL
        )

    def clean_sidebar_config(self):
        from dlux.discovery import sanitize_sidebar_config

        data = self.cleaned_data.get('sidebar_config')
        if not data:
            return normalize_sidebar_behavior({'home_url_name': None, 'entries': []})
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            raise ValidationError("Invalid sidebar JSON format.")
        if not isinstance(parsed, dict):
            raise ValidationError("Sidebar configuration must be a valid JSON object.")
        entries = parsed.get('entries', [])
        if not isinstance(entries, list):
            raise ValidationError("Sidebar entries must be a list.")
        return sanitize_sidebar_config({
            'enabled': parsed.get('enabled', True),
            'home_url_name': None,
            'entries': entries,
            'enable_reorder': parsed.get('enable_reorder', True),
            'show_toolbar': parsed.get('show_toolbar', True),
            'show_icons': parsed.get('show_icons', True),
            'density': parsed.get('density', DEFAULT_SIDEBAR_DENSITY),
            'allow_user_density': parsed.get('allow_user_density', True),
            'collapse_mode': parsed.get('collapse_mode', DEFAULT_SIDEBAR_COLLAPSE_MODE),
        }, allow_system_items=True)

    def clean_navbar_config(self):
        data = self.cleaned_data.get('navbar_config')
        if not data:
            return default_navbar_config()
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            raise ValidationError("Invalid nav bar JSON format.")
        if not isinstance(parsed, dict):
            raise ValidationError("Nav bar configuration must be a valid JSON object.")
        return normalize_navbar_config(parsed)

    def clean_log_config(self):
        data = self.cleaned_data.get('log_config')
        if not data:
            return default_log_config()
        if isinstance(data, dict):
            return normalize_log_config(data)
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            raise ValidationError("Invalid logging JSON format.")
        if not isinstance(parsed, dict):
            raise ValidationError("Logging configuration must be a valid JSON object.")
        return normalize_log_config(parsed)

    def clean_profile_config(self):
        data = self.cleaned_data.get('profile_config')
        if not data:
            return default_profile_config()
        if isinstance(data, dict):
            return normalize_profile_config(data)
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            raise ValidationError("Invalid profile JSON format.")
        if not isinstance(parsed, dict):
            raise ValidationError("Profile configuration must be a valid JSON object.")
        return normalize_profile_config(parsed)

    def clean_backup_config(self):
        data = self.cleaned_data.get('backup_config')
        if not data:
            return normalize_backup_config(getattr(self.instance, 'backup_config', None) or default_backup_config())
        if isinstance(data, dict):
            return normalize_backup_config(data)
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            raise ValidationError("Invalid backup JSON format.")
        if not isinstance(parsed, dict):
            raise ValidationError("Backup configuration must be a valid JSON object.")
        return normalize_backup_config(parsed)

    def clean_backup_auto_export_target(self):
        target = str(self.cleaned_data.get('backup_auto_export_target') or '').strip().strip('/')
        if not target:
            existing = normalize_backup_config(getattr(self.instance, 'backup_config', None) or {})
            return existing['auto_export_target']
        parts = target.split('/') if target else []
        if not parts or any(part in {'', '.', '..'} or not re.fullmatch(r'[A-Za-z0-9._-]+', part) for part in parts):
            raise ValidationError("Use a relative storage folder containing only letters, numbers, dots, underscores, hyphens, and slashes.")
        return target

    def clean_notification_config(self):
        data = self.cleaned_data.get('notification_config')
        if not data:
            return default_notification_config()
        if isinstance(data, dict):
            return normalize_notification_config(data)
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            raise ValidationError("Invalid notification JSON format.")
        if not isinstance(parsed, dict):
            raise ValidationError("Notification configuration must be a valid JSON object.")
        return normalize_notification_config(parsed)

    def clean_email_config(self):
        existing = normalize_email_config(getattr(self.instance, 'email_config', {}))
        transport = self.cleaned_data.get('email_config_transport') or existing.get('transport', 'direct')
        secret_storage = self.cleaned_data.get('email_config_secret_storage') or existing.get('secret_storage', 'env')
        config = normalize_email_config({
            'transport': transport,
            'secret_storage': secret_storage,
            'provider_preset': self.cleaned_data.get('email_config_provider_preset') or existing.get('provider_preset', 'custom'),
            'host': self.cleaned_data.get('email_config_host') or '',
            'port': self.cleaned_data.get('email_config_port') or 587,
            'use_tls': self.cleaned_data.get('email_config_use_tls'),
            'use_ssl': self.cleaned_data.get('email_config_use_ssl'),
            'username': self.cleaned_data.get('email_config_username') or '',
            'default_from_email': self.cleaned_data.get('email_config_default_from_email') or '',
            'failure_notification_recipients': self.cleaned_data.get('email_config_failure_recipients') or '',
        })
        if config.get('secret_storage') == 'encrypted_db':
            raw_password = self.cleaned_data.get('email_config_password') or ''
            if raw_password:
                config['encrypted_password'] = encrypt_email_secret(raw_password)
            elif existing.get('transport') == config.get('transport') and existing.get('secret_storage') == 'encrypted_db':
                config['encrypted_password'] = existing.get('encrypted_password', '')
        config['password_configured'] = bool(config.get('encrypted_password'))
        return config

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

    def _apply_imported_settings(self, cleaned, imported):
        if not imported:
            return
        # Skip re-applying import if JS already populated the form (user may have edited values)
        if cleaned.get('settings_import_processed'):
            return
        direct_fields = (
            'system_names',
            'languages',
            'translations_override',
            'home_url',
            'public_root_url',
            'default_language',
            'default_theme',
            'allowed_themes',
            'allow_user_theme_override',
            'allowed_fonts',
            'default_fonts',
            'allow_user_font_override',
            'allow_user_language_override',
            'default_table_density',
            'email_2fa',
            'prevent_multiple_active_sessions',
            'login_lockout_enabled',
            'enforce_strong_passwords',
            'client_ip_config',
            'public_root',
            'public_root_split_enabled',
            'public_registration_enabled',
            'registration_activation_mode',
            'registration_throttle_enabled',
            'email_config',
            'notification_config',
            'backup_config',
        )
        for field_name in direct_fields:
            if field_name in imported:
                cleaned[field_name] = imported[field_name]

        email_config = imported.get('email_config')
        if isinstance(email_config, dict):
            cleaned['email_config'] = email_config
            cleaned['email_config_transport'] = email_config.get('transport', 'direct')
            cleaned['email_config_secret_storage'] = email_config.get('secret_storage', 'env')
            cleaned['email_config_provider_preset'] = email_config.get('provider_preset', 'custom')
            cleaned['email_config_host'] = email_config.get('host', '')
            cleaned['email_config_port'] = email_config.get('port', 587)
            cleaned['email_config_use_tls'] = bool(email_config.get('use_tls', True))
            cleaned['email_config_use_ssl'] = bool(email_config.get('use_ssl', False))
            cleaned['email_config_username'] = email_config.get('username', '')
            cleaned['email_config_default_from_email'] = email_config.get('default_from_email', '')
            cleaned['email_config_failure_recipients'] = '\n'.join(
                email_config.get('failure_notification_recipients', []) or []
            )
            cleaned['email_config_password'] = ''

        client_ip_config = imported.get('client_ip_config')
        if isinstance(client_ip_config, dict):
            client_ip_config = normalize_client_ip_config(client_ip_config)
            cleaned['client_ip_config'] = client_ip_config
            cleaned['client_ip_mode'] = client_ip_config.get('mode', CLIENT_IP_MODE_X_FORWARDED_FOR)
            cleaned['client_ip_trusted_proxy_hops'] = client_ip_config.get('trusted_proxy_hops', 1)
            cleaned['client_ip_custom_header'] = client_ip_config.get('custom_header', '')

        sidebar = imported.get('sidebar_config')
        if isinstance(sidebar, dict):
            cleaned['sidebar_config'] = sidebar
            cleaned['sidebar_enabled'] = bool(sidebar.get('enabled', True))
            cleaned['sidebar_enable_reorder'] = bool(sidebar.get('enable_reorder', True))
            cleaned['sidebar_enable_toolbar'] = bool(sidebar.get('show_toolbar', True))
            cleaned['sidebar_show_icons'] = bool(sidebar.get('show_icons', True))
            cleaned['sidebar_density'] = sidebar.get('density', DEFAULT_SIDEBAR_DENSITY)
            cleaned['sidebar_allow_user_density'] = bool(sidebar.get('allow_user_density', True))
            cleaned['sidebar_collapse_mode'] = sidebar.get('collapse_mode', DEFAULT_SIDEBAR_COLLAPSE_MODE)

        navbar = imported.get('navbar_config')
        if isinstance(navbar, dict):
            navbar = normalize_navbar_config(navbar)
            cleaned['navbar_config'] = navbar
            cleaned['navbar_enabled'] = bool(navbar.get('enabled', False))
            cleaned['navbar_default_mode'] = navbar.get('default_mode', DEFAULT_NAVBAR_MODE)
            cleaned['navbar_allow_user_mode_override'] = bool(navbar.get('allow_user_mode_override', True))

        log = imported.get('log_config')
        if isinstance(log, dict):
            cleaned['log_config'] = normalize_log_config(log)

        profile = imported.get('profile_config')
        if isinstance(profile, dict):
            cleaned['profile_config'] = normalize_profile_config(profile)

        backup = imported.get('backup_config')
        if isinstance(backup, dict):
            backup = normalize_backup_config(backup)
            cleaned['backup_config'] = backup
            cleaned['backup_scheduled_enabled'] = backup['scheduled_enabled']
            cleaned['backup_schedule_interval_hours'] = backup['schedule_interval_hours']
            cleaned['backup_retention_days'] = backup['retention_days']
            cleaned['backup_max_backups_to_keep'] = backup['max_backups_to_keep']
            cleaned['backup_auto_export_target'] = backup['auto_export_target']

        titlebar = imported.get('titlebar_config')
        if isinstance(titlebar, dict):
            titlebar = normalize_titlebar_config(titlebar)
            cleaned['titlebar_show_title'] = bool(titlebar.get('show_title', True))
            cleaned['titlebar_show_logo'] = bool(titlebar.get('show_logo', True))
            cleaned['titlebar_show_home_button'] = bool(titlebar.get('show_home_button', True))
            cleaned['titlebar_hide_on_public_unauthenticated_index'] = bool(
                titlebar.get('hide_on_public_unauthenticated_index', False)
            )
            cleaned['titlebar_home_shape'] = titlebar.get('buttons_shape', titlebar.get('home_shape', 'circle'))
            cleaned['titlebar_user_hub_style'] = titlebar.get('user_hub_style', TITLEBAR_USER_HUB_STYLE_DROPDOWN)
            cleaned['titlebar_actions_order'] = normalize_titlebar_actions_order(titlebar.get('actions_order'))
            cleaned['titlebar_title_align'] = titlebar.get('title_align', 'start')
            cleaned['titlebar_title_size'] = titlebar.get('title_size', 'md')
            cleaned['titlebar_height'] = titlebar.get('height', 'balanced')
            cleaned['titlebar_surface'] = titlebar.get('surface', 'default')
            cleaned['titlebar_logo_treatment'] = titlebar.get('logo_treatment', 'none')
            cleaned['titlebar_logo_treatment_shape'] = titlebar.get('logo_treatment_shape', 'soft')

        notifications = imported.get('notification_config')
        if isinstance(notifications, dict):
            notifications = normalize_notification_config(notifications)
            cleaned['notification_config'] = notifications
            cleaned['notifications_enabled'] = bool(notifications.get('enabled', True))
            flash_config = notifications.get('flash', {})
            drawer_config = notifications.get('drawer', {})
            bridge_config = notifications.get('bridge', {})
            email_notification_config = notifications.get('email', {})
            automatic_config = notifications.get('automatic', {})
            cleaned['notification_flash_enabled'] = bool(flash_config.get('enabled', True))
            cleaned['notification_flash_position'] = flash_config.get('position', 'top_center')
            cleaned['notification_flash_size'] = flash_config.get('size', 'balanced')
            cleaned['notification_flash_text_size'] = flash_config.get('text_size', 'md')
            cleaned['notification_flash_timeout_ms'] = flash_config.get('timeout_ms', 3200)
            cleaned['notification_flash_max_visible'] = flash_config.get('max_visible', 3)
            cleaned['notification_drawer_enabled'] = bool(drawer_config.get('enabled', True))
            cleaned['notification_badge_enabled'] = bool(drawer_config.get('badge_enabled', True))
            cleaned['notification_bridge_enabled'] = bool(bridge_config.get('django_messages_enabled', False))
            cleaned['notification_email_enabled'] = bool(email_notification_config.get('enabled', False))
            cleaned['notification_email_default'] = bool(email_notification_config.get('default', False))
            cleaned['notification_auto_crud_enabled'] = bool(automatic_config.get('scoped_model_crud', True))
            cleaned['notification_auto_create'] = bool(automatic_config.get('create', True))
            cleaned['notification_auto_update'] = automatic_config.get('update', 'summary')
            cleaned['notification_auto_delete'] = bool(automatic_config.get('delete', True))

        login = imported.get('login_config')
        if isinstance(login, dict):
            cleaned['login_config'] = login
            cleaned['login_style'] = login.get('style', 'split')
            cleaned['login_show_logo'] = bool(login.get('show_logo', True))
            cleaned['login_banner_color'] = login.get('banner_color', '')
            cleaned['login_logo_treatment'] = login.get('logo_treatment', 'none')
            cleaned['login_logo_treatment_shape'] = login.get('logo_treatment_shape', 'soft')
            hero = login.get('hero_message') if isinstance(login.get('hero_message'), dict) else {}
            for lang_code, _label, field_name in getattr(self, '_login_hero_lang_fields', []):
                if lang_code in hero:
                    cleaned[field_name] = hero.get(lang_code, '')

    def clean(self):
        cleaned = super().clean()
        self._imported_settings = self._read_imported_settings()
        self._apply_imported_settings(cleaned, self._imported_settings)
        allowed_themes = cleaned.get('allowed_themes') or []
        default_theme = cleaned.get('default_theme') or 'light'
        if allowed_themes and default_theme not in allowed_themes:
            self.add_error('default_theme', "Default theme must remain allowed.")
        languages = cleaned.get('languages') or normalize_language_catalog()
        default_language = cleaned.get('default_language') or 'en'
        if default_language not in languages:
            fallback_language = 'en' if 'en' in languages else next(iter(languages), 'en')
            cleaned['default_language'] = fallback_language
        layout_config = self._schema_group_from_cleaned('layout_config')
        cleaned['layout_config'] = layout_config
        cleaned.update(layout_config)
        public_root_config = self._schema_group_from_cleaned('public_root_config')
        if not public_root_config.get('public_root', False):
            public_root_config['public_root_split_enabled'] = False
        cleaned['public_root_config'] = public_root_config
        cleaned.update(public_root_config)
        registration_config = self._schema_group_from_cleaned('registration_config')
        cleaned['registration_config'] = registration_config
        cleaned.update(registration_config)

        sidebar = cleaned.get('sidebar_config')
        if isinstance(sidebar, dict):
            sidebar['enabled'] = bool(cleaned.get('sidebar_enabled', True))
            if sidebar['enabled']:
                sidebar['enable_reorder'] = bool(cleaned.get('sidebar_enable_reorder', True))
                sidebar['show_toolbar'] = bool(cleaned.get('sidebar_enable_toolbar', True))
                sidebar['show_icons'] = bool(cleaned.get('sidebar_show_icons', True))
                sidebar['density'] = cleaned.get('sidebar_density', DEFAULT_SIDEBAR_DENSITY)
                sidebar['allow_user_density'] = bool(cleaned.get('sidebar_allow_user_density', True))
                sidebar['collapse_mode'] = cleaned.get('sidebar_collapse_mode', DEFAULT_SIDEBAR_COLLAPSE_MODE)
            if sidebar['enabled'] and not _system_settings_sidebar_tools_available(cleaned):
                sidebar['show_toolbar'] = False
                cleaned['sidebar_enable_toolbar'] = False
            sidebar = normalize_sidebar_behavior(sidebar)
            cleaned['sidebar_config'] = sidebar
            cleaned['sidebar_enabled'] = bool(sidebar.get('enabled', True))
            cleaned['sidebar_enable_reorder'] = bool(sidebar.get('enable_reorder', True))
            cleaned['sidebar_enable_toolbar'] = bool(sidebar.get('show_toolbar', True))
            cleaned['sidebar_show_icons'] = bool(sidebar.get('show_icons', True))
            cleaned['sidebar_density'] = sidebar.get('density', DEFAULT_SIDEBAR_DENSITY)
            cleaned['sidebar_allow_user_density'] = bool(sidebar.get('allow_user_density', True))
            cleaned['sidebar_collapse_mode'] = sidebar.get('collapse_mode', DEFAULT_SIDEBAR_COLLAPSE_MODE)
        navbar = cleaned.get('navbar_config')
        if isinstance(navbar, dict):
            navbar['enabled'] = bool(cleaned.get('navbar_enabled', False))
            mode = cleaned.get('navbar_default_mode') or DEFAULT_NAVBAR_MODE
            navbar['default_mode'] = mode if mode in NAVBAR_MODE_VALUES else DEFAULT_NAVBAR_MODE
            navbar['allow_user_mode_override'] = bool(cleaned.get('navbar_allow_user_mode_override', True))
            navbar = normalize_navbar_config(navbar)
            cleaned['navbar_config'] = navbar
            cleaned['navbar_enabled'] = navbar.get('enabled', False)
            cleaned['navbar_default_mode'] = navbar.get('default_mode', DEFAULT_NAVBAR_MODE)
            cleaned['navbar_allow_user_mode_override'] = navbar.get('allow_user_mode_override', True)
        log = cleaned.get('log_config')
        if isinstance(log, dict):
            cleaned['log_config'] = normalize_log_config(log)
        profile = cleaned.get('profile_config')
        if isinstance(profile, dict):
            cleaned['profile_config'] = normalize_profile_config(profile)
        backup_fields_posted = any(name in self.data for name in (
            'backup_scheduled_enabled',
            'backup_schedule_interval_hours',
            'backup_retention_days',
            'backup_max_backups_to_keep',
            'backup_auto_export_target',
        ))
        existing_backup = normalize_backup_config(getattr(self.instance, 'backup_config', None) or {})
        if self.is_bound and self.mode != 'setup' and self.single_step_mode and self.single_step_index != 11 and not backup_fields_posted:
            cleaned['backup_config'] = existing_backup
        else:
            submitted_backup = cleaned.get('backup_config')
            backup_base = normalize_backup_config(submitted_backup) if isinstance(submitted_backup, dict) else existing_backup
            cleaned['backup_config'] = normalize_backup_config({
                **backup_base,
                'scheduled_enabled': bool(cleaned.get('backup_scheduled_enabled', False)),
                'schedule_interval_hours': cleaned.get('backup_schedule_interval_hours'),
                'retention_days': cleaned.get('backup_retention_days'),
                'max_backups_to_keep': cleaned.get('backup_max_backups_to_keep'),
                'auto_export_target': cleaned.get('backup_auto_export_target'),
            })
        existing_email_config = normalize_email_config(getattr(self.instance, 'email_config', {}))
        email_features_enabled = bool(cleaned.get('public_registration_enabled') or cleaned.get('email_2fa'))
        email_fields_posted = any(
            field_name in self.data
            for field_name in (
                'email_config_transport',
                'email_config_secret_storage',
                'email_config_host',
                'email_config_port',
                'email_config_use_tls',
                'email_config_use_ssl',
                'email_config_username',
                'email_config_password',
                'email_config_default_from_email',
                'email_config_provider_preset',
                'email_config_failure_recipients',
            )
        )
        imported_email_config = cleaned.get('email_config') if isinstance(cleaned.get('email_config'), dict) else {}
        imported_email_config = normalize_email_config(imported_email_config) if imported_email_config else {}
        if imported_email_config.get('secret_storage') == 'encrypted_db' and not imported_email_config.get('encrypted_password'):
            imported_email_config['password_configured'] = False
        if not email_fields_posted and imported_email_config and imported_email_config != default_email_config():
            cleaned['email_config'] = imported_email_config
        elif not email_features_enabled and not email_fields_posted and existing_email_config:
            cleaned['email_config'] = existing_email_config
        else:
            email_transport = cleaned.get('email_config_transport') or existing_email_config.get('transport', 'direct')
            email_secret_storage = cleaned.get('email_config_secret_storage') or existing_email_config.get('secret_storage', 'env')
            email_config = normalize_email_config({
                'transport': email_transport,
                'secret_storage': email_secret_storage,
                'provider_preset': cleaned.get('email_config_provider_preset') or existing_email_config.get('provider_preset', 'custom'),
                'host': cleaned.get('email_config_host') or '',
                'port': cleaned.get('email_config_port') or 587,
                'use_tls': cleaned.get('email_config_use_tls'),
                'use_ssl': cleaned.get('email_config_use_ssl'),
                'username': cleaned.get('email_config_username') or '',
                'default_from_email': cleaned.get('email_config_default_from_email') or '',
                'failure_notification_recipients': cleaned.get('email_config_failure_recipients') or '',
            })
            if email_config.get('secret_storage') == 'encrypted_db':
                raw_password = cleaned.get('email_config_password') or ''
                if raw_password:
                    email_config['encrypted_password'] = encrypt_email_secret(raw_password)
                elif (
                    existing_email_config.get('transport') == email_config.get('transport')
                    and existing_email_config.get('secret_storage') == 'encrypted_db'
                ):
                    email_config['encrypted_password'] = existing_email_config.get('encrypted_password', '')
            email_config['password_configured'] = bool(email_config.get('encrypted_password'))
            cleaned['email_config'] = email_config
        email_config = normalize_email_config(cleaned.get('email_config') or existing_email_config)
        client_ip_config = self._schema_group_from_cleaned('client_ip_config')
        cleaned['client_ip_config'] = client_ip_config
        cleaned['client_ip_mode'] = client_ip_config.get('mode', CLIENT_IP_MODE_X_FORWARDED_FOR)
        cleaned['client_ip_trusted_proxy_hops'] = client_ip_config.get('trusted_proxy_hops', 1)
        cleaned['client_ip_custom_header'] = client_ip_config.get('custom_header', '')
        hero_dict = {
            lang_code: str(cleaned.get(field_name) or '').strip()
            for lang_code, _label, field_name in getattr(self, '_login_hero_lang_fields', [])
        }
        auth_config = self._schema_group_from_cleaned('auth_config')
        cleaned['auth_config'] = auth_config
        cleaned.update(auth_config)
        cleaned['login_config'] = normalize_login_config({
            'style': cleaned.get('login_style') or 'split',
            'show_logo': bool(cleaned.get('login_show_logo', True)),
            'banner_color': cleaned.get('login_banner_color') or '',
            'logo_treatment': cleaned.get('login_logo_treatment') or 'none',
            'logo_treatment_shape': cleaned.get('login_logo_treatment_shape') or 'soft',
            'hero_message': hero_dict or '',
        })
        cleaned['titlebar_config'] = normalize_titlebar_config({
            'show_title': bool(cleaned.get('titlebar_show_title', True)),
            'show_logo': bool(cleaned.get('titlebar_show_logo', True)),
            'show_home_button': bool(cleaned.get('titlebar_show_home_button', True)),
            'hide_on_public_unauthenticated_index': bool(
                cleaned.get('titlebar_hide_on_public_unauthenticated_index', False)
            ),
            'buttons_shape': cleaned.get('titlebar_home_shape', 'circle'),
            'home_shape': cleaned.get('titlebar_home_shape', 'circle'),
            'user_hub_style': cleaned.get('titlebar_user_hub_style', TITLEBAR_USER_HUB_STYLE_DROPDOWN),
            'actions_order': cleaned.get('titlebar_actions_order') or list(TITLEBAR_ACTIONS_ORDER),
            'title_align': cleaned.get('titlebar_title_align', 'start'),
            'title_size': cleaned.get('titlebar_title_size', 'md'),
            'height': cleaned.get('titlebar_height', 'balanced'),
            'surface': cleaned.get('titlebar_surface', 'default'),
            'logo_treatment': cleaned.get('titlebar_logo_treatment', 'none'),
            'logo_treatment_shape': cleaned.get('titlebar_logo_treatment_shape', 'soft'),
        })
        notification_split_fields = (
            'notifications_enabled',
            'notification_flash_enabled',
            'notification_flash_position',
            'notification_flash_size',
            'notification_flash_text_size',
            'notification_flash_timeout_ms',
            'notification_flash_max_visible',
            'notification_drawer_enabled',
            'notification_badge_enabled',
            'notification_bridge_enabled',
            'notification_email_enabled',
            'notification_email_default',
            'notification_auto_crud_enabled',
            'notification_auto_create',
            'notification_auto_update',
            'notification_auto_delete',
        )
        notification_fields_posted = any(field_name in self.data for field_name in notification_split_fields)
        if (
            self.is_bound
            and self.mode != 'setup'
            and self.single_step_mode
            and self.single_step_index != 7
            and not notification_fields_posted
        ):
            cleaned['notification_config'] = normalize_notification_config(
                getattr(self.instance, 'notification_config', None) or cleaned.get('notification_config')
            )
        else:
            notification_email_enabled = bool(cleaned.get('notification_email_enabled', False))
            cleaned['notification_config'] = normalize_notification_config({
                'enabled': bool(cleaned.get('notifications_enabled', True)),
                'flash': {
                    'enabled': bool(cleaned.get('notification_flash_enabled', True)),
                    'position': cleaned.get('notification_flash_position') or 'top_center',
                    'size': cleaned.get('notification_flash_size') or 'balanced',
                    'text_size': cleaned.get('notification_flash_text_size') or 'md',
                    'timeout_ms': cleaned.get('notification_flash_timeout_ms') if cleaned.get('notification_flash_timeout_ms') is not None else 3200,
                    'max_visible': cleaned.get('notification_flash_max_visible') if cleaned.get('notification_flash_max_visible') is not None else 3,
                },
                'drawer': {
                    'enabled': bool(cleaned.get('notification_drawer_enabled', True)),
                    'badge_enabled': bool(cleaned.get('notification_badge_enabled', True)),
                },
                'bridge': {
                    'django_messages_enabled': bool(cleaned.get('notification_bridge_enabled', False)),
                },
                'email': {
                    'enabled': notification_email_enabled,
                    'default': bool(notification_email_enabled and cleaned.get('notification_email_default', False)),
                },
                'automatic': {
                    'scoped_model_crud': bool(cleaned.get('notification_auto_crud_enabled', True)),
                    'create': bool(cleaned.get('notification_auto_create', True)),
                    'update': cleaned.get('notification_auto_update') or 'summary',
                    'delete': bool(cleaned.get('notification_auto_delete', True)),
                    'actor_flash_actions': ['create', 'delete', 'error'],
                    'watchable': True,
                },
            })
        if cleaned.get('registration_activation_mode') not in REGISTRATION_ACTIVATION_VALUES:
            cleaned['registration_activation_mode'] = 'auto_login_after_verify'
        email_ready = get_email_service_status().get('available')
        backend = getattr(settings, 'EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
        local_backends = {
            'django.core.mail.backends.console.EmailBackend',
            'django.core.mail.backends.locmem.EmailBackend',
            'django.core.mail.backends.filebased.EmailBackend',
        }
        if backend in local_backends and getattr(settings, 'DEBUG', False):
            email_ready = True
        elif email_config.get('transport') == 'relay':
            relay_host = str(email_config.get('host') or os.getenv('SMTP_RELAY_HOST') or '').strip()
            relay_port = email_config.get('port')
            relay_from_email = str(
                email_config.get('default_from_email')
                or getattr(settings, 'DEFAULT_FROM_EMAIL', '')
                or os.getenv('DEFAULT_FROM_EMAIL')
                or ''
            ).strip()
            relay_password_ok = True
            if email_config.get('secret_storage') == 'encrypted_db' and email_config.get('username'):
                relay_password_ok = bool(email_config.get('encrypted_password'))
            email_ready = bool(relay_host and relay_port and relay_from_email and relay_password_ok)
        elif email_config.get('secret_storage') == 'encrypted_db':
            email_ready = bool(
                email_config.get('host')
                and email_config.get('port')
                and email_config.get('default_from_email')
                and (not email_config.get('username') or email_config.get('encrypted_password'))
            )
        elif backend == 'django.core.mail.backends.smtp.EmailBackend':
            email_ready = bool(
                (email_config.get('host') or getattr(settings, 'EMAIL_HOST', ''))
                and (email_config.get('port') or getattr(settings, 'EMAIL_PORT', None))
                and (
                    email_config.get('default_from_email')
                    or getattr(settings, 'DEFAULT_FROM_EMAIL', '')
                )
            )
        if not email_ready:
            cleaned['notification_email_enabled'] = False
            cleaned['notification_email_default'] = False
            notification_config = cleaned.get('notification_config')
            if isinstance(notification_config, dict):
                notification_config = {
                    **notification_config,
                    'email': {
                        'enabled': False,
                        'default': False,
                    },
                }
                cleaned['notification_config'] = normalize_notification_config(notification_config)
        if (cleaned.get('public_registration_enabled') or cleaned.get('email_2fa')) and not email_ready:
            self.add_error(
                'email_config',
                "Public registration and email 2FA require configured email delivery. Use env/secrets, the generated internal SMTP relay with a saved upstream secret, local debug email backends during development, or encrypted DB mode with a saved SMTP secret.",
            )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        fallback_home = getattr(settings, 'DLUX_CONFIG', {}).get('home_url') or DEFAULT_HOME_URL
        auth_config = self.cleaned_data.get('auth_config') or default_auth_config()
        layout_config = self.cleaned_data.get('layout_config') or {}
        public_root_config = self.cleaned_data.get('public_root_config') or {}
        registration_config = self.cleaned_data.get('registration_config') or {}
        apply_system_settings_import(instance, {
            'system_names': self.cleaned_data.get('system_names', {}),
            'languages': self.cleaned_data.get('languages', normalize_language_catalog()),
            'translations_override': self.cleaned_data.get('translations_override', {}),
            'home_url': self.cleaned_data.get('home_url') or fallback_home,
            'default_language': self.cleaned_data.get('default_language') or 'en',
            'default_theme': self.cleaned_data.get('default_theme') or 'light',
            'allowed_themes': self.cleaned_data.get('allowed_themes', list(normalize_allowed_themes())),
            'allow_user_theme_override': bool(self.cleaned_data.get('allow_user_theme_override', True)),
            'allowed_fonts': self.cleaned_data.get('allowed_fonts', []),
            'default_fonts': self.cleaned_data.get('default_fonts', {}),
            'allow_user_font_override': bool(self.cleaned_data.get('allow_user_font_override', True)),
            'allow_user_language_override': bool(self.cleaned_data.get('allow_user_language_override', True)),
            'default_table_density': layout_config.get(
                'default_table_density',
                self.cleaned_data.get('default_table_density', DEFAULT_TABLE_DENSITY),
            ),
            'email_2fa': bool(auth_config.get('email_2fa', False)),
            'prevent_multiple_active_sessions': bool(auth_config.get('prevent_multiple_active_sessions', False)),
            'login_lockout_enabled': bool(auth_config.get('login_lockout_enabled', True)),
            'enforce_strong_passwords': bool(auth_config.get('enforce_strong_passwords', False)),
            'client_ip_config': self.cleaned_data.get('client_ip_config', default_client_ip_config()),
            'public_root': bool(public_root_config.get('public_root', False)),
            'public_root_split_enabled': bool(public_root_config.get('public_root_split_enabled', False)),
            'public_root_url': str(public_root_config.get('public_root_url') or '').strip(),
            'public_registration_enabled': bool(registration_config.get('public_registration_enabled', False)),
            'registration_activation_mode': registration_config.get('registration_activation_mode'),
            'registration_throttle_enabled': bool(registration_config.get('registration_throttle_enabled', True)),
            'email_config': self.cleaned_data.get('email_config', default_email_config()),
            'sidebar_config': self.cleaned_data.get('sidebar_config', {'home_url_name': None, 'entries': []}),
            'navbar_config': self.cleaned_data.get('navbar_config', default_navbar_config()),
            'log_config': self.cleaned_data.get('log_config', default_log_config()),
            'profile_config': self.cleaned_data.get('profile_config', default_profile_config()),
            'backup_config': self.cleaned_data.get('backup_config', default_backup_config()),
            'titlebar_config': self.cleaned_data.get('titlebar_config', default_titlebar_config()),
            'notification_config': self.cleaned_data.get('notification_config', default_notification_config()),
            'login_config': self.cleaned_data.get('login_config', default_login_config()),
        }, commit=False, preserve_email_secret=True)
        imported = getattr(self, '_imported_settings', {}) or {}
        if imported.get('logo') and not self.files.get('logo'):
            instance.logo = str(imported.get('logo'))
        if imported.get('favicon') and not self.files.get('favicon'):
            instance.favicon = str(imported.get('favicon'))
        if isinstance(instance.sidebar_config, dict):
            instance.sidebar_config['home_url_name'] = None

        if commit:
            instance.save()
        return instance
