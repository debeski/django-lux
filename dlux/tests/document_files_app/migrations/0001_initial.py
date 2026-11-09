"""Fixture tables, created after `dlux_scope` so PostgreSQL can add the scope FK.

Without a migration Django syncs this app before the migrated apps, which only
SQLite tolerates. Scope is created in `dlux.0001_initial` with the same BigAutoField
key it still has, so nothing later is needed.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('dlux', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LegacyFileText',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('deleted_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='Deleted At')),
                ('object_id', models.PositiveBigIntegerField()),
                ('document_model', models.CharField(max_length=64)),
                ('field_name', models.CharField(default='pdf_file', max_length=64)),
                ('file_name', models.CharField(blank=True, max_length=500)),
                ('file_sha256', models.CharField(max_length=64)),
                ('is_current', models.BooleanField(default=True)),
                ('status', models.CharField(default='pending', max_length=16)),
                ('source', models.CharField(default='auto', max_length=16)),
                ('engine', models.CharField(blank=True, max_length=64)),
                ('engine_version', models.CharField(blank=True, max_length=64)),
                ('model_version', models.CharField(blank=True, max_length=64)),
                ('markdown', models.TextField(blank=True)),
                ('text', models.TextField(blank=True)),
                ('pages', models.JSONField(blank=True, default=list)),
                ('page_count', models.PositiveIntegerField(default=0)),
                ('mean_confidence', models.FloatField(blank=True, null=True)),
                ('timings', models.JSONField(blank=True, default=dict)),
                ('duration_ms', models.PositiveIntegerField(blank=True, null=True)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('error', models.TextField(blank=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype')),
                ('created_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Created By')),
                ('deleted_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Deleted By')),
                ('scope', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='dlux.scope', verbose_name='Scope')),
                ('updated_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Updated By')),
            ],
        ),
        migrations.CreateModel(
            name='LegacyFileVersion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('deleted_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='Deleted At')),
                ('object_id', models.PositiveBigIntegerField()),
                ('document_model', models.CharField(max_length=64)),
                ('field_name', models.CharField(default='pdf_file', max_length=64)),
                ('version_number', models.PositiveIntegerField()),
                ('action_type', models.CharField(default='replace', max_length=32)),
                ('archived_file', models.FileField(max_length=500, upload_to='legacy/')),
                ('active_name_before', models.CharField(blank=True, max_length=500)),
                ('active_name_after', models.CharField(blank=True, max_length=500)),
                ('page_count', models.PositiveIntegerField(default=0)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype')),
                ('created_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Created By')),
                ('deleted_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Deleted By')),
                ('scope', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='dlux.scope', verbose_name='Scope')),
                ('updated_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Updated By')),
            ],
        ),
        migrations.CreateModel(
            name='Paper',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('deleted_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='Deleted At')),
                ('title', models.CharField(max_length=100)),
                ('pdf_file', models.FileField(blank=True, upload_to='papers/')),
                ('attachment', models.FileField(blank=True, upload_to='papers/')),
                ('created_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Created By')),
                ('deleted_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Deleted By')),
                ('scope', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='dlux.scope', verbose_name='Scope')),
                ('updated_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Updated By')),
            ],
        ),
    ]
