"""Regression tests for the settings-save theme-persistence bug.

A single-step settings save (e.g. the public-theme step) re-serialises the whole
system config and preserves non-edited fields from ``form.instance``. Views hand
the form ``SystemSettings.load()`` (the cached singleton); when that cache had
diverged from the DB, saving one step wrote the stale value back — the reported
bug where ``default_theme`` silently reverted to 'light' on every save.

The fix refreshes the bound instance from the DB before any clean/preserve runs,
so the authoritative row — not a stale cache — is always the source of truth.
"""
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from dlux.forms import SystemSettingsForm
from dlux.models import SystemSettings


class SettingsThemePersistenceTests(TestCase):
    def _configured_settings(self, default_theme='gothic'):
        instance = SystemSettings.load()
        instance.is_configured = True
        instance.default_theme = default_theme
        instance.theme_config = {
            'allowed_themes': ['light', 'dark', 'gothic'],
            'allow_user_theme_override': True,
        }
        instance.save()
        return instance

    def test_single_step_save_with_stale_instance_preserves_db_default_theme(self):
        """Saving an unrelated step must not revert default_theme to the stale
        cache value; the DB row is authoritative."""
        self._configured_settings(default_theme='gothic')

        # Simulate the view passing a STALE cached singleton (default_theme reset
        # to 'light') while the DB still holds the real 'gothic'.
        stale = SystemSettings.objects.get(pk=1)
        stale.default_theme = 'light'

        user = get_user_model().objects.create_superuser('admin', 'a@example.com', 'pw')
        request = RequestFactory().post('/sys/setup/?step=6', data={})
        request.user = user

        form = SystemSettingsForm(
            request.POST, request.FILES,
            instance=stale, request=request, user=user, mode='modal',
        )
        self.assertTrue(form.single_step_mode)

        # The fix refreshes the bound instance from the DB in __init__.
        self.assertEqual(form.instance.default_theme, 'gothic')

        form.is_valid()
        self.assertEqual(form.cleaned_data.get('default_theme'), 'gothic')

    def test_bare_save_keeps_default_theme(self):
        """A no-op model save must never mutate default_theme."""
        self._configured_settings(default_theme='gothic')
        SystemSettings.objects.get(pk=1).save()
        self.assertEqual(SystemSettings.objects.get(pk=1).default_theme, 'gothic')
