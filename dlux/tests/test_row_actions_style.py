from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.test import TestCase

from dlux.models import DluxNotification, SystemSettings
from dlux.system.constants import SYSTEM_SETTINGS_EXPORT_FIELDS
from dlux.system.normalizers import normalize_layout_config
from dlux.utils.config import get_system_config
from dlux.utils.crud import _build_generic_table_class

User = get_user_model()


def _set_mode(mode):
    s = SystemSettings.load()
    s.is_configured = True
    layout = dict(s.layout_config or {})
    layout['row_actions_style'] = mode
    s.layout_config = layout
    s.save()


class RowActionsSettingTests(TestCase):
    """The row_actions_style setting must survive the real save path and be
    exposed at runtime — same pipeline contract as options_style."""

    def setUp(self):
        s = SystemSettings.load()
        s.is_configured = True
        s.save()

    def test_default_is_context(self):
        self.assertEqual(normalize_layout_config({})['row_actions_style'], 'context')

    def test_normalizer_validates_against_choices(self):
        self.assertEqual(normalize_layout_config({'row_actions_style': 'column'})['row_actions_style'], 'column')
        self.assertEqual(normalize_layout_config({'row_actions_style': 'both'})['row_actions_style'], 'both')
        # Unknown value falls back to the default rather than persisting garbage.
        self.assertEqual(normalize_layout_config({'row_actions_style': 'nope'})['row_actions_style'], 'context')

    def test_in_export_whitelist(self):
        self.assertIn('row_actions_style', SYSTEM_SETTINGS_EXPORT_FIELDS)

    def test_apply_import_persists_and_exposes(self):
        from dlux.utils.import_export import apply_system_settings_import, export_system_settings_payload

        s = SystemSettings.load()
        apply_system_settings_import(s, {'row_actions_style': 'column'}, mark_configured=False)
        reloaded = SystemSettings.load()
        self.assertEqual(reloaded.layout_config.get('row_actions_style'), 'column')
        self.assertEqual(reloaded.row_actions_style, 'column')  # flat property
        self.assertEqual(get_system_config().get('row_actions_style'), 'column')  # runtime
        payload = export_system_settings_payload(reloaded)
        self.assertEqual(payload['settings'].get('row_actions_style'), 'column')

    def test_survives_saving_a_different_step(self):
        from django.test import RequestFactory
        from dlux.forms import SystemSettingsForm
        from dlux.utils.import_export import apply_system_settings_import

        apply_system_settings_import(SystemSettings.load(), {'row_actions_style': 'both'}, mark_configured=False)
        admin = User.objects.create_superuser('su', 'su@e.com', 'pw12345!x')
        req = RequestFactory().post('/?step=3', {'x': '1'})
        req.user = admin
        form = SystemSettingsForm(data={'x': '1'}, instance=SystemSettings.load(), request=req, mode='modal')
        form.cleaned_data = {}
        # A single-step save of another step must preserve the stored choice.
        self.assertEqual(form._clean_preserved_choice('row_actions_style', 9, {'context', 'column', 'both'}, 'context'), 'both')


class RowActionsColumnTests(TestCase):
    """The dedicated three-dot column is added (or not) per mode, and pure
    'column' mode disables the right-click marker so the button is the only
    trigger; both modes keep data-dlux-actions so the shared JS can read it."""

    def setUp(self):
        DluxNotification.objects.create(title='t', message='m')
        self.Table = _build_generic_table_class(DluxNotification)

    def _table(self):
        return self.Table(DluxNotification.objects.all(), request=None)

    def test_context_mode_has_no_column_and_keeps_right_click(self):
        _set_mode('context')
        t = self._table()
        self.assertNotIn('dlux_row_actions', t.columns.names())
        self.assertEqual(t.row_attrs.get('data-dlux-context'), 'true')
        self.assertIn('data-dlux-actions', t.row_attrs)

    def test_column_mode_adds_last_column_and_drops_right_click(self):
        _set_mode('column')
        t = self._table()
        names = list(t.columns.names())
        self.assertEqual(names[-1], 'dlux_row_actions')
        self.assertIsNone(t.row_attrs.get('data-dlux-context'))  # right-click off
        self.assertIn('data-dlux-actions', t.row_attrs)  # button still needs the payload
        cell = str(t.rows[0].get_cell('dlux_row_actions'))
        self.assertIn('dlux-row-actions-trigger', cell)

    def test_both_mode_has_column_and_right_click(self):
        _set_mode('both')
        t = self._table()
        self.assertEqual(list(t.columns.names())[-1], 'dlux_row_actions')
        self.assertEqual(t.row_attrs.get('data-dlux-context'), 'true')
        cell = str(t.rows[0].get_cell('dlux_row_actions'))
        self.assertIn('dlux-row-actions-trigger', cell)

    def test_actions_column_header_is_empty(self):
        _set_mode('column')
        t = self._table()
        self.assertEqual(str(t.columns['dlux_row_actions'].header), '')

    def test_actions_column_is_not_orderable(self):
        _set_mode('column')
        t = self._table()
        self.assertFalse(t.columns['dlux_row_actions'].orderable)
