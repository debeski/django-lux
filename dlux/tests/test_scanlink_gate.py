"""ScanLink is opt-in, and off means nothing reaches the page.

ScanLink drives a tray app on the operator's own workstation over
``https://localhost:5443`` and ``http://localhost:5000``. On any deployment
whose operators never installed it, those are refused connections that the
browser writes to the console itself — the ``catch`` in main.js swallows the
exception, not the log. The only real fix is not to probe, so the gate has to
hold at both ends: no scan button to click, and no ScanLink script on the page.
"""
from django.core.cache import cache
from django.template import Context, Template
from django.test import TestCase

from dlux.models import SystemSettings
from dlux.utils import scanlink_enabled
from dlux.widgets import DluxFileInput


def _set_enabled(value):
    """Flip the stored setting the way the settings form does."""
    record = SystemSettings.load()
    extra = dict(record.extra_config or {})
    extra['scanlink'] = {'enabled': value}
    record.extra_config = extra
    record.save()


class ScanLinkTestCase(TestCase):
    """`SystemSettings.load()` reads through the cache, which a test rollback
    does not touch — so a test that enables ScanLink leaks into the next one
    unless the cached singleton is dropped first. The test settings isolate the
    cache per process, so clearing it here cannot affect anything else.
    """

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)

ASSETS = '{% include "dlux/forms/assets_scripts.html" %}'


def _render_assets():
    return Template('{% load dlux_tags %}' + ASSETS).render(Context({
        'DLUX_SCANLINK_ENABLED': scanlink_enabled(),
    }))


class GateDefaultTests(ScanLinkTestCase):
    def test_it_is_off_on_a_fresh_install(self):
        self.assertFalse(scanlink_enabled())

    def test_it_is_on_once_the_setting_is_saved(self):
        _set_enabled(True)
        self.assertTrue(scanlink_enabled())

    def test_it_is_off_again_when_switched_back(self):
        _set_enabled(True)
        _set_enabled(False)
        self.assertFalse(scanlink_enabled())

    def test_an_install_predating_the_key_reads_as_off(self):
        """`extra_config` on an existing system has no `scanlink` key at all."""
        record = SystemSettings.load()
        record.extra_config = {'app': {'someproject.settings': {'a': 1}}}
        record.save()
        self.assertFalse(scanlink_enabled())

    def test_a_corrupt_value_reads_as_off_rather_than_raising(self):
        record = SystemSettings.load()
        record.extra_config = {'scanlink': 'not-a-dict'}
        record.save()
        self.assertFalse(scanlink_enabled())

    def test_saving_the_toggle_leaves_project_namespaces_alone(self):
        """The whole reason this is safe to keep in `extra_config`."""
        record = SystemSettings.load()
        record.extra_config = {'app': {'myproject.settings': {'keep': 'me'}}}
        record.save()
        _set_enabled(True)

        stored = SystemSettings.load().extra_config
        self.assertEqual(stored['app'], {'myproject.settings': {'keep': 'me'}})
        self.assertTrue(stored['scanlink']['enabled'])


class WidgetTests(ScanLinkTestCase):
    def _show_scan(self, requested):
        widget = DluxFileInput(field_label='File', show_scan=requested)
        return widget.get_context('f', None, {})['widget']['show_scan']

    def test_a_requested_scan_button_is_withheld_while_the_gate_is_shut(self):
        self.assertFalse(
            self._show_scan(True),
            'the button is the thing that fires the localhost probe',
        )

    def test_a_requested_scan_button_is_rendered_once_the_gate_is_open(self):
        _set_enabled(True)
        self.assertTrue(self._show_scan(True))

    def test_the_gate_does_not_add_a_button_nobody_asked_for(self):
        _set_enabled(True)
        self.assertFalse(
            self._show_scan(False),
            'enabling the integration must not put a scan button on every file field',
        )

    def test_the_widget_template_only_draws_the_button_when_told_to(self):
        widget = DluxFileInput(field_label='File', show_scan=True)
        self.assertNotIn('data-dlux-file-scan', widget.render('f', None))


class AssetScriptTests(ScanLinkTestCase):
    def test_no_scanlink_script_is_served_while_the_gate_is_shut(self):
        html = _render_assets()
        self.assertNotIn('scanlink/js/main.js', html)
        self.assertNotIn('scanlink/js/scan_button.js', html)

    def test_both_scanlink_scripts_are_served_once_the_gate_is_open(self):
        _set_enabled(True)
        html = _render_assets()
        self.assertIn('scanlink/js/main.js', html)
        self.assertIn('scanlink/js/scan_button.js', html)

    def test_the_other_form_helpers_are_unaffected_by_the_gate(self):
        """The gate wraps two lines, not the whole include."""
        html = _render_assets()
        self.assertIn('filefield/js/main.js', html)
        self.assertIn('asset_picker/js/main.js', html)


class ProbeTargetTests(ScanLinkTestCase):
    """Pin the addresses, since they are what shows up in a user's console."""

    def test_the_helper_urls_are_the_ones_the_gate_exists_to_silence(self):
        from pathlib import Path
        import dlux
        source = (Path(dlux.__file__).parent
                  / 'static/dlux/helpers/scanlink/js/main.js').read_text(encoding='utf-8')
        self.assertIn('http://localhost:5000', source)
        self.assertIn('https://localhost:5443', source)
        self.assertIn('/health', source)


class SettingsFormTests(ScanLinkTestCase):
    """The Extra Features step is the only UI for the toggle, so the round-trip
    through the form is what makes it real. `extra_config` also carries every
    downstream project's config under `app`, so saving must never rebuild it.
    """

    def _form(self, **data):
        from dlux.forms import SystemSettingsForm
        record = SystemSettings.load()
        payload = {'scanlink_enabled': ''}
        payload.update(data)
        return SystemSettingsForm(payload, instance=record)

    def test_the_step_seeds_its_initial_from_the_stored_value(self):
        from dlux.forms import SystemSettingsForm
        _set_enabled(True)
        form = SystemSettingsForm(instance=SystemSettings.load())
        self.assertTrue(form.initial.get('scanlink_enabled'))

    def test_a_fresh_install_seeds_the_toggle_off(self):
        from dlux.forms import SystemSettingsForm
        form = SystemSettingsForm(instance=SystemSettings.load())
        self.assertFalse(form.initial.get('scanlink_enabled'))

    def test_the_field_exists_and_is_optional(self):
        from dlux.forms import SystemSettingsForm
        field = SystemSettingsForm().fields['scanlink_enabled']
        self.assertFalse(field.required, 'an unticked checkbox posts nothing')

    def test_the_toggle_is_not_a_model_field(self):
        """It lives in `extra_config`, which the form never lists in Meta."""
        from dlux.forms import SystemSettingsForm
        self.assertNotIn('scanlink_enabled', SystemSettingsForm.Meta.fields)

    def test_writing_the_toggle_preserves_project_namespaces(self):
        record = SystemSettings.load()
        record.extra_config = {'app': {'myproject.settings': {'keep': 'me'}}}
        record.save()

        from dlux.forms import SystemSettingsForm
        form = SystemSettingsForm(instance=SystemSettings.load())
        instance = form.instance
        form.cleaned_data = {'scanlink_enabled': True}
        form.single_step_mode = False
        form._apply_extra_features(instance)

        self.assertEqual(instance.extra_config['app'], {'myproject.settings': {'keep': 'me'}})
        self.assertTrue(instance.extra_config['scanlink']['enabled'])

    def test_a_save_of_another_step_leaves_the_toggle_alone(self):
        """Single-step modal saves post only their own step's fields."""
        from dlux.forms import SystemSettingsForm
        from dlux.system.constants import SETUP_STEP_BACKUPS

        _set_enabled(True)
        form = SystemSettingsForm(instance=SystemSettings.load())
        instance = form.instance
        form.cleaned_data = {'scanlink_enabled': False}
        form.single_step_mode = True
        form.single_step_index = SETUP_STEP_BACKUPS
        form._apply_extra_features(instance)

        self.assertTrue(
            instance.extra_config['scanlink']['enabled'],
            'saving the Backups step silently switched ScanLink off',
        )
