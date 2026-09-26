"""System Settings previews render real pages with the unsaved form.

The draft endpoint validates the form and parks it under a token; a GET carrying
that token renders an ordinary page with the draft standing in for the stored
settings. These tests pin the three promises that makes: the page shows the
draft, nothing is ever written, and only the superuser who made the draft can
see it.
"""

import re
from pathlib import Path

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from dlux.models import SystemSettings
from dlux.system import preview as settings_preview
from dlux.tests.test_accent_edges import _form_data


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SETUP_JS = PACKAGE_ROOT / 'static' / 'dlux' / 'setup' / 'js'
User = get_user_model()
FOOTER = 'Draft footer 7c1e'
SAMPLE_KINDS = ('table', 'form', 'modal', 'components')


class PreviewModuleTests(SimpleTestCase):
    def test_preview_script_loads_after_its_dependencies_and_before_main(self):
        template = (PACKAGE_ROOT / 'templates' / 'dlux' / 'base.html').read_text()
        language = template.index("dlux/setup/js/language.js")
        shell = template.index("dlux/setup/js/shell.js")
        previews = template.index("dlux/setup/js/previews.js")
        main = template.index("dlux/setup/js/main.js")
        self.assertLess(language, previews)
        self.assertLess(shell, previews)
        self.assertLess(previews, main)

    def test_previews_render_on_the_server_instead_of_patching_the_page(self):
        source = (SETUP_JS / 'previews.js').read_text()
        self.assertIn('settingsPreviewDraft', source)
        for retired in ('applyTitlebarPreview', 'applySidebarPreview', 'buildPopupShell', 'applyLayoutPreview'):
            self.assertNotIn(retired, source)

    def test_every_preview_eye_names_a_target_the_endpoint_offers(self):
        source = (PACKAGE_ROOT / 'forms' / 'system_settings_groups' / 'layout.py').read_text()
        used = re.findall(r"_preview_eye\(s, '([a-z_]+)'\)", source)
        # Eyes only where the step's own Preview cannot show the subject: the
        # Options page has no tables, forms or modals to lift the modal off.
        self.assertEqual(sorted(used), ['sample_form', 'sample_modal', 'sample_table', 'sample_table'])


class _PreviewCase(TestCase):
    def setUp(self):
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save()
        cache.clear()
        self.admin = User.objects.create_superuser('preview-admin', 'admin@example.com', 'pw')
        self.client.force_login(self.admin)

    def draft(self, **overrides):
        return self.client.post(
            reverse('system_settings_preview_draft'),
            _form_data(footer_enabled='on', footer_text=FOOTER, **overrides),
        )

    def token(self, **overrides):
        response = self.draft(**overrides)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()['token']

    def preview(self, path, token, **params):
        return self.client.get(path, {settings_preview.PREVIEW_PARAM: token, **params})

    def sample(self, kind):
        return reverse('system_settings_preview_sample', kwargs={'kind': kind})


class DraftEndpointTests(_PreviewCase):
    def test_a_valid_draft_answers_with_a_token_and_the_real_targets(self):
        payload = self.draft().json()
        self.assertTrue(payload['ok'])
        self.assertTrue(payload['token'])
        self.assertEqual(payload['targets']['login'], {'path': reverse('login'), 'audience': 'anonymous'})
        for kind in SAMPLE_KINDS:
            self.assertIn(f'sample_{kind}', payload['targets'])

    def test_an_invalid_draft_reports_its_errors_and_stores_nothing(self):
        response = self.draft(allowed_themes=[])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])
        self.assertIn('allowed_themes', response.json()['errors'])
        self.assertFalse(self.client.session.get(settings_preview.SESSION_KEY))

    def test_a_draft_is_never_saved(self):
        self.draft()
        stored = SystemSettings.objects.get()
        self.assertNotEqual((stored.layout_config or {}).get('footer_text'), FOOTER)

    def test_only_a_superuser_may_draft_and_only_by_post(self):
        self.assertEqual(self.client.get(reverse('system_settings_preview_draft')).status_code, 405)
        staff = User.objects.create_user('staff', 'staff@example.com', 'pw', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.draft().status_code, 403)

    def test_an_options_step_is_validated_like_its_own_save(self):
        # The Options modal posts the titlebar step with ?step=5, as its save does;
        # unchecked toggles are simply absent and must read as off.
        response = self.client.post(
            reverse('system_settings_preview_draft') + '?step=5',
            _form_data(titlebar_title_align='center'),
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = self.preview(self.sample('components'), response.json()['token']).content.decode()
        self.assertIn('data-title-align="center"', body)
        self.assertIn('data-titlebar-show-title="false"', body)


class PreviewRenderTests(_PreviewCase):
    def test_the_page_renders_the_draft_and_only_with_its_token(self):
        token = self.token()
        self.assertIn(FOOTER, self.preview(self.sample('components'), token).content.decode())
        self.assertNotIn(FOOTER, self.client.get(reverse('user_profile')).content.decode())
        self.assertIn(FOOTER, self.preview(reverse('user_profile'), token).content.decode())

    def test_nothing_the_preview_renders_is_kept(self):
        token = self.token()
        session_before = dict(self.client.session.items())
        self.preview(reverse('user_profile'), token)
        stored = SystemSettings.objects.get()
        self.assertNotEqual((stored.layout_config or {}).get('footer_text'), FOOTER)
        self.assertEqual(session_before, dict(self.client.session.items()))
        self.assertNotIn(FOOTER, self.client.get(reverse('user_profile')).content.decode())

    def test_a_preview_response_is_inert_uncached_and_frameable_only_by_us(self):
        response = self.preview(self.sample('components'), self.token())
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')
        body = response.content.decode()
        self.assertIn('data-dlux-preview-guard', body)
        self.assertRegex(body, r'<html data-dlux-preview[ >]', 'marked before first paint')
        # CSP: the guard is a static script, never inline code.
        guard = re.search(r'<script[^>]*data-dlux-preview-guard[^>]*>(.*?)</script>', body, re.S)
        self.assertIsNotNone(guard)
        self.assertIn('src="', guard.group(0))
        self.assertIn(settings_preview.GUARD_SCRIPT_PATH, guard.group(0))
        self.assertEqual(guard.group(1).strip(), '')

    def test_a_token_is_useless_to_anyone_but_its_superuser(self):
        token = self.token()
        other = User.objects.create_superuser('other-admin', 'other@example.com', 'pw')
        self.client.force_login(other)
        self.assertNotIn(FOOTER, self.preview(reverse('user_profile'), token).content.decode())
        self.assertEqual(self.preview(self.sample('components'), token).status_code, 404)

    def test_an_unknown_token_renders_the_stored_settings(self):
        self.token()
        self.assertNotIn(FOOTER, self.preview(reverse('user_profile'), 'not-a-token').content.decode())

    def test_a_post_is_never_a_preview(self):
        token = self.token()
        url = reverse('user_profile') + f'?{settings_preview.PREVIEW_PARAM}={token}'
        self.assertNotIn(FOOTER, self.client.post(url, {}).content.decode())

    def test_the_draft_default_language_is_the_preview_language(self):
        languages = '{"en": {"name": "English", "dir": "ltr"}, "ar": {"name": "Arabic", "dir": "rtl"}}'
        token = self.token(default_language='ar', languages=languages)
        body = self.preview(self.sample('components'), token).content.decode()
        self.assertIn('lang="ar"', body)
        self.assertIn('dir="rtl"', body)
        english = self.preview(self.sample('components'), token, **{settings_preview.LANG_PARAM: 'en'})
        self.assertIn('lang="en"', english.content.decode())

    def test_personal_preferences_do_not_mask_the_defaults_being_edited(self):
        profile = self.admin.profile
        profile.preferences = {'theme': 'dark'}
        profile.save()
        body = self.preview(self.sample('components'), self.token(default_theme='light')).content.decode()
        self.assertNotIn('"theme": "dark"', body)
        profile.refresh_from_db()
        self.assertEqual(profile.preferences.get('theme'), 'dark')

    def test_the_login_page_renders_for_a_visitor(self):
        response = self.preview(reverse('login'), self.token(), **{settings_preview.AS_PARAM: 'anonymous'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="password"', response.content.decode())

    def test_a_redirect_keeps_the_preview(self):
        request = RequestFactory().get('/')
        request.dlux_preview = {'token': 'tok', 'audience': ''}
        response = settings_preview.finish(request, HttpResponseRedirect('/somewhere/?a=1'))
        self.assertIn(f'{settings_preview.PREVIEW_PARAM}=tok', response['Location'])
        self.assertIn('a=1', response['Location'])


class SamplePageTests(_PreviewCase):
    def test_sample_pages_exist_only_inside_a_preview(self):
        for kind in SAMPLE_KINDS:
            self.assertEqual(self.client.get(self.sample(kind)).status_code, 404)
        self.assertEqual(self.client.get(reverse('system_settings_preview_sample_modal')).status_code, 404)

    def test_the_table_sample_is_a_real_ribbon_list_page(self):
        body = self.preview(self.sample('table'), self.token()).content.decode()
        self.assertIn('dlux-ribbon', body)
        self.assertIn('dlux-data-table', body)
        self.assertIn('sample_status', body)
        # The year strip nests under the status strip (chain nesting by default).
        chosen = self.preview(self.sample('table'), self.token(), sample_status='active').content.decode()
        self.assertIn('sample_year', chosen)

    def test_the_modal_sample_opens_the_real_dynamic_modal_with_a_form(self):
        token = self.token()
        page = self.preview(self.sample('modal'), token).content.decode()
        self.assertIn('dlux/system/js/preview_sample_modal.js', page)
        self.assertIn('dlux-preview-modal-url', page)
        self.assertIn(settings_preview.PREVIEW_PARAM, page)
        script = (PACKAGE_ROOT / 'static' / 'dlux' / 'system' / 'js' / 'preview_sample_modal.js').read_text()
        self.assertIn('dlux:dynamic_modal:open', script)
        content = self.preview(reverse('system_settings_preview_sample_modal'), token)
        self.assertEqual(content.status_code, 200)
        self.assertIn('dlux-form', content.json()['html'])

    def test_the_form_sample_uses_the_shared_form_markup(self):
        body = self.preview(self.sample('form'), self.token()).content.decode()
        self.assertIn('dlux-form-action-primary', body)


class FooterPlacementTests(TestCase):
    """The global footer belongs to configured pages, and stays on screen while
    System Settings are edited from Options (its own settings live there)."""

    def test_the_first_run_setup_pages_have_no_global_footer(self):
        for name in ('setup/main.html', 'setup/language.html'):
            template = (PACKAGE_ROOT / 'templates' / 'dlux' / name).read_text()
            self.assertIn('{% block footer %}{% endblock %}', template)

    def test_an_open_modal_does_not_hide_the_footer(self):
        css = (PACKAGE_ROOT / 'static' / 'dlux' / 'system' / 'css' / 'footer.css').read_text()
        rule = css[css.index('body.modal-open .dlux-footer'):]
        rule = rule[:rule.index('}')]
        self.assertNotIn('display: none', rule)
        self.assertIn('backdrop-filter: none', rule)


class LanguageFontRuleTests(TestCase):
    def test_a_language_default_font_must_be_an_allowed_font(self):
        from django.core.cache import cache as _cache

        from dlux.fonts import get_available_fonts
        from dlux.forms import SystemSettingsForm

        slugs = [font['slug'] for font in get_available_fonts()]
        self.assertGreaterEqual(len(slugs), 2)
        allowed, disallowed = slugs[0], slugs[1]
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save()
        _cache.clear()
        form = SystemSettingsForm(
            data=_form_data(allowed_fonts=[allowed], default_fonts=f'{{"en": "{disallowed}", "ar": "{allowed}"}}'),
            instance=SystemSettings.objects.get(),
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['default_fonts'], {'en': allowed, 'ar': allowed})
