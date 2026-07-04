import dlux.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dlux', '0007_groupprofile_groupmembership'),
    ]

    operations = [
        migrations.CreateModel(
            name='DluxImageUpdate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(default=dlux.models.generate_report_backup_token, editable=False, max_length=64, unique=True, verbose_name='Token')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('backing_up', 'Backing Up'), ('awaiting_recreate', 'Awaiting Recreate'), ('completed', 'Completed'), ('failed', 'Failed')], db_index=True, default='pending', max_length=32, verbose_name='Status')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='Active')),
                ('source_version', models.CharField(blank=True, max_length=32, verbose_name='Source Version')),
                ('target_version', models.CharField(blank=True, max_length=32, verbose_name='Target Version')),
                ('requested_by_username', models.CharField(blank=True, max_length=150, verbose_name='Requested By')),
                ('backup_mode', models.CharField(choices=[('full', 'Full (database + media)'), ('data', 'Quick (data only)'), ('skip', 'Skip backup')], db_default='data', default='data', max_length=8, verbose_name='Backup Mode')),
                ('backup_token', models.CharField(blank=True, max_length=64, verbose_name='Backup Token')),
                ('progress_log', models.TextField(blank=True, verbose_name='Progress Log')),
                ('error', models.TextField(blank=True, verbose_name='Error')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('handoff_at', models.DateTimeField(blank=True, null=True, verbose_name='Handoff At')),
                ('completed_at', models.DateTimeField(blank=True, null=True, verbose_name='Completed At')),
            ],
            options={
                'verbose_name': 'Dlux Image Update',
                'verbose_name_plural': 'Dlux Image Updates',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['is_active', 'created_at'], name='dlux_image_active_idx')],
            },
        ),
    ]
