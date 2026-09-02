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
        self.assertEqual(self.client.get(reverse('manage_assets')).status_code, 403)
        self.assertEqual(self.client.post(
            reverse('managed_image_picker_upload'), {'file': image_upload()}
        ).status_code, 403)
        self.client.force_login(self.user)
        response = self.client.get(reverse('manage_assets'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('html', response.json())
        html = response.json()['html']
        self.assertNotIn('<html', html)
        self.assertIn('data-dlux-modal-footer', html)
        self.assertIn('data-managed-image-form', html)
        self.assertIn('data-dlux-modal-nav', html)
        self.assertIn('/sys/assets/?asset_tab=fonts', html)
        self.assertNotIn('name="kind"', html)
        self.assertNotIn('>Name</label>', html)

        fonts = self.client.get(reverse('manage_assets'), {'asset_tab': 'fonts'}).json()['html']
        self.assertIn('data-managed-font-form', fonts)
        self.assertIn('>Name</label>', fonts)
        self.assertNotIn('data-dlux-modal-footer', fonts)

    def test_asset_manager_uploads_and_blocks_deleting_used_asset(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('manage_assets'), {'file': image_upload()})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertTrue(payload['reload_current'])
        asset = ManagedAsset.objects.get(kind='image')
        self.assertEqual(payload['assets'], [{
            'id': asset.pk,
            'title': asset.title,
            'url': asset.url,
            'kind': 'image',
        }])
        instance = SystemSettings.load()
        instance.logo_asset = asset
        instance.save()

        response = self.client.post(reverse('manage_assets_delete', args=[asset.pk]))

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()['success'])
        self.assertTrue(ManagedAsset.objects.filter(pk=asset.pk).exists())

    def test_image_name_can_be_edited_without_changing_slug(self):
        asset, _created = create_managed_asset(image_upload(), kind='image')
        original_slug = asset.slug
        self.client.force_login(self.user)

        response = self.client.post(reverse('manage_assets_rename', args=[asset.pk]), {
            'title': 'Main public logo',
        })

        self.assertEqual(response.status_code, 200)
        asset.refresh_from_db()
        self.assertEqual(asset.title, 'Main public logo')
        self.assertEqual(asset.slug, original_slug)

    def test_font_tab_upload_registers_one_font_variant(self):
        self.client.force_login(self.user)

        response = self.client.post(
            f"{reverse('manage_assets')}?asset_tab=fonts",
            {
                'title': 'Acme Regular',
                'font_slug': 'acme',
                'font_family': 'Acme Sans',
                'font_label': 'Acme',
                'font_weight': '400',
                'font_style': 'normal',
                'file': font_upload(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['reload_current'])
        self.assertTrue(ManagedFontFamily.objects.filter(slug='acme', variants__weight=400).exists())

    def test_settings_form_renders_central_asset_picker(self):
        html = str(SystemSettingsForm(instance=SystemSettings.load()))
        self.assertIn('data-asset-picker', html)
        self.assertIn('data-dlux-file-primary="library"', html)
        self.assertIn('data-dlux-file-library', html)
        self.assertIn('class="dlux-file-library" data-asset-picker-library hidden', html)
        self.assertIn('aria-controls="id_logo_library"', html)
        self.assertNotIn('data-bs-toggle="dropdown"', html)
        self.assertNotIn('dropdown-menu', html)
        self.assertIn('name="logo_upload"', html)
        self.assertIn('name="login_logo_asset"', html)
        self.assertIn('data-asset-upload-url="/sys/setup/assets/upload/"', html)

    def test_invalid_image_upload_returns_picker_safe_error(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('managed_image_picker_upload'), {
            'file': SimpleUploadedFile('not-image.txt', b'plain text', content_type='text/plain'),
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())
        self.assertTrue(response.json()['error'])

    def test_picker_upload_persists_before_system_is_configured(self):
        self.client.force_login(self.user)
        system_settings = SystemSettings.load()
        system_settings.is_configured = False
        system_settings.save()

        response = self.client.post(reverse('managed_image_picker_upload'), {
            'file': image_upload('during-setup.png'),
        })

        self.assertEqual(response.status_code, 200)
        asset_id = response.json()['assets'][0]['id']
        self.assertTrue(ManagedAsset.objects.filter(pk=asset_id, title='during-setup').exists())

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
        from dlux.forms.assets import ManagedFontUploadForm, ManagedImageUploadForm

        image_form = ManagedImageUploadForm()
        font_form = ManagedFontUploadForm()

        self.assertEqual(set(image_form.fields), {'file'})
        self.assertEqual(font_form.fields['title'].label, 'Name')
        self.assertEqual(font_form.fields['font_family'].label, 'CSS family')
        self.assertEqual(font_form.fields['file'].widget.template_name, 'dlux/forms/file_input.html')


class AssetPickerSearchFieldTests(SimpleTestCase):
    @property
    def _css(self):
        return (_STATIC / 'helpers' / 'asset_picker' / 'css' / 'main.css').read_text(encoding='utf-8')

    def test_search_icon_does_not_sit_on_the_text(self):
        # `.glass-input` sets `padding: ... !important` globally, so the room for
        # the icon must be important too or they overlap in both directions.
        block = self._css[self._css.index('.dlux-file-library__search input {'):]
        block = block[:block.index('}')]

        self.assertIn('padding-inline-start: 2.25rem !important;', block)


class ManagerUploadBatchTests(TestCase):
    """The library screen takes a whole selection, not one file per round trip.

    `forms.FileField` validates a single upload, so a control marked `multiple`
    kept only the last file chosen — the selection looked accepted and four
    fifths of it vanished.
    """

    def _form(self, files, **data):
        """Built the way Django builds it: `request.FILES` is a MultiValueDict,
        which is what lets a `multiple` control deliver more than one file."""
        from django.utils.datastructures import MultiValueDict

        from dlux.forms.assets import ManagedImageUploadForm

        payload = {}
        payload.update(data)
        return ManagedImageUploadForm(payload, MultiValueDict({'file': list(files)}))

    def test_every_selected_file_is_saved(self):
        form = self._form([image_upload('one.png', (10, 20, 30)),
                           image_upload('two.png', (40, 50, 60))])
        self.assertTrue(form.is_valid(), form.errors)
        assets, created = form.save()
        self.assertEqual(len(assets), 2)
        self.assertEqual(created, 2)

    def test_one_file_still_works(self):
        form = self._form([image_upload('solo.png')])
        self.assertTrue(form.is_valid(), form.errors)
        assets, created = form.save()
        self.assertEqual((len(assets), created), (1, 1))

    def test_names_are_derived_from_each_uploaded_file(self):
        form = self._form([image_upload('a.png', (1, 2, 3)),
                           image_upload('b.png', (4, 5, 6))])
        self.assertTrue(form.is_valid(), form.errors)
        assets, _created = form.save()
        self.assertEqual([asset.title for asset in assets], ['a', 'b'])

    def test_every_file_in_the_batch_is_validated(self):
        """Not just the first — one bad file must refuse the whole selection."""
        form = self._form([image_upload('fine.png'),
                           SimpleUploadedFile('theme.css', b'body{}', content_type='text/css')])
        self.assertFalse(form.is_valid())
        self.assertIn('file', form.errors)

    def test_the_control_offers_multiple_selection(self):
        from dlux.forms.assets import ManagedImageUploadForm

        html = str(ManagedImageUploadForm()['file'])
        self.assertIn('multiple', html)


class ManagerLayoutTests(SimpleTestCase):
    """Two layout faults the screen shipped with."""

    CSS = _STATIC / 'assets' / 'css' / 'main.css'
    HTML = _TEMPLATES / 'assets' / 'manager.html'

    def test_the_preview_cannot_paint_over_the_card_body(self):
        """A centred grid item is not stretched, so `height: 100%` on the image
        had no definite basis and fell back to its intrinsic size — a square
        logo rendered far taller than its 160px box and covered the name,
        dimensions, usage line and delete button underneath it."""
        css = self.CSS.read_text()
        preview = css[css.index('.dlux-managed-asset-preview {'):]
        preview = preview[:preview.index('}')]
        self.assertIn('position: relative', preview)
        self.assertIn('overflow: hidden', preview)

        image = css[css.index('.dlux-managed-asset-preview img {'):]
        image = image[:image.index('}')]
        self.assertIn('position: absolute', image)
        self.assertNotIn('place-items', preview)

    def test_only_image_upload_opts_into_the_modal_footer(self):
        markup = self.HTML.read_text()
        self.assertIn('data-dlux-modal-footer', markup)
        self.assertIn('data-managed-image-upload-trigger', markup)
        self.assertIn('data-managed-font-form', markup)

    def test_the_form_takes_the_shared_field_styling(self):
        self.assertIn('class="dlux-form mb-4"', self.HTML.read_text())

    def test_the_font_metadata_uses_two_rows_before_the_file_row(self):
        markup = self.HTML.read_text()
        self.assertEqual(markup.count('data-managed-font-row='), 3)
        self.assertIn('data-managed-font-row="identity"', markup)
        self.assertIn('data-managed-font-row="variant"', markup)
        self.assertIn('data-managed-font-row="file"', markup)
