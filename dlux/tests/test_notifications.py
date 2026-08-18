from dlux.tests.harness import setup_test_environment

setup_test_environment()

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from dlux.forms import SystemSettingsForm
from dlux.models import DluxNotification, DluxNotificationRule, DluxNotificationState, SystemSettings
from dlux.notifications import (
    FLASH_SESSION_KEY,
    NotificationLockedError,
    clear_all_notifications,
    dismiss_notification,
    get_flash_notifications,
    get_notification_context,
    mark_notification_read,
    notify,
)


User = get_user_model()


class NotificationPipelineTests(TestCase):
    def setUp(self):
        cache.delete(SystemSettings.__name__)
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='notify-user',
            email='notify@example.com',
            password='testpass123',
        )

    def _request(self, path='/sys/options/'):
        request = self.factory.get(path)
        request.user = self.user
        request.session = SessionStore()
        return request

    def test_notify_success_creates_inbox_state_and_flash(self):
        request = self._request()

        notification = notify.success('Saved.', request=request, action='save')

        self.assertIsNotNone(notification)
        self.assertEqual(notification.level, 'success')
        self.assertEqual(notification.action, 'save')
        self.assertTrue(DluxNotificationState.objects.filter(notification=notification, user=self.user).exists())
        self.assertEqual(request.session[FLASH_SESSION_KEY][0]['message'], 'Saved.')

    def test_flash_queue_drains_once(self):
        request = self._request()
        notify.warning('Check this.', request=request, persist=False)

        first = get_flash_notifications(request)
        second = get_flash_notifications(request)

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]['level'], 'warning')
        self.assertEqual(second, [])

    def test_keyed_notifications_render_in_request_language(self):
        request = self._request()
        notification = notify.success(
            request=request,
            action='password_changed',
            category='security',
            message_key='msg_password_changed',
        )

        self.assertIsNotNone(notification)
        self.assertEqual(notification.message, 'Password changed successfully!')
        self.assertEqual(notification.metadata.get('message_key'), 'msg_password_changed')

        profile = self.user.profile
        profile.preferences = {**(profile.preferences or {}), 'language': 'ar'}
        profile.save(update_fields=['preferences'])
        request.session['lang'] = 'ar'

        flash_items = get_flash_notifications(request)
        drawer_items = get_notification_context(request)['items']

        self.assertEqual(flash_items[0]['message'], 'تم تغيير كلمة المرور بنجاح!')
        self.assertEqual(drawer_items[0]['message'], 'تم تغيير كلمة المرور بنجاح!')

    def test_legacy_translated_notification_text_rerenders_in_request_language(self):
        request = self._request()
        notification = notify.success(
            'Password changed successfully!',
            request=request,
            action='legacy_password_changed_en',
            category='security',
        )

        self.assertIsNotNone(notification)
        self.assertNotIn('message_key', notification.metadata)

        profile = self.user.profile
        profile.preferences = {**(profile.preferences or {}), 'language': 'ar'}
        profile.save(update_fields=['preferences'])
        request.session['lang'] = 'ar'

        flash_items = get_flash_notifications(request)
        drawer_items = get_notification_context(request)['items']

        self.assertEqual(flash_items[0]['message'], 'تم تغيير كلمة المرور بنجاح!')
        self.assertEqual(drawer_items[0]['message'], 'تم تغيير كلمة المرور بنجاح!')

    def test_legacy_arabic_notification_text_rerenders_in_english(self):
        request = self._request()
        notification = notify.error(
            'لا يمكنك حذف حسابك الخاص!',
            request=request,
            action='legacy_delete_self_ar',
            category='users',
        )

        self.assertIsNotNone(notification)
        self.assertNotIn('message_key', notification.metadata)

        request.session['lang'] = 'en'
        drawer_items = get_notification_context(request)['items']

        self.assertEqual(drawer_items[0]['message'], 'You cannot delete your own account!')

    def test_rule_can_make_matching_event_persist_without_flash(self):
        request = self._request()
        DluxNotificationRule.objects.create(
            name='Quiet custom',
            match_config={'action': 'quiet_action'},
            delivery_config={'flash': False, 'persist': True},
            created_by=self.user,
            updated_by=self.user,
        )

        notification = notify('Stored only.', request=request, action='quiet_action')

        self.assertIsNotNone(notification)
        self.assertTrue(DluxNotification.objects.filter(pk=notification.pk).exists())
        self.assertNotIn(FLASH_SESSION_KEY, request.session)

    def test_mark_read_and_dismiss_helpers_only_touch_current_user_state(self):
        request = self._request()
        notification = notify('Read me.', request=request)

        read_state = mark_notification_read(self.user, notification.pk)
        dismissed_state = dismiss_notification(self.user, notification.pk)

        self.assertIsNotNone(read_state.read_at)
        self.assertIsNotNone(dismissed_state.dismissed_at)

    def test_unread_section_counts_group_by_notification_source_model(self):
        request = self._request()
        first_user_notification = notify('First user.', request=request, obj=self.user)
        notify('Second user.', request=request, obj=self.user)
        settings_obj = SystemSettings.load()
        notify('Settings changed.', request=request, obj=settings_obj)
        mark_notification_read(self.user, first_user_notification.pk)

        context = get_notification_context(request)

        self.assertEqual(context['section_counts'], {
            'auth.user': 1,
            'dlux.systemsettings': 1,
        })

        client = Client()
        client.force_login(self.user)
        response = client.get(reverse('notifications_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['section_counts'], context['section_counts'])

    def test_sidebar_section_counts_are_independent_of_drawer_badge_toggle(self):
        request = self._request()
        notify('User changed.', request=request, obj=self.user)
        settings_obj = SystemSettings.load()
        settings_obj.notification_config = {
            'enabled': True,
            'drawer': {
                'enabled': True,
                'badge_enabled': False,
            },
        }
        settings_obj.save()
        cache.delete(SystemSettings.__name__)

        self.assertEqual(get_notification_context(request)['section_counts'], {'auth.user': 1})

    def test_sidebar_section_counts_remain_available_when_drawer_is_disabled(self):
        request = self._request()
        notification = notify('User drawer disabled.', request=request, obj=self.user)
        self.assertIsNotNone(notification)
        self.assertEqual(notification.source_model_key, 'auth.user')
        self.assertTrue(
            DluxNotificationState.objects.filter(notification=notification, user=self.user).exists()
        )
        settings_obj = SystemSettings.load()
        settings_obj.notification_config = {
            'enabled': True,
            'drawer': {
                'enabled': False,
                'badge_enabled': True,
            },
        }
        settings_obj.save()
        cache.delete(SystemSettings.__name__)

        context = get_notification_context(request)

        self.assertFalse(context['enabled'])
        self.assertEqual(context['section_counts'], {'auth.user': 1})

    def test_active_backup_notification_cannot_be_dismissed_or_cleared(self):
        request = self._request()
        notification = notify.info(
            'Backup running.',
            request=request,
            action='backup_progress',
            category='backup',
            metadata={'backup_progress': True, 'locked': True, 'progress': 42},
        )
        mark_notification_read(self.user, notification.pk)

        with self.assertRaises(NotificationLockedError):
            dismiss_notification(self.user, notification.pk)
        self.assertEqual(clear_all_notifications(self.user), 0)

        client = Client()
        client.force_login(self.user)
        response = client.post(reverse('notification_dismiss', args=[notification.pk]))
        self.assertEqual(response.status_code, 409)
        state = DluxNotificationState.objects.get(user=self.user, notification=notification)
        self.assertIsNone(state.dismissed_at)

    def test_clear_all_notifications_api_dismisses_only_read_drawer_states(self):
        request = self._request()
        unread_notification = notify('First.', request=request, action='first')
        read_notification = notify('Second.', request=request, action='second')
        mark_notification_read(self.user, read_notification.pk)

        client = Client()
        client.force_login(self.user)
        response = client.post(reverse('notifications_clear_all'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['updated'], 1)
        unread_state = DluxNotificationState.objects.get(user=self.user, notification=unread_notification)
        read_state = DluxNotificationState.objects.get(user=self.user, notification=read_notification)
        self.assertIsNone(unread_state.dismissed_at)
        self.assertIsNone(unread_state.read_at)
        self.assertIsNotNone(read_state.dismissed_at)
        self.assertIsNotNone(read_state.read_at)

    def test_clear_all_notifications_helper_dismisses_read_without_touching_unread(self):
        request = self._request()
        unread_notification = notify('Clear helper.', request=request, action='clear_helper')
        read_notification = notify('Keep helper.', request=request, action='keep_helper')
        mark_notification_read(self.user, read_notification.pk)

        count = clear_all_notifications(self.user)
        unread_state = DluxNotificationState.objects.get(user=self.user, notification=unread_notification)
        read_state = DluxNotificationState.objects.get(user=self.user, notification=read_notification)

        self.assertEqual(count, 1)
        self.assertIsNone(unread_state.read_at)
        self.assertIsNone(unread_state.dismissed_at)
        self.assertIsNotNone(read_state.read_at)
        self.assertIsNotNone(read_state.dismissed_at)

    def test_master_gate_off_suppresses_emit_flash_and_drawer(self):
        settings_obj = SystemSettings.load()
        settings_obj.notification_config = {'enabled': False}
        settings_obj.save()
        cache.delete(SystemSettings.__name__)

        request = self._request()
        notification = notify.success('Gated.', request=request, action='save')

        self.assertIsNone(notification)
        self.assertFalse(DluxNotificationState.objects.filter(user=self.user).exists())
        self.assertNotIn(FLASH_SESSION_KEY, request.session)
        self.assertEqual(get_flash_notifications(request), [])
        self.assertFalse(get_notification_context(request)['enabled'])


class NotificationSettingsFormTests(TestCase):
    def setUp(self):
        cache.delete(SystemSettings.__name__)

    def test_flash_controls_have_localized_help_text(self):
        from dlux.translations import get_strings

        help_keys = {
            'notification_flash_position': 'help_sys_notification_flash_position',
            'notification_flash_size': 'help_sys_notification_flash_size',
            'notification_flash_text_size': 'help_sys_notification_flash_text_size',
            'notification_flash_timeout_ms': 'help_sys_notification_flash_timeout',
            'notification_flash_max_visible': 'help_sys_notification_flash_max_visible',
        }
        for language in ('en', 'ar'):
            strings = get_strings(language)
            with patch('dlux.forms.system_settings.get_strings', return_value=strings):
                form = SystemSettingsForm(instance=SystemSettings.load())
            for field_name, help_key in help_keys.items():
                with self.subTest(language=language, field=field_name):
                    self.assertEqual(form.fields[field_name].help_text, strings[help_key])

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST='',
        EMAIL_PORT=None,
        DEFAULT_FROM_EMAIL='',
    )
    def test_notification_email_toggles_disable_without_email_delivery(self):
        from dlux.models import SystemSettings

        settings_obj = SystemSettings.load()
        settings_obj.notification_config = {
            'email': {
                'enabled': True,
                'default': True,
            },
        }
        settings_obj.save()

        form = SystemSettingsForm(instance=settings_obj)

        self.assertTrue(form.fields['notification_email_enabled'].disabled)
        self.assertTrue(form.fields['notification_email_default'].disabled)
        self.assertFalse(form.initial['notification_email_enabled'])
        self.assertFalse(form.initial['notification_email_default'])

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST='smtp.example.com',
        EMAIL_PORT=587,
        DEFAULT_FROM_EMAIL='notify@example.com',
    )
    def test_notification_email_toggles_stay_locked_until_email_is_verified(self):
        """Configured is not the same as proven: the toggles need a passed test send."""
        from dlux.models import SystemSettings
        from dlux.system.normalizers import email_config_fingerprint, normalize_email_config

        settings_obj = SystemSettings.load()

        # Reachable SMTP settings alone are not enough.
        form = SystemSettingsForm(instance=settings_obj)
        self.assertTrue(form.fields['notification_email_enabled'].disabled)
        self.assertTrue(form.fields['notification_email_default'].disabled)

        # Enabled but still untested stays locked.
        config = normalize_email_config({
            'host': 'smtp.example.com',
            'port': 587,
            'default_from_email': 'notify@example.com',
            'enabled': True,
        })
        settings_obj.email_config = config
        settings_obj.save(update_fields=['email_config'])
        form = SystemSettingsForm(instance=SystemSettings.load())
        self.assertTrue(form.fields['notification_email_enabled'].disabled)

        # A recorded successful test unlocks them.
        config['verified'] = True
        config['verified_fingerprint'] = email_config_fingerprint(config)
        settings_obj.email_config = config
        settings_obj.save(update_fields=['email_config'])
        form = SystemSettingsForm(instance=SystemSettings.load())
        self.assertFalse(form.fields['notification_email_enabled'].disabled)
        self.assertFalse(form.fields['notification_email_default'].disabled)

    def test_master_gate_initial_reflects_config(self):
        from dlux.models import SystemSettings

        settings_obj = SystemSettings.load()
        settings_obj.notification_config = {'enabled': False}
        settings_obj.save()

        form = SystemSettingsForm(instance=settings_obj)

        self.assertFalse(form.initial['notifications_enabled'])
