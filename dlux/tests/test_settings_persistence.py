"""Catalogue-wide contracts for section edits, import patches and settings writers."""

from copy import deepcopy
from unittest.mock import patch

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase, TransactionTestCase, skipUnlessDBFeature

from dlux.forms import SystemSettingsForm
from dlux.models import SystemSettings
from dlux.options import write_app_system_config, write_app_system_configs
from dlux.system.constants import SETUP_STEP_SLUGS
from dlux.system.normalizers import _to_bool, normalize_email_config
from dlux.system.registry import iter_setting_groups
from dlux.utils import encrypt_email_secret
from dlux.utils.import_export import (
    apply_system_settings_import,
    export_system_settings_payload,
    normalize_system_settings_import_payload,
)


def _leaves(value, path=()):
    if isinstance(value, dict):
        for name, child in value.items():
            yield from _leaves(child, (*path, name))
    else:
        yield path, value


def _at(value, path):
    for key in path:
        value = value[key]
    return value


def _put(value, path, replacement):
    for key in path[:-1]:
        value = value.setdefault(key, {})
    value[path[-1]] = replacement


class CatalogBooleanContracts(SimpleTestCase):
    def test_boolean_tokens_have_one_meaning_across_every_group(self):
        probes = 0
        for group in iter_setting_groups():
            defaults = group.default_factory()
            for path, default in _leaves(defaults):
                if not isinstance(default, bool):
                    continue
                for token, expected in [('false', False), ('0', False), ('off', False), ('true', True), ('1', True), ('on', True)]:
                    with self.subTest(group=group.key, path=path, token=token):
                        supplied = deepcopy(defaults)
                        _put(supplied, path, token)
                        if group.key == 'email' and path == ('use_tls',):
                            supplied['use_ssl'] = False
                        if group.key == 'email' and path in {('verified',), ('password_configured',)}:
                            # Derived verification/credential state has independent prerequisites.
                            continue
                        if group.key == 'log' and path in {('audit', 'enabled'), ('audit', 'immutable')}:
                            # Audit logging cannot be disabled or made mutable by configuration.
                            self.assertTrue(_at(group.normalizer(supplied), path))
                            continue
                        self.assertIs(_at(group.normalizer(supplied), path), expected)
                        probes += 1
        self.assertGreater(probes, 500)

    def test_invalid_tokens_keep_the_explicit_default(self):
        for default in (False, True):
            for value in (None, 'invalid', [], {}, 2):
                with self.subTest(default=default, value=value):
                    self.assertIs(_to_bool(value, default), default)

    def test_credential_presence_is_not_string_truthiness(self):
        self.assertFalse(normalize_email_config({'password_configured': 'false'})['password_configured'])


class SettingsPersistenceContracts(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_superuser('catalog-admin', 'admin@example.com', 'test-password')
        self.factory = RequestFactory()

    def tearDown(self):
        cache.clear()

    def configured(self, enabled=True):
        obj = SystemSettings(pk=1, is_configured=True, default_language='ar')
        for group in iter_setting_groups():
            config = group.default_factory()
            for path, default in list(_leaves(config)):
                if isinstance(default, bool):
                    _put(config, path, enabled)
            setattr(obj, group.storage_field, group.normalizer(config))
        obj.system_names = {'en': 'Catalog fixture', 'ar': 'اختبار'}
        obj.extra_config = {'app': {'project.one': {'limit': 41}}, 'scanlink': {'enabled': enabled}}
        obj.notification_config['automatic'].update(include_actor=True, watchable=False, actor_flash_actions=['update'])
        obj.save()
        cache.clear()
        return obj

    def form(self, obj, step, data):
        request = self.factory.post(f'/sys/settings/?step={step}', data)
        request.user = self.user
        request.session = {}
        return SystemSettingsForm(request.POST, instance=obj, request=request, user=self.user)

    def test_inactive_fields_ignore_missing_and_stale_payloads_in_every_section(self):
        for enabled in (False, True):
            for step in range(len(SETUP_STEP_SLUGS)):
                with self.subTest(enabled=enabled, step=SETUP_STEP_SLUGS[step]):
                    obj = self.configured(enabled)
                    form = self.form(obj, step, {'default_language': 'ar'})
                    self.assertGreater(len(form.field_steps), 150)
                    self.assertEqual(
                        set(form.fields) - set(form.field_steps),
                        {'settings_import_file', 'settings_import_processed'},
                        'A new settings field must have a section owner before it can be saved safely.',
                    )
                    self.assertTrue(form.is_valid(), form.errors)
                    for name, owner in form.field_steps.items():
                        if owner != step:
                            self.assertTrue(form.fields[name].disabled, (name, owner, step))
                    expected = {name: deepcopy(form.cleaned_data.get(name)) for name, owner in form.field_steps.items() if owner != step}
                    stale = {'default_language': 'en'}
                    for name in expected:
                        if form.fields[name].__class__.__name__ == 'BooleanField':
                            stale[name] = '' if enabled else 'on'
                    rebound = self.form(SystemSettings.objects.get(pk=obj.pk), step, stale)
                    self.assertTrue(rebound.is_valid(), rebound.errors)
                    for name, value in expected.items():
                        self.assertEqual(rebound.cleaned_data.get(name), value, (name, step))

    def test_unrelated_saves_preserve_all_fourteen_reported_toggles(self):
        paths = {
            'languages': [('language_config', 'allow_user_language_override')],
            'appearance': [('theme_config', 'allow_user_theme_override'), ('typography_config', 'allow_user_font_override')],
            'security': [('registration_config', 'public_registration_enabled'), ('registration_config', 'registration_throttle_enabled')],
            'titlebar': [('titlebar_config', k) for k in ('accent_edge', 'show_home_button', 'show_language_switcher', 'show_logo', 'show_title')],
            'sidebar': [('sidebar_config', 'enabled'), ('sidebar_config', 'accent_edge')],
            'navbar': [('navbar_config', 'enabled')],
            'login_page': [('login_config', 'show_logo')],
        }
        for step, slug in enumerate(SETUP_STEP_SLUGS):
            with self.subTest(step=slug):
                obj = self.configured(True)
                form = self.form(obj, step, {'default_language': 'ar'})
                self.assertTrue(form.is_valid(), form.errors)
                form.save()
                obj.refresh_from_db()
                for owner, fields in paths.items():
                    if owner != slug:
                        for group, key in fields:
                            self.assertIs(getattr(obj, group)[key], True, (slug, group, key))

    def test_partial_imports_preserve_every_unsupplied_group_leaf(self):
        for group in iter_setting_groups():
            defaults = group.default_factory()
            boolean = next(((path, value) for path, value in _leaves(defaults) if isinstance(value, bool)), None)
            if not boolean:
                continue
            path, _ = boolean
            with self.subTest(group=group.key):
                obj = self.configured(True)
                before = deepcopy(getattr(obj, group.storage_field))
                incoming = {}
                _put(incoming, path, False)
                apply_system_settings_import(obj, {group.storage_field: incoming}, preserve_email_secret=True)
                obj.refresh_from_db()
                after = getattr(obj, group.storage_field)
                for other, value in _leaves(before):
                    if other != path:
                        self.assertEqual(_at(after, other), value, (group.key, other))

    @patch('dlux.forms.system_settings.email_features_unlocked', return_value=True)
    def test_reported_toggles_still_accept_on_and_off_in_their_own_section(self, _verified_email):
        fields = {
            'languages': ['allow_user_language_override'],
            'appearance': ['allow_user_theme_override', 'allow_user_font_override'],
            'security': ['public_registration_enabled', 'registration_throttle_enabled'],
            'titlebar': ['titlebar_accent_edge', 'titlebar_show_home_button', 'titlebar_show_language_switcher', 'titlebar_show_logo', 'titlebar_show_title'],
            'sidebar': ['sidebar_enabled', 'sidebar_accent_edge'],
            'navbar': ['navbar_enabled'],
            'login_page': ['login_show_logo'],
        }
        for slug, names in fields.items():
            for name in names:
                for enabled in (False, True):
                    with self.subTest(field=name, enabled=enabled):
                        obj = self.configured(True)
                        data = {'default_language': 'ar'}
                        if enabled:
                            data[name] = 'on'
                        form = self.form(obj, SETUP_STEP_SLUGS.index(slug), data)
                        self.assertTrue(form.is_valid(), form.errors)
                        self.assertIs(form.cleaned_data[name], enabled)
                        form.save()
                        obj.refresh_from_db()
                        reopened = self.form(obj, SETUP_STEP_SLUGS.index(slug), data)
                        self.assertIs(reopened.initial[name], enabled)

    def test_flat_auth_patch_does_not_disable_other_protections(self):
        obj = self.configured(True)
        before = deepcopy(obj.auth_config)
        apply_system_settings_import(obj, {'email_2fa': False})
        obj.refresh_from_db()
        self.assertEqual(obj.auth_config, {**before, 'email_2fa': False})
        self.assertEqual(normalize_system_settings_import_payload({'email_2fa': False}), {'email_2fa': False})

    def test_partial_extra_import_keeps_other_features_and_namespaces(self):
        obj = self.configured(True)
        before = deepcopy(obj.extra_config)
        apply_system_settings_import(obj, {'extra_config': {'scanlink': {'enabled': False}}})
        obj.refresh_from_db()
        self.assertEqual(obj.extra_config, {**before, 'scanlink': {'enabled': False}})

    def test_redacted_and_partial_imports_preserve_the_encrypted_smtp_secret(self):
        for full_export, preserve in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(full_export=full_export, preserve=preserve):
                obj = self.configured(False)
                token = encrypt_email_secret('test-only-secret')
                obj.email_config.update(secret_storage='encrypted_db', encrypted_password=token, password_configured=True)
                obj.save()
                payload = export_system_settings_payload(obj) if full_export else {'email_config': {'timeout': 25}}
                apply_system_settings_import(obj, payload, preserve_email_secret=preserve)
                obj.refresh_from_db()
                self.assertEqual(obj.email_config['encrypted_password'], token)
                self.assertTrue(obj.email_config['password_configured'])

    def test_section_can_explicitly_clear_a_mapping_without_changing_other_sections(self):
        import json

        obj = self.configured(True)
        obj.translations_override = {'en': {'custom': 'old'}}
        obj.save()
        step = SETUP_STEP_SLUGS.index('languages')
        form = self.form(obj, step, {'default_language': 'ar', 'translations_override': json.dumps({})})
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        obj.refresh_from_db()
        self.assertEqual(obj.translations_override, {})
        self.assertTrue(obj.allow_user_theme_override)

    def test_import_review_apply_and_revert_preserve_credentials(self):
        import json
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.urls import reverse

        obj = self.configured(False)
        token = encrypt_email_secret('test-only-secret')
        obj.email_config.update(secret_storage='encrypted_db', encrypted_password=token, password_configured=True)
        obj.save()
        timeout = obj.email_config['timeout']
        self.client.force_login(self.user)
        upload = SimpleUploadedFile('settings.json', json.dumps({'email_config': {'timeout': 25}}).encode(), content_type='application/json')
        preview = self.client.post(reverse('system_settings_import_preview'), {'config_file': upload})
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()['change_count'], 1)
        response = self.client.post(reverse('system_settings_import_apply'), {'apply': ['email_config:timeout']})
        self.assertEqual(response.status_code, 200)
        obj.refresh_from_db()
        self.assertEqual(obj.email_config['encrypted_password'], token)
        self.assertEqual(obj.email_config['timeout'], 25)
        response = self.client.post(reverse('system_settings_import_revert'))
        self.assertEqual(response.status_code, 200)
        obj.refresh_from_db()
        self.assertEqual(obj.email_config['encrypted_password'], token)
        self.assertEqual(obj.email_config['timeout'], timeout)

    def test_partial_review_describes_a_patch_without_claiming_removed_neighbors(self):
        from dlux.system.settings_diff import build_change_set, selected_settings

        current = {'extra_config': {'app': {'one': {'value': 1}, 'two': {'value': 2}}}}
        incoming = {'extra_config': {'app': {'one': {'value': 3}}}}
        changes = build_change_set(current, incoming)
        change = changes['groups'][0]['changes'][0]
        self.assertEqual(change['incoming']['app']['two'], {'value': 2})
        self.assertEqual(change['summary']['removed'], [])
        chosen = selected_settings(changes, ['extra_config'], current)
        self.assertEqual(chosen, incoming)

    def test_stale_app_namespace_writers_merge_the_current_row(self):
        for grouped in (False, True):
            with self.subTest(grouped=grouped):
                obj = self.configured(True)
                stale = SystemSettings.objects.get(pk=obj.pk)
                newer = SystemSettings.objects.get(pk=obj.pk)
                newer.extra_config['app']['project.two'] = {'limit': 99}
                newer.default_language = 'en'
                newer.save()
                with patch.object(SystemSettings, 'load', return_value=stale):
                    if grouped:
                        write_app_system_configs({'project.one': {'limit': 42}})
                    else:
                        write_app_system_config('project.one', {'limit': 42})
                newer.refresh_from_db()
                self.assertEqual(newer.extra_config['app']['project.two'], {'limit': 99})
                self.assertEqual(newer.extra_config['app']['project.one'], {'limit': 42})
                self.assertEqual(newer.default_language, 'en')

    def test_notification_policy_survives_every_unrelated_save(self):
        for step, slug in enumerate(SETUP_STEP_SLUGS):
            with self.subTest(step=slug):
                obj = self.configured(True)
                expected = deepcopy(obj.notification_config['automatic'])
                form = self.form(obj, step, {'default_language': 'ar'})
                self.assertTrue(form.is_valid(), form.errors)
                form.save()
                obj.refresh_from_db()
                actual = obj.notification_config['automatic']
                for key in ('include_actor', 'watchable', 'actor_flash_actions'):
                    self.assertEqual(actual[key], expected[key])


class ConcurrentSettingsWriterContracts(TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_namespace_writers_serialize_concurrent_merges(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from django.db import close_old_connections, connection
        from dlux.options import merge_app_system_config

        obj = SystemSettings(pk=1, is_configured=True)
        obj.save()
        first_locked, release_first, second_started, second_finished = (Event() for _ in range(4))

        def merge(extra, namespace, value):
            if namespace == 'concurrent.first':
                first_locked.set()
                if not release_first.wait(10):
                    raise AssertionError('Timed out waiting to release first writer')
            return merge_app_system_config(extra, namespace, value)

        def write(namespace, grouped):
            close_old_connections()
            try:
                if grouped:
                    second_started.set()
                    write_app_system_configs({namespace: {'value': 2}})
                    second_finished.set()
                else:
                    write_app_system_config(namespace, {'value': 1})
            finally:
                connection.close()

        with patch('dlux.options.merge_app_system_config', side_effect=merge), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(write, 'concurrent.first', False)
            try:
                self.assertTrue(first_locked.wait(10))
                second = pool.submit(write, 'concurrent.second', True)
                self.assertTrue(second_started.wait(10))
                self.assertFalse(second_finished.wait(0.2), 'Second writer bypassed the row lock')
            finally:
                release_first.set()
            first.result(timeout=10)
            second.result(timeout=10)
        obj.refresh_from_db()
        self.assertEqual(obj.extra_config['app']['concurrent.first'], {'value': 1})
        self.assertEqual(obj.extra_config['app']['concurrent.second'], {'value': 2})
