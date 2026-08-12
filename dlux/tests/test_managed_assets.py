import shutil
import tempfile
from pathlib import Path
from io import BytesIO

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from dlux.forms.assets import AssetPickerField
from dlux.assets import create_managed_asset, register_managed_font
from dlux.fonts import generate_font_face_css, get_available_fonts
from dlux.forms import SystemSettingsForm
from dlux.models import ManagedAsset, ManagedFontFamily, SystemSettings
from dlux.utils import apply_system_settings_import, export_system_settings_payload, get_system_config

_STATIC = Path(__file__).resolve().parents[1] / 'static' / 'dlux'
_TEMPLATES = Path(__file__).resolve().parents[1] / 'templates' / 'dlux'


def image_upload(name='brand.png', color=(32, 92, 180)):
    stream = BytesIO()
    Image.new('RGB', (12, 8), color).save(stream, format='PNG')
    return SimpleUploadedFile(name, stream.getvalue(), content_type='image/png')


def font_upload(name='custom.woff2'):
    payload = bytearray(64)
    payload[0:4] = b'wOF2'
    payload[4:8] = b'\x00\x01\x00\x00'
    payload[8:12] = len(payload).to_bytes(4, 'big')
    payload[12:14] = (1).to_bytes(2, 'big')
    payload[16:20] = (12).to_bytes(4, 'big')
    payload[20:24] = (1).to_bytes(4, 'big')
    return SimpleUploadedFile(name, bytes(payload), content_type='font/woff2')


class ManagedAssetTests(TestCase):
    def setUp(self):
        cache.clear()
        self.media_root = tempfile.mkdtemp(prefix='dlux-managed-assets-')
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.user = get_user_model().objects.create_superuser('asset-admin', 'asset@example.com', 'pw')
        system_settings = SystemSettings.load()
        system_settings.is_configured = True
        system_settings.save()

    def tearDown(self):
        cache.clear()
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_image_upload_is_validated_and_deduplicated(self):
        first, created = create_managed_asset(image_upload(), kind='image', user=self.user)
        second, duplicate_created = create_managed_asset(image_upload('same.png'), kind='image', user=self.user)

        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual((first.width, first.height), (12, 8))

    def test_css_and_invalid_woff2_uploads_are_rejected(self):
        with self.assertRaises(ValidationError):
            create_managed_asset(SimpleUploadedFile('theme.css', b'body{}'), kind='image')
        with self.assertRaises(ValidationError):
            create_managed_asset(SimpleUploadedFile('fake.woff2', b'not-a-font'), kind='font')

    def test_picker_accepts_existing_or_direct_upload(self):
        asset, _ = create_managed_asset(image_upload(), kind='image')
        field = AssetPickerField(kind='image')

        self.assertEqual(field.clean({'asset_id': str(asset.pk)}).asset, asset)
        uploaded = field.clean({'upload': image_upload('fresh.png')})
        self.assertEqual(uploaded.upload.name, 'fresh.png')

    def test_system_settings_helper_creates_reusable_asset_from_direct_upload(self):
        instance = SystemSettings.load()
        request = RequestFactory().get('/sys/options/?step=0')
        request.user = self.user
        form = SystemSettingsForm(instance=instance, request=request, user=self.user)
        form.cleaned_data = {'logo': AssetPickerField(kind='image').clean({'upload': image_upload()})}

        asset = form._resolve_asset_selection('logo', None)

        self.assertIsInstance(asset, ManagedAsset)
        self.assertEqual(asset.created_by, self.user)

    def test_system_settings_save_registers_direct_logo_upload(self):
        instance = SystemSettings.load()
        request = RequestFactory().get('/sys/options/?step=0')
        request.user = self.user
        form = SystemSettingsForm(
            data={
                'system_names': '{"en":"System","ar":"System"}',
                'home_url': '/dashboard/',
                'default_language': 'en',
                'default_theme': 'light',
                'allowed_themes': ['light'],
                'languages': '{}',
                'translations_override': '{}',
                'sidebar_config': '{"enabled":true,"entries":[]}',
                'logo_asset': '',
                'logo_clear': '0',
            },
            files={'logo_upload': image_upload()},
            instance=instance,
            request=request,
            user=self.user,
        )

        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()

        self.assertIsNotNone(saved.logo_asset)
        self.assertEqual(saved.logo_asset.created_by, self.user)
        self.assertFalse(bool(saved.logo))

    def test_runtime_uses_separate_login_branding_and_background(self):
        system_logo, _ = create_managed_asset(image_upload('system.png', (10, 10, 10)), kind='image')
        login_logo, _ = create_managed_asset(image_upload('login.png', (20, 20, 20)), kind='image')
        background, _ = create_managed_asset(image_upload('background.png', (30, 30, 30)), kind='image')
        instance = SystemSettings.load()
        instance.is_configured = True
        instance.logo_asset = system_logo
        instance.login_logo_asset = login_logo
        instance.login_background_asset = background
        instance.save()

        config = get_system_config()

        self.assertEqual(config['logo_url'], system_logo.url)
        self.assertEqual(config['login_logo_url'], login_logo.url)
        self.assertEqual(config['login']['background_url'], background.url)

    def test_login_logo_falls_back_to_system_logo(self):
        system_logo, _ = create_managed_asset(image_upload(), kind='image')
        instance = SystemSettings.load()
        instance.is_configured = True
        instance.logo_asset = system_logo
        instance.login_logo_asset = None
        instance.save()

        self.assertEqual(get_system_config()['login_logo_url'], system_logo.url)

    def test_settings_export_uses_managed_asset_storage_names(self):
        logo, _ = create_managed_asset(image_upload(), kind='image')
        background, _ = create_managed_asset(image_upload('background.png', (1, 2, 3)), kind='image')
        instance = SystemSettings.load()
        instance.logo_asset = logo
        instance.login_background_asset = background
        instance.save()

        settings_payload = export_system_settings_payload(instance)['settings']

        self.assertEqual(settings_payload['logo'], logo.file.name)
        self.assertEqual(settings_payload['login_background'], background.file.name)

        target = SystemSettings()
        apply_system_settings_import(target, {'logo': logo.file.name, 'login_background': background.file.name}, commit=False)
        self.assertEqual(target.logo_asset, logo)
        self.assertEqual(target.login_background_asset, background)

    def test_managed_font_is_available_and_generates_media_url(self):
        asset, _ = create_managed_asset(font_upload(), kind='font')
        register_managed_font(asset, slug='inter_ui', family='Inter UI', label='Inter UI', weight=400)

        managed = next(font for font in get_available_fonts() if font['slug'] == 'inter_ui')
        css = generate_font_face_css(['inter_ui'])

        self.assertEqual(managed['family'], 'Inter UI')
        self.assertIn(asset.url, css)
        self.assertTrue(ManagedFontFamily.objects.filter(slug='inter_ui').exists())

    def test_asset_manager_is_superuser_only(self):
        normal = get_user_model().objects.create_user('normal', password='pw')
        self.client.force_login(normal)
        self.assertEqual(self.client.get(reverse('asset_manager')).status_code, 403)
        self.client.force_login(self.user)
        response = self.client.get(reverse('asset_manager'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('html', response.json())
        html = response.json()['html']
        self.assertNotIn('<html', html)
        self.assertIn('data-dlux-modal-footer', html)
        self.assertIn('data-managed-asset-form', html)
        self.assertIn('>Name</label>', html)

    def test_asset_manager_uploads_and_blocks_deleting_used_asset(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('asset_manager'), {
            'title': 'Reusable Brand',
            'kind': 'image',
            'file': image_upload(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        asset = ManagedAsset.objects.get(title='Reusable Brand')
        instance = SystemSettings.load()
        instance.logo_asset = asset
        instance.save()

        response = self.client.post(reverse('asset_manager_delete', args=[asset.pk]))

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()['success'])
        self.assertTrue(ManagedAsset.objects.filter(pk=asset.pk).exists())

    def test_settings_form_renders_central_asset_picker(self):
        html = str(SystemSettingsForm(instance=SystemSettings.load()))
        self.assertIn('data-asset-picker', html)
        self.assertIn('data-archive-file-primary="library"', html)
        self.assertIn('data-archive-file-library', html)
        self.assertIn('class="archive-file-library" data-asset-picker-library hidden', html)
        self.assertIn('aria-controls="id_logo_library"', html)
        self.assertNotIn('data-bs-toggle="dropdown"', html)
        self.assertNotIn('dropdown-menu', html)
        self.assertIn('name="logo_upload"', html)
        self.assertIn('name="login_logo_asset"', html)

    def test_selected_asset_picker_uses_active_language_copy(self):
        asset, _created = create_managed_asset(image_upload(), kind='image', title='Brand')
        settings_obj = SystemSettings.load()
        settings_obj.logo_asset = asset
        settings_obj.default_language = 'ar'
        settings_obj.save()

        html = str(SystemSettingsForm(instance=settings_obj))

        self.assertIn('الملف الحالي المرفق بهذا السجل.', html)
        self.assertIn('اختيار أصل', html)
        self.assertIn('البحث في الأصول', html)
        self.assertNotIn('Current file on this record.', html)

    def test_manager_form_uses_translated_field_labels(self):
        from dlux.forms.assets import ManagedAssetUploadForm

        form = ManagedAssetUploadForm()

        self.assertEqual(form.fields['title'].label, 'Name')
        self.assertEqual(form.fields['kind'].label, 'File type')
        self.assertEqual(form.fields['font_family'].label, 'CSS family')
        self.assertEqual(form.fields['file'].widget.template_name, 'dlux/forms/file_input.html')


class AssetPickerSearchFieldTests(SimpleTestCase):
    @property
    def _css(self):
        return (_STATIC / 'helpers' / 'asset_picker' / 'css' / 'main.css').read_text(encoding='utf-8')

    def test_search_icon_does_not_sit_on_the_text(self):
        # `.glass-input` sets `padding: ... !important` globally, so the room for
        # the icon must be important too or they overlap in both directions.
        block = self._css[self._css.index('.archive-file-library__search input {'):]
        block = block[:block.index('}')]

        self.assertIn('padding-inline-start: 2.25rem !important;', block)
