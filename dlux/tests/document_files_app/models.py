"""Fixture models for document-file tests: a document and a project-owned legacy history table."""

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from dlux.models import ScopedModel


class Paper(ScopedModel):
    title = models.CharField(max_length=100)
    pdf_file = models.FileField(upload_to='papers/', blank=True)

    class Meta:
        app_label = 'document_files_app'

    def __str__(self):
        return self.title


class LegacyFileVersion(ScopedModel):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    document = GenericForeignKey('content_type', 'object_id')
    document_model = models.CharField(max_length=64)
    field_name = models.CharField(max_length=64, default='pdf_file')
    version_number = models.PositiveIntegerField()
    action_type = models.CharField(max_length=32, default='replace')
    archived_file = models.FileField(upload_to='legacy/', max_length=500)
    active_name_before = models.CharField(max_length=500, blank=True)
    active_name_after = models.CharField(max_length=500, blank=True)
    page_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = 'document_files_app'


class LegacyFileText(ScopedModel):
    """Shaped like Archive's `documents.DocumentOCR`, the source `dlux_adopt_ocr_text` copies from."""
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    document = GenericForeignKey('content_type', 'object_id')
    document_model = models.CharField(max_length=64)
    field_name = models.CharField(max_length=64, default='pdf_file')
    file_name = models.CharField(max_length=500, blank=True)
    file_sha256 = models.CharField(max_length=64)
    is_current = models.BooleanField(default=True)
    status = models.CharField(max_length=16, default='pending')
    source = models.CharField(max_length=16, default='auto')
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
        app_label = 'document_files_app'
