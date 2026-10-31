import re
import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from dlux.files.media import APP_ONLY_MEDIA, PUBLIC_MEDIA, media_decision, media_name
from dlux.files.registry import register_document_file, unregister_document_file
from dlux.models import Scope, ScopeSettings, SystemSettings
from dlux.tests.document_files_app.models import Paper

PROXY_TEMPLATES = Path(__file__).resolve().parents[1] / 'scaffold' / 'templates' / 'project' / '.proxy'


class MediaNameTests(SimpleTestCase):
    def test_names_are_decoded_and_normalised_like_the_file_server(self):
        self.assertEqual(media_name('/media/papers/a.pdf'), 'papers/a.pdf')
        self.assertEqual(media_name('/media/papers//./a.pdf?download=1'), 'papers/a.pdf')
        self.assertEqual(media_name('/media/papers%2Fa%20b.pdf'), 'papers/a b.pdf')
        self.assertEqual(media_name('/media/public/%2e%2e/papers/a.pdf'), 'papers/a.pdf')

    def test_anything_outside_media_or_climbing_out_is_refused(self):
        for uri in ('', '/static/a.css', '/media/', '/media/..', '/media/papers/../../etc/passwd',
                    '/media/%2e%2e/secret', '/media/a%00b.pdf', '/media/a%5cb.pdf', '/MEDIA/papers/a.pdf'):
            with self.subTest(uri=uri):
                self.assertIsNone(media_name(uri))


class MediaAccessTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        settings_obj = SystemSettings.load()
        settings_obj.is_configured = True
        settings_obj.save()
        cache.clear()
        self.addCleanup(cache.clear)
        register_document_file(Paper, 'pdf_file')
        self.addCleanup(unregister_document_file, Paper, 'pdf_file')
        User = get_user_model()
        self.admin = User.objects.create_superuser('media-admin', 'media-admin@example.com', 'pw12345!')
        self.reader = User.objects.create_user('media-reader', password='pw12345!')
        self.reader.user_permissions.add(Permission.objects.get(codename='view_paper'))
        self.stranger = User.objects.create_user('media-stranger', password='pw12345!')
        self.paper = Paper.objects.create(title='Annual report')
        self.paper.pdf_file.save('original.pdf', ContentFile(b'%PDF-1.4'))
        self.name = self.paper.pdf_file.name

    def decide(self, user, name):
        request = RequestFactory().get('/sys/files/media-access/')
        request.user = user
        return media_decision(request, name)

    def ask(self, uri, user=None, **headers):
        self.client.logout()
        if user is not None:
            self.client.force_login(user)
        return self.client.get(reverse('dlux_media_access'), HTTP_X_FORWARDED_URI=uri, **headers)

    def test_public_folders_are_served_to_anyone(self):
        from django.contrib.auth.models import AnonymousUser

        for name in ('public/flyer.pdf', 'dlux/branding/logo.png', 'dlux/assets/image/dlux.systemsettings/a.png',
                     'dlux/assets/font/dlux.fonts/a.woff2', 'PUBLIC/flyer.pdf'):
            with self.subTest(name=name):
                self.assertTrue(self.decide(AnonymousUser(), name))

    def test_app_only_folders_are_refused_even_to_a_superuser(self):
        for name in ('dlux_backups/full.dlb', 'DLUX_BACKUPS/full.dlb', 'dlux/assets/private/installer/x/a.msi',
                     'dlux/file_history/document_files_app_paper/1/pdf_file/v1_original.pdf'):
            with self.subTest(name=name):
                self.assertFalse(self.decide(self.admin, name))

    def test_private_media_needs_a_signed_in_user(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertFalse(self.decide(AnonymousUser(), 'profile_pictures/me.png'))
        self.assertTrue(self.decide(self.stranger, 'profile_pictures/me.png'))

    def test_a_document_file_follows_its_document_permission(self):
        self.assertTrue(self.decide(self.reader, self.name))
        self.assertTrue(self.decide(self.admin, self.name))
        self.assertFalse(self.decide(self.stranger, self.name))

    def test_a_case_variant_of_a_document_file_is_refused(self):
        self.assertFalse(self.decide(self.reader, self.name.upper()))

    def test_the_can_access_hook_decides_first(self):
        register_document_file(Paper, 'pdf_file', can_access=lambda request, document, action: request.user == self.stranger)
        self.assertTrue(self.decide(self.stranger, self.name))
        self.assertFalse(self.decide(self.admin, self.name))

    def test_another_scope_hides_the_file(self):
        ScopeSettings.objects.update_or_create(pk=1, defaults={'is_enabled': True})
        other = Scope.objects.create(name='Other branch')
        mine = Scope.objects.create(name='My branch')
        Paper.all_objects.filter(pk=self.paper.pk).update(scope=other)
        self.reader.profile.scope = mine
        self.reader.profile.save()
        cache.clear()
        self.assertFalse(self.decide(self.reader, self.name))

    @override_settings(DLUX_PUBLIC_MEDIA=['products/'], DLUX_APP_ONLY_MEDIA=('exports',))
    def test_projects_add_public_and_app_only_folders(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertTrue(self.decide(AnonymousUser(), 'products/shoe.jpg'))
        self.assertFalse(self.decide(self.admin, 'exports/2026.xlsx'))

    def test_endpoint_answers_204_or_403_and_is_never_cached(self):
        allowed = self.ask(f'/media/{self.name}', self.reader)
        self.assertEqual(allowed.status_code, 204)
        self.assertEqual(allowed['Cache-Control'], 'no-store')
        self.assertEqual(self.ask(f'/media/{self.name}', self.stranger).status_code, 403)
        self.assertEqual(self.ask(f'/media/{self.name}').status_code, 403)
        self.assertEqual(self.ask('/media/dlux/branding/logo.png').status_code, 204)

    def test_endpoint_reads_only_the_proxy_header(self):
        response = self.client.get(reverse('dlux_media_access'), HTTP_X_ORIGINAL_URI='/media/public/a.pdf')
        self.assertEqual(response.status_code, 403)

    def test_endpoint_refuses_unsafe_methods(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('dlux_media_access'), HTTP_X_FORWARDED_URI='/media/public/a.pdf')
        self.assertEqual(response.status_code, 405)


class ProxyTemplateTests(SimpleTestCase):
    """The generated proxies must agree with `dlux.files.media` on what is public."""

    def test_caddy_public_matcher_lists_exactly_the_public_folders(self):
        text = (PROXY_TEMPLATES / 'Caddyfile.tmpl').read_text(encoding='utf-8')
        line = re.search(r'@public_media path (.+)', text).group(1).split()
        self.assertEqual(sorted(line), sorted(f'/media/{prefix}*' for prefix in PUBLIC_MEDIA))
        self.assertIn('uri /sys/files/media-access/', text)
        self.assertNotIn('handle_path /media/*', text)

    def test_nginx_serves_public_folders_and_asks_the_app_for_the_rest(self):
        text = (PROXY_TEMPLATES / 'default.conf.template.tmpl').read_text(encoding='utf-8')
        public = re.findall(r'location \^~ /media/(\S+) \{ root /app; \}', text)
        self.assertEqual(sorted(public), sorted(PUBLIC_MEDIA))
        self.assertIn('auth_request /_dlux_media_access;', text)
        self.assertIn('proxy_set_header X-Forwarded-Uri $request_uri;', text)
        self.assertNotIn('alias /app/media/', text)

    def test_backups_stay_blocked_at_the_proxy(self):
        self.assertIn('dlux_backups/', APP_ONLY_MEDIA)
        for template in ('Caddyfile.tmpl', 'default.conf.template.tmpl'):
            self.assertIn('/media/dlux_backups/', (PROXY_TEMPLATES / template).read_text(encoding='utf-8'))
