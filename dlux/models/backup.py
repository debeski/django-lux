"""System backup/restore and report-backup records."""

from django.db import models
from django.conf import settings
from django.utils import timezone
import secrets


def generate_report_backup_token():
    return secrets.token_urlsafe(32)


class ReportBackup(models.Model):
    """A requested reports backup zip build (background via Celery when available).

    State is kept in the DB so the requesting web process and the worker only
    need a shared database + shared default storage to hand off the result.
    """

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]

    token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_report_backup_token,
        editable=False,
        verbose_name="Token",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='dlux_report_backups',
        verbose_name="User",
    )
    window = models.CharField(max_length=10, default='all', verbose_name="Window")
    criteria = models.JSONField(default=dict, db_default={}, blank=True, verbose_name="Report Criteria")
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        verbose_name="Status",
    )
    file_path = models.CharField(max_length=512, blank=True, verbose_name="File Path")
    file_size = models.BigIntegerField(default=0, verbose_name="File Size")
    model_count = models.PositiveIntegerField(default=0, verbose_name="Model Count")
    file_count = models.PositiveIntegerField(default=0, verbose_name="File Count")
    missing_file_count = models.PositiveIntegerField(default=0, verbose_name="Missing File Count")
    progress_percent = models.PositiveSmallIntegerField(
        default=0,
        db_default=0,
        verbose_name="Progress Percent",
    )
    progress_message = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_default="",
        verbose_name="Progress Message",
    )
    error = models.TextField(blank=True, verbose_name="Error")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    started_at = models.DateTimeField(blank=True, null=True, verbose_name="Started At")
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name="Completed At")

    class Meta:
        verbose_name = "Report Backup"
        verbose_name_plural = "Report Backups"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} backup ({self.window}, {self.status})"


class SystemBackup(models.Model):
    """A full encrypted system snapshot (.dlb) — separate from the reports backup.

    Stores the requesting username as plain text (no user FK): a restore wipes
    and replaces the user table inside one transaction, so these bookkeeping
    rows must not reference it.
    """

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]
    TRIGGER_MANUAL = 'manual'
    TRIGGER_SCHEDULED = 'scheduled'
    TRIGGER_UPDATE = 'update'
    TRIGGER_CHOICES = [
        (TRIGGER_MANUAL, 'Manual'),
        (TRIGGER_SCHEDULED, 'Scheduled'),
        (TRIGGER_UPDATE, 'DjangoLux update'),
    ]

    token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_report_backup_token,
        editable=False,
        verbose_name="Token",
    )
    requested_by_username = models.CharField(max_length=150, blank=True, verbose_name="Requested By")
    trigger = models.CharField(
        max_length=12,
        choices=TRIGGER_CHOICES,
        default=TRIGGER_MANUAL,
        # db_default keeps a persistent database-level default so a *previous*
        # release's code (which has no `trigger` field) can still INSERT a
        # SystemBackup row after this migration is applied — e.g. the updater's
        # pre-update backup step running under the old code after a rollback.
        # A plain Python `default` alone is dropped from the column by Django and
        # would make those inserts violate the NOT NULL constraint.
        db_default=TRIGGER_MANUAL,
        db_index=True,
        verbose_name="Trigger",
    )
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        verbose_name="Status",
    )
    # Whether this snapshot includes uploaded media blobs. False = a fast data-only
    # backup (database + migration state only). The runner reads this off the row so
    # the choice survives a Celery handoff (the task only receives the pk). db_default
    # keeps it insert-safe for any code that doesn't set it.
    media_included = models.BooleanField(default=True, db_default=True, verbose_name="Media Included")
    file_path = models.CharField(max_length=512, blank=True, verbose_name="File Path")
    file_size = models.BigIntegerField(default=0, verbose_name="File Size")
    model_count = models.PositiveIntegerField(default=0, verbose_name="Model Count")
    row_count = models.PositiveIntegerField(default=0, verbose_name="Row Count")
    file_count = models.PositiveIntegerField(default=0, verbose_name="File Count")
    missing_file_count = models.PositiveIntegerField(default=0, verbose_name="Missing File Count")
    progress_percent = models.PositiveSmallIntegerField(
        default=0,
        db_default=0,
        verbose_name="Progress Percent",
    )
    progress_message = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_default="",
        verbose_name="Progress Message",
    )
    passphrase_required = models.BooleanField(default=False, verbose_name="Passphrase Required")
    error = models.TextField(blank=True, verbose_name="Error")
    # Liveness marker written by every progress tick. A running row whose heartbeat
    # stops advancing is the only reliable signal that its worker died mid-build:
    # an OOM-killed or restarted worker never reaches the failure path, so without
    # this the row would stay 'running' forever (a ghost).
    heartbeat_at = models.DateTimeField(blank=True, null=True, verbose_name="Heartbeat At")
    # Coarse machine-readable phase so the UI can say where a stall happened.
    stage = models.CharField(max_length=20, blank=True, default='', db_default='', verbose_name="Stage")
    attempt_count = models.PositiveSmallIntegerField(default=0, db_default=0, verbose_name="Attempts")
    next_attempt_at = models.DateTimeField(blank=True, null=True, verbose_name="Next Attempt At")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    started_at = models.DateTimeField(blank=True, null=True, verbose_name="Started At")
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name="Completed At")

    STAGE_PREPARING = 'preparing'
    STAGE_MODELS = 'models'
    STAGE_ENCRYPTING = 'encrypting'
    STAGE_STORING = 'storing'

    class Meta:
        verbose_name = "System Backup"
        verbose_name_plural = "System Backups"
        ordering = ['-created_at']

    def __str__(self):
        return f"system backup {self.token[:8]} ({self.status})"

    @property
    def is_active(self):
        return self.status in (self.STATUS_PENDING, self.STATUS_RUNNING)

    @property
    def last_signal_at(self):
        """Most recent proof of life for this run, whatever stage it reached."""
        return self.heartbeat_at or self.started_at or self.created_at

    def seconds_since_signal(self, now=None):
        reference = self.last_signal_at
        if reference is None:
            return 0
        return max(0, int(((now or timezone.now()) - reference).total_seconds()))


class SystemRestore(models.Model):
    """A full-replace restore run from an .dlb file (same no-user-FK rule as SystemBackup)."""

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]

    token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_report_backup_token,
        editable=False,
        verbose_name="Token",
    )
    requested_by_username = models.CharField(max_length=150, blank=True, verbose_name="Requested By")
    backup_file_path = models.CharField(max_length=512, verbose_name="Backup File Path")
    ignore_version_mismatch = models.BooleanField(default=False, verbose_name="Ignore Version Mismatch")
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        verbose_name="Status",
    )
    report = models.JSONField(default=dict, blank=True, verbose_name="Report")
    error = models.TextField(blank=True, verbose_name="Error")
    progress_percent = models.PositiveSmallIntegerField(
        default=0,
        db_default=0,
        verbose_name="Progress Percent",
    )
    progress_message = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_default="",
        verbose_name="Progress Message",
    )
    # Coarse machine-readable phase, so the UI can say which half of a restore is
    # slow: decrypting a large container and rewriting media files are long, and
    # the database load between them runs in one transaction.
    stage = models.CharField(max_length=20, blank=True, default='', db_default='', verbose_name="Stage")
    heartbeat_at = models.DateTimeField(blank=True, null=True, verbose_name="Heartbeat At")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    started_at = models.DateTimeField(blank=True, null=True, verbose_name="Started At")
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name="Completed At")

    STAGE_READING = 'reading'
    STAGE_DECRYPTING = 'decrypting'
    STAGE_DATABASE = 'database'
    STAGE_FILES = 'files'
    STAGE_FINALIZING = 'finalizing'

    class Meta:
        verbose_name = "System Restore"
        verbose_name_plural = "System Restores"
        ordering = ['-created_at']

    def __str__(self):
        return f"system restore {self.token[:8]} ({self.status})"

    @property
    def is_active(self):
        return self.status in (self.STATUS_PENDING, self.STATUS_RUNNING)

    @property
    def last_signal_at(self):
        return self.heartbeat_at or self.started_at or self.created_at

    def seconds_since_signal(self, now=None):
        reference = self.last_signal_at
        if reference is None:
            return 0
        return max(0, int(((now or timezone.now()) - reference).total_seconds()))
