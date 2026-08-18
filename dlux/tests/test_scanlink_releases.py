"""ScanLink installer distribution, centralized from project-archive.

The risky parts are all about the bytes: an installer is an executable, so it
must never be reachable over MEDIA_URL, the SHA-256 the manifest publishes must
come from the stored file rather than from operator input, and every endpoint
must be inert while the integration is switched off.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from dlux.models import ManagedAsset, ScanLinkRelease, SystemSettings
from dlux.models.assets import PROTECTED_ASSET_PREFIX

User = get_user_model()


def _enable(value=True):
    record = SystemSettings.load()
    extra = dict(record.extra_config or {})
    extra['scanlink'] = {'enabled': value}
    record.extra_config = extra
    # Without this the setup middleware bounces every request to the wizard.
    record.is_configured = True
    record.save()


def _exe(content=b'MZ fake installer bytes', name='ScanLinkSetup.exe'):
    return SimpleUploadedFile(name, content, content_type='application/octet-stream')


class ScanLinkTestCase(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.admin = User.objects.create_superuser('admin', 'a@example.com', 'pw')
        self.plain = User.objects.create_user('plain', 'p@example.com', 'pw')
        _enable(True)

    def _publish(self, version='0.7.2', arch='x64', content=b'MZ payload', **extra):
        self.client.force_login(self.admin)
        payload = {'version': version, 'arch': arch, 'is_active': 'on'}
        payload.update(extra)
        payload['installer'] = _exe(content)
        return self.client.post(reverse('scanlink_release_upload'), payload)


class StorageTests(ScanLinkTestCase):
    def test_an_installer_is_stored_off_the_public_media_path(self):
        self._publish()
        asset = ScanLinkRelease.objects.get().asset
        self.assertTrue(
            asset.file.name.startswith(PROTECTED_ASSET_PREFIX),
            f'an executable was stored at a public media path: {asset.file.name}',
        )

    def test_a_protected_asset_exposes_no_public_url(self):
        """Otherwise a template could link straight at the executable."""
        self._publish()
        self.assertEqual(ScanLinkRelease.objects.get().asset.url, '')

    def test_an_image_asset_is_unaffected_and_keeps_its_url(self):
        from dlux.models.assets import managed_asset_upload_to
        path = managed_asset_upload_to(ManagedAsset(kind='image'), 'a.png')
        self.assertFalse(path.startswith(PROTECTED_ASSET_PREFIX))

    def test_the_checksum_is_computed_from_the_bytes_not_supplied(self):
        import hashlib
        content = b'MZ deterministic'
        self._publish(content=content)
        release = ScanLinkRelease.objects.get()
        self.assertEqual(release.sha256, hashlib.sha256(content).hexdigest())


class UploadTests(ScanLinkTestCase):
    def test_a_superuser_can_publish(self):
        response = self._publish()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertEqual(ScanLinkRelease.objects.count(), 1)

    def test_a_non_superuser_cannot_publish(self):
        self.client.force_login(self.plain)
        response = self.client.post(reverse('scanlink_release_upload'), {
            'version': '1.0', 'arch': 'x64', 'installer': _exe(),
        })
        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(ScanLinkRelease.objects.count(), 0)

    def test_get_is_rejected(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('scanlink_release_upload')).status_code, 405)

    def test_a_non_exe_upload_is_refused(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('scanlink_release_upload'), {
            'version': '1.0', 'arch': 'x64',
            'installer': SimpleUploadedFile('notes.txt', b'hello', content_type='text/plain'),
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ScanLinkRelease.objects.count(), 0)

    def test_a_non_numeric_version_is_refused(self):
        response = self._publish(version='latest')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ScanLinkRelease.objects.count(), 0)

    def test_the_same_version_and_arch_cannot_be_published_twice(self):
        self._publish(version='1.0', arch='x64')
        response = self._publish(version='1.0', arch='x64')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ScanLinkRelease.objects.count(), 1)

    def test_the_same_version_may_exist_for_each_architecture(self):
        self._publish(version='1.0', arch='x64')
        self._publish(version='1.0', arch='x86', content=b'MZ other')
        self.assertEqual(ScanLinkRelease.objects.count(), 2)

    def test_publishing_is_refused_while_scanlink_is_off(self):
        _enable(False)
        response = self._publish()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ScanLinkRelease.objects.count(), 0)


class ManifestTests(ScanLinkTestCase):
    def test_the_manifest_advertises_the_active_release(self):
        self._publish(version='0.7.2')
        self.client.force_login(self.plain)
        body = self.client.get(reverse('scanlink_update_manifest')).json()

        self.assertEqual(body['latest_version'], '0.7.2')
        self.assertIn('x64', body['downloads'])
        self.assertEqual(len(body['sha256']['x64']), 64)

    def test_version_ordering_is_numeric_not_lexical(self):
        """The bug this ordering exists to avoid: '0.9' outranking '0.10'."""
        self._publish(version='0.9', content=b'MZ nine')
        self._publish(version='0.10', content=b'MZ ten')
        self.client.force_login(self.plain)
        self.assertEqual(
            self.client.get(reverse('scanlink_update_manifest')).json()['latest_version'],
            '0.10',
        )

    def test_an_inactive_release_is_not_advertised(self):
        self._publish(version='1.0', is_active='')
        self.client.force_login(self.plain)
        body = self.client.get(reverse('scanlink_update_manifest')).json()
        self.assertIsNone(body['latest_version'])
        self.assertEqual(body['downloads'], {})

    def test_the_manifest_is_empty_while_scanlink_is_off(self):
        self._publish()
        _enable(False)
        self.client.force_login(self.plain)
        body = self.client.get(reverse('scanlink_update_manifest')).json()
        self.assertIsNone(body['latest_version'])
        self.assertEqual(body['downloads'], {})

    def test_an_anonymous_visitor_cannot_read_the_manifest(self):
        self._publish()
        self.client.logout()
        response = self.client.get(reverse('scanlink_update_manifest'))
        self.assertNotEqual(response.status_code, 200)


class DownloadTests(ScanLinkTestCase):
    def _url(self):
        self._publish()
        return reverse('scanlink_download', args=[ScanLinkRelease.objects.get().pk])

    def test_a_logged_in_user_can_download(self):
        url = self._url()
        self.client.force_login(self.plain)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Content-SHA256'], ScanLinkRelease.objects.get().sha256)

    def test_an_anonymous_visitor_cannot_download(self):
        """The whole point of keeping installers off MEDIA_URL."""
        url = self._url()
        self.client.logout()
        self.assertNotEqual(self.client.get(url).status_code, 200)

    def test_downloading_is_refused_while_scanlink_is_off(self):
        url = self._url()
        _enable(False)
        self.client.force_login(self.plain)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_an_inactive_release_cannot_be_downloaded(self):
        url = self._url()
        ScanLinkRelease.objects.update(is_active=False)
        self.client.force_login(self.plain)
        self.assertEqual(self.client.get(url).status_code, 404)


class CspTests(TestCase):
    def test_the_helper_origins_are_the_ones_the_browser_must_allow(self):
        from dlux.system.constants import SCANLINK_CONNECT_ORIGINS
        self.assertIn('https://localhost:5443', SCANLINK_CONNECT_ORIGINS)
        self.assertIn('http://localhost:5000', SCANLINK_CONNECT_ORIGINS)


class ToggleEndpointTests(ScanLinkTestCase):
    """The switch takes effect on click, not on save.

    Managing installers is gated on ScanLink being on, so requiring a save and a
    reopen of the step first put a detour between the operator and the thing they
    opened the step to do.
    """

    def setUp(self):
        super().setUp()
        _enable(False)
        self.url = reverse('scanlink_toggle')

    def test_a_superuser_can_switch_it_on_immediately(self):
        from dlux.utils import scanlink_enabled
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {'enabled': 'true'})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['enabled'])
        cache.clear()
        self.assertTrue(scanlink_enabled())

    def test_it_can_be_switched_back_off(self):
        from dlux.utils import scanlink_enabled
        self.client.force_login(self.admin)
        self.client.post(self.url, {'enabled': 'true'})
        self.client.post(self.url, {'enabled': 'false'})
        cache.clear()
        self.assertFalse(scanlink_enabled())

    def test_the_releases_modal_works_straight_after_the_toggle(self):
        """The whole point: no save, no reopen, no second trip."""
        self.client.force_login(self.admin)
        self.client.post(self.url, {'enabled': 'true'})
        response = self.client.get(reverse('scanlink_releases_modal'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('scanlink_disabled_message', response.json()['html'])

    def test_a_non_superuser_cannot_flip_it(self):
        self.client.force_login(self.plain)
        self.assertNotEqual(self.client.post(self.url, {'enabled': 'true'}).status_code, 200)

    def test_get_is_rejected(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_flipping_it_preserves_project_namespaces(self):
        record = SystemSettings.load()
        record.extra_config = {'app': {'myproject.settings': {'keep': 'me'}}}
        record.save()
        self.client.force_login(self.admin)
        self.client.post(self.url, {'enabled': 'true'})

        stored = SystemSettings.load().extra_config
        self.assertEqual(stored['app'], {'myproject.settings': {'keep': 'me'}})


class ReleasesModalTests(ScanLinkTestCase):
    def test_the_form_uses_the_dlux_file_widget_not_a_bare_input(self):
        """Project standard: DluxFileInput, never a raw file input."""
        from dlux.forms.scanlink import ScanLinkReleaseForm
        from dlux.widgets import DluxFileInput
        self.assertIsInstance(ScanLinkReleaseForm().fields['installer'].widget, DluxFileInput)

    def test_the_architecture_uses_the_dlux_choice_selector(self):
        from dlux.forms.scanlink import ScanLinkReleaseForm
        from dlux.widgets import DluxChoiceSelectorWidget
        widget = ScanLinkReleaseForm().fields['arch'].widget
        self.assertIsInstance(widget, DluxChoiceSelectorWidget)
        self.assertEqual(widget.selector_variant, 'chip')
        self.assertIn('dlux-scanlink-arch-selector', widget.attrs['class'])

    def test_version_and_notes_use_system_settings_text_styling(self):
        from dlux.forms.scanlink import ScanLinkReleaseForm
        form = ScanLinkReleaseForm()

        for field_name, direction in (('version', 'ltr'), ('notes', 'auto')):
            widget = form.fields[field_name].widget
            self.assertIn('glass-input', widget.attrs['class'].split())
            self.assertEqual(widget.attrs['dir'], direction)

    def test_the_form_renders_details_beside_the_installer_column(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse('scanlink_releases_modal')).json()['html']

        self.assertIn('dlux/system/css/scanlink_releases.css', html)
        self.assertIn('dlux-scanlink-release-form__details', html)
        self.assertIn('dlux-scanlink-release-form__installer', html)
        self.assertIn('dlux-scanlink-release-form__publish-row', html)
        self.assertIn('dlux-scanlink-release-form__notes', html)
        self.assertEqual(html.count('id="id_notes"'), 1)
        self.assertNotRegex(
            html,
            r'class="[^"]*dlux-settings-toggle-field[^"]*\bh-100\b',
        )

    def test_the_modal_offers_a_way_back_to_the_settings_step(self):
        from dlux.system.constants import SETUP_STEP_EXTRAS
        self.client.force_login(self.admin)
        html = self.client.get(reverse('scanlink_releases_modal')).json()['html']
        self.assertIn(f'?step={SETUP_STEP_EXTRAS}', html, 'no Back navigation to the step')

    def test_the_modal_renders_the_dlux_switch_for_active(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse('scanlink_releases_modal')).json()['html']
        self.assertIn('dlux-settings-toggle-field', html, 'Active is not the dlux switch')
