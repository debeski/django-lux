import json

import django_tables2 as tables
from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import reverse

from .translations import get_strings

User = get_user_model()

class UserTable(tables.Table):
    username = tables.Column(verbose_name="اسم المستخدم")
    phone = tables.Column(verbose_name="رقم الهاتف", accessor='profile.phone', default='-')
    email = tables.Column(verbose_name="البريد الالكتروني")
    scope = tables.Column(verbose_name="النطاق", accessor='profile.scope.name', default='-')
    full_name = tables.Column(
        verbose_name="الاسم الكامل",
        accessor='profile.full_name', # Assuming profile has full_name property, or use user.get_full_name
        order_by='first_name'
    )
    is_staff = tables.BooleanColumn(verbose_name="مسؤول")
    is_active = tables.BooleanColumn(verbose_name="نشط")
    last_login = tables.DateColumn(
        format="H:i Y-m-d ",
        verbose_name="اخر دخول"
    )

    class Meta:
        model = User
        template_name = "django_tables2/bootstrap5.html"
        fields = ("username", "phone", "email", "full_name", "scope", "is_staff", "is_active","last_login")
        attrs = {'class': 'table table-hover align-middle'}
        row_attrs = {
            "data-micro-context": "true",
            "data-micro-actions": lambda record: json.dumps(_build_user_row_actions(record))
        }

class UserActivityLogTable(tables.Table):
    timestamp = tables.DateColumn(
        format="H:i Y-m-d ",
        verbose_name="وقت العملية",
        accessor='created_at'  # Use inherited field via accessor
    )
    full_name = tables.Column(
        verbose_name="الاسم الكامل",
        accessor='created_by.profile.full_name',
        order_by='created_by__first_name'
    )
    scope = tables.Column(
        verbose_name="النطاق",
        accessor='created_by.profile.scope.name',
        default='عام'
    )
    # Explicitly declare to prevent django-tables2 from using get_FOO_display()
    action = tables.Column(verbose_name="الإجراء")
    model_name = tables.Column(verbose_name="النموذج")

    class Meta:
        model = apps.get_model('microsys', 'UserActivityLog')
        template_name = "django_tables2/bootstrap5.html"
        fields = ("timestamp", "created_by", "full_name", "model_name", "action", "object_id", "number", "scope")
        exclude = ("id", "ip_address", "user_agent", "created_at", "updated_at", "updated_by", "deleted_at", "deleted_by")
        attrs = {'class': 'table table-hover align-middle'}
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



    def render_action(self, value, record):
        """Translate action type dynamically."""
        from .translations import get_strings
        s = get_strings()
        raw_value = record.action
        if not raw_value:
            return "-"
        return s.get(f"action_{raw_value.lower()}", raw_value)

    def render_model_name(self, value):
        """Translate model name dynamically."""
        if not value:
            return "-"
        from .translations import get_strings
        s = get_strings()
        keys_to_try = [
            f"model_{value.lower().replace('.', '_')}", 
            f"model_{value.split('.')[-1].lower()}"
        ]
        for key in keys_to_try:
            if key in s:
                return s[key]
        return value

class UserActivityLogTableNoUser(UserActivityLogTable):
    class Meta(UserActivityLogTable.Meta):
        exclude = ("user", "user.full_name", "scope")

class ScopeTable(tables.Table):
    actions = tables.TemplateColumn(
        template_name='microsys/scopes/scope_actions.html',
        orderable=False,
        verbose_name=''
    )
    class Meta:
        model = apps.get_model('microsys', 'Scope')
        template_name = "django_tables2/bootstrap5.html"
        fields = ("name", "actions")
        attrs = {'class': 'table table-hover align-middle'}


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
        },
    ]
