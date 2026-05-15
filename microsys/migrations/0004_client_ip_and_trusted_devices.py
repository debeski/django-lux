from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('microsys', '0003_public_root_split'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='client_ip_config',
            field=models.JSONField(blank=True, default=dict, verbose_name='Client IP Configuration'),
        ),
        migrations.CreateModel(
            name='TrustedDevice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token_hash', models.CharField(max_length=64, unique=True, verbose_name='Token Hash')),
                ('session_key', models.CharField(blank=True, max_length=64, verbose_name='Session Key')),
                ('device_label', models.CharField(blank=True, max_length=255, verbose_name='Device Label')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='IP Address')),
                ('user_agent', models.TextField(blank=True, verbose_name='User Agent')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('last_used_at', models.DateTimeField(auto_now=True, verbose_name='Last Used At')),
                ('trusted_until', models.DateTimeField(verbose_name='Trusted Until')),
                ('revoked_at', models.DateTimeField(blank=True, null=True, verbose_name='Revoked At')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='trusted_devices', to=settings.AUTH_USER_MODEL, verbose_name='User')),
            ],
            options={
                'verbose_name': 'Trusted Device',
                'verbose_name_plural': 'Trusted Devices',
                'ordering': ['-last_used_at'],
            },
        ),
    ]
