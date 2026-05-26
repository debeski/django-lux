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


class MicrosysTable(tables.Table):
    """
    Framework-owned base table for Microsys-managed data grids.
    """

    class Meta:
        template_name = "microsys/tables/table.html"
        attrs = {'class': 'table table-hover align-middle ms-data-table'}
        row_attrs = {
            'data-micro-context': 'true',
        }
        microsys_actions = True
        microsys_per_page = DEFAULT_TABLE_PAGE_SIZE
        microsys_per_page_options = TABLE_PAGE_SIZE_OPTIONS

    def get_microsys_record_name(self, record):
        if hasattr(record, 'get_full_name'):
            value = record.get_full_name() or ''
            if value:
                return value
        return str(record)

    def get_microsys_model_name(self):
        if getattr(self, 'model_name', None):
            return self.model_name
        model = getattr(self._meta, 'model', None)
        if model is not None:
            return model._meta.model_name
        return ''

    def get_microsys_base_actions(self, record):
        model = getattr(self._meta, 'model', None)
        if model is None or getattr(record, 'pk', None) is None:
            return []

        record_name = self.get_microsys_record_name(record)
        payload = {
            'app': model._meta.app_label,
            'model': self.get_microsys_model_name(),
            'id': record.pk,
            'name': record_name,
        }

        return [
            {
                'label': 'view_label',
                'icon': 'bi bi-eye',
                'type': 'event',
                'event': 'micro:record:view',
                'data': payload,
                'dblclick': True,
            },
            {'type': 'divider'},
            {
                'label': 'edit_label',
                'icon': 'bi bi-pencil',
                'type': 'event',
                'event': 'micro:record:edit',
                'data': payload,
                'permissions': [f"{model._meta.app_label}.change_{model._meta.model_name}"],
            },
            {
                'label': 'delete_label',
                'icon': 'bi bi-trash',
                'type': 'event',
                'event': 'micro:record:delete',
                'data': payload,
                'textClass': 'text-danger',
                'permissions': [f"{model._meta.app_label}.delete_{model._meta.model_name}"],
            },
        ]

    def get_microsys_row_actions(self, record, base_actions):
        return base_actions


class UserTable(MicrosysTable):
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
    is_active = tables.BooleanColumn(verbose_name="Active")
    last_login = tables.DateColumn(
        format="H:i Y-m-d ",
        verbose_name="Last Login"
    )

    class Meta(MicrosysTable.Meta):
        model = User
        fields = ("username", "phone", "email", "full_name", "scope", "staff_tier", "is_active", "last_login")
        row_attrs = {
            "data-micro-context": "true",
            "data-micro-actions": lambda record: json.dumps(_build_user_row_actions(record))
        }

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
                '<span class="badge ms-staff-tier-badge ms-staff-tier-badge--{}"><i class="bi {} me-1"></i>{}</span>',
                tier['tier_key'],
                tier['icon'],
                tier['title'],
            )
        ]
        if tier.get('can_delegate_staff'):
            badges.append(
                format_html(
                    '<span class="badge ms-staff-tier-badge ms-staff-tier-badge--delegate ms-1">{}</span>',
                    tier['delegation_badge_label'],
                )
            )
        return mark_safe(''.join(str(badge) for badge in badges))


class UserActivityLogTable(MicrosysTable):
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

    class Meta(MicrosysTable.Meta):
        model = apps.get_model('microsys', 'UserActivityLog')
        fields = ("timestamp", "created_by", "full_name", "model_name", "action", "object_id", "number", "scope")
        exclude = ("id", "ip_address", "user_agent", "created_at", "updated_at", "updated_by", "deleted_at", "deleted_by")
        row_attrs = {
            "data-micro-context": "true",
            "data-micro-actions": lambda record: json.dumps([
                {
                    "label": get_strings().get("view_details", "View Details"),
                    "icon": "bi bi-eye",
                    "type": "event",
                    "event": "micro:view-log-details",
                    "data": {"url": reverse('user_activity_log_detail', args=[record.pk])},
                    "dblclick": True,
                }
            ]),
        }
        microsys_actions = False

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


class ScopeTable(MicrosysTable):
    actions = tables.TemplateColumn(
        template_name='microsys/scopes/scope_actions.html',
        orderable=False,
        verbose_name=''
    )

    class Meta(MicrosysTable.Meta):
        model = apps.get_model('microsys', 'Scope')
        fields = ("name", "actions")
        microsys_actions = False


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
            "event": "micro:view-user-details",
            "data": {"url": reverse('user_detail_modal', args=[record.pk])},
            "dblclick": True,
            "permissions": ["auth.view_user"],
        },
        {"type": "divider"},
        {
            "label": s.get("edit_user_label", "Edit User"),
            "icon": "bi bi-pencil",
            "type": "event",
            "event": "micro:dynamic_modal:open",
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
            "event": "micro:dynamic_modal:open",
            "data": {
                "url": reverse('user_report_modal', args=[record.pk]),
                "title": f"{s.get('user_report_title')} {display_name}".strip(),
            },
            "permissions": ["microsys.view_activitylog", "auth.view_user"],
        },
        {
            "label": s.get("edit_permissions_label", "Edit Permissions"),
            "icon": "bi bi-shield-lock",
            "type": "event",
            "event": "micro:dynamic_modal:open",
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
            "event": "micro:reset-password",
            "data": {
                "id": record.pk,
                "username": record.username,
                "url": reverse('reset_password', args=[record.pk]),
            },
            "permissions": ["auth.change_user"],
        },
    ]
