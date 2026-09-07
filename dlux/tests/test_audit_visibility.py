from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase

from dlux import middleware
from dlux.models import DluxNotification, SystemSettings
from dlux.system.constants import SETUP_STEP_LAYOUT, SETUP_STEP_SECURITY
from dlux.system.normalizers import normalize_layout_config
from dlux.utils.authorization import audit_fields_visible, soft_deleted_visible, user_can_view_audit_fields
from dlux.utils.crud import _build_generic_table_class

User = get_user_model()

AUDIT_COLS = {'created_at', 'updated_at', 'created_by', 'updated_by'}


def _set_layout(**flags):
    s = SystemSettings.load()
    s.is_configured = True
    layout = dict(s.layout_config or {})
    layout.update(flags)
    s.layout_config = layout
    s.save()


class _ThreadLocalUser:
    """Context manager mirroring what DluxMiddleware sets per request."""

    def __init__(self, user):
        self.user = user

    def __enter__(self):
        middleware._thread_locals.user = self.user
        return self.user

    def __exit__(self, *exc):
        if hasattr(middleware._thread_locals, 'user'):
            del middleware._thread_locals.user


class AuditVisibilityHelperTests(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser('su', 'su@e.com', 'pw12345!x')
        self.plain = User.objects.create_user('bob', 'b@e.com', 'pw12345!x')
        perm = Permission.objects.get(codename='view_audit_fields')
        user = User.objects.create_user('carol', 'c@e.com', 'pw12345!x')
        user.user_permissions.add(perm)
        self.permitted = User.objects.get(pk=user.pk)  # refresh perm cache

    def test_audit_permission_matrix(self):
        self.assertTrue(user_can_view_audit_fields(self.su))
        self.assertTrue(user_can_view_audit_fields(self.permitted))
        self.assertFalse(user_can_view_audit_fields(self.plain))

    def test_audit_visible_requires_setting_and_permission(self):
        _set_layout(show_audit_fields=False)
        self.assertFalse(audit_fields_visible(self.su))  # setting off → hidden even for superuser
        _set_layout(show_audit_fields=True)
        self.assertTrue(audit_fields_visible(self.su))
        self.assertTrue(audit_fields_visible(self.permitted))
        self.assertFalse(audit_fields_visible(self.plain))  # no permission

    def test_soft_deleted_visible_is_superadmin_only(self):
        _set_layout(show_soft_deleted=True)
        self.assertTrue(soft_deleted_visible(self.su))
        self.assertFalse(soft_deleted_visible(self.permitted))  # permission does NOT grant this
        self.assertFalse(soft_deleted_visible(self.plain))
        _set_layout(show_soft_deleted=False)
        self.assertFalse(soft_deleted_visible(self.su))  # setting off → hidden

    def test_helpers_fall_back_to_thread_local_user(self):
        _set_layout(show_audit_fields=True)
        with _ThreadLocalUser(self.su):
            self.assertTrue(audit_fields_visible())
        with _ThreadLocalUser(self.plain):
            self.assertFalse(audit_fields_visible())


class AuditColumnGatingTests(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser('su', 'su@e.com', 'pw12345!x')
        self.plain = User.objects.create_user('bob', 'b@e.com', 'pw12345!x')
        self.table = _build_generic_table_class(DluxNotification)

    def _columns_for(self, user):
        with _ThreadLocalUser(user):
            return set(self.table(DluxNotification.objects.none(), request=None).columns.names())

    def test_audit_columns_shown_only_when_visible(self):
        _set_layout(show_audit_fields=True, show_soft_deleted=True)
        su_cols = self._columns_for(self.su)
        self.assertLessEqual(AUDIT_COLS, su_cols)
        self.assertIn('deleted_at', su_cols)

        plain_cols = self._columns_for(self.plain)
        self.assertFalse(AUDIT_COLS & plain_cols)
        self.assertNotIn('deleted_at', plain_cols)

    def test_setting_off_hides_columns_for_everyone(self):
        _set_layout(show_audit_fields=False, show_soft_deleted=False)
        self.assertFalse(AUDIT_COLS & self._columns_for(self.su))
        self.assertNotIn('deleted_at', self._columns_for(self.su))

    def test_custom_table_with_explicit_fields_also_gains_audit_columns(self):
        """The decrees case: a project table lists only business columns in
        Meta.fields; audit columns are added (not merely un-hidden)."""
        import django_tables2 as tables

        class CustomNotifTable(tables.Table):
            class Meta:
                model = DluxNotification
                fields = ('title', 'message')

        _set_layout(show_audit_fields=True, show_soft_deleted=True)
        with _ThreadLocalUser(self.su):
            cols = set(CustomNotifTable(DluxNotification.objects.none(), request=None).columns.names())
        self.assertLessEqual(AUDIT_COLS, cols)
        self.assertIn('deleted_at', cols)
        self.assertIn('title', cols)  # business columns still present


class AuditTrailTagTests(TestCase):
    """The reusable {% dlux_audit_trail %} tag renders the grouped audit block
    only when permitted — replacing per-project hand-rolled audit sections."""

    def setUp(self):
        from django.template import Context, Template

        self.su = User.objects.create_superuser('su', 'su@e.com', 'pw12345!x')
        self.plain = User.objects.create_user('bob', 'b@e.com', 'pw12345!x')
        self.note = DluxNotification.objects.create(title='t', message='m')
        self._Template = Template
        self._Context = Context

    def _render(self, user):
        request = type('R', (), {'user': user})()
        tpl = self._Template('{% load dlux_tags %}{% dlux_audit_trail obj %}')
        return tpl.render(self._Context({'obj': self.note, 'request': request}))

    def test_tag_renders_audit_block_only_when_visible(self):
        _set_layout(show_audit_fields=True)
        self.assertIn('Created by', self._render(self.su))
        self.assertEqual(self._render(self.plain).strip(), '')  # no permission → nothing

    def test_setting_off_renders_nothing(self):
        _set_layout(show_audit_fields=False)
        self.assertEqual(self._render(self.su).strip(), '')

    def test_deleted_line_is_superadmin_gated(self):
        _set_layout(show_audit_fields=True, show_soft_deleted=True)
        self.note.delete()  # soft-delete
        self.note = DluxNotification.all_objects.get(pk=self.note.pk)
        self.assertIn('Deleted by', self._render(self.su))
        # A permitted non-superadmin sees the audit block but not the deleted line.
        perm = Permission.objects.get(codename='view_audit_fields')
        carol = User.objects.create_user('carol', 'c2@e.com', 'pw12345!x')
        carol.user_permissions.add(perm)
        carol = User.objects.get(pk=carol.pk)
        out = self._render(carol)
        self.assertIn('Created by', out)
        self.assertNotIn('Deleted by', out)


class SoftDeleteManagerTests(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser('su', 'su@e.com', 'pw12345!x')
        self.plain = User.objects.create_user('bob', 'b@e.com', 'pw12345!x')
        DluxNotification.objects.create(title='a', message='m')
        self.b = DluxNotification.objects.create(title='b', message='m')
        self.b.delete()  # soft-delete

    def test_default_manager_hides_soft_deleted(self):
        # No request/superadmin in context → hidden (safe default).
        self.assertEqual(DluxNotification.objects.count(), 1)
        self.assertEqual(DluxNotification.all_objects.count(), 2)
        self.assertIsNotNone(DluxNotification.all_objects.get(pk=self.b.pk).deleted_at)

    def test_review_mode_includes_soft_deleted_transparently(self):
        _set_layout(show_soft_deleted=True)
        with _ThreadLocalUser(self.su):
            # A plain `objects.all()` now includes the deleted row — no view change.
            self.assertEqual(DluxNotification.objects.count(), 2)
        with _ThreadLocalUser(self.plain):
            self.assertEqual(DluxNotification.objects.count(), 1)  # not superadmin → still hidden

    def test_setting_off_keeps_soft_deleted_hidden_for_superadmin(self):
        _set_layout(show_soft_deleted=False)
        with _ThreadLocalUser(self.su):
            self.assertEqual(DluxNotification.objects.count(), 1)

    def test_force_hide_overrides_review_mode(self):
        from dlux.managers import force_hide_deleted

        _set_layout(show_soft_deleted=True)
        with _ThreadLocalUser(self.su):
            self.assertEqual(DluxNotification.objects.count(), 2)  # review mode: visible
            with force_hide_deleted():
                self.assertEqual(DluxNotification.objects.count(), 1)  # forced hidden


class PickerGuardTests(TestCase):
    """Even in the superadmin review mode, a related picker must never offer
    soft-deleted rows (approach B: transparent reads, safe mutation)."""

    def test_related_picker_excludes_soft_deleted_in_review_mode(self):
        from django import forms

        su = User.objects.create_superuser('su', 'su@e.com', 'pw12345!x')
        keep = DluxNotification.objects.create(title='keep', message='m')
        gone = DluxNotification.objects.create(title='gone', message='m')
        gone.delete()
        _set_layout(show_soft_deleted=True)

        class PickerForm(forms.ModelForm):
            picker = forms.ModelChoiceField(queryset=DluxNotification.objects.all(), required=False)

            class Meta:
                model = DluxNotification
                fields = ['title']

        with _ThreadLocalUser(su):
            form = PickerForm()
            ids = set(form.fields['picker'].queryset.values_list('pk', flat=True))
        self.assertIn(keep.pk, ids)
        self.assertNotIn(gone.pk, ids)  # excluded despite review mode


class SettingsPersistenceTests(TestCase):
    """Regression for the reported "toggles turn themselves off": the JSON-only
    flags must survive the settings save path (they were dropped by the export
    whitelist) AND be preserved when a *different* settings step is saved."""

    def setUp(self):
        self.admin = User.objects.create_superuser('su', 'su@e.com', 'pw12345!x')
        s = SystemSettings.load()
        s.is_configured = True
        s.save()

    def test_apply_settings_persists_the_flags(self):
        from dlux.utils.import_export import apply_system_settings_import

        s = SystemSettings.load()
        apply_system_settings_import(
            s, {'show_audit_fields': True, 'show_soft_deleted': True}, mark_configured=False
        )
        reloaded = SystemSettings.load()
        self.assertTrue(getattr(reloaded, 'show_audit_fields'))
        self.assertTrue(getattr(reloaded, 'show_soft_deleted'))
        self.assertTrue(reloaded.layout_config.get('show_audit_fields'))

    def test_flags_survive_saving_a_different_step(self):
        from django.test import RequestFactory
        from dlux.forms import SystemSettingsForm
        from dlux.utils.import_export import apply_system_settings_import

        apply_system_settings_import(
            SystemSettings.load(), {'show_audit_fields': True, 'show_soft_deleted': True},
            mark_configured=False,
        )
        # A single-step save of another step (3) must preserve the stored values,
        # not read their absence as False.
        req = RequestFactory().post('/?step=3', {'x': '1'})
        req.user = self.admin
        form = SystemSettingsForm(
            data={'x': '1'}, instance=SystemSettings.load(), request=req, mode='modal'
        )
        form.cleaned_data = {}
        self.assertTrue(form._clean_preserved_toggle('show_audit_fields', 9, False))
        self.assertTrue(form._clean_preserved_toggle('show_soft_deleted', 9, False))

    def test_flags_are_in_the_export_whitelist(self):
        from dlux.utils.import_export import SYSTEM_SETTINGS_EXPORT_FIELDS

        self.assertIn('show_audit_fields', SYSTEM_SETTINGS_EXPORT_FIELDS)
        self.assertIn('show_soft_deleted', SYSTEM_SETTINGS_EXPORT_FIELDS)


class LayoutConfigNormalizerTests(TestCase):
    def test_normalizer_coerces_and_defaults_the_new_flags(self):
        out = normalize_layout_config({'show_audit_fields': 'yes', 'show_soft_deleted': 1})
        self.assertTrue(out['show_audit_fields'])
        self.assertTrue(out['show_soft_deleted'])
        empty = normalize_layout_config({})
        self.assertFalse(empty['show_audit_fields'])
        self.assertFalse(empty['show_soft_deleted'])


class AuditToggleCanBeTurnedBackOffTests(TestCase):
    """Turning the audit toggle off must actually store False.

    Every other test in this module writes `layout_config` straight onto the
    model, so they all prove the *render* path and none of them exercise the
    *save* path. And they only ever assert the flag going on or surviving an
    unrelated step's save — the one direction never covered is the one that was
    reported from production: on once, then off, and the columns never went away.
    """

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username='audit-toggle-admin', email='a@example.com', password='x'
        )

    def _save_security_step(self, settings_obj, **overrides):
        from dlux.forms import SystemSettingsForm

        data = {
            'system_names': '{"en":"System","ar":"System"}',
            'home_url': '/accounts/profile/',
            'default_language': 'en',
            'default_theme': 'light',
            'allowed_themes': ['light'],
            'languages': '{}',
            'translations_override': '{}',
            'sidebar_config': '{"entries":[]}',
            'default_table_density': 'balanced',
            'table_edges': 'curved',
            'card_edges': 'curved',
            'default_form_density': 'balanced',
            'default_modal_size': 'standard',
            'row_actions_style': 'context',
            'ribbon_layout': 'default',
            'ribbon_style': 'accent',
            'ribbon_advanced_trigger': 'button',
        }
        data.update(overrides)
        request = RequestFactory().get(
            f'/sys/modals/dlux/systemsettings/{settings_obj.pk}/?step={SETUP_STEP_SECURITY}'
        )
        request.user = self.admin
        form = SystemSettingsForm(data=data, instance=settings_obj, request=request)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save(commit=False)
        saved.save()
        return saved

    def test_the_audit_toggle_goes_off_again(self):
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save()

        # On: the checkbox is present in the POST.
        settings_obj = self._save_security_step(settings_obj, show_audit_fields='on')
        self.assertIs(
            settings_obj.layout_config.get('show_audit_fields'), True,
            'turning the audit toggle on did not store True',
        )

        # Off: an unchecked checkbox is simply absent from the POST.
        settings_obj = self._save_security_step(settings_obj)
        self.assertIs(
            settings_obj.layout_config.get('show_audit_fields'), False,
            'the audit toggle could be turned on but never off — the stored value '
            'won over the submitted one, so the columns stayed visible for good',
        )
        # The field is `legacy_flat`, so a mirrored column exists too. If the two
        # disagree, whichever one the runtime reads decides, and the UI lies.
        self.assertIs(
            getattr(SystemSettings.load(), 'show_audit_fields'), False,
            'layout_config went False but the mirrored flat column stayed True',
        )
        from dlux.utils.config import get_system_config
        self.assertIs(
            bool(get_system_config().get('show_audit_fields')), False,
            'the stored value is False but the effective runtime config still reads True',
        )

    def test_the_soft_deleted_toggle_goes_off_again(self):
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save()

        settings_obj = self._save_security_step(settings_obj, show_soft_deleted='on')
        self.assertIs(settings_obj.layout_config.get('show_soft_deleted'), True)

        settings_obj = self._save_security_step(settings_obj)
        self.assertIs(settings_obj.layout_config.get('show_soft_deleted'), False)


class RecordVisibilityTogglesSaveFromTheirOwnStepTests(TestCase):
    """The audit/soft-delete toggles must save from the step that shows them.

    They render under Access & Security ("Record Visibility"), but their clean
    methods anchored them to the Components step. `_clean_preserved_toggle`
    restores the stored value whenever the step being saved is not the anchored
    one — so saving Access & Security, the only place these switches appear,
    silently discarded the change. They could be turned on by a first-launch
    config.json and then never turned off from the UI again.
    """

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username='visibility-admin', email='v@example.com', password='x'
        )

    def _save_step(self, settings_obj, step, **overrides):
        from dlux.forms import SystemSettingsForm

        data = {
            'system_names': '{"en":"System","ar":"System"}',
            'home_url': '/accounts/profile/',
            'default_language': 'en', 'default_theme': 'light', 'allowed_themes': ['light'],
            'languages': '{}', 'translations_override': '{}', 'sidebar_config': '{"entries":[]}',
            'default_table_density': 'balanced', 'table_edges': 'curved', 'card_edges': 'curved',
            'default_form_density': 'balanced', 'default_modal_size': 'standard',
            'row_actions_style': 'context', 'ribbon_layout': 'default', 'ribbon_style': 'accent',
            'ribbon_advanced_trigger': 'button',
        }
        data.update(overrides)
        request = RequestFactory().get(
            f'/sys/modals/dlux/systemsettings/{settings_obj.pk}/?step={step}'
        )
        request.user = self.admin
        form = SystemSettingsForm(data=data, instance=settings_obj, request=request)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save(commit=False)
        saved.save()
        return saved

    def _configured(self, **layout):
        s = SystemSettings.load()
        s.is_configured = True
        s.layout_config = {**(s.layout_config or {}), **layout}
        for key, value in layout.items():
            setattr(s, key, value)
        s.save()
        return s

    def test_audit_fields_can_be_turned_off_from_access_and_security(self):
        s = self._configured(show_audit_fields=True)
        # Unchecked switch = absent from the POST, saved from the step it renders in.
        s = self._save_step(s, SETUP_STEP_SECURITY)
        self.assertIs(
            s.layout_config.get('show_audit_fields'), False,
            'saving Access & Security discarded the change: the toggle renders there '
            'but is anchored to the Components step, so it can never be turned off',
        )

    def test_soft_deleted_can_be_turned_off_from_access_and_security(self):
        s = self._configured(show_soft_deleted=True)
        s = self._save_step(s, SETUP_STEP_SECURITY)
        self.assertIs(s.layout_config.get('show_soft_deleted'), False)

    def test_saving_an_unrelated_step_still_preserves_them(self):
        # The guard's real purpose must survive the fix.
        s = self._configured(show_audit_fields=True, show_soft_deleted=True)
        s = self._save_step(s, SETUP_STEP_LAYOUT)
        self.assertIs(s.layout_config.get('show_audit_fields'), True)
        self.assertIs(s.layout_config.get('show_soft_deleted'), True)
