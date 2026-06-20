import django.db.models.deletion
import dlux.models
from django.conf import settings
from django.db import migrations, models


REGISTRATION_ACTIVATION_AUTO_LOGIN = 'auto_login_after_verify'
REGISTRATION_ACTIVATION_PENDING_APPROVAL = 'verified_pending_approval'
TABLE_DENSITY_VALUES = {'balanced', 'dense', 'roomy'}


def _dict(value):
    return dict(value) if isinstance(value, dict) else {}


def _list(value):
    return list(value) if isinstance(value, (list, tuple, set)) else []


def forwards(apps, schema_editor):
    """Move released flat SystemSettings columns into grouped JSON config fields."""
    SystemSettings = apps.get_model('dlux', 'SystemSettings')
    for obj in SystemSettings.objects.all():
        activation_mode = getattr(obj, 'registration_activation_mode', REGISTRATION_ACTIVATION_AUTO_LOGIN)
        if activation_mode not in {REGISTRATION_ACTIVATION_AUTO_LOGIN, REGISTRATION_ACTIVATION_PENDING_APPROVAL}:
            activation_mode = REGISTRATION_ACTIVATION_AUTO_LOGIN

        table_density = getattr(obj, 'default_table_density', 'balanced')
        if table_density not in TABLE_DENSITY_VALUES:
            table_density = 'balanced'

        obj.auth_config = {
            'email_2fa': bool(getattr(obj, 'email_2fa', False)),
            'prevent_multiple_active_sessions': bool(getattr(obj, 'prevent_multiple_active_sessions', False)),
            'login_lockout_enabled': True,
        }
        obj.registration_config = {
            'public_registration_enabled': bool(getattr(obj, 'public_registration_enabled', False)),
            'registration_activation_mode': activation_mode,
            'registration_throttle_enabled': bool(getattr(obj, 'registration_throttle_enabled', True)),
        }
        obj.public_root_config = {
            'public_root': bool(getattr(obj, 'public_root', False)),
            'public_root_split_enabled': bool(getattr(obj, 'public_root_split_enabled', False)),
            'public_root_url': getattr(obj, 'public_root_url', '') or '',
        }
        obj.layout_config = {
            'default_table_density': table_density,
        }
        obj.language_config = {
            'languages': _dict(getattr(obj, 'languages', {})),
            'translations_override': _dict(getattr(obj, 'translations_override', {})),
            'allow_user_language_override': bool(getattr(obj, 'allow_user_language_override', True)),
        }
        obj.theme_config = {
            'allowed_themes': _list(getattr(obj, 'allowed_themes', [])),
            'allow_user_theme_override': bool(getattr(obj, 'allow_user_theme_override', True)),
        }
        obj.typography_config = {
            'allowed_fonts': _list(getattr(obj, 'allowed_fonts', [])),
            'default_fonts': _dict(getattr(obj, 'default_fonts', {})),
            'allow_user_font_override': bool(getattr(obj, 'allow_user_font_override', True)),
        }
        obj.extra_config = {}
        obj.save(update_fields=[
            'auth_config',
            'registration_config',
            'public_root_config',
            'layout_config',
            'language_config',
            'theme_config',
            'typography_config',
            'extra_config',
        ])


def backwards(apps, schema_editor):
    """Restore legacy flat SystemSettings columns from grouped JSON config fields."""
    SystemSettings = apps.get_model('dlux', 'SystemSettings')
    for obj in SystemSettings.objects.all():
        auth = _dict(getattr(obj, 'auth_config', {}))
        registration = _dict(getattr(obj, 'registration_config', {}))
        public_root = _dict(getattr(obj, 'public_root_config', {}))
        layout = _dict(getattr(obj, 'layout_config', {}))
        language = _dict(getattr(obj, 'language_config', {}))
        theme = _dict(getattr(obj, 'theme_config', {}))
        typography = _dict(getattr(obj, 'typography_config', {}))

        activation_mode = registration.get('registration_activation_mode') or REGISTRATION_ACTIVATION_AUTO_LOGIN
        if activation_mode not in {REGISTRATION_ACTIVATION_AUTO_LOGIN, REGISTRATION_ACTIVATION_PENDING_APPROVAL}:
            activation_mode = REGISTRATION_ACTIVATION_AUTO_LOGIN

        table_density = layout.get('default_table_density') or 'balanced'
        if table_density not in TABLE_DENSITY_VALUES:
            table_density = 'balanced'

        obj.email_2fa = bool(auth.get('email_2fa', False))
        obj.prevent_multiple_active_sessions = bool(auth.get('prevent_multiple_active_sessions', False))
        obj.public_registration_enabled = bool(registration.get('public_registration_enabled', False))
        obj.registration_activation_mode = activation_mode
        obj.registration_throttle_enabled = bool(registration.get('registration_throttle_enabled', True))
        obj.public_root = bool(public_root.get('public_root', False))
        obj.public_root_split_enabled = bool(public_root.get('public_root_split_enabled', False))
        obj.public_root_url = public_root.get('public_root_url') or ''
        obj.default_table_density = table_density
        obj.languages = _dict(language.get('languages'))
        obj.translations_override = _dict(language.get('translations_override'))
        obj.allow_user_language_override = bool(language.get('allow_user_language_override', True))
        obj.allowed_themes = _list(theme.get('allowed_themes'))
        obj.allow_user_theme_override = bool(theme.get('allow_user_theme_override', True))
        obj.allowed_fonts = _list(typography.get('allowed_fonts'))
        obj.default_fonts = _dict(typography.get('default_fonts'))
        obj.allow_user_font_override = bool(typography.get('allow_user_font_override', True))
        obj.save(update_fields=[
            'email_2fa',
            'prevent_multiple_active_sessions',
            'public_registration_enabled',
            'registration_activation_mode',
            'registration_throttle_enabled',
            'public_root',
            'public_root_split_enabled',
            'public_root_url',
            'default_table_density',
            'languages',
            'translations_override',
            'allow_user_language_override',
            'allowed_themes',
            'allow_user_theme_override',
            'allowed_fonts',
            'default_fonts',
            'allow_user_font_override',
        ])


def backfill_activity_category(apps, schema_editor):
    """Classify existing activity-log rows into user/system/audit using only data
    available on the row (model_key is NULL for legacy/auth rows, so lean on
    action/model_name). Order: audit -> system -> user (AddField default)."""
    ActivityLog = apps.get_model('dlux', 'ActivityLog')
    AUDIT_ACTIONS = {
        'LOGIN', 'LOGOUT', 'LOGIN_FAILED', 'LOCKOUT',
        '2FA_ENABLE', '2FA_DISABLE', '2FA_FAILED',
        'PASSWORD_CHANGE', 'PASSWORD_RESET', 'SESSION_REVOKE',
        'TRUSTED_DEVICE', 'TRUSTED_DEVICE_REVOKE', 'PERMISSION_DENIED',
        'REGISTER_VERIFY', 'APPROVE', 'REJECT',
    }
    SYSTEM_NAMES = {'session', 'Session', 'Dlux System Backup', 'Dlux Reports Backup'}
    ActivityLog.objects.filter(action__in=AUDIT_ACTIONS).update(category='audit')
    ActivityLog.objects.filter(category='user', model_key__istartswith='dlux.').update(category='system')
    ActivityLog.objects.filter(
        category='user', model_key__isnull=True, model_name__in=SYSTEM_NAMES,
    ).update(category='system')


class Migration(migrations.Migration):

    dependencies = [
        ('dlux', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='systemsettings',
            name='email_config',
            field=models.JSONField(
                blank=True,
                default=dlux.models.default_email_config,
                verbose_name='Email Configuration',
            ),
        ),
        migrations.AlterField(
            model_name='systemsettings',
            name='client_ip_config',
            field=models.JSONField(
                blank=True,
                default=dlux.models.default_client_ip_config,
                verbose_name='Client IP Configuration',
            ),
        ),
        migrations.AlterField(
            model_name='systemsettings',
            name='login_config',
            field=models.JSONField(
                blank=True,
                default=dlux.models.default_login_config,
                verbose_name='Login Page Configuration',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='auth_config',
            field=models.JSONField(
                blank=True,
                default=dlux.models.default_auth_config,
                verbose_name='Authentication Configuration',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='registration_config',
            field=models.JSONField(
                blank=True,
                default=dlux.models.default_registration_config,
                verbose_name='Registration Configuration',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='public_root_config',
            field=models.JSONField(
                blank=True,
                default=dlux.models.default_public_root_config,
                verbose_name='Public Root Configuration',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='notification_config',
            field=models.JSONField(
                blank=True,
                default=dlux.models.default_notification_config,
                verbose_name='Notification Configuration',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='layout_config',
            field=models.JSONField(
                blank=True,
                default=dlux.models.default_layout_config,
                verbose_name='Layout Configuration',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='language_config',
            field=models.JSONField(
                blank=True,
                default=dlux.models.default_language_config,
                verbose_name='Language Configuration',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='theme_config',
            field=models.JSONField(
                blank=True,
                default=dlux.models.default_theme_config,
                verbose_name='Theme Configuration',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='typography_config',
            field=models.JSONField(
                blank=True,
                default=dlux.models.default_typography_config,
                verbose_name='Typography Configuration',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='extra_config',
            field=models.JSONField(
                blank=True,
                default=dlux.models.default_extra_config,
                verbose_name='Extra Configuration',
            ),
        ),
        migrations.AddField(
            model_name='userpresencesession',
            name='session_key',
            field=models.CharField(blank=True, max_length=64, verbose_name='Session Key'),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name='systemsettings',
            name='email_2fa',
        ),
        migrations.RemoveField(
            model_name='systemsettings',
            name='prevent_multiple_active_sessions',
        ),
        migrations.RemoveField(
            model_name='systemsettings',
            name='public_root',
        ),
        migrations.RemoveField(
            model_name='systemsettings',
            name='public_root_split_enabled',
        ),
        migrations.RemoveField(
            model_name='systemsettings',
            name='public_root_url',
        ),
        migrations.RemoveField(
            model_name='systemsettings',
            name='public_registration_enabled',
        ),
        migrations.RemoveField(
            model_name='systemsettings',
            name='registration_activation_mode',
        ),
        migrations.RemoveField(
            model_name='systemsettings',
            name='registration_throttle_enabled',
        ),
        migrations.RemoveField(
            model_name='systemsettings',
            name='languages',
        ),
        migrations.RemoveField(
            model_name='systemsettings',
            name='translations_override',
        ),
        migrations.RemoveField(
            model_name='systemsettings',
            name='default_table_density',
        ),
        migrations.RemoveField(
            model_name='systemsettings',
            name='allowed_themes',
        ),
        migrations.RemoveField(
            model_name='systemsettings',
            name='allow_user_theme_override',
        ),
        migrations.RemoveField(
            model_name='systemsettings',
            name='allowed_fonts',
        ),
        migrations.RemoveField(
            model_name='systemsettings',
            name='default_fonts',
        ),
        migrations.RemoveField(
            model_name='systemsettings',
            name='allow_user_font_override',
        ),
        migrations.RemoveField(
            model_name='systemsettings',
            name='allow_user_language_override',
        ),
        migrations.CreateModel(
            name='DluxNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, editable=False, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, editable=False, verbose_name='Updated At')),
                ('deleted_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='Deleted At')),
                ('title', models.CharField(blank=True, max_length=180, verbose_name='Title')),
                ('message', models.TextField(verbose_name='Message')),
                ('level', models.CharField(choices=[('info', 'Info'), ('success', 'Success'), ('warning', 'Warning'), ('error', 'Error')], db_index=True, default='info', max_length=16, verbose_name='Level')),
                ('category', models.CharField(db_index=True, default='general', max_length=64, verbose_name='Category')),
                ('source', models.CharField(db_index=True, default='manual', max_length=64, verbose_name='Source')),
                ('action', models.CharField(blank=True, db_index=True, max_length=64, verbose_name='Action')),
                ('source_model', models.CharField(blank=True, max_length=120, verbose_name='Source Model')),
                ('source_model_key', models.CharField(blank=True, db_index=True, max_length=120, verbose_name='Source Model Key')),
                ('source_object_id', models.CharField(blank=True, db_index=True, max_length=64, verbose_name='Source Object ID')),
                ('source_label', models.CharField(blank=True, max_length=255, verbose_name='Source Label')),
                ('target_url', models.CharField(blank=True, max_length=512, verbose_name='Target URL')),
                ('request_path', models.CharField(blank=True, max_length=512, verbose_name='Request Path')),
                ('audience_type', models.CharField(choices=[('actor', 'Actor'), ('watchers', 'Watchers'), ('users', 'Specific Users'), ('broadcast', 'Broadcast')], default='actor', max_length=24, verbose_name='Audience Type')),
                ('metadata', models.JSONField(blank=True, default=dict, verbose_name='Metadata')),
                ('expires_at', models.DateTimeField(blank=True, db_index=True, null=True, verbose_name='Expires At')),
                ('created_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Created By')),
                ('deleted_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Deleted By')),
                ('scope', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='dlux.scope', verbose_name='Scope')),
                ('updated_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Updated By')),
            ],
            options={
                'verbose_name': 'Dlux Notification',
                'verbose_name_plural': 'Dlux Notifications',
                'default_permissions': (),
                'permissions': [('view_notification', 'View notifications'), ('manage_notifications', 'Manage notification rules and watches')],
                'indexes': [
                    models.Index(fields=['created_at'], name='dlux_notif_created_idx'),
                    models.Index(fields=['scope', 'created_at'], name='dlux_notif_scope_created_idx'),
                    models.Index(fields=['level', 'created_at'], name='dlux_notif_level_created_idx'),
                    models.Index(fields=['source_model_key', 'created_at'], name='dlux_notif_model_created_idx'),
                    models.Index(fields=['action', 'created_at'], name='dlux_notif_action_created_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='DluxNotificationRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, editable=False, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, editable=False, verbose_name='Updated At')),
                ('deleted_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='Deleted At')),
                ('name', models.CharField(max_length=120, verbose_name='Name')),
                ('enabled', models.BooleanField(db_index=True, default=True, verbose_name='Enabled')),
                ('priority', models.IntegerField(db_index=True, default=100, verbose_name='Priority')),
                ('match_config', models.JSONField(blank=True, default=dict, verbose_name='Match Configuration')),
                ('delivery_config', models.JSONField(blank=True, default=dict, verbose_name='Delivery Configuration')),
                ('stop_processing', models.BooleanField(default=False, verbose_name='Stop Processing')),
                ('created_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Created By')),
                ('deleted_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Deleted By')),
                ('scope', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='dlux.scope', verbose_name='Scope')),
                ('updated_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Updated By')),
            ],
            options={
                'verbose_name': 'Dlux Notification Rule',
                'verbose_name_plural': 'Dlux Notification Rules',
                'ordering': ['priority', 'name'],
                'default_permissions': (),
                'indexes': [
                    models.Index(fields=['enabled', 'priority'], name='dlux_notif_rule_enabled_idx'),
                    models.Index(fields=['scope', 'priority'], name='dlux_notif_rule_scope_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='DluxNotificationWatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, editable=False, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, editable=False, verbose_name='Updated At')),
                ('deleted_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='Deleted At')),
                ('model_key', models.CharField(db_index=True, max_length=120, verbose_name='Model Key')),
                ('enabled', models.BooleanField(db_index=True, default=True, verbose_name='Enabled')),
                ('email_enabled', models.BooleanField(default=False, verbose_name='Email Enabled')),
                ('created_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Created By')),
                ('deleted_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Deleted By')),
                ('scope', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='dlux.scope', verbose_name='Scope')),
                ('updated_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Updated By')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dlux_notification_watches', to=settings.AUTH_USER_MODEL, verbose_name='User')),
            ],
            options={
                'verbose_name': 'Dlux Notification Watch',
                'verbose_name_plural': 'Dlux Notification Watches',
                'default_permissions': (),
                'indexes': [
                    models.Index(fields=['model_key', 'enabled'], name='dlux_nw_model_idx'),
                    models.Index(fields=['scope', 'model_key'], name='dlux_nw_scope_model_idx'),
                ],
                'constraints': [
                    models.UniqueConstraint(fields=('user', 'scope', 'model_key'), name='dlux_nw_user_scope_model'),
                ],
            },
        ),
        migrations.CreateModel(
            name='DluxNotificationState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('read_at', models.DateTimeField(blank=True, db_index=True, null=True, verbose_name='Read At')),
                ('dismissed_at', models.DateTimeField(blank=True, db_index=True, null=True, verbose_name='Dismissed At')),
                ('emailed_at', models.DateTimeField(blank=True, null=True, verbose_name='Emailed At')),
                ('email_status', models.CharField(blank=True, max_length=32, verbose_name='Email Status')),
                ('email_error', models.TextField(blank=True, verbose_name='Email Error')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('notification', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='states', to='dlux.dluxnotification', verbose_name='Notification')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dlux_notification_states', to=settings.AUTH_USER_MODEL, verbose_name='User')),
            ],
            options={
                'verbose_name': 'Dlux Notification State',
                'verbose_name_plural': 'Dlux Notification States',
                'default_permissions': (),
                'indexes': [
                    models.Index(fields=['user', 'read_at'], name='dlux_ns_read_idx'),
                    models.Index(fields=['user', 'dismissed_at'], name='dlux_ns_dismiss_idx'),
                    models.Index(fields=['user', 'created_at'], name='dlux_ns_created_idx'),
                ],
                'constraints': [
                    models.UniqueConstraint(fields=('notification', 'user'), name='dlux_notif_state_user_uniq'),
                ],
            },
        ),
        # ── Activity log: single source of truth (user/system/audit) ──
        migrations.RenameModel(
            old_name='UserActivityLog',
            new_name='ActivityLog',
        ),
        migrations.AddField(
            model_name='activitylog',
            name='category',
            field=models.CharField(
                choices=[('user', 'User'), ('system', 'System'), ('audit', 'Audit')],
                default='user',
                max_length=10,
                verbose_name='Category',
            ),
        ),
        migrations.AddIndex(
            model_name='activitylog',
            index=models.Index(fields=['category', 'created_at'], name='dlux_ual_cat_created_idx'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='log_config',
            field=models.JSONField(
                blank=True,
                default=dlux.models.default_log_config,
                verbose_name='Logging Configuration',
            ),
        ),
        migrations.RunPython(backfill_activity_category, migrations.RunPython.noop),
        # ── Profile page configuration + per-user onboarding flag ──
        migrations.AddField(
            model_name='systemsettings',
            name='profile_config',
            field=models.JSONField(
                blank=True,
                default=dlux.models.default_profile_config,
                verbose_name='Profile Page Configuration',
            ),
        ),
        migrations.AddField(
            model_name='profile',
            name='is_configured',
            field=models.BooleanField(
                default=False,
                verbose_name='Completed Initial User Setup',
            ),
        ),
    ]
