"""Compatibility surfaces downstream projects depend on.

The v1.8.0 reorganisation moved most of the package. Everything a project can
reference from outside — a template path, a static path, an import — is pinned
here, so a later cleanup cannot quietly delete a shim that something still uses.

Each entry corresponds to a `docs/deprecation-countdown.md` record. When a shim
is finally removed, delete its assertion here in the same commit.
"""
from dlux.tests.harness import setup_test_environment

setup_test_environment()

import pathlib
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.template import Context, Template
from django.template import TemplateDoesNotExist
from django.template.loader import get_template, render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase

from dlux.context_processors import dlux_context

PACKAGE = pathlib.Path(__file__).resolve().parents[1]

# Old path -> new path. Kept working by a shim; both must resolve.
TEMPLATE_SHIMS = {
    'dlux/includes/messages.html': 'dlux/notifications/messages.html',
}

STATIC_SHIMS = {
    'dlux/main/css/main.css': 'dlux/base/css/main.css',
    'dlux/main/css/buttons.css': 'dlux/base/css/buttons.css',
    'dlux/main/css/index_cards.css': 'dlux/base/css/index_cards.css',
}

# Templates the six active projects include or extend directly (audited 2026-08-10).
PROJECT_TEMPLATES = [
    'dlux/base.html',
    'dlux/form_base.html',
    'dlux/list_base.html',
    'dlux/forms/assets_head.html',
    'dlux/forms/assets_scripts.html',
    'dlux/helpers/dynamic_modal_form.html',
]

# The project extension namespace: dlux renders these if a project supplies them.
EXTENSION_HOOKS = [
    'dlux/includes/custom_head.html',
    'dlux/includes/custom_scripts.html',
    'dlux/includes/custom_footer.html',
]


class TemplateCompatTests(SimpleTestCase):
    def test_templates_projects_reference_directly_still_resolve(self):
        missing = []
        for name in PROJECT_TEMPLATES:
            try:
                get_template(name)
            except TemplateDoesNotExist:
                missing.append(name)

        self.assertEqual(
            missing, [],
            f'Template(s) removed that active projects include by path: {missing}. '
            'Leave a shim at the old path and record it in docs/deprecation-countdown.md.',
        )

    def test_shimmed_template_paths_resolve_and_match_their_target(self):
        for old, new in TEMPLATE_SHIMS.items():
            with self.subTest(shim=old):
                get_template(old)
                get_template(new)
                self.assertEqual(
                    render_to_string(old, {}).strip(),
                    render_to_string(new, {}).strip(),
                    f'{old} no longer renders the same as {new}.',
                )

    def test_extension_hook_paths_are_unchanged(self):
        """These are project-supplied; dlux must keep looking for these names."""
        base = (PACKAGE / 'templates' / 'dlux' / 'base.html').read_text(encoding='utf-8')
        footer = (PACKAGE / 'templates' / 'dlux' / 'system' / 'footer.html').read_text(encoding='utf-8')
        combined = base + footer
        for hook in EXTENSION_HOOKS:
            with self.subTest(hook=hook):
                self.assertIn(hook, combined)


class FormBaseTemplateTests(SimpleTestCase):
    def _context(self):
        request = RequestFactory().get('/form/')
        request.user = AnonymousUser()
        request.session = {}
        request.resolver_match = SimpleNamespace(url_name='form')
        with patch('dlux.context_processors.is_scope_enabled', return_value=False):
            return {'request': request, **dlux_context(request)}

    def test_form_base_renders_an_opt_in_footer_after_form_content(self):
        html = Template(
            "{% extends 'dlux/form_base.html' %}"
            "{% block form_content %}<form id=\"example-form\">Fields</form>{% endblock %}"
            "{% block form_footer %}<footer class=\"dlux-form-footer\">"
            "<button type=\"submit\" form=\"example-form\">Save</button>"
            "</footer>{% endblock %}"
        ).render(Context(self._context()))

        self.assertLess(html.index('id="example-form"'), html.index('dlux-form-footer'))
        self.assertIn('form="example-form"', html)
        self.assertIn('class="dlux-form-page"', html)

    def test_form_base_footer_has_no_default_output(self):
        html = Template(
            "{% extends 'dlux/form_base.html' %}"
            "{% block form_content %}<form id=\"example-form\">Fields</form>{% endblock %}"
        ).render(Context(self._context()))

        self.assertNotIn('dlux-form-footer', html)

    def test_form_footer_sticks_inside_a_page_local_scroll_boundary(self):
        styles = (PACKAGE / 'static' / 'dlux' / 'forms' / 'css' / 'form_actions.css').read_text(encoding='utf-8')

        self.assertIn('@media (min-width: 768px)', styles)
        self.assertIn('.dlux-form-page {', styles)
        self.assertIn('contain: layout;', styles)
        self.assertIn('position: sticky;', styles)
        self.assertIn('bottom: -1.5rem;', styles)
        self.assertIn('body:has(.dlux-footer) .dlux-form-footer', styles)
        self.assertIn('bottom: calc(1.35rem - 1.5rem);', styles)
        self.assertNotIn('padding-block-end: 8rem;', styles)
        self.assertNotIn('transform: translateY(1.5rem);', styles)


class StaticCompatTests(SimpleTestCase):
    def test_shimmed_static_paths_exist_and_point_at_the_new_file(self):
        for old, new in STATIC_SHIMS.items():
            with self.subTest(shim=old):
                old_path = PACKAGE / 'static' / old
                new_path = PACKAGE / 'static' / new
                self.assertTrue(old_path.exists(), f'{old} shim is gone; projects link it.')
                self.assertTrue(new_path.exists(), f'{new} (shim target) is missing.')
                self.assertIn(
                    pathlib.Path(new).name, old_path.read_text(encoding='utf-8'),
                    f'{old} no longer imports {new}.',
                )


class EmbeddedStringsBlockTests(SimpleTestCase):
    """Trademarks' dashboard parses ``#dlux-strings-data``; base_head.js keeps an
    element by that id that serialises ``window.DLUX_STRINGS`` until v2.0."""

    def test_base_head_keeps_the_legacy_strings_element(self):
        source = (PACKAGE / 'static' / 'dlux' / 'base' / 'js' / 'base_head.js').read_text(encoding='utf-8')
        self.assertIn("legacyStrings.id = 'dlux-strings-data'", source)
        self.assertIn('JSON.stringify(window.DLUX_STRINGS', source)


class ImportCompatTests(SimpleTestCase):
    def test_the_archive_file_names_were_removed_in_1_10(self):
        """`build_archive_file_field` and `_build_archive_file_widget` are gone; the framework names remain."""
        from dlux import forms

        self.assertFalse(hasattr(forms, 'build_archive_file_field'))
        self.assertFalse(hasattr(forms, '_build_archive_file_widget'))
        self.assertNotIn('build_archive_file_field', forms.__all__)
        self.assertTrue(callable(forms.build_file_field))

    def test_the_old_archive_file_translation_keys_no_longer_apply(self):
        from unittest import mock

        from dlux.widgets import DluxFileInput

        with mock.patch(
            'dlux.translations.get_strings',
            return_value={'archive_file_empty_title': 'Legacy title', 'file_field_upload_action': 'Pick'},
        ):
            context = DluxFileInput().get_context('f', None, {'id': 'id_f'})

        self.assertEqual(context['widget']['empty_title'], 'No file selected')
        self.assertEqual(context['widget']['upload_action'], 'Pick')

    def test_the_archive_file_input_class_no_longer_selects_the_file_template(self):
        from django import forms as django_forms
        from django.template.loader import render_to_string

        class LegacyForm(django_forms.Form):
            doc = django_forms.FileField(
                widget=django_forms.ClearableFileInput(attrs={'class': 'archive-file-input'}),
            )

        html = render_to_string('dlux/forms/crispy_file_field.html', {'field': LegacyForm()['doc']})

        # Without the shim the widget takes the ordinary `form-control` branch.
        self.assertIn('form-control', html)

    def test_relocated_archive_helpers_are_still_importable_from_reports(self):
        """dlux.backup used to get these from dlux.reports; both paths must work."""
        import dlux.reports as reports
        import dlux.utils.archive as archive
        import dlux.utils.common as common

        for name in ('_CursorlessJSONSerializer', '_model_natural_key_fields',
                     '_safe_archive_segment', 'stream_model_into_zip'):
            with self.subTest(name=name):
                self.assertIs(getattr(reports, name), getattr(archive, name))

        from dlux.reports.queries import _iter_queryset_by_pk

        self.assertIs(_iter_queryset_by_pk, common._iter_queryset_by_pk)

    def test_reports_wrappers_keep_the_config_driven_label_default(self):
        """The utils versions default to no resolver; the reports ones must not."""
        import inspect

        from dlux.reports.archive import backup_record_folder, build_relation_schema

        for func in (backup_record_folder, build_relation_schema):
            with self.subTest(func=func.__name__):
                source = inspect.getsource(func)
                self.assertIn(
                    '_backup_label_field', source,
                    f'{func.__name__} stopped applying the reports label resolver — '
                    'record folders would silently change name.',
                )


class CeleryEraNamesTests(SimpleTestCase):
    """Kept until 1.18.0 (deprecation countdown, "Celery for project tasks")."""

    def test_the_backup_availability_aliases_still_import(self):
        from dlux.backup import system_backup_celery_available, system_backup_worker_available
        from dlux.reports import report_backup_celery_available, report_backup_worker_available

        self.assertIs(system_backup_celery_available, system_backup_worker_available)
        self.assertIs(report_backup_celery_available, report_backup_worker_available)

    def test_dlux_tasks_keeps_its_attribute_names(self):
        from dlux import jobs, tasks

        for attribute, name in (
            ("build_report_backup_task", "build_report_backup"),
            ("build_system_backup_task", "build_system_backup"),
            ("restore_system_backup_task", "restore_system_backup"),
            ("run_scheduled_system_backup_task", "run_scheduled_system_backup"),
            ("weather_refresh_task", "weather_refresh"),
            ("weather_search_task", "weather_search"),
            ("dlux_update_check_task", "dlux_update_check"),
            ("dlux_state_tick_task", "dlux_state_tick"),
            ("ocr_background", "ocr_background"),
            ("ocr_file", "ocr_file"),
            ("reap_stalled_system_backups_task", "reap_stalled_system_backups"),
        ):
            self.assertIs(getattr(tasks, attribute), getattr(jobs, name), attribute)
            self.assertEqual(getattr(tasks, attribute).name, f"dlux.tasks.{name}")

    def test_dlux_settings_still_defines_a_beat_schedule_projects_can_add_to(self):
        """dlux-panel assigns CELERY_BEAT_SCHEDULE[...] right after dlux_settings()."""
        from dlux.utils.settings import dlux_settings

        scope = {}
        dlux_settings(scope)
        scope["CELERY_BEAT_SCHEDULE"]["fleet-prune-operation-logs"] = {"task": "fleet.prune", "schedule": 86400}
        self.assertNotIn("dlux-state-tick", scope["CELERY_BEAT_SCHEDULE"])


class OnDemandAssetCompatTests(SimpleTestCase):
    """Shims for assets that stopped loading on every page (docs/deprecation-countdown.md:
    `pdfjsLib` before PDF.js loads, `dlux/tutorial/main.html`)."""

    def test_pdfjslib_stand_in_is_set_up_by_the_pdf_assets(self):
        assets = (PACKAGE / 'templates' / 'dlux/pdf/assets.html').read_text(encoding='utf-8')
        self.assertIn('dlux/pdf/js/pdfjs.js', assets)
        shim = (PACKAGE / 'static' / 'dlux/pdf/js/pdfjs.js').read_text(encoding='utf-8')
        # Archive's composition/js/paper.js: window.pdfjsLib.getDocument({data}).promise
        self.assertIn('if (!window.pdfjsLib) {', shim)
        self.assertIn('getDocument: function (source)', shim)
        self.assertIn('promise: promise', shim)
        self.assertIn('GlobalWorkerOptions', shim)

    def test_tutorial_template_still_resolves_and_renders_nothing(self):
        html = render_to_string('dlux/tutorial/main.html', {'request': SimpleNamespace(csp_nonce='n')})
        self.assertEqual(html.strip(), '')

    def test_locked_toggle_dimming_still_loads_on_every_page(self):
        # Archive and Decrees forms render server-locked build_settings_toggle_field() cards.
        toggle_css = (PACKAGE / 'static' / 'dlux/helpers/toggle/css/main.css').read_text(encoding='utf-8')
        self.assertIn('.dlux-dependent-settings.is-disabled,', toggle_css)
        base = (PACKAGE / 'templates' / 'dlux/base.html').read_text(encoding='utf-8')
        self.assertIn('dlux/helpers/toggle/css/main.css', base)

    def test_settings_globals_still_load_with_settings_markup(self):
        from dlux.lazy_assets import ASSET_BUNDLES
        settings = ASSET_BUNDLES['settings']
        for path in ('dlux/setup/js/dom.js', 'dlux/helpers/inspector/js/main.js', 'dlux/helpers/icon_picker/js/main.js'):
            with self.subTest(path=path):
                self.assertIn(path, settings['js'])
        for selector in ('form.dlux-system-setup-form', '[data-dlux-icon-picker]', '[data-dlux-assets~="settings"]'):
            with self.subTest(selector=selector):
                self.assertIn(selector, settings['selector'])


class SingletonCacheKeyTests(TestCase):
    """Projects invalidate the cached System Settings row with
    ``cache.delete("SystemSettings")``: CRM sales in migrations after a raw update
    (``machinery/0002``, ``public_catalog/0001`` and ``0003``), and Archive and
    CRM sales in their tests. The key must stay the class name."""

    def test_deleting_the_class_name_key_invalidates_the_row(self):
        from django.core.cache import cache
        from dlux.models import SystemSettings

        row = SystemSettings.load()
        row.home_url = "/before/"
        row.save()
        SystemSettings.objects.filter(pk=1).update(home_url="/migrated/")
        cache.delete("SystemSettings")
        self.assertEqual(SystemSettings.load().home_url, "/migrated/")

