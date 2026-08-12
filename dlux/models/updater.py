"""Updater state, runs, image updates and control-panel link requests."""

from django.db import models
from django.utils import timezone
import uuid

from .backup import generate_report_backup_token


class DluxUpdateState(models.Model):
    """Singleton mirror of the active runtime release and last verified update."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    baked_version = models.CharField(max_length=32, blank=True, verbose_name="Baked Version")
    active_version = models.CharField(max_length=32, blank=True, verbose_name="Active Version")
    active_wheel_url = models.TextField(blank=True, verbose_name="Active Wheel URL")
    active_wheel_sha256 = models.CharField(max_length=64, blank=True, verbose_name="Active Wheel SHA256")
    active_manifest = models.JSONField(default=dict, blank=True, verbose_name="Active Manifest")
    previous_version = models.CharField(max_length=32, blank=True, verbose_name="Previous Version")
    previous_wheel_url = models.TextField(blank=True, verbose_name="Previous Wheel URL")
    previous_wheel_sha256 = models.CharField(max_length=64, blank=True, verbose_name="Previous Wheel SHA256")
    previous_manifest = models.JSONField(default=dict, blank=True, verbose_name="Previous Manifest")
    latest_version = models.CharField(max_length=32, blank=True, verbose_name="Latest Version")
    latest_wheel_url = models.TextField(blank=True, verbose_name="Latest Wheel URL")
    latest_wheel_sha256 = models.CharField(max_length=64, blank=True, verbose_name="Latest Wheel SHA256")
    latest_manifest = models.JSONField(default=dict, blank=True, verbose_name="Latest Manifest")
    latest_compatible = models.BooleanField(default=False, verbose_name="Latest Compatible")
    latest_reason = models.TextField(blank=True, verbose_name="Latest Compatibility Reason")
    last_checked_at = models.DateTimeField(blank=True, null=True, verbose_name="Last Checked At")
    last_check_error = models.TextField(blank=True, verbose_name="Last Check Error")
    generation = models.PositiveBigIntegerField(default=0, verbose_name="Runtime Generation")
    degraded = models.BooleanField(default=False, verbose_name="Runtime Degraded")
    degraded_reason = models.TextField(blank=True, verbose_name="Runtime Degraded Reason")
    active_run_token = models.CharField(max_length=64, blank=True, db_index=True, verbose_name="Active Run Token")
    # Versions the admin has chosen to permanently skip. The update check never
    # offers a skipped version (it picks the latest non-skipped release instead),
    # until the admin un-skips it. A list of canonical version strings. Nullable so
    # the AddField stays inline-safe (readers coalesce None -> []).
    skipped_versions = models.JSONField(default=list, blank=True, null=True, verbose_name="Skipped Versions")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        verbose_name = "Dlux Update State"
        verbose_name_plural = "Dlux Update State"

    @classmethod
    def load(cls):
        from .. import __version__
        from ..updater import get_baked_version

        obj, _created = cls.objects.get_or_create(
            pk=1,
            defaults={
                'baked_version': get_baked_version(),
                'active_version': __version__,
            },
        )
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return None

    def __str__(self):
        return f"Dlux updater ({self.active_version or self.baked_version or 'unknown'})"


class DluxUpdateRun(models.Model):
    """Durable check/apply/rollback request consumed by the isolated update worker."""

    ACTION_CHECK = 'check'
    ACTION_APPLY = 'apply'
    ACTION_ROLLBACK = 'rollback'
    ACTION_CHOICES = [
        (ACTION_CHECK, 'Check'),
        (ACTION_APPLY, 'Apply'),
        (ACTION_ROLLBACK, 'Rollback'),
    ]

    BACKUP_FULL = 'full'
    BACKUP_DATA = 'data'
    BACKUP_SKIP = 'skip'
    BACKUP_MODE_CHOICES = [
        (BACKUP_FULL, 'Full (database + media)'),
        (BACKUP_DATA, 'Quick (data only)'),
        (BACKUP_SKIP, 'Skip backup'),
    ]

    STATUS_QUEUED = 'queued'
    STATUS_CHECKING = 'checking'
    STATUS_DOWNLOADING = 'downloading'
    STATUS_VERIFYING = 'verifying'
    STATUS_STAGING = 'staging'
    STATUS_PREFLIGHT = 'preflight'
    STATUS_BACKING_UP = 'backing_up'
    STATUS_MAINTENANCE = 'maintenance'
    STATUS_MIGRATING = 'migrating'
    STATUS_COLLECTING_STATIC = 'collecting_static'
    STATUS_SWITCHING = 'switching'
    STATUS_RESTARTING = 'restarting'
    STATUS_VERIFYING_HEALTH = 'verifying_health'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_ROLLED_BACK = 'rolled_back'
    STATUS_CHOICES = [
        (STATUS_QUEUED, 'Queued'),
        (STATUS_CHECKING, 'Checking'),
        (STATUS_DOWNLOADING, 'Downloading'),
        (STATUS_VERIFYING, 'Verifying'),
        (STATUS_STAGING, 'Staging'),
        (STATUS_PREFLIGHT, 'Preflight'),
        (STATUS_BACKING_UP, 'Backing Up'),
        (STATUS_MAINTENANCE, 'Maintenance'),
        (STATUS_MIGRATING, 'Migrating'),
        (STATUS_COLLECTING_STATIC, 'Collecting Static'),
        (STATUS_SWITCHING, 'Switching'),
        (STATUS_RESTARTING, 'Restarting'),
        (STATUS_VERIFYING_HEALTH, 'Verifying Health'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_ROLLED_BACK, 'Rolled Back'),
    ]

    token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_report_backup_token,
        editable=False,
        verbose_name="Token",
    )
    action = models.CharField(max_length=16, choices=ACTION_CHOICES, db_index=True, verbose_name="Action")
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_QUEUED,
        db_index=True,
        verbose_name="Status",
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Active")
    source_version = models.CharField(max_length=32, blank=True, verbose_name="Source Version")
    target_version = models.CharField(max_length=32, blank=True, verbose_name="Target Version")
    requested_by_username = models.CharField(max_length=150, blank=True, verbose_name="Requested By")
    manifest = models.JSONField(default=dict, blank=True, verbose_name="Verified Manifest")
    wheel_url = models.TextField(blank=True, verbose_name="Wheel URL")
    wheel_sha256 = models.CharField(max_length=64, blank=True, verbose_name="Wheel SHA256")
    # Operator's pre-update backup choice, read by the worker off the row (the run is
    # processed asynchronously). db_default keeps it insert-safe for older code.
    backup_mode = models.CharField(
        max_length=8,
        choices=BACKUP_MODE_CHOICES,
        default=BACKUP_DATA,
        db_default=BACKUP_DATA,
        verbose_name="Backup Mode",
    )
    backup_token = models.CharField(max_length=64, blank=True, verbose_name="Backup Token")
    progress_log = models.TextField(blank=True, verbose_name="Progress Log")
    report = models.JSONField(default=dict, blank=True, verbose_name="Report")
    error = models.TextField(blank=True, verbose_name="Error")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    started_at = models.DateTimeField(blank=True, null=True, verbose_name="Started At")
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name="Completed At")

    class Meta:
        verbose_name = "Dlux Update Run"
        verbose_name_plural = "Dlux Update Runs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active', 'created_at'], name='dlux_update_active_idx'),
        ]

    def append_log(self, message):
        line = str(message or '').replace('\x00', '').strip()
        if not line:
            return
        combined = f"{self.progress_log}\n{line}".strip()
        self.progress_log = combined[-65536:]

    def finish(self, status, *, error='', report=None):
        self.status = status
        self.is_active = False
        self.completed_at = timezone.now()
        self.error = str(error or '')[:4000]
        if report is not None:
            self.report = report

    def __str__(self):
        return f"Dlux {self.action} {self.target_version or self.source_version} ({self.status})"


class DluxImageUpdate(models.Model):
    """Image-level (full container) update request, executed by the external
    Composer agent rather than the inline wheel worker.

    Deliberately SEPARATE from DluxUpdateRun so the battle-tested inline update
    worker/recovery state machine is never disturbed. Lifecycle is driven by
    ``UpdateService.tick_image_update()`` from the same worker loop: pending →
    backing_up → awaiting_recreate → (composer recreates this container) →
    completed/failed, finalized by reading composer's ``deploy-status.json``.
    Backup-mode values intentionally mirror ``DluxUpdateRun`` so the shared
    ``_create_backup`` helper can be reused unchanged.
    """

    BACKUP_FULL = 'full'
    BACKUP_DATA = 'data'
    BACKUP_SKIP = 'skip'
    BACKUP_MODE_CHOICES = [
        (BACKUP_FULL, 'Full (database + media)'),
        (BACKUP_DATA, 'Quick (data only)'),
        (BACKUP_SKIP, 'Skip backup'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_BACKING_UP = 'backing_up'
    STATUS_AWAITING_RECREATE = 'awaiting_recreate'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_BACKING_UP, 'Backing Up'),
        (STATUS_AWAITING_RECREATE, 'Awaiting Recreate'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]
    TERMINAL_STATUSES = frozenset({STATUS_COMPLETED, STATUS_FAILED})

    token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_report_backup_token,
        editable=False,
        verbose_name="Token",
    )
    control_operation_id = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
        verbose_name="Control Operation ID",
    )
    request_source = models.CharField(
        max_length=16,
        choices=[('local', 'Local'), ('control', 'Control Plane')],
        default='local',
        db_default='local',
        verbose_name="Request Source",
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        verbose_name="Status",
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Active")
    source_version = models.CharField(max_length=32, blank=True, verbose_name="Source Version")
    target_version = models.CharField(max_length=32, blank=True, verbose_name="Target Version")
    requested_by_username = models.CharField(max_length=150, blank=True, verbose_name="Requested By")
    backup_mode = models.CharField(
        max_length=8,
        choices=BACKUP_MODE_CHOICES,
        default=BACKUP_DATA,
        db_default=BACKUP_DATA,
        verbose_name="Backup Mode",
    )
    backup_token = models.CharField(max_length=64, blank=True, verbose_name="Backup Token")
    progress_log = models.TextField(blank=True, verbose_name="Progress Log")
    error = models.TextField(blank=True, verbose_name="Error")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    handoff_at = models.DateTimeField(blank=True, null=True, verbose_name="Handoff At")
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name="Completed At")

    class Meta:
        verbose_name = "Dlux Image Update"
        verbose_name_plural = "Dlux Image Updates"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active', 'created_at'], name='dlux_image_active_idx'),
        ]

    def append_log(self, message):
        line = str(message or '').replace('\x00', '').strip()
        if not line:
            return
        combined = f"{self.progress_log}\n{line}".strip()
        self.progress_log = combined[-65536:]

    def __str__(self):
        return f"Dlux image update {self.target_version or ''} ({self.status})"


class DluxControlLinkRequest(models.Model):
    """Queued Control Panel pairing action, applied by the update worker.

    The web tier mounts the runtime volume read-only — the agent bridge is the
    channel the Composer agent takes commands from, and the agent holds Docker
    API access, so the application tier deliberately cannot write it. The
    superuser's intent is recorded here instead, and
    ``UpdateService.tick_control_link()`` performs the bridge write from the
    worker, which owns the only read-write mount.

    The worker deletes the row as soon as the bridge file is written, so the
    one-use pairing token is at rest for at most one worker tick.
    """

    ACTION_ENROLL = 'enroll'
    ACTION_CANCEL = 'cancel'
    ACTION_CHOICES = [
        (ACTION_ENROLL, 'Enroll'),
        (ACTION_CANCEL, 'Cancel'),
    ]

    action = models.CharField(
        max_length=16,
        choices=ACTION_CHOICES,
        default=ACTION_ENROLL,
        verbose_name="Action",
    )
    operation_id = models.UUIDField(default=uuid.uuid4, editable=False, verbose_name="Operation ID")
    control_url = models.CharField(max_length=500, blank=True, verbose_name="Control URL")
    pairing_token = models.CharField(max_length=255, blank=True, verbose_name="Pairing Token")
    error = models.TextField(blank=True, verbose_name="Error")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")

    class Meta:
        verbose_name = "Dlux Control Link Request"
        verbose_name_plural = "Dlux Control Link Requests"
        ordering = ['created_at']

    def __str__(self):
        return f"Dlux control link {self.action} ({self.operation_id})"
