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
from django.test import RequestFactory, SimpleTestCase

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


class ImportCompatTests(SimpleTestCase):
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
