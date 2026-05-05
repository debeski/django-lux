from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_activity_log_permission(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    UserActivityLog = apps.get_model('microsys', 'UserActivityLog')
    Profile = apps.get_model('microsys', 'Profile')

    activity_type = ContentType.objects.get_for_model(UserActivityLog, for_concrete_model=False)
    profile_type = ContentType.objects.get_for_model(Profile, for_concrete_model=False)
    new_permission, _ = Permission.objects.get_or_create(
        content_type=activity_type,
        codename='view_activitylog',
        defaults={'name': 'View activity log'},
    )

    try:
        old_permission = Permission.objects.get(
            content_type=profile_type,
            codename='view_activitylog',
        )
    except Permission.DoesNotExist:
        return

    for user in old_permission.user_set.all():
        user.user_permissions.add(new_permission)
    for group in old_permission.group_set.all():
        group.permissions.add(new_permission)
    old_permission.delete()


def encrypt_existing_totp_secrets(apps, schema_editor):
    Profile = apps.get_model('microsys', 'Profile')
    from microsys.utils import encrypt_totp_secret, is_encrypted_totp_secret

    for profile in Profile.objects.exclude(totp_secret__isnull=True).exclude(totp_secret='').iterator():
        if is_encrypted_totp_secret(profile.totp_secret):
            continue
        profile.totp_secret = encrypt_totp_secret(profile.totp_secret)
        profile.save(update_fields=['totp_secret'])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('microsys', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='public_registration_enabled',
            field=models.BooleanField(default=False, verbose_name='Enable Public Registration'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='registration_activation_mode',
            field=models.CharField(
                choices=[
                    ('auto_login_after_verify', 'Auto-login after verification'),
                    ('verified_pending_approval', 'Verified pending approval'),
                ],
                default='auto_login_after_verify',
                max_length=32,
                verbose_name='Registration Activation Mode',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='registration_throttle_enabled',
            field=models.BooleanField(default=True, verbose_name='Enable Registration Throttles'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='email_config',
            field=models.JSONField(blank=True, default=dict, verbose_name='Email Configuration'),
        ),
        migrations.AddField(
            model_name='profile',
            name='email_verified_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Email Verified At'),
        ),
        migrations.AlterField(
            model_name='profile',
            name='totp_secret',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='TOTP Secret'),
        ),
        migrations.RunPython(encrypt_existing_totp_secrets, migrations.RunPython.noop),
        migrations.CreateModel(
            name='PublicRegistration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(db_index=True, max_length=254, verbose_name='Email')),
                ('status', models.CharField(
                    choices=[
                        ('pending_email', 'Pending email verification'),
                        ('pending_approval', 'Pending approval'),
                        ('activated', 'Activated'),
                        ('rejected', 'Rejected'),
                        ('expired', 'Expired'),
                    ],
                    db_index=True,
                    default='pending_email',
                    max_length=32,
                    verbose_name='Status',
                )),
                ('activation_mode', models.CharField(
                    choices=[
                        ('auto_login_after_verify', 'Auto-login after verification'),
                        ('verified_pending_approval', 'Verified pending approval'),
                    ],
                    default='auto_login_after_verify',
                    max_length=32,
                    verbose_name='Activation Mode',
                )),
                ('token_hash', models.CharField(blank=True, max_length=64, verbose_name='Verification Token Hash')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='IP Address')),
                ('user_agent', models.TextField(blank=True, verbose_name='User Agent')),
                ('expires_at', models.DateTimeField(verbose_name='Expires At')),
                ('verified_at', models.DateTimeField(blank=True, null=True, verbose_name='Verified At')),
                ('approved_at', models.DateTimeField(blank=True, null=True, verbose_name='Approved At')),
                ('rejected_at', models.DateTimeField(blank=True, null=True, verbose_name='Rejected At')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('approved_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='approved_public_registrations',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Approved By',
                )),
                ('rejected_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='rejected_public_registrations',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Rejected By',
                )),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='public_registration',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='User',
                )),
            ],
            options={
                'verbose_name': 'Public Registration',
                'verbose_name_plural': 'Public Registrations',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AlterModelOptions(
            name='profile',
            options={
                'default_permissions': (),
                'permissions': [
                    ('manage_staff', 'Can manage staff'),
                    ('manage_scopes', 'Can manage scopes and all users'),
                ],
                'verbose_name': 'Profile',
                'verbose_name_plural': 'Profiles',
            },
        ),
        migrations.AlterModelOptions(
            name='useractivitylog',
            options={
                'default_permissions': (),
                'permissions': [('view_activitylog', 'View activity log')],
                'verbose_name': 'Activity Log',
                'verbose_name_plural': 'Activity Logs',
            },
        ),
        migrations.RunPython(migrate_activity_log_permission, migrations.RunPython.noop),
    ]
