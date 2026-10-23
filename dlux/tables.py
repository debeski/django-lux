import json

import django_tables2 as tables
from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.html import format_html
from django.utils.functional import lazy
from django.utils.safestring import mark_safe

from .system.constants import DEFAULT_TABLE_PAGE_SIZE, TABLE_PAGE_SIZE_OPTIONS
from .translations import get_strings
from .utils import get_user_management_tier_state_for_user, translate_activity_log_model_name

User = get_user_model()



# Column labels are evaluated when the class body runs — i.e. at import, before
# any request or language is known. Resolving them lazily keeps the header in the
# viewer's language and keeps module import free of translation lookups.
_lazy_label = lazy(lambda key, default: get_strings().get(key, default), str)


def _translated_renderer(field):
    """A ``render_<field>`` for django-tables2 to find on the table instance.

    A plain function taking ``record``: ``call_with_appropriate`` inspects the
    signature to decide what to pass, so the argument name is the contract.
    """
    def render(record):
        return getattr(record, f"t_{field}")

    return render


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
        dlux_resizable_columns = True
        dlux_show_footer = True

    def __init__(self, *args, **kwargs):
        # Before super(), because BoundColumns.__init__ resolves each column's
        # renderer with getattr(table, "render_<name>") while binding — an
        # attribute set afterwards is never consulted.
        self._install_translated_renderers()
        super().__init__(*args, **kwargs)

    def _install_translated_renderers(self):
        """Render a column in the viewer's language when the model translates it.

        ``TranslationMixin`` gives a model ``t_<field>``, but django-tables2 reads
        the raw field, so a list stayed in the source language under any other
        interface language even where a translation existed — the model half of
        the feature shipped without the table half.

        Applies to every name in the model's ``translated_fields`` that is also a
        column, so a table gets this by declaring the field once on the model
        rather than by remembering a mixin per table.

        Two things deliberately left alone. A ``render_<field>`` defined on the
        table wins, since a table that has already said how to draw a column
        means it. And a row whose *base* field is empty still renders the column
        default: django-tables2 short-circuits on the raw value before any
        renderer runs, so a translation cannot rescue a blank canonical value —
        which matches the mixin's own contract, where the base field is the
        canonical one and the translations are optional.
        """
        model = getattr(self._meta, "model", None)
        translated = getattr(model, "translated_fields", None) or ()
        for field in translated:
            if field not in self.base_columns:
                continue
            if hasattr(type(self), f"render_{field}"):
                continue
            setattr(self, f"render_{field}", _translated_renderer(field))

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

        app_label = model._meta.app_label
        model_name = model._meta.model_name
        section_action = bool(getattr(self, 'dlux_section_actions', False))
        record_name = self.get_dlux_record_name(record)
        payload = {
            'app': app_label,
            'model': self.get_dlux_model_name(),
            'id': record.pk,
            'name': record_name,
        }
        if getattr(self, 'dlux_modal_manager_url', ''):
            payload['delete_url'] = reverse('modal_delete', args=[app_label, model._meta.object_name, record.pk])

        edit_action = {
            'label': 'edit_label',
            'icon': 'bi bi-pencil',
            'type': 'event',
            'event': 'dlux:record:edit',
            'data': payload,
            'permissions': [f"{app_label}.change_{model_name}"],
        }
        delete_action = {
            'label': 'delete_label',
            'icon': 'bi bi-trash',
            'type': 'event',
            'event': 'dlux:record:delete',
            'data': payload,
            'textClass': 'text-danger',
            'permissions': [f"{app_label}.delete_{model_name}"],
        }
        if section_action:
            edit_action['section_action'] = True
            delete_action['section_action'] = True

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
            edit_action,
            delete_action,
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
    staff_tier = tables.Column(verbose_name=_lazy_label('tbl_staff_tier', 'Staff Tier'), empty_values=())
    twofa_status = tables.Column(
        verbose_name=_lazy_label('tbl_2fa_status', '2FA'),
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
    description = tables.Column(orderable=False, default='')
    public_registration_default = tables.Column(empty_values=(), orderable=False)

    class Meta(DluxTable.Meta):
        model = apps.get_model('dlux', 'Scope')
        fields = ("name", "description", "public_registration_default")
        row_attrs = {
            "data-dlux-context": "true",
            "data-dlux-actions": lambda record: json.dumps(_build_scope_row_actions(record)),
        }
        dlux_actions = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        s = get_strings()
        self.columns['name'].column.verbose_name = s.get('form_scope_name', 'Scope Name')
        self.columns['description'].column.verbose_name = s.get('form_scope_description', 'Description')
        self.columns['public_registration_default'].column.verbose_name = s.get('public_registration_default_short', 'Registration')

    def render_description(self, value):
        return value or format_html('<span class="text-muted">{}</span>', '-')

    def render_public_registration_default(self, record):
        if getattr(record, 'is_public_registration_default', False):
            return format_html(
                '<span class="badge bg-primary"><i class="bi bi-person-plus-fill me-1"></i>{}</span>',
                get_strings().get('public_registration_default_badge', 'Public default'),
            )
        return format_html('<span class="text-muted small">{}</span>', '-')


class GroupPresetTable(DluxTable):
    """Permission-preset (auth.Group + GroupProfile) directory grid."""
    scope = tables.Column(accessor='dlux_profile__scope__name', orderable=False)
    public_registration_default = tables.Column(empty_values=(), orderable=False)
    member_count = tables.Column(accessor='member_count', orderable=False)
    permission_count = tables.Column(accessor='permission_count', orderable=False)

    class Meta(DluxTable.Meta):
        model = apps.get_model('auth', 'Group')
        fields = ("name", "scope", "public_registration_default", "member_count", "permission_count")
        row_attrs = {
            "data-dlux-context": "true",
            "data-dlux-actions": lambda record: json.dumps(_build_group_preset_row_actions(record)),
        }
        dlux_actions = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        s = get_strings()
        self.columns['name'].column.verbose_name = s.get('form_group_name', 'Group Name')
        self.columns['scope'].column.verbose_name = s.get('form_scope', 'Scope')
        self.columns['public_registration_default'].column.verbose_name = s.get('public_registration_default_short', 'Registration')
        self.columns['member_count'].column.verbose_name = s.get('group_member_count', 'Members')
        self.columns['permission_count'].column.verbose_name = s.get('group_permission_count', 'Permissions')

    def render_scope(self, value):
        return value or get_strings().get('group_scope_global', 'Global')

    def render_public_registration_default(self, record):
        profile = getattr(record, 'dlux_profile', None)
        if profile and getattr(profile, 'is_public_registration_default', False):
            return format_html(
                '<span class="badge bg-primary"><i class="bi bi-person-plus-fill me-1"></i>{}</span>',
                get_strings().get('public_registration_default_badge', 'Public default'),
            )
        return format_html('<span class="text-muted small">{}</span>', '-')


class GroupMembershipTable(DluxTable):
    """Read-only who/which/when history for a preset's membership."""
    class Meta(DluxTable.Meta):
        model = apps.get_model('dlux', 'GroupMembership')
        fields = ("user", "assigned_by", "assigned_at")
        dlux_actions = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        s = get_strings()
        self.columns['user'].column.verbose_name = s.get('group_member_user', 'User')
        self.columns['assigned_by'].column.verbose_name = s.get('group_assigned_by', 'Assigned By')
        self.columns['assigned_at'].column.verbose_name = s.get('group_assigned_at', 'Assigned At')


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
            "event": "dlux:dynamic_modal:open",
            "data": {
                "url": reverse('user_detail_modal', args=[record.pk]),
                "title": f"{s.get('view_label', 'View')} {display_name}".strip(),
            },
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


def _build_group_preset_row_actions(record):
    s = get_strings()
    can_manage = bool(getattr(record, 'dlux_can_manage', False))
    profile = getattr(record, 'dlux_profile', None)
    is_default = bool(profile and getattr(profile, 'is_public_registration_default', False))
    actions = []
    if can_manage:
        actions.extend([
            {
                "label": s.get("group_members_label", "Members"),
                "icon": "bi bi-people-fill",
                "type": "event",
                "event": "dlux:group:members",
                "data": {"url": reverse('group_members', args=[record.pk])},
                "dblclick": True,
            },
            {
                "label": s.get("edit_group", "Edit Group"),
                "icon": "bi bi-pencil-square",
                "type": "event",
                "event": "dlux:group:edit",
                "data": {"url": reverse('get_group_form', args=[record.pk])},
            },
            {"type": "divider"},
            {
                "label": (
                    s.get("group_clear_public_registration_default", "Clear public-registration default")
                    if is_default else
                    s.get("group_set_public_registration_default", "Use for public registrations")
                ),
                "icon": "bi bi-person-plus-fill",
                "type": "event",
                "event": "dlux:group:toggle-public-default",
                "data": {"url": reverse('toggle_group_public_registration_default', args=[record.pk])},
            },
            {
                "label": s.get("delete_label", "Delete"),
                "icon": "bi bi-trash",
                "type": "event",
                "event": "dlux:group:delete",
                "textClass": "text-danger",
                "data": {"url": reverse('delete_group', args=[record.pk])},
            },
        ])
    else:
        actions.append({
            "label": s.get("group_view_only", "View only"),
            "icon": "bi bi-eye",
            "type": "event",
            "event": "dlux:noop",
        })
    return actions


def _build_scope_row_actions(record):
    s = get_strings()
    is_default = bool(getattr(record, 'is_public_registration_default', False))
    return [
        {
            "label": s.get("view_details", "View Details"),
            "icon": "bi bi-eye",
            "type": "event",
            "event": "dlux:scope:detail",
            "data": {"url": reverse('scope_detail', args=[record.pk])},
            "dblclick": True,
        },
        {
            "label": s.get("edit_scope", "Edit Scope"),
            "icon": "bi bi-pencil-square",
            "type": "event",
            "event": "dlux:scope:edit",
            "data": {"url": reverse('get_scope_form', args=[record.pk])},
        },
        {"type": "divider"},
        {
            "label": (
                s.get("scope_clear_public_registration_default", "Clear public-registration default")
                if is_default else
                s.get("scope_set_public_registration_default", "Use for public registrations")
            ),
            "icon": "bi bi-person-plus-fill",
            "type": "event",
            "event": "dlux:scope:toggle-public-default",
            "data": {"url": reverse('toggle_scope_public_registration_default', args=[record.pk])},
        },
        {
            "label": s.get("delete_label", "Delete"),
            "icon": "bi bi-trash",
            "type": "event",
            "event": "dlux:scope:delete",
            "textClass": "text-danger",
            "data": {"url": reverse('delete_scope', args=[record.pk])},
        },
    ]


def _backup_cell_context(table, backup):
    """What every SystemBackupTable cell template reads, computed once per row."""
    return {
        'backup': backup,
        'DLUX_STRINGS': get_strings(),
        'backup_policy': table.backup_policy,
        'backup_stall_warn_seconds': table.backup_stall_warn_seconds,
        'quiet_for': backup.seconds_since_signal() if backup.is_active else 0,
        'eta': backup.eta_seconds(),
    }


def system_backup_row_actions(backup):
    """The row actions of one system backup, in the shared Dlux row-action schema.

    Download is a plain link. Everything else is an event that the backup page
    script (backup/js/manage.js) handles with the page's own panels, prompts and
    POST forms, so a context menu, a three-dot column and a keyboard user all
    reach the same code. The endpoints keep their own superuser and POST checks:
    a hidden or shown action is never the authorization.
    """
    s = get_strings()
    label = backup.created_at.strftime('%Y-%m-%d %H:%M') if backup.created_at else backup.token
    actions = [{
        'label': s.get('sysbackup_details', 'Details'),
        'icon': 'bi bi-terminal',
        'type': 'event',
        'event': 'dlux:backup:details',
        'data': {'url': reverse('system_backup_status', args=[backup.token]), 'label': label},
        'dblclick': True,
    }]
    if backup.status == 'completed':
        if backup.is_incremental:
            actions.append({
                'label': s.get('sysbackup_download_chain', 'Download chain'),
                'icon': 'bi bi-download',
                'type': 'url',
                'url': reverse('system_backup_chain_download', args=[backup.token]),
            })
        else:
            actions.append({
                'label': s.get('sysbackup_download', 'Download'),
                'icon': 'bi bi-download',
                'type': 'url',
                'url': reverse('system_backup_download', args=[backup.token]),
            })
        actions.append({
            'label': s.get('sysrestore_action', 'Restore'),
            'icon': 'bi bi-arrow-counterclockwise',
            'type': 'event',
            'event': 'dlux:backup:restore',
            'data': {'token': backup.token, 'label': label},
        })
    elif backup.status in ('failed', 'cancelled'):
        actions.append({
            'label': s.get('sysbackup_resume', 'Retry'),
            'icon': 'bi bi-arrow-repeat',
            'type': 'event',
            'event': 'dlux:backup:resume',
            'data': {
                'url': reverse('system_backup_resume', args=[backup.token]),
                'label': label,
                'needsPassphrase': bool(backup.passphrase_required or backup.encryption == 'passphrase'),
            },
        })
    actions.append({'type': 'divider'})
    if backup.is_active:
        actions.append({
            'label': s.get('sysbackup_cancel', 'Cancel'),
            'icon': 'bi bi-x-circle',
            'type': 'event',
            'event': 'dlux:backup:cancel',
            'data': {'url': reverse('system_backup_cancel', args=[backup.token]), 'label': label},
            'textClass': 'text-danger',
        })
    else:
        delete = {
            'url': reverse('system_backup_delete', args=[backup.token]),
            'label': label,
            'confirm': s.get('sysbackup_delete_confirm', 'Delete the backup from {label}? This cannot be undone.').replace('{label}', label),
        }
        # Judged here, not from the rows on screen: with pagination the later
        # backups of a chain are often on another page.
        if backup.status == 'completed' and backup.index_root and backup.chain_id:
            later = type(backup).objects.filter(chain_id=backup.chain_id, sequence__gt=backup.sequence).exists()
            if later:
                delete['chainConfirm'] = s.get(
                    'sysbackup_delete_chain_confirm',
                    'Later incremental backups of this chain depend on this one and will be deleted with it. Continue?',
                )
        actions.append({
            'label': s.get('sysbackup_delete', 'Delete'),
            'icon': 'bi bi-trash',
            'type': 'event',
            'event': 'dlux:backup:delete',
            'data': delete,
            'textClass': 'text-danger',
        })
    return actions


class _FixedPageSizeTable(DluxTable):
    """A DluxTable whose page size is its ``Meta.dlux_per_page``, whatever the URL says.

    django-tables2's RequestConfig reads ``<prefix>per_page`` straight from the
    query string and passes it to ``paginate``, so even a single-option table
    could be asked for any page size. These histories have a fixed size.
    """

    def paginate(self, *args, **kwargs):
        # The class's own Meta: django-tables2's options object drops dlux_* keys.
        kwargs['per_page'] = type(self).Meta.dlux_per_page
        return super().paginate(*args, **kwargs)


class SystemBackupTable(_FixedPageSizeTable):
    """Backup history on the backup page: ten per page, newest first.

    Row actions follow the shared Layout setting (context menu, three-dot column
    or both); they are built per row by ``system_backup_row_actions``.
    """

    # Not `created_at`: that name is an audit column, which the table patch hides
    # unless audit fields are visible — and here the time is the row's identity.
    when = tables.DateTimeColumn(format='Y-m-d H:i', accessor='created_at',
                                 verbose_name=_lazy_label('user_report_timestamp', 'Timestamp'))
    requested_by_username = tables.Column(verbose_name=_lazy_label('sysbackup_requested_by', 'Requested by'), default='-')
    trigger = tables.Column(verbose_name=_lazy_label('sysbackup_trigger', 'Trigger'), empty_values=())
    status = tables.Column(verbose_name=_lazy_label('sysbackup_status', 'Status'), empty_values=())
    progress = tables.Column(verbose_name=_lazy_label('backup_progress', 'Progress'), empty_values=(), accessor='pk',
                             attrs={'td': {'class': 'dlux-backup-progress-cell'}})
    row_count = tables.Column(verbose_name=_lazy_label('sysbackup_rows', 'Rows'))
    file_count = tables.Column(verbose_name=_lazy_label('sysbackup_files', 'Files'))
    file_size = tables.Column(verbose_name=_lazy_label('sysbackup_size', 'Size'))

    class Meta(DluxTable.Meta):
        model = apps.get_model('dlux', 'SystemBackup')
        fields = ('when', 'requested_by_username', 'trigger', 'status', 'progress',
                  'row_count', 'file_count', 'file_size')
        sequence = fields
        orderable = False
        dlux_per_page = 10
        dlux_per_page_options = (10,)
        dlux_resizable_columns = False
        row_attrs = {
            'data-system-backup-row': '',
            'data-backup-token': lambda record: record.token,
            'data-backup-status': lambda record: record.status,
            'data-dlux-actions': lambda record: json.dumps(system_backup_row_actions(record)),
        }

    def __init__(self, *args, **kwargs):
        from .backup import backup_retry_policy

        self.backup_policy = backup_retry_policy()
        # Warn well before the row is actually reaped, so a genuinely slow stage
        # is visible as "quiet" rather than silently looking identical to a hang.
        self.backup_stall_warn_seconds = max(60, self.backup_policy['stall_timeout_minutes'] * 60 // 3)
        super().__init__(*args, **kwargs)

    def _cell(self, name, record):
        from django.template.loader import render_to_string

        return mark_safe(render_to_string(f'dlux/backup/cells/_backup_{name}.html', _backup_cell_context(self, record)))

    def render_trigger(self, record):
        return self._cell('trigger', record)

    def render_status(self, record):
        return self._cell('status', record)

    def render_progress(self, record):
        return self._cell('progress', record)

    def render_file_size(self, value):
        from django.template.defaultfilters import filesizeformat

        return filesizeformat(value)


class SystemRestoreTable(_FixedPageSizeTable):
    """Restore history on the backup page: five per page, newest first, no row actions."""

    # Not `created_at`: that name is an audit column, which the table patch hides
    # unless audit fields are visible — and here the time is the row's identity.
    when = tables.DateTimeColumn(format='Y-m-d H:i', accessor='created_at',
                                 verbose_name=_lazy_label('user_report_timestamp', 'Timestamp'))
    requested_by_username = tables.Column(verbose_name=_lazy_label('sysbackup_requested_by', 'Requested by'), default='-')
    status = tables.Column(verbose_name=_lazy_label('sysbackup_status', 'Status'), empty_values=())
    progress = tables.Column(verbose_name=_lazy_label('sysrestore_progress', 'Progress'), empty_values=(), accessor='pk',
                             attrs={'td': {'class': 'dlux-backup-progress-cell'}})

    class Meta(DluxTable.Meta):
        model = apps.get_model('dlux', 'SystemRestore')
        fields = ('when', 'requested_by_username', 'status', 'progress')
        sequence = fields
        orderable = False
        dlux_actions = False
        dlux_per_page = 5
        dlux_per_page_options = (5,)
        dlux_resizable_columns = False
        row_attrs = {
            'data-system-restore-row': '',
            'data-restore-token': lambda record: record.token,
            'data-restore-status': lambda record: record.status,
        }

    def _cell(self, name, record):
        from django.template.loader import render_to_string

        from .utils.backup_progress import read_restore_progress

        # A running restore's fine-grained progress lives in the cache mirror, not
        # the row, because the database phase runs inside one transaction.
        if not hasattr(record, 'live_progress'):
            record.live_progress = read_restore_progress(record)
            record.live_eta = record.eta_seconds(percent=record.live_progress['progress_percent'])
        return mark_safe(render_to_string(
            f'dlux/backup/cells/_restore_{name}.html',
            {'restore': record, 'DLUX_STRINGS': get_strings()},
        ))

    def render_status(self, record):
        return self._cell('status', record)

    def render_progress(self, record):
        return self._cell('progress', record)
