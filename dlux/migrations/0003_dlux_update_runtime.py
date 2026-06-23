import dlux.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dlux', '0002_system_settings_configs_and_notifications'),
    ]

    operations = [
        migrations.CreateModel(
            name='DluxUpdateState',
            fields=[
                ('id', models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ('baked_version', models.CharField(blank=True, max_length=32, verbose_name='Baked Version')),
                ('active_version', models.CharField(blank=True, max_length=32, verbose_name='Active Version')),
                ('active_wheel_url', models.TextField(blank=True, verbose_name='Active Wheel URL')),
                ('active_wheel_sha256', models.CharField(blank=True, max_length=64, verbose_name='Active Wheel SHA256')),
                ('active_manifest', models.JSONField(blank=True, default=dict, verbose_name='Active Manifest')),
                ('previous_version', models.CharField(blank=True, max_length=32, verbose_name='Previous Version')),
                ('previous_wheel_url', models.TextField(blank=True, verbose_name='Previous Wheel URL')),
                ('previous_wheel_sha256', models.CharField(blank=True, max_length=64, verbose_name='Previous Wheel SHA256')),
                ('previous_manifest', models.JSONField(blank=True, default=dict, verbose_name='Previous Manifest')),
                ('latest_version', models.CharField(blank=True, max_length=32, verbose_name='Latest Version')),
                ('latest_wheel_url', models.TextField(blank=True, verbose_name='Latest Wheel URL')),
                ('latest_wheel_sha256', models.CharField(blank=True, max_length=64, verbose_name='Latest Wheel SHA256')),
                ('latest_manifest', models.JSONField(blank=True, default=dict, verbose_name='Latest Manifest')),
                ('latest_compatible', models.BooleanField(default=False, verbose_name='Latest Compatible')),
                ('latest_reason', models.TextField(blank=True, verbose_name='Latest Compatibility Reason')),
                ('last_checked_at', models.DateTimeField(blank=True, null=True, verbose_name='Last Checked At')),
                ('last_check_error', models.TextField(blank=True, verbose_name='Last Check Error')),
                ('generation', models.PositiveBigIntegerField(default=0, verbose_name='Runtime Generation')),
                ('degraded', models.BooleanField(default=False, verbose_name='Runtime Degraded')),
                ('degraded_reason', models.TextField(blank=True, verbose_name='Runtime Degraded Reason')),
                ('active_run_token', models.CharField(blank=True, db_index=True, max_length=64, verbose_name='Active Run Token')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
            ],
            options={
                'verbose_name': 'Dlux Update State',
                'verbose_name_plural': 'Dlux Update State',
            },
        ),
        migrations.CreateModel(
            name='DluxUpdateRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(default=dlux.models.generate_report_backup_token, editable=False, max_length=64, unique=True, verbose_name='Token')),
                ('action', models.CharField(choices=[('check', 'Check'), ('apply', 'Apply'), ('rollback', 'Rollback')], db_index=True, max_length=16, verbose_name='Action')),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('checking', 'Checking'), ('downloading', 'Downloading'), ('verifying', 'Verifying'), ('staging', 'Staging'), ('preflight', 'Preflight'), ('backing_up', 'Backing Up'), ('maintenance', 'Maintenance'), ('migrating', 'Migrating'), ('collecting_static', 'Collecting Static'), ('switching', 'Switching'), ('restarting', 'Restarting'), ('verifying_health', 'Verifying Health'), ('completed', 'Completed'), ('failed', 'Failed'), ('rolled_back', 'Rolled Back')], db_index=True, default='queued', max_length=32, verbose_name='Status')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='Active')),
                ('source_version', models.CharField(blank=True, max_length=32, verbose_name='Source Version')),
                ('target_version', models.CharField(blank=True, max_length=32, verbose_name='Target Version')),
                ('requested_by_username', models.CharField(blank=True, max_length=150, verbose_name='Requested By')),
                ('manifest', models.JSONField(blank=True, default=dict, verbose_name='Verified Manifest')),
                ('wheel_url', models.TextField(blank=True, verbose_name='Wheel URL')),
                ('wheel_sha256', models.CharField(blank=True, max_length=64, verbose_name='Wheel SHA256')),
                ('backup_token', models.CharField(blank=True, max_length=64, verbose_name='Backup Token')),
                ('progress_log', models.TextField(blank=True, verbose_name='Progress Log')),
                ('report', models.JSONField(blank=True, default=dict, verbose_name='Report')),
                ('error', models.TextField(blank=True, verbose_name='Error')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('started_at', models.DateTimeField(blank=True, null=True, verbose_name='Started At')),
                ('completed_at', models.DateTimeField(blank=True, null=True, verbose_name='Completed At')),
            ],
            options={
                'verbose_name': 'Dlux Update Run',
                'verbose_name_plural': 'Dlux Update Runs',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['is_active', 'created_at'], name='dlux_update_active_idx')],
            },
        ),
    ]
