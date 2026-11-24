"""Long requests handed to the task worker: their progress, result and file."""

import secrets

from django.conf import settings
from django.db import models


def generate_job_token():
    return secrets.token_urlsafe(32)


class DluxJob(models.Model):
    """One long request (an export, a data reset) run by the task worker.

    Web creates the row and queues ``dlux.tasks.run_job``; the worker writes
    progress, the result and any file here, and the requester polls it over the
    shared database. ``dlux.background_jobs`` owns the kinds and their runners.
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

    token = models.CharField(max_length=64, unique=True, default=generate_job_token, editable=False)
    kind = models.CharField(max_length=40, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='dlux_jobs')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    params = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    progress_message = models.CharField(max_length=255, blank=True, default='')
    file_path = models.CharField(max_length=512, blank=True, default='')
    file_name = models.CharField(max_length=255, blank=True, default='')
    file_size = models.BigIntegerField(default=0)
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = 'Background job'
        verbose_name_plural = 'Background jobs'
        default_permissions = ()
        indexes = [models.Index(fields=['user', 'kind', '-created_at'], name='dlux_job_user_kind')]

    def __str__(self):
        return f'{self.kind} {self.token[:8]} ({self.status})'
