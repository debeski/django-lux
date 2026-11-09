"""The DjangoLux task runner's queue and worker heartbeat tables (``DLUX_TASK_BACKEND="dlux"``).

Neither table has a foreign key to project or user data, so a system restore can
leave them alone, and both are excluded from system backups, reports and the
permissions UI (see ``docs/task-runner.md``).
"""

import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone


def new_task_run_id():
    return uuid.uuid4().hex


class DluxTaskRun(models.Model):
    """One queued job, or the single state row of one schedule entry.

    A schedule entry never creates a row per tick: its row (``schedule_name``
    set) goes back to READY with the next ``run_after`` when a run finishes.
    """

    STATUS_READY = "READY"
    STATUS_RUNNING = "RUNNING"
    STATUS_SUCCESSFUL = "SUCCESSFUL"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_READY, "Ready"),
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESSFUL, "Successful"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.CharField(primary_key=True, max_length=32, default=new_task_run_id, editable=False)
    task_name = models.CharField(max_length=255, verbose_name="Task")
    queue_name = models.CharField(max_length=64, default="default", verbose_name="Queue")
    args = models.JSONField(default=list, blank=True, verbose_name="Arguments")
    kwargs = models.JSONField(default=dict, blank=True, verbose_name="Keyword Arguments")
    # Arguments of a ``sensitive`` task (a backup passphrase), Fernet-encrypted
    # with a SECRET_KEY-derived key and cleared once the run is finished.
    sealed_arguments = models.TextField(blank=True, default="", verbose_name="Sealed Arguments")
    # django.tasks semantics: higher runs first, -100..100.
    priority = models.SmallIntegerField(default=0, verbose_name="Priority")
    run_after = models.DateTimeField(default=timezone.now, verbose_name="Run After")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_READY, verbose_name="Status")
    last_status = models.CharField(max_length=10, blank=True, default="", verbose_name="Last Status")
    attempts = models.PositiveIntegerField(default=0, verbose_name="Attempts")
    recoveries = models.PositiveSmallIntegerField(default=0, verbose_name="Recoveries")
    worker_id = models.CharField(max_length=64, blank=True, default="", verbose_name="Worker")
    worker_ids = models.JSONField(default=list, blank=True, verbose_name="Workers")
    claim_token = models.CharField(max_length=32, blank=True, default="", verbose_name="Claim Token")
    enqueued_at = models.DateTimeField(default=timezone.now, verbose_name="Enqueued At")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Started At")
    last_attempted_at = models.DateTimeField(null=True, blank=True, verbose_name="Last Attempted At")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Finished At")
    errors = models.JSONField(default=list, blank=True, verbose_name="Errors")
    return_value = models.JSONField(null=True, blank=True, verbose_name="Return Value")
    schedule_name = models.CharField(max_length=200, null=True, blank=True, unique=True, verbose_name="Schedule Entry")
    schedule_signature = models.CharField(max_length=64, blank=True, default="", verbose_name="Schedule Signature")

    # Not project work: keep it out of the reports builder.
    dlux_report = False

    class Meta:
        app_label = "dlux"
        verbose_name = "Task run"
        verbose_name_plural = "Task runs"
        indexes = [
            models.Index(
                fields=["-priority", "run_after"],
                condition=Q(status="READY"),
                name="dlux_taskrun_ready_idx",
            ),
            models.Index(fields=["status", "finished_at"], name="dlux_taskrun_finished_idx"),
            models.Index(fields=["worker_id"], condition=Q(status="RUNNING"), name="dlux_taskrun_running_idx"),
        ]

    def __str__(self):
        return f"{self.task_name} [{self.status}]"


class DluxTaskWorker(models.Model):
    """A running ``dlux_worker`` process; its heartbeat is what "a worker is alive" means."""

    id = models.CharField(primary_key=True, max_length=64, verbose_name="Worker")
    hostname = models.CharField(max_length=255, blank=True, default="", verbose_name="Hostname")
    pid = models.PositiveIntegerField(default=0, verbose_name="PID")
    version = models.CharField(max_length=32, blank=True, default="", verbose_name="DjangoLux Version")
    threads = models.PositiveSmallIntegerField(default=1, verbose_name="Threads")
    queues = models.JSONField(default=list, blank=True, verbose_name="Queues")
    started_at = models.DateTimeField(default=timezone.now, verbose_name="Started At")
    heartbeat_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="Heartbeat At")
    stopped_at = models.DateTimeField(null=True, blank=True, verbose_name="Stopped At")

    dlux_report = False

    class Meta:
        app_label = "dlux"
        verbose_name = "Task worker"
        verbose_name_plural = "Task workers"

    def __str__(self):
        return self.id
