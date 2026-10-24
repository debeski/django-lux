"""File history and file text: earlier versions of document files, and their OCR text."""

import os

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from .base import ScopedModel


def file_version_upload_to(instance, filename):
    """``dlux/file_history/<app>_<model>/<object id>/<field>/v<version>_<name>``."""
    from django.utils.text import get_valid_filename

    label = f'{instance.content_type.app_label}_{instance.content_type.model}' if instance.content_type_id else 'unknown'
    name = get_valid_filename(os.path.basename(filename)) or 'file.pdf'
    return f'dlux/file_history/{label}/{instance.object_id}/{instance.field_name}/v{instance.version_number}_{name}'


class FileVersion(ScopedModel):
    """One earlier version of a document's file, kept byte-for-byte.

    The row points at its document through a generic link, so any model with a
    registered document file uses this one table. Scope follows the document;
    audit fields record who replaced the file and when.
    """

    dlux_report = False
    dlux_seed = False
    dlux_notify = False

    ACTION_REPLACE = 'replace'
    ACTION_EDIT = 'edit'
    ACTION_NORMALIZE = 'normalize'
    ACTION_CLEAR = 'clear'
    ACTION_CHOICES = [
        (ACTION_REPLACE, 'Replaced'),
        (ACTION_EDIT, 'Edited'),
        (ACTION_NORMALIZE, 'Normalized'),
        (ACTION_CLEAR, 'Cleared'),
    ]

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    document = GenericForeignKey('content_type', 'object_id')
    document_model = models.CharField(max_length=64, verbose_name='Document Model')
    field_name = models.CharField(max_length=64, default='pdf_file', verbose_name='File Field')
    version_number = models.PositiveIntegerField(verbose_name='Version Number')
    action_type = models.CharField(max_length=32, choices=ACTION_CHOICES, default=ACTION_REPLACE, verbose_name='Action Type')
    archived_file = models.FileField(upload_to=file_version_upload_to, max_length=500, verbose_name='Archived File')
    active_name_before = models.CharField(max_length=500, blank=True, verbose_name='Active File Before')
    active_name_after = models.CharField(max_length=500, blank=True, verbose_name='Active File After')
    page_count = models.PositiveIntegerField(default=0, verbose_name='Page Count')
    metadata = models.JSONField(default=dict, blank=True, verbose_name='Metadata')

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['content_type', 'object_id', 'field_name', 'version_number'],
                name='dlux_file_version_unique',
            ),
        ]
        indexes = [models.Index(fields=['content_type', 'object_id', 'field_name'], name='dlux_file_version_doc_idx')]

    def __str__(self):
        return f'{self.document_model} #{self.object_id} {self.field_name} V{self.version_number}'


class FileText(ScopedModel):
    """Text read from one exact file (by SHA-256) of a registered document file, by OCR.

    Generic like ``FileVersion``: every model registered with
    ``register_document_file()`` uses this one table. A row is kept per file
    content, so an unchanged file is never read twice; ``is_current`` marks the
    row for the file the document holds now. Scope follows the document.
    """

    dlux_report = False
    dlux_seed = False
    dlux_notify = False

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_DONE = 'done'
    STATUS_FAILED = 'failed'
    STATUS_SKIPPED = 'skipped'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Queued'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_DONE, 'Done'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_SKIPPED, 'Skipped'),
    ]
    SOURCE_CHOICES = [('auto', 'Automatic'), ('manual', 'On demand'), ('backfill', 'Backfill')]

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    document = GenericForeignKey('content_type', 'object_id')
    document_model = models.CharField(max_length=64)
    field_name = models.CharField(max_length=64, default='pdf_file')
    file_version = models.ForeignKey(FileVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name='texts')
    file_name = models.CharField(max_length=500, blank=True)
    file_sha256 = models.CharField(max_length=64)
    is_current = models.BooleanField(default=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default='auto')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    engine = models.CharField(max_length=64, blank=True)
    engine_version = models.CharField(max_length=64, blank=True)
    model_version = models.CharField(max_length=64, blank=True)
    markdown = models.TextField(blank=True)
    text = models.TextField(blank=True)
    pages = models.JSONField(default=list, blank=True)
    page_count = models.PositiveIntegerField(default=0)
    mean_confidence = models.FloatField(null=True, blank=True)
    timings = models.JSONField(default=dict, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(
                fields=['content_type', 'object_id', 'field_name', 'file_sha256'],
                name='dlux_file_text_unique',
            ),
        ]
        indexes = [
            models.Index(fields=['content_type', 'object_id', 'field_name', 'is_current'], name='dlux_file_text_current_idx'),
            models.Index(fields=['status'], name='dlux_file_text_status_idx'),
        ]

    def __str__(self):
        return f'{self.document_model} #{self.object_id} {self.field_name} text {self.status}'
