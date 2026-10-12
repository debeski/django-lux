"""`manage.py dlux_translations`: the translation audit for projects and DjangoLux itself."""

import json
from io import StringIO
from unittest import mock

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.apps import apps
from django.core.management import call_command
from django.test import SimpleTestCase

from dlux.management.commands.dlux_translations import Command

FIXTURE_APP = 'dlux.tests.translation_audit_app.apps.TranslationAuditAppConfig'


class TranslationsCommandTests(SimpleTestCase):
    def setUp(self):
        settings_patch = self.modify_settings(INSTALLED_APPS={'append': FIXTURE_APP})
        settings_patch.enable()
        self.addCleanup(settings_patch.disable)
        fixture = apps.get_app_config('translation_audit_app')
        project_apps = mock.patch.object(Command, '_project_apps', lambda command: iter([fixture]))
        project_apps.start()
        self.addCleanup(project_apps.stop)

    def run_command(self, *args):
        out = StringIO()
        call_command('dlux_translations', *args, stdout=out)
        return out.getvalue()

    def report(self, *args):
        return json.loads(self.run_command('--json', *args))

    @staticmethod
    def keyed(rows):
        return {row['key']: row for row in rows}

    def test_missing_lists_keys_another_language_has(self):
        missing = self.keyed(self.report('--check', 'missing')['missing'])

        self.assertEqual(missing['fx_only_en']['missing'], ['ar'])
        self.assertEqual(missing['fx_only_en']['source'], 'Only English')
        self.assertNotIn('fx_title', missing)
        # English shows model/permission keys through verbose names already.
        self.assertNotIn('model_gadget', missing)

    def test_undefined_finds_code_and_template_lookups_but_not_comments(self):
        undefined = self.keyed(self.report('--check', 'undefined')['undefined'])

        self.assertEqual(undefined['fx_missing_everywhere']['missing'], ['ar', 'en'])
        self.assertEqual(undefined['fx_missing_everywhere']['default'], 'Fallback text')
        self.assertIn('views.py', undefined['fx_missing_everywhere']['locations'][0])
        self.assertEqual(undefined['fx_template_only']['default'], 'From template')
        self.assertNotIn('fx_in_comment', undefined)
        self.assertNotIn('fx_title', undefined)
        self.assertFalse([key for key in undefined if key.startswith('fx_dyn')])

    def test_models_reports_the_permission_manager_keys_per_language(self):
        models = self.keyed(self.report('--check', 'models')['models'])

        self.assertEqual(models['app_translation_audit_app']['missing'], ['ar'])
        self.assertEqual(models['perm_use_gadget']['default'], 'Can use gadget')
        self.assertIn('perm_view_gadget', models)
        self.assertNotIn('model_gadget', models)

    def test_duplicates_report_repeated_keys_and_dlux_overrides(self):
        rows = self.report('--check', 'duplicates')['duplicates']
        kinds = {(row['key'], row['lang'], row['kind']) for row in rows}

        self.assertIn(('fx_dup', 'en', 'repeated in file'), kinds)
        self.assertIn(('theme_dark', 'en', 'overrides DLux'), kinds)
        self.assertNotIn(('fx_dup', 'ar', 'repeated in file'), kinds)

    def test_same_flags_values_left_in_english(self):
        same = self.keyed(self.report('--check', 'same')['same'])

        self.assertEqual(same['fx_same']['lang'], 'ar')
        self.assertNotIn('fx_title', same)

    def test_unused_is_opt_in_and_skips_dynamic_prefixes(self):
        self.assertNotIn('unused', self.report())
        unused = self.keyed(self.report('--check', 'unused')['unused'])

        self.assertIn('fx_unused_key', unused)
        self.assertNotIn('fx_dyn_one', unused)
        self.assertNotIn('fx_title', unused)

    def test_stub_prints_paste_ready_entries_for_one_language(self):
        output = self.run_command('--stub', 'ar', '--no-color')

        self.assertIn('translation_audit_app/translations.py', output)
        self.assertIn('"fx_only_en": "Only English",  # TODO translate', output)
        self.assertIn('"perm_use_gadget": "Can use gadget",  # TODO translate', output)

    def test_fail_exits_non_zero_only_for_failing_findings(self):
        with self.assertRaises(SystemExit) as raised:
            self.run_command('--fail')
        self.assertEqual(raised.exception.code, 1)

        self.run_command('--fail', '--check', 'same')

    def test_overriding_dlux_alone_does_not_fail(self):
        report = {'duplicates': [{'key': 'theme_dark', 'lang': 'en', 'kind': 'overrides DLux'}]}
        self.assertEqual(Command._failures(report), [])

    def test_core_mode_audits_the_shipped_catalogue(self):
        report = self.report('--core', '--check', 'missing', '--check', 'duplicates')

        self.assertEqual(report['missing'], [])
        self.assertTrue(all(row['kind'] == 'repeated in file' for row in report['duplicates']))
