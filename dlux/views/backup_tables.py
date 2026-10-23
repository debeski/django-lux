"""The backup page's two histories as DluxTables (SystemBackupTable, SystemRestoreTable).

Kept out of ``dlux/tables.py`` on purpose: they need the backup package, and
``dlux.tables`` is imported widely, so depending on backup from there pulls it
into a deferred-import cluster (``test_import_graph``). Only the backup views
import this module.
"""

import json

import django_tables2 as tables
from django.apps import apps
from django.template.defaultfilters import filesizeformat
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.safestring import mark_safe

from ..backup import backup_retry_policy
from ..tables import DluxTable, _lazy_label
from ..translations import get_strings
from ..utils.backup_progress import read_restore_progress


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
        self.backup_policy = backup_retry_policy()
        # Warn well before the row is actually reaped, so a genuinely slow stage
        # is visible as "quiet" rather than silently looking identical to a hang.
        self.backup_stall_warn_seconds = max(60, self.backup_policy['stall_timeout_minutes'] * 60 // 3)
        super().__init__(*args, **kwargs)

    def _cell(self, name, record):
        return mark_safe(render_to_string(f'dlux/backup/cells/_backup_{name}.html', _backup_cell_context(self, record)))

    def render_trigger(self, record):
        return self._cell('trigger', record)

    def render_status(self, record):
        return self._cell('status', record)

    def render_progress(self, record):
        return self._cell('progress', record)

    def render_file_size(self, value):
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
