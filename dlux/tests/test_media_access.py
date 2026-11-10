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

from dlux.files.media import APP_ONLY_MEDIA, PUBLIC_MEDIA, backup_folder_is_public, media_decision, media_name
from dlux.files.registry import register_document_file, unregister_document_file
from dlux.models import ReportBackup, Scope, ScopeSettings, SystemBackup, SystemSettings
from dlux.system.normalizers import normalize_backup_config
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

    def test_files_beside_document_files_are_refused_even_to_a_superuser(self):
        # A replaced original, a project's own history copy, an orphan: no document is left to check.
        for name in ('papers/replaced.pdf', 'papers/paper_1_2026-01-01_V2.pdf', 'PAPERS/orphan.pdf'):
            with self.subTest(name=name):
                self.assertFalse(self.decide(self.admin, name))

    def test_an_attachment_beside_its_document_file_needs_a_signed_in_user(self):
        from django.contrib.auth.models import AnonymousUser

        self.paper.attachment.save('annex.pdf', ContentFile(b'%PDF-1.4'))
        self.assertTrue(self.decide(self.stranger, self.paper.attachment.name))
        self.assertFalse(self.decide(AnonymousUser(), self.paper.attachment.name))
        self.assertFalse(self.decide(self.stranger, self.paper.attachment.name.upper()))

    def test_other_folders_and_subfolders_need_a_signed_in_user(self):
        for name in ('papers/2026/scan.pdf', 'reports/q1.pdf', 'loose.pdf'):
            with self.subTest(name=name):
                self.assertTrue(self.decide(self.stranger, name))

    def test_a_file_a_document_had_before_is_refused_in_any_folder(self):
        from django.contrib.contenttypes.models import ContentType

        from dlux.models import FileVersion

        FileVersion.objects.create(
            content_type=ContentType.objects.get_for_model(Paper), object_id=self.paper.pk, document_model='Paper',
            version_number=1, active_name_before='scans/2019/old.pdf', archived_file='scans/2019/old_V1.pdf',
        )
        for name in ('scans/2019/old.pdf', 'scans/2019/old_V1.pdf'):
            with self.subTest(name=name):
                self.assertFalse(self.decide(self.admin, name))
        self.assertTrue(self.decide(self.admin, 'scans/2019/other.pdf'))

    def test_a_file_elsewhere_costs_one_lookup_per_document_field(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as queries:
            self.assertTrue(self.decide(self.stranger, 'reports/q1.pdf'))
        papers = [q['sql'] for q in queries.captured_queries if Paper._meta.db_table in q['sql']]
        self.assertEqual(len(papers), 1, papers)

    def test_the_file_the_editor_replaced_stays_on_disk_but_no_one_fetches_it(self):
        from dlux.files.history import save_new_version
        from dlux.tests.test_document_history import PdfWriter, pdf_bytes

        if PdfWriter is None:
            self.skipTest('Install django-lux[pdf] to test file history.')
        self.paper.pdf_file.save('signed.pdf', ContentFile(pdf_bytes(2)))
        before = self.paper.pdf_file.name
        with self.captureOnCommitCallbacks(execute=True):
            saved, _ = save_new_version(self.paper, pdf_bytes(1), user=self.admin)
        self.assertTrue(self.paper.pdf_file.storage.exists(before))
        for user in (self.stranger, self.reader, self.admin):
            self.assertFalse(self.decide(user, before))
        self.assertFalse(self.decide(self.stranger, saved))
        self.assertTrue(self.decide(self.reader, saved))

    def test_a_document_file_without_a_public_rule_is_never_served_signed_out(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertFalse(self.decide(AnonymousUser(), self.name))

    def test_the_public_rule_serves_a_document_file_to_anyone(self):
        from django.contrib.auth.models import AnonymousUser

        register_document_file(Paper, 'pdf_file', public=lambda document: document.title == 'Annual report')
        draft = Paper.objects.create(title='Draft')
        draft.pdf_file.save('draft.pdf', ContentFile(b'%PDF-1.4'))
        self.assertTrue(self.decide(AnonymousUser(), self.name))
        self.assertTrue(self.decide(self.stranger, self.name))
        self.assertFalse(self.decide(AnonymousUser(), draft.pdf_file.name))
        self.assertFalse(self.decide(self.stranger, draft.pdf_file.name))
        self.assertTrue(self.decide(self.reader, draft.pdf_file.name))
        self.assertFalse(self.decide(AnonymousUser(), self.name.upper()))

    def test_a_public_document_file_ignores_the_readers_scope(self):
        register_document_file(Paper, 'pdf_file', public=lambda document: True)
        ScopeSettings.objects.update_or_create(pk=1, defaults={'is_enabled': True})
        Paper.all_objects.filter(pk=self.paper.pk).update(scope=Scope.objects.create(name='Other branch'))
        self.stranger.profile.scope = Scope.objects.create(name='My branch')
        self.stranger.profile.save()
        cache.clear()
        self.assertTrue(self.decide(self.stranger, self.name))

    def test_a_soft_deleted_document_is_not_public(self):
        from django.contrib.auth.models import AnonymousUser

        register_document_file(Paper, 'pdf_file', public=lambda document: True)
        self.paper.delete()
        self.assertFalse(self.decide(AnonymousUser(), self.name))

    @override_settings(DLUX_PUBLIC_MEDIA=['products/'], DLUX_APP_ONLY_MEDIA=('exports',))
    def test_projects_add_public_and_app_only_folders(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertTrue(self.decide(AnonymousUser(), 'products/shoe.jpg'))
        self.assertFalse(self.decide(self.admin, 'exports/2026.xlsx'))

    @override_settings(DLUX_PUBLIC_MEDIA=['publication/*.png'], DLUX_APP_ONLY_MEDIA=['reports/*.xlsx'])
    def test_entries_with_a_wildcard_match_files_one_folder_level_per_slash(self):
        from django.contrib.auth.models import AnonymousUser

        for name, allowed in (('publication/mark.png', True), ('PUBLICATION/MARK.PNG', True),
                              ('publication/mark.pdf', False), ('publication/old/mark.png', False),
                              ('publication.png', False)):
            with self.subTest(name=name):
                self.assertEqual(self.decide(AnonymousUser(), name), allowed)
        self.assertFalse(self.decide(self.admin, 'reports/2026.xlsx'))
        self.assertTrue(self.decide(self.admin, 'reports/2026.csv'))

    @override_settings(ROOT_URLCONF='dlux.tests.urls_with_prefix_mount')
    def test_the_proxy_uri_reaches_a_prefixed_mount(self):
        def ask_root(user=None):
            self.client.logout()
            if user is not None:
                self.client.force_login(user)
            return self.client.get('/sys/files/media-access/', HTTP_X_FORWARDED_URI=f'/media/{self.name}')

        self.assertEqual(reverse('dlux_media_access'), '/dlux/sys/files/media-access/')
        self.assertEqual(ask_root(self.reader).status_code, 204)
        self.assertEqual(ask_root(self.stranger).status_code, 403)
        self.assertEqual(ask_root().status_code, 403)
        self.assertEqual(self.ask(f'/media/{self.name}', self.reader).status_code, 204)

    @override_settings(ROOT_URLCONF='dlux.tests.urls_with_own_media_access')
    def test_a_project_route_at_the_proxy_uri_wins(self):
        self.client.force_login(self.reader)
        root = self.client.get('/sys/files/media-access/', HTTP_X_FORWARDED_URI=f'/media/{self.name}')
        self.assertEqual(root.status_code, 403)
        self.assertEqual(self.ask(f'/media/{self.name}', self.reader).status_code, 204)

    def test_signed_out_requests_look_up_only_public_registrations(self):
        from django.contrib.auth.models import AnonymousUser

        with self.assertNumQueries(0):
            self.assertFalse(self.decide(AnonymousUser(), self.name))

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


class BackupMediaTests(TestCase):
    """Backups are refused wherever they are written, not only in `dlux_backups/`."""

    def setUp(self):
        self.settings_obj = SystemSettings.load()
        self.settings_obj.is_configured = True
        self.settings_obj.save()
        cache.clear()
        self.addCleanup(cache.clear)
        self.admin = get_user_model().objects.create_superuser('backup-admin', 'backup-admin@example.com', 'pw12345!')

    def use_folder(self, folder):
        self.settings_obj.backup_config = normalize_backup_config({'auto_export_target': folder})
        self.settings_obj.save(update_fields=['backup_config'])
        cache.clear()

    def decide(self, user, name):
        request = RequestFactory().get('/sys/files/media-access/')
        request.user = user
        return media_decision(request, name)

    def test_the_configured_backup_folder_is_refused_even_to_a_superuser(self):
        self.use_folder('backups/system')
        for name in ('backups/system/system-abc.dlb', 'backups/system/system-abc.idx',
                     'backups/system/uploaded-20261106-101500.dlb', 'backups/system/notes.txt',
                     'BACKUPS/System/system-abc.idx'):
            with self.subTest(name=name):
                self.assertFalse(self.decide(self.admin, name))
        self.assertTrue(self.decide(self.admin, 'backups/other/notes.txt'))
        self.client.force_login(self.admin)
        response = self.client.get(reverse('dlux_media_access'), HTTP_X_FORWARDED_URI='/media/backups/system/system-abc.idx')
        self.assertEqual(response.status_code, 403)

    def test_the_folder_is_read_per_request(self):
        self.use_folder('vault')
        self.assertFalse(self.decide(self.admin, 'vault/system-abc.idx'))
        self.use_folder('dlux_backups')
        self.assertTrue(self.decide(self.admin, 'vault/notes.txt'))

    def test_a_backup_archive_is_refused_in_any_folder(self):
        from django.contrib.auth.models import AnonymousUser

        for name in ('papers/system-abc.dlb', 'public/full.dlb', 'Exports/FULL.DLB'):
            with self.subTest(name=name):
                self.assertFalse(self.decide(self.admin, name))
                self.assertFalse(self.decide(AnonymousUser(), name))

    def test_backups_left_in_a_former_folder_stay_refused(self):
        SystemBackup.objects.create(requested_by_username='system', file_path='old_vault/system-abc.dlb')
        ReportBackup.objects.create(user=self.admin, file_path='old_reports/report-abc.zip')
        self.use_folder('new_vault')
        for name in ('old_vault/system-abc.idx', 'OLD_VAULT/system-abc.IDX', 'old_reports/report-abc.zip'):
            with self.subTest(name=name):
                self.assertFalse(self.decide(self.admin, name))
        self.assertTrue(self.decide(self.admin, 'old_vault/notes.txt'))

    @override_settings(DLUX_PUBLIC_MEDIA=['exports/'], DLUX_CONFIG={'reports': {'backup_storage_prefix': 'exports/reports'}})
    def test_the_report_backup_folder_is_refused_even_inside_a_public_folder(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertFalse(self.decide(AnonymousUser(), 'exports/reports/abc.zip'))
        self.assertFalse(self.decide(self.admin, 'exports/reports/abc.zip'))
        self.assertTrue(self.decide(AnonymousUser(), 'exports/catalogue.pdf'))

    def test_refusals_to_signed_out_visitors_stay_query_free(self):
        from django.contrib.auth.models import AnonymousUser

        with self.assertNumQueries(0):
            self.assertFalse(self.decide(AnonymousUser(), 'backups/system/system-abc.idx'))

    @override_settings(DLUX_PUBLIC_MEDIA=['exports/', 'gallery/*'])
    def test_public_folders_cannot_hold_backups(self):
        for folder in ('public', 'public/backups', 'PUBLIC/backups', 'dlux/branding', 'dlux/assets/image/x',
                       'dlux/assets/font', 'exports', 'exports/system', 'gallery'):
            with self.subTest(folder=folder):
                self.assertTrue(backup_folder_is_public(folder))
        for folder in ('dlux_backups', 'backups/system', 'publicity', 'dlux', 'dlux/assets', 'gallery/old', ''):
            with self.subTest(folder=folder):
                self.assertFalse(backup_folder_is_public(folder))


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
