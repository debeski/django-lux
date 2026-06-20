import json

import django_tables2 as tables
from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .constants import DEFAULT_TABLE_PAGE_SIZE, TABLE_PAGE_SIZE_OPTIONS
from .translations import get_strings
from .utils import get_user_management_tier_state_for_user, translate_activity_log_model_name

User = get_user_model()


class DluxTable(tables.Table):
    """
    Framework-owned base table for Dlux-managed data grids.
    """

    class Meta:
        template_name = "dlux/tables/table.html"
        attrs = {'class': 'table table-hover align-middle dlux-data-table'}
        row_attrs = {
            'data-dlux-context': 'true',
        }
        dlux_actions = True
        dlux_per_page = DEFAULT_TABLE_PAGE_SIZE
        dlux_per_page_options = TABLE_PAGE_SIZE_OPTIONS

    def get_dlux_record_name(self, record):
        if hasattr(record, 'get_full_name'):
            value = record.get_full_name() or ''
            if value:
                return value
        return str(record)

    def get_dlux_model_name(self):
        if getattr(self, 'model_name', None):
            return self.model_name
        model = getattr(self._meta, 'model', None)
        if model is not None:
            return model._meta.model_name
        return ''

    def get_dlux_base_actions(self, record):
        model = getattr(self._meta, 'model', None)
        if model is None or getattr(record, 'pk', None) is None:
            return []

        record_name = self.get_dlux_record_name(record)
        payload = {
            'app': model._meta.app_label,
            'model': self.get_dlux_model_name(),
            'id': record.pk,
            'name': record_name,
        }

        return [
            {
                'label': 'view_label',
                'icon': 'bi bi-eye',
                'type': 'event',
                'event': 'dlux:record:view',
                'data': payload,
                'dblclick': True,
            },
            {'type': 'divider'},
            {
                'label': 'edit_label',
                'icon': 'bi bi-pencil',
                'type': 'event',
                'event': 'dlux:record:edit',
                'data': payload,
                'permissions': [f"{model._meta.app_label}.change_{model._meta.model_name}"],
            },
            {
                'label': 'delete_label',
                'icon': 'bi bi-trash',
                'type': 'event',
                'event': 'dlux:record:delete',
                'data': payload,
                'textClass': 'text-danger',
                'permissions': [f"{model._meta.app_label}.delete_{model._meta.model_name}"],
            },
        ]

    def get_dlux_row_actions(self, record, base_actions):
        return base_actions


class UserTable(DluxTable):
    online_status = tables.Column(
        verbose_name="",
        empty_values=(),
        orderable=False,
        attrs={"td": {"class": "text-center ps-2 pe-1"}, "th": {"class": "text-center ps-2 pe-1", "style": "width:28px"}},
    )
    username = tables.Column(verbose_name="Username")
    phone = tables.Column(verbose_name="Phone Number", accessor='profile.phone', default='-')
    email = tables.Column(verbose_name="Email")
    scope = tables.Column(verbose_name="Scope", accessor='profile.scope.name', default='-')
    full_name = tables.Column(
        verbose_name="Full Name",
        accessor='profile.full_name',
        order_by='first_name'
    )
    staff_tier = tables.Column(verbose_name=get_strings().get('tbl_staff_tier', 'Staff Tier'), empty_values=())
    twofa_status = tables.Column(
        verbose_name=get_strings().get('tbl_2fa_status', '2FA'),
        empty_values=(),
        orderable=False,
    )
    is_active = tables.BooleanColumn(verbose_name="Active")
    last_login = tables.DateColumn(
        format="H:i Y-m-d ",
        verbose_name="Last Login"
    )

    class Meta(DluxTable.Meta):
        model = User
        fields = ("online_status", "username", "phone", "email", "full_name", "scope", "staff_tier", "twofa_status", "is_active", "last_login")
        row_attrs = {
            "data-dlux-context": "true",
            "data-dlux-actions": lambda record: json.dumps(_build_user_row_actions(record))
        }

    def render_online_status(self, record):
        s = getattr(self, 'translations', None) or get_strings()
        is_online = getattr(record, 'is_online', False)
        if is_online:
            return format_html(
                '<span class="dlux-online-dot dlux-online-dot--on" title="{}"></span>',
                s.get('user_is_online', 'Online now'),
            )
        return format_html('<span class="dlux-online-dot dlux-online-dot--off" title="{}"></span>', s.get('user_is_offline', 'Offline'))

    def render_username(self, value, record):
        s = get_strings()
        try:
            public_registration = record.public_registration
        except Exception:
            public_registration = None
        if public_registration:
            return format_html(
                '{} <span class="badge bg-light text-primary border ms-2"><i class="bi bi-person-plus me-1"></i>{}</span>',
                value,
                s.get('account_source_public', 'Public signup'),
            )
        return value

    def render_staff_tier(self, record):
        strings = getattr(self, 'translations', None) or get_strings()
        tier = get_user_management_tier_state_for_user(record, strings=strings)
        badges = [
            format_html(
                '<span class="badge dlux-staff-tier-badge dlux-staff-tier-badge--{}"><i class="bi {} me-1"></i>{}</span>',
                tier['tier_key'],
                tier['icon'],
                tier['title'],
            )
        ]
        if tier.get('can_delegate_staff'):
            badges.append(
                format_html(
                    '<span class="badge dlux-staff-tier-badge dlux-staff-tier-badge--delegate ms-1">{}</span>',
                    tier['delegation_badge_label'],
                )
            )
        return mark_safe(''.join(str(badge) for badge in badges))

    def render_twofa_status(self, record):
        s = getattr(self, 'translations', None) or get_strings()
        profile = getattr(record, 'profile', None)
        if profile is None:
            return format_html('<span class="text-muted small">{}</span>', s.get('twofa_none', 'No'))
        methods = []
        if getattr(profile, 'is_totp_2fa_enabled', False):
            methods.append(format_html(
                '<span class="badge dlux-2fa-badge dlux-2fa-badge--totp" title="TOTP"><i class="bi bi-phone me-1"></i>{}</span>',
                s.get('twofa_totp_method', 'App'),
            ))
        if getattr(profile, 'is_email_2fa_enabled', False):
            methods.append(format_html(
                '<span class="badge dlux-2fa-badge dlux-2fa-badge--email" title="Email 2FA"><i class="bi bi-envelope me-1"></i>{}</span>',
                s.get('twofa_email_method', 'Email'),
            ))
        if not methods:
            return format_html('<span class="text-muted small">{}</span>', s.get('twofa_none', 'No'))
        return mark_safe(''.join(str(b) for b in methods))


class UserActivityLogTable(DluxTable):
    timestamp = tables.DateColumn(
        format="H:i Y-m-d ",
        verbose_name="Timestamp",
        accessor='created_at'
    )
    full_name = tables.Column(
        verbose_name="Full Name",
        accessor='created_by.profile.full_name',
        order_by='created_by__first_name'
    )
    scope = tables.Column(
        verbose_name="Scope",
        accessor='created_by.profile.scope.name',
        default='Global'
    )
    action = tables.Column(verbose_name="Action")
    model_name = tables.Column(verbose_name="Model")

    class Meta(DluxTable.Meta):
        model = apps.get_model('dlux', 'ActivityLog')
        fields = ("timestamp", "created_by", "full_name", "model_name", "action", "object_id", "number", "scope")
        exclude = ("id", "ip_address", "user_agent", "created_at", "updated_at", "updated_by", "deleted_at", "deleted_by")
        row_attrs = {
            "data-dlux-context": "true",
            "data-dlux-actions": lambda record: json.dumps([
                {
                    "label": get_strings().get("view_details", "View Details"),
                    "icon": "bi bi-eye",
                    "type": "event",
                    "event": "dlux:view-log-details",
                    "data": {"url": reverse('user_activity_log_detail', args=[record.pk])},
                    "dblclick": True,
                }
            ]),
        }
        dlux_actions = False

    def render_action(self, value, record):
        s = get_strings()
        raw_value = record.action
        if not raw_value:
            return "-"
        return s.get(f"action_{raw_value.lower()}", raw_value)

    def render_model_name(self, value):
        if not value:
            return "-"
        return translate_activity_log_model_name(value, strings=get_strings())


class UserActivityLogTableNoUser(UserActivityLogTable):
    class Meta(UserActivityLogTable.Meta):
        exclude = ("user", "user.full_name", "scope")


class ScopeTable(DluxTable):
    actions = tables.TemplateColumn(
        template_name='dlux/scopes/scope_actions.html',
        orderable=False,
        verbose_name=''
    )

    class Meta(DluxTable.Meta):
        model = apps.get_model('dlux', 'Scope')
        fields = ("name", "actions")
        dlux_actions = False


def _build_user_row_actions(record):
    s = get_strings()
    display_name = ''
    if hasattr(record, 'get_full_name'):
        display_name = record.get_full_name() or ''
    display_name = display_name or getattr(record, 'username', '')

    return [
        {
            "label": s.get("view_label", "View"),
            "icon": "bi bi-eye",
            "type": "event",
            "event": "dlux:view-user-details",
            "data": {"url": reverse('user_detail_modal', args=[record.pk])},
            "dblclick": True,
            "permissions": ["auth.view_user"],
        },
        {"type": "divider"},
        {
            "label": s.get("edit_user_label", "Edit User"),
            "icon": "bi bi-pencil",
            "type": "event",
            "event": "dlux:dynamic_modal:open",
            "data": {
                "url": reverse('modal_user_edit', args=[record.pk]),
                "title": f"{s.get('edit_user_label', 'Edit User')} {display_name}".strip(),
            },
            "permissions": ["auth.change_user"],
        },
        {
            "label": s.get("user_report_title"),
            "icon": "bi bi-file-earmark-text",
            "type": "event",
            "event": "dlux:dynamic_modal:open",
            "data": {
                "url": reverse('user_report_modal', args=[record.pk]),
                "title": f"{s.get('user_report_title')} {display_name}".strip(),
            },
            "permissions": ["dlux.view_activitylog", "auth.view_user"],
        },
        {
            "label": s.get("edit_permissions_label", "Edit Permissions"),
            "icon": "bi bi-shield-lock",
            "type": "event",
            "event": "dlux:dynamic_modal:open",
            "data": {
                "url": reverse('modal_user_permissions', args=[record.pk]),
                "title": f"{s.get('edit_permissions_label', 'Edit Permissions')} {display_name}".strip(),
            },
            "permissions": ["auth.change_user"],
        },
        {
            "label": s.get("reset_password", "Reset Password"),
            "icon": "bi bi-key",
            "type": "event",
            "event": "dlux:reset-password",
            "data": {
                "id": record.pk,
                "username": record.username,
                "url": reverse('reset_password', args=[record.pk]),
            },
            "permissions": ["auth.change_user"],
        },
    ]
