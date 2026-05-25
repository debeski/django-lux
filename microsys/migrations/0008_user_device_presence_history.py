from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('microsys', '0007_systemsettings_prevent_multiple_active_sessions'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UserKnownDevice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('device_hash', models.CharField(max_length=64, verbose_name='Device Hash')),
                ('device_label', models.CharField(blank=True, max_length=255, verbose_name='Device Label')),
                ('ip_addresses', models.JSONField(blank=True, default=list, verbose_name='IP Addresses')),
                ('user_agents', models.JSONField(blank=True, default=list, verbose_name='User Agents')),
                ('browser_names', models.JSONField(blank=True, default=list, verbose_name='Browsers')),
                ('os_names', models.JSONField(blank=True, default=list, verbose_name='Operating Systems')),
                ('first_seen_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='First Seen At')),
                ('last_seen_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Last Seen At')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('trusted_device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='known_device_links', to='microsys.trusteddevice', verbose_name='Trusted Device')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='microsys_known_devices', to=settings.AUTH_USER_MODEL, verbose_name='User')),
            ],
            options={
                'verbose_name': 'Known Device',
                'verbose_name_plural': 'Known Devices',
                'ordering': ['-last_seen_at'],
            },
        ),
        migrations.CreateModel(
            name='UserPresenceSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_key_hash', models.CharField(max_length=64, verbose_name='Session Key Hash')),
                ('device_label', models.CharField(blank=True, max_length=255, verbose_name='Device Label')),
                ('ip_addresses', models.JSONField(blank=True, default=list, verbose_name='IP Addresses')),
                ('user_agents', models.JSONField(blank=True, default=list, verbose_name='User Agents')),
                ('browser_names', models.JSONField(blank=True, default=list, verbose_name='Browsers')),
                ('os_names', models.JSONField(blank=True, default=list, verbose_name='Operating Systems')),
                ('first_seen_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='First Seen At')),
                ('last_seen_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Last Seen At')),
                ('estimated_seconds', models.PositiveIntegerField(default=0, verbose_name='Estimated Seconds')),
                ('request_count', models.PositiveIntegerField(default=0, verbose_name='Request Count')),
                ('ended_at', models.DateTimeField(blank=True, null=True, verbose_name='Ended At')),
                ('revoked_at', models.DateTimeField(blank=True, null=True, verbose_name='Revoked At')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('known_device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='presence_sessions', to='microsys.userknowndevice', verbose_name='Known Device')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='microsys_presence_sessions', to=settings.AUTH_USER_MODEL, verbose_name='User')),
            ],
            options={
                'verbose_name': 'Presence Session',
                'verbose_name_plural': 'Presence Sessions',
                'ordering': ['-last_seen_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='userknowndevice',
            constraint=models.UniqueConstraint(fields=('user', 'device_hash'), name='microsys_unique_known_device'),
        ),
        migrations.AddIndex(
            model_name='userknowndevice',
            index=models.Index(fields=['user', '-last_seen_at'], name='microsys_known_device_seen_idx'),
        ),
        migrations.AddConstraint(
            model_name='userpresencesession',
            constraint=models.UniqueConstraint(fields=('user', 'session_key_hash'), name='microsys_unique_presence_session'),
        ),
        migrations.AddIndex(
            model_name='userpresencesession',
            index=models.Index(fields=['user', '-last_seen_at'], name='microsys_presence_seen_idx'),
        ),
        migrations.AddIndex(
            model_name='userpresencesession',
            index=models.Index(fields=['session_key_hash'], name='microsys_presence_session_idx'),
        ),
    ]
