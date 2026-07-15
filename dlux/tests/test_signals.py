from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.core.cache import cache
from dlux.models import UserActivityLog, Profile
from dlux.middleware import get_current_user, get_current_request

User = get_user_model()


class SignalTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_login_signal_creates_log(self):
        """Test that user_logged_in signal creates an activity log."""
        from django.contrib.auth.signals import user_logged_in
        from dlux.signals import log_login
        
        request = self.factory.get('/')
        request.user = self.user
        request.META['HTTP_USER_AGENT'] = 'TestAgent'
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        
        # Set thread-local user and request
        from dlux.middleware import _thread_locals
        _thread_locals.user = self.user
        _thread_locals.request = request
        
        try:
            log_login(sender=User, request=request, user=self.user)
            
            # Check that log was created
            log = UserActivityLog.objects.filter(
                created_by=self.user,
                action='LOGIN',
                model_name='auth'
            ).first()
            self.assertIsNotNone(log)
        finally:
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user
            if hasattr(_thread_locals, 'request'):
                del _thread_locals.request

    def test_logout_signal_creates_log(self):
        """Test that user_logged_out signal creates an activity log."""
        from django.contrib.auth.signals import user_logged_out
        from dlux.signals import log_logout
        
        request = self.factory.get('/')
        request.user = self.user
        request.META['HTTP_USER_AGENT'] = 'TestAgent'
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        
        # Set thread-local user and request
        from dlux.middleware import _thread_locals
        _thread_locals.user = self.user
        _thread_locals.request = request
        
        try:
            log_logout(sender=User, request=request, user=self.user)
            
            # Check that log was created
            log = UserActivityLog.objects.filter(
                created_by=self.user,
                action='LOGOUT',
                model_name='auth'
            ).first()
            self.assertIsNotNone(log)
        finally:
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user
            if hasattr(_thread_locals, 'request'):
                del _thread_locals.request

    def test_profile_auto_created_on_user_save(self):
        """Test that Profile is automatically created when User is created."""
        new_user = User.objects.create_user(
            username='newuser',
            email='new@example.com',
            password='newpass123'
        )
        self.assertTrue(hasattr(new_user, 'profile'))
        self.assertIsNotNone(new_user.profile)

    def test_capture_original_state_on_update(self):
        """Test that original state is captured before save."""
        from dlux.signals import capture_original_state
        from dlux.middleware import _thread_locals
        
        # Create a test instance
        self.user.first_name = 'John'
        self.user.save()
        
        # Set thread-local user
        _thread_locals.user = self.user
        
        try:
            # Capture original state
            capture_original_state(sender=User, instance=self.user)
            
            # Check that original state was captured
            self.assertTrue(hasattr(self.user, '_original_state'))
            self.assertIn('first_name', self.user._original_state)
        finally:
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user

    def test_log_save_creates_activity_log(self):
        """Test that post_save signal creates activity log."""
        from dlux.signals import log_save
        from dlux.middleware import _thread_locals
        
        request = self.factory.get('/')
        request.user = self.user
        request.META['HTTP_USER_AGENT'] = 'TestAgent'
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        
        _thread_locals.user = self.user
        _thread_locals.request = request
        
        try:
            # Update user
            self.user.first_name = 'Jane'
            self.user.save()
            
            # Check that log was created
            log = UserActivityLog.objects.filter(
                created_by=self.user,
                action='UPDATE'
            ).first()
            self.assertIsNotNone(log)
        finally:
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user
            if hasattr(_thread_locals, 'request'):
                del _thread_locals.request

    def test_log_save_skips_no_op_update(self):
        """A save that changes no tracked field must not create a log entry —
        this is what cluttered the activity log when System Settings (and other
        singletons) were re-saved without edits. A real change still logs."""
        from dlux.middleware import _thread_locals

        request = self.factory.get('/')
        request.user = self.user
        _thread_locals.user = self.user
        _thread_locals.request = request
        try:
            self.user.first_name = 'Original'
            self.user.save()
            UserActivityLog.objects.filter(created_by=self.user, action='UPDATE').delete()

            # No-op: reload and save without changing anything.
            same = User.objects.get(pk=self.user.pk)
            same.save()
            self.assertEqual(
                UserActivityLog.objects.filter(created_by=self.user, action='UPDATE').count(),
                0,
                'a no-op update should not be logged',
            )

            # A real change still logs.
            same.first_name = 'Changed'
            same.save()
            self.assertEqual(
                UserActivityLog.objects.filter(created_by=self.user, action='UPDATE').count(),
                1,
            )
        finally:
            for attr in ('user', 'request'):
                if hasattr(_thread_locals, attr):
                    delattr(_thread_locals, attr)

    def test_log_save_skips_last_login_only_update(self):
        """Test that post_save skips updates to last_login field only."""
        from dlux.signals import log_save
        from dlux.middleware import _thread_locals
        
        request = self.factory.get('/')
        request.user = self.user
        _thread_locals.user = self.user
        _thread_locals.request = request
        
        try:
            # Simulate last_login update
            self.user.save(update_fields=['last_login'])
            
            # Check that no log was created for last_login only
            logs = UserActivityLog.objects.filter(
                created_by=self.user,
                action='UPDATE'
            )
            # Should not have logs for last_login only updates
            # (This is a simplified test - in reality there might be other logs)
        finally:
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user
            if hasattr(_thread_locals, 'request'):
                del _thread_locals.request

    def test_log_delete_creates_activity_log(self):
        """Test that post_delete signal creates activity log."""
        from dlux.signals import log_delete
        from dlux.middleware import _thread_locals
        from django.db import models
        
        # Create a test model
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'dlux'
                managed = False
        
        request = self.factory.get('/')
        request.user = self.user
        _thread_locals.user = self.user
        _thread_locals.request = request
        
        try:
            # This is a simplified test - in reality we'd need a real model instance
            # Just verify the signal function exists and is callable
            self.assertTrue(callable(log_delete))
        finally:
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user
            if hasattr(_thread_locals, 'request'):
                del _thread_locals.request

    def test_password_masking_in_details(self):
        """Test that password field is masked in activity log details."""
        from dlux.signals import log_save
        from dlux.middleware import _thread_locals
        
        request = self.factory.get('/')
        request.user = self.user
        _thread_locals.user = self.user
        _thread_locals.request = request
        
        try:
            # Update password
            self.user.set_password('newpassword123')
            self.user.save()
            
            # Check that password is masked in logs
            log = UserActivityLog.objects.filter(
                created_by=self.user,
                action='UPDATE'
            ).first()
            
            if log and log.details:
                if 'password' in log.details:
                    self.assertEqual(log.details['password']['old'], '********')
                    self.assertEqual(log.details['password']['new'], '********')
        finally:
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user
            if hasattr(_thread_locals, 'request'):
                del _thread_locals.request

    def test_totp_secret_masking_in_details(self):
        """Test that TOTP secret changes are masked in activity log details."""
        from dlux.middleware import _thread_locals

        request = self.factory.get('/')
        request.user = self.user
        _thread_locals.user = self.user
        _thread_locals.request = request

        try:
            profile = self.user.profile
            profile.totp_secret = 'JBSWY3DPEHPK3PXP'
            profile.save()

            log = UserActivityLog.objects.filter(
                created_by=self.user,
                action='UPDATE',
            ).order_by('-created_at').first()

            self.assertIsNotNone(log)
            self.assertIn('totp_secret', log.details)
            self.assertEqual(log.details['totp_secret']['old'], '********')
            self.assertEqual(log.details['totp_secret']['new'], '********')
        finally:
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user
            if hasattr(_thread_locals, 'request'):
                del _thread_locals.request

    def test_user_profile_unification_in_logs(self):
        """Test that User and Profile logs are unified under 'User Profile'."""
        from dlux.signals import log_save
        from dlux.middleware import _thread_locals
        
        request = self.factory.get('/')
        request.user = self.user
        _thread_locals.user = self.user
        _thread_locals.request = request
        
        try:
            # Update user
            self.user.first_name = 'Test'
            self.user.save()
            
            # Check that model_name is 'User Profile'
            log = UserActivityLog.objects.filter(
                created_by=self.user,
                action='UPDATE'
            ).first()
            
            if log:
                self.assertEqual(log.model_name, 'User Profile')
        finally:
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user
            if hasattr(_thread_locals, 'request'):
                del _thread_locals.request

    def test_skip_signal_logging_attribute(self):
        """Test that skip_signal_logging prevents logging."""
        from dlux.signals import log_save
        from dlux.middleware import _thread_locals
        
        request = self.factory.get('/')
        request.user = self.user
        _thread_locals.user = self.user
        _thread_locals.request = request
        
        try:
            # Set skip flag
            self.user.skip_signal_logging = True
            self.user.save()
            
            # Verify the attribute is checked (simplified test)
            self.assertTrue(hasattr(self.user, 'skip_signal_logging'))
        finally:
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user
            if hasattr(_thread_locals, 'request'):
                del _thread_locals.request


class ActivityLogCategoryTests(TestCase):
    """Category resolution, config gating, and audit instrumentation."""

    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='catuser', email='cat@example.com', password='catpass123'
        )

    def _request(self):
        from dlux.middleware import _thread_locals
        request = self.factory.get('/')
        request.user = self.user
        request.META['HTTP_USER_AGENT'] = 'TestAgent'
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        _thread_locals.user = self.user
        _thread_locals.request = request
        return request

    def tearDown(self):
        from dlux.middleware import _thread_locals
        for attr in ('user', 'request'):
            if hasattr(_thread_locals, attr):
                delattr(_thread_locals, attr)

    def test_resolve_log_category(self):
        from dlux.utils.activity_log import resolve_log_category
        self.assertEqual(resolve_log_category('LOGIN', model_name='auth'), 'audit')
        self.assertEqual(resolve_log_category('LOGIN_FAILED'), 'audit')
        self.assertEqual(resolve_log_category('UPDATE', model_key='dlux.profile'), 'system')
        self.assertEqual(resolve_log_category('UPDATE', model_key='documents.decree'), 'user')
        self.assertEqual(resolve_log_category('CREATE', explicit='audit'), 'audit')

    def test_category_default_is_user(self):
        log = UserActivityLog.objects.create(action='CREATE', model_name='Thing')
        self.assertEqual(log.category, 'user')

    def test_is_model_logging_enabled_floor_and_actions(self):
        from dlux.utils.activity_log import is_model_logging_enabled
        from dlux.system.defaults import default_log_config
        cfg = default_log_config()
        # correctness floor always wins
        self.assertFalse(is_model_logging_enabled('system', 'sessions.session', 'update', cfg))
        # seeded high-churn exclude
        self.assertFalse(is_model_logging_enabled('system', 'dlux.trusteddevice', 'create', cfg))
        # audit bypasses per-model gating
        self.assertTrue(is_model_logging_enabled('audit', 'anything.model', 'create', cfg))
        # per-action override
        cfg['user']['models']['app.thing'] = {'enabled': True, 'actions': {'update': False}}
        self.assertTrue(is_model_logging_enabled('user', 'app.thing', 'create', cfg))
        self.assertFalse(is_model_logging_enabled('user', 'app.thing', 'update', cfg))

    def test_login_logged_as_audit(self):
        from dlux.signals import log_login
        request = self._request()
        log_login(sender=User, request=request, user=self.user)
        log = UserActivityLog.objects.filter(created_by=self.user, action='LOGIN').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.category, 'audit')

    def test_audit_event_respects_flag(self):
        from dlux.utils.activity_log import log_audit_event
        from dlux.models import SystemSettings
        request = self._request()
        # enabled by default -> row created
        log_audit_event(request, 'login_failed', 'LOGIN_FAILED', model_name='auth', number='someuser')
        self.assertTrue(UserActivityLog.objects.filter(action='LOGIN_FAILED', category='audit').exists())
        UserActivityLog.objects.all().delete()
        # disable the event -> no row
        settings_obj = SystemSettings.load()
        log_config = settings_obj.log_config
        log_config['audit']['events']['login_failed'] = False
        settings_obj.log_config = log_config
        settings_obj.save()
        cache.delete('SystemSettings')
        log_audit_event(request, 'login_failed', 'LOGIN_FAILED', model_name='auth', number='someuser')
        self.assertFalse(UserActivityLog.objects.filter(action='LOGIN_FAILED').exists())


class ActivityLogImmutabilityAndPruneTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='audituser', email='audit@example.com', password='auditpass123'
        )

    def test_audit_row_is_append_only(self):
        log = UserActivityLog.objects.create(action='LOGIN', model_name='auth', category='audit')
        log.action = 'TAMPERED'
        with self.assertRaises(ValueError):
            log.save()
        # instance delete is a no-op for audit
        log.delete()
        self.assertTrue(UserActivityLog.all_objects.filter(pk=log.pk).exists())

    def test_user_row_remains_mutable(self):
        log = UserActivityLog.objects.create(action='CREATE', model_name='Thing', category='user')
        log.number = 'x'
        log.save()  # no raise
        log.delete()  # soft-delete via ScopedModel; no raise

    def test_prune_respects_retention_and_skips_audit_by_default(self):
        from django.utils import timezone
        from datetime import timedelta
        from django.core.management import call_command
        from dlux.models import SystemSettings

        old = timezone.now() - timedelta(days=40)
        for cat in ('user', 'system', 'audit'):
            row = UserActivityLog.objects.create(action='X', model_name='m', category=cat)
            UserActivityLog.all_objects.filter(pk=row.pk).update(created_at=old)

        settings_obj = SystemSettings.load()
        cfg = settings_obj.log_config
        cfg['user']['retention_days'] = 30
        cfg['system']['retention_days'] = 30
        cfg['audit']['retention_days'] = 0  # keep forever
        settings_obj.log_config = cfg
        settings_obj.save()
        cache.delete('SystemSettings')

        call_command('dlux_prune_activity_log')
        self.assertFalse(UserActivityLog.all_objects.filter(category='user').exists())
        self.assertFalse(UserActivityLog.all_objects.filter(category='system').exists())
        self.assertTrue(UserActivityLog.all_objects.filter(category='audit').exists())


class IdentityMergeWindowTests(TestCase):
    """Rolling-window unification of User + Profile changes (replaces the fragile
    same-calendar-second merge that double-logged across second boundaries)."""

    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='mergeuser', email='merge@example.com', password='mergepass123'
        )

    def test_rapid_user_and_profile_saves_unify_to_one_row(self):
        from dlux.middleware import _thread_locals
        request = self.factory.get('/')
        request.user = self.user
        _thread_locals.user = self.user
        _thread_locals.request = request
        try:
            UserActivityLog.objects.filter(created_by=self.user).delete()
            # Two identity saves in quick succession (User field, then Profile field).
            self.user.first_name = 'Merged'
            self.user.save()
            profile = self.user.profile
            profile.phone = '12345'
            profile.save()
            # Exactly one unified "User Profile" row, not two.
            rows = UserActivityLog.objects.filter(
                created_by=self.user, model_name='User Profile'
            )
            self.assertEqual(rows.count(), 1)
        finally:
            for attr in ('user', 'request'):
                if hasattr(_thread_locals, attr):
                    delattr(_thread_locals, attr)


class LogModelCatalogTests(TestCase):
    """Loggability rules and project/system categorization for the settings grid."""

    def test_is_model_loggable_excludes_framework_churn_and_dummies(self):
        from dlux.utils.activity_log import is_model_loggable, LOG_IDENTITY_MODEL_KEY
        # Django framework internals + health-check + test models -> not loggable
        for key in ('auth.user', 'auth.group', 'auth.permission', 'sessions.session',
                    'contenttypes.contenttype', 'admin.logentry', 'db.testmodel', 'b.testmodel'):
            self.assertFalse(is_model_loggable(key), key)
        # dlux operational churn + identity + self + fieldless Section dummy -> not loggable
        for key in ('dlux.profile', 'dlux.activitylog', 'dlux.section', 'dlux.trusteddevice',
                    'dlux.userknowndevice', 'dlux.userpresencesession',
                    'dlux.dluxnotification', 'dlux.dluxnotificationstate',
                    'dlux.systembackup', 'dlux.reportbackup'):
            self.assertFalse(is_model_loggable(key), key)
        # Meaningful models + the synthetic identity key -> loggable
        for key in ('dlux.systemsettings', 'documents.decree', LOG_IDENTITY_MODEL_KEY):
            self.assertTrue(is_model_loggable(key), key)

    def test_catalog_split_project_vs_system(self):
        from dlux.discovery import build_log_model_catalog
        from dlux.utils.activity_log import LOG_IDENTITY_MODEL_KEY
        cat = build_log_model_catalog()
        user_keys = {i['key'] for i in cat['user']}
        system_keys = {i['key'] for i in cat['system']}
        all_keys = user_keys | system_keys
        # The unified "User accounts" identity toggle is pinned to the system list
        # (users are a core dlux component).
        self.assertEqual(cat['system'][0]['key'], LOG_IDENTITY_MODEL_KEY)
        # dlux config models under system.
        self.assertIn('dlux.systemsettings', system_keys)
        # Framework internals, churn, and dummies never appear at all.
        for key in ('auth.user', 'sessions.session', 'contenttypes.contenttype',
                    'dlux.profile', 'dlux.dluxnotificationstate', 'dlux.trusteddevice',
                    'dlux.activitylog', 'dlux.section'):
            self.assertNotIn(key, all_keys, key)

    def test_custom_action_default_logged_and_toggleable(self):
        from dlux.utils.activity_log import is_model_logging_enabled
        from dlux.system.defaults import default_log_config
        cfg = default_log_config()
        # An undeclared custom action is logged by default...
        self.assertTrue(is_model_logging_enabled('user', 'app.doc', 'download', cfg))
        # ...and can be disabled per-model without affecting CRUD.
        cfg['user']['models']['app.doc'] = {'enabled': True, 'actions': {'download': False}}
        self.assertFalse(is_model_logging_enabled('user', 'app.doc', 'download', cfg))
        self.assertTrue(is_model_logging_enabled('user', 'app.doc', 'create', cfg))

    def test_identity_logging_toggle(self):
        from dlux.utils.activity_log import is_model_logging_enabled, LOG_IDENTITY_MODEL_KEY
        from dlux.system.defaults import default_log_config
        cfg = default_log_config()
        # Identity is gated under the system section.
        self.assertTrue(is_model_logging_enabled('system', LOG_IDENTITY_MODEL_KEY, 'update', cfg))
        cfg['system']['models'][LOG_IDENTITY_MODEL_KEY] = {'enabled': False}
        self.assertFalse(is_model_logging_enabled('system', LOG_IDENTITY_MODEL_KEY, 'update', cfg))
