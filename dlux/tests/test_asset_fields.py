"""`ManagedAssetField`, namespaces, and the authorization on instant upload.

The behaviour these lock down is the reason the feature exists: a picker shows
one pool and not the whole library, and an upload endpoint that any signed-in
user can now reach decides what it may write from its *own* declarations rather
than from anything in the request.
"""
import shutil
import tempfile
from io import BytesIO

from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import models
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.test.utils import isolate_apps
from django.urls import reverse

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from dlux.assets import create_managed_asset
from dlux.forms import resolve_asset_selection
from dlux.forms.assets import AssetPickerField, AssetSelection
from dlux.models import ManagedAsset, ManagedAssetField
from dlux.models.asset_field import FieldDeclaration, _REGISTRY, register_asset_field

User = get_user_model()
PRODUCT_NS = 'catalog.product'
LISTING_NS = 'public_catalog.listing'


def _font_upload(name='custom.woff2'):
    payload = bytearray(64)
    payload[0:4] = b'wOF2'
    payload[4:8] = b'\x00\x01\x00\x00'
    payload[8:12] = len(payload).to_bytes(4, 'big')
    payload[12:14] = (1).to_bytes(2, 'big')
    payload[16:20] = (12).to_bytes(4, 'big')
    payload[20:24] = (1).to_bytes(4, 'big')
    return SimpleUploadedFile(name, bytes(payload), content_type='font/woff2')


def image_upload(name='photo.png', color=(10, 120, 200)):
    stream = BytesIO()
    Image.new('RGB', (8, 6), color).save(stream, format='PNG')
    return SimpleUploadedFile(name, stream.getvalue(), content_type='image/png')


class ManagedAssetFieldDeclarationTests(SimpleTestCase):
    @isolate_apps('dlux')
    def test_defaults_and_derived_namespace(self):
        class Widget(models.Model):
            image = ManagedAssetField(kind='image')

            class Meta:
                app_label = 'dlux'

        field = Widget._meta.get_field('image')
        self.assertTrue(field.null)
        self.assertTrue(field.blank)
        self.assertIs(field.remote_field.on_delete, models.PROTECT)
        # Named nothing, so it follows the model it is declared on.
        self.assertEqual(field.namespace, 'dlux.widget')
        self.assertEqual(field.identity, 'dlux.widget.image')

    @isolate_apps('dlux')
    def test_explicit_namespace_and_reads(self):
        class Listing(models.Model):
            image_override = ManagedAssetField(
                kind='image', namespace=LISTING_NS, reads=[PRODUCT_NS],
            )

            class Meta:
                app_label = 'dlux'

        field = Listing._meta.get_field('image_override')
        self.assertEqual(field.namespace, LISTING_NS)
        self.assertEqual(field.reads, (PRODUCT_NS,))

    @isolate_apps('dlux')
    def test_deconstruct_keeps_a_derived_namespace_out_of_migrations(self):
        class Derived(models.Model):
            image = ManagedAssetField(kind='image')

            class Meta:
                app_label = 'dlux'

        class Explicit(models.Model):
            image = ManagedAssetField(kind='image', namespace=PRODUCT_NS, reads=[LISTING_NS])

            class Meta:
                app_label = 'dlux'

        _, _, _, derived_kwargs = Derived._meta.get_field('image').deconstruct()
        _, _, _, explicit_kwargs = Explicit._meta.get_field('image').deconstruct()

        # A derived namespace follows its model; freezing it would mean a
        # migration every time the model is renamed.
        self.assertNotIn('namespace', derived_kwargs)
        self.assertEqual(explicit_kwargs['namespace'], PRODUCT_NS)
        self.assertEqual(explicit_kwargs['reads'], [LISTING_NS])
        self.assertEqual(explicit_kwargs['kind'], 'image')

    @isolate_apps('dlux')
    def test_declaration_is_registered_for_the_upload_endpoint(self):
        class Registered(models.Model):
            image = ManagedAssetField(kind='image')

            class Meta:
                app_label = 'dlux'

        from dlux.models.asset_field import get_asset_field

        declaration = get_asset_field('dlux.registered.image')
        self.assertIsNotNone(declaration)
        self.assertEqual(declaration.namespace, 'dlux.registered')
        self.assertEqual(declaration.change_permission, 'dlux.change_registered')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='dlux-asset-ns-'))
class NamespaceIsolationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.media_root = tempfile.mkdtemp(prefix='dlux-asset-ns-')
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.product_asset, _ = create_managed_asset(
            image_upload('product.png'), kind='image', namespace=PRODUCT_NS,
        )
        self.listing_asset, _ = create_managed_asset(
            image_upload('listing.png', (200, 30, 30)), kind='image', namespace=LISTING_NS,
        )

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _titles(self, field):
        return {asset.pk for asset in field.widget._compatible_assets()}

    def test_a_picker_lists_only_its_own_namespace(self):
        field = AssetPickerField(kind='image', namespace=PRODUCT_NS)
        self.assertEqual(self._titles(field), {self.product_asset.pk})

    def test_reads_widens_the_listing(self):
        field = AssetPickerField(kind='image', namespace=LISTING_NS, reads=[PRODUCT_NS])
        self.assertEqual(self._titles(field), {self.listing_asset.pk, self.product_asset.pk})

    def test_an_asset_outside_the_read_set_is_refused_not_merely_hidden(self):
        field = AssetPickerField(kind='image', namespace=LISTING_NS)
        with self.assertRaises(ValidationError):
            # The id arrives in the POST body, so hiding it in the UI is not enough.
            field.clean({'asset_id': str(self.product_asset.pk)})

    def test_a_readable_asset_is_accepted(self):
        field = AssetPickerField(kind='image', namespace=LISTING_NS, reads=[PRODUCT_NS])
        self.assertEqual(field.clean({'asset_id': str(self.product_asset.pk)}).asset, self.product_asset)

    def test_dedup_does_not_reach_across_namespaces(self):
        first, created_first = create_managed_asset(
            image_upload('same.png', (1, 2, 3)), kind='image', namespace=PRODUCT_NS,
        )
        second, created_second = create_managed_asset(
            image_upload('same.png', (1, 2, 3)), kind='image', namespace=LISTING_NS,
        )
        again, created_again = create_managed_asset(
            image_upload('same.png', (1, 2, 3)), kind='image', namespace=PRODUCT_NS,
        )

        self.assertTrue(created_first)
        # Identical bytes, different pool: a new row, not a handle on someone
        # else's asset.
        self.assertTrue(created_second)
        self.assertNotEqual(first.pk, second.pk)
        # Same pool: reused, which is the saving dedup is for.
        self.assertFalse(created_again)
        self.assertEqual(first.pk, again.pk)

    def test_namespace_appears_in_the_storage_path(self):
        self.assertIn(PRODUCT_NS, self.product_asset.file.name)

    def test_a_picker_with_no_namespace_still_sees_everything(self):
        # A hand-built picker naming no namespace keeps its pre-namespace view.
        field = AssetPickerField(kind='image')
        self.assertEqual(self._titles(field), {self.product_asset.pk, self.listing_asset.pk})

    def test_the_shared_pool_is_readable_from_every_picker(self):
        from dlux.models import SHARED_ASSET_NAMESPACE

        shared, _ = create_managed_asset(
            image_upload('shared.png', (7, 7, 7)), kind='image', namespace=SHARED_ASSET_NAMESPACE,
        )
        # Uploaded by hand into the library, so it is offered wherever a picker is.
        for namespace in (PRODUCT_NS, LISTING_NS):
            field = AssetPickerField(kind='image', namespace=namespace)
            self.assertIn(shared.pk, self._titles(field), namespace)
            self.assertEqual(field.clean({'asset_id': str(shared.pk)}).asset, shared)

    def test_a_row_predating_the_column_belongs_to_its_kind_s_default(self):
        from dlux.models import DEFAULT_ASSET_NAMESPACE, ManagedAsset

        legacy, _ = create_managed_asset(image_upload('legacy.png', (9, 1, 1)), kind='image')
        ManagedAsset.objects.filter(pk=legacy.pk).update(namespace='')
        legacy.refresh_from_db()
        self.assertEqual(legacy.effective_namespace, DEFAULT_ASSET_NAMESPACE)

        # Visible where that default is read (branding), and nowhere else.
        branding = AssetPickerField(kind='image', namespace=DEFAULT_ASSET_NAMESPACE)
        self.assertIn(legacy.pk, self._titles(branding))
        product = AssetPickerField(kind='image', namespace=PRODUCT_NS)
        self.assertNotIn(legacy.pk, self._titles(product))

    def test_a_legacy_font_is_not_stranded_in_the_branding_pool(self):
        """The thing a single stamped default would have got wrong."""
        from dlux.models import FONT_ASSET_NAMESPACE, ManagedAsset

        asset, _ = create_managed_asset(_font_upload(), kind='font')
        ManagedAsset.objects.filter(pk=asset.pk).update(namespace='')
        asset.refresh_from_db()
        self.assertEqual(asset.effective_namespace, FONT_ASSET_NAMESPACE)
        field = AssetPickerField(kind='font', namespace=FONT_ASSET_NAMESPACE)
        self.assertIn(asset.pk, self._titles(field))

    def test_saving_a_legacy_row_fills_the_namespace_in(self):
        from dlux.models import DEFAULT_ASSET_NAMESPACE, ManagedAsset

        asset, _ = create_managed_asset(image_upload('heal.png', (3, 3, 3)), kind='image')
        ManagedAsset.objects.filter(pk=asset.pk).update(namespace='')
        asset.refresh_from_db()

        asset.save()

        self.assertEqual(asset.namespace, DEFAULT_ASSET_NAMESPACE)


class PickerWidgetRenderTests(SimpleTestCase):
    def test_identity_namespace_and_capture_reach_the_markup(self):
        field = AssetPickerField(
            kind='image', namespace=PRODUCT_NS, identity='catalog.product.image', capture='environment',
        )
        html = field.widget.render('image', None, {'id': 'id_image'})

        self.assertIn('data-asset-field="catalog.product.image"', html)
        self.assertIn(f'data-asset-namespace="{PRODUCT_NS}"', html)
        self.assertIn('capture="environment"', html)

    def test_capture_is_absent_unless_asked_for(self):
        field = AssetPickerField(kind='image', namespace=PRODUCT_NS)
        self.assertNotIn('capture=', field.widget.render('image', None, {'id': 'id_image'}))


class UploadAuthorizationTests(TestCase):
    """The endpoint decides from its registry, never from the request body."""

    IDENTITY = 'dlux.scope.image'

    def setUp(self):
        cache.clear()
        # An unconfigured system redirects every page to setup, including this
        # endpoint — the other admin-action suites do the same.
        from dlux.models import SystemSettings

        SystemSettings.objects.all().delete()
        cache.clear()
        settings_row = SystemSettings.load()
        settings_row.is_configured = True
        settings_row.save()
        cache.clear()
        self.media_root = tempfile.mkdtemp(prefix='dlux-asset-auth-')
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        from dlux.models import Scope

        # A declaration against a real model, so its permissions really exist.
        self._declaration = register_asset_field(FieldDeclaration(
            identity=self.IDENTITY, model=Scope, field_name='image',
            kind='image', namespace=PRODUCT_NS, reads=(),
        ))
        self.url = reverse('managed_asset_picker_upload')
        self.superuser = User.objects.create_superuser('root', 'r@x.com', 'pw')
        self.staff = User.objects.create_user('clerk', 'c@x.com', 'pw')

    def tearDown(self):
        _REGISTRY.pop(self.IDENTITY, None)
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _client(self, user):
        client = Client()
        client.force_login(user)
        return client

    def _post(self, user, **extra):
        payload = {'file': image_upload()}
        payload.update(extra)
        return self._client(user).post(self.url, payload)

    def test_an_unknown_field_identity_is_refused(self):
        response = self._post(self.superuser, field='catalog.nothing.image')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_a_user_without_the_owning_permission_is_refused(self):
        self.assertEqual(self._post(self.staff, field=self.IDENTITY).status_code, 403)

    def test_the_permission_that_edits_the_record_is_the_one_that_uploads(self):
        self.staff.user_permissions.add(Permission.objects.get(codename='change_scope'))
        self.staff = User.objects.get(pk=self.staff.pk)   # drop the permission cache

        response = self._post(self.staff, field=self.IDENTITY)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        asset = ManagedAsset.objects.get(pk=payload['assets'][0]['id'])
        # It landed in the pool the *declaration* names, not one the client asked for.
        self.assertEqual(asset.namespace, PRODUCT_NS)

    def test_the_request_cannot_choose_its_own_namespace(self):
        self.staff.user_permissions.add(Permission.objects.get(codename='change_scope'))
        self.staff = User.objects.get(pk=self.staff.pk)

        response = self._post(self.staff, field=self.IDENTITY, namespace='dlux.systemsettings')

        self.assertEqual(response.status_code, 200)
        asset = ManagedAsset.objects.get(pk=response.json()['assets'][0]['id'])
        self.assertEqual(asset.namespace, PRODUCT_NS)

    def test_no_identity_stays_superuser_only(self):
        # The pre-1.9 System Settings picker sends no field.
        self.assertEqual(self._post(self.staff).status_code, 403)
        self.assertEqual(self._post(self.superuser).status_code, 200)

    def test_the_legacy_route_still_resolves(self):
        self.assertEqual(
            self._client(self.superuser).post(
                reverse('managed_image_picker_upload'), {'file': image_upload()},
            ).status_code,
            200,
        )


class ResolveAssetSelectionTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix='dlux-asset-resolve-')
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.current, _ = create_managed_asset(
            image_upload('current.png'), kind='image', namespace=PRODUCT_NS,
        )
        self.other, _ = create_managed_asset(
            image_upload('other.png', (5, 5, 5)), kind='image', namespace=PRODUCT_NS,
        )

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_an_upload_wins_and_lands_in_the_namespace(self):
        resolved = resolve_asset_selection(
            AssetSelection(upload=image_upload('new.png', (9, 9, 9))),
            self.current, namespace=PRODUCT_NS,
        )
        self.assertNotEqual(resolved.pk, self.current.pk)
        self.assertEqual(resolved.namespace, PRODUCT_NS)

    def test_a_chosen_asset_is_used(self):
        self.assertEqual(
            resolve_asset_selection(AssetSelection(asset=self.other), self.current),
            self.other,
        )

    def test_clear_clears(self):
        self.assertIsNone(resolve_asset_selection(AssetSelection(clear=True), self.current))

    def test_an_omitted_field_keeps_what_is_there(self):
        # A multi-step form that did not render this field must not blank it.
        self.assertEqual(
            resolve_asset_selection(AssetSelection(omitted=True), self.current),
            self.current,
        )

    def test_nothing_at_all_keeps_what_is_there(self):
        self.assertEqual(resolve_asset_selection(AssetSelection(), self.current), self.current)

    def test_commit_false_writes_nothing(self):
        before = ManagedAsset.objects.count()
        resolved = resolve_asset_selection(
            AssetSelection(upload=image_upload('preview.png', (7, 7, 7))),
            self.current, namespace=PRODUCT_NS, commit=False,
        )
        self.assertEqual(resolved, self.current)
        self.assertEqual(ManagedAsset.objects.count(), before)


class AssetPruneTests(TestCase):
    """Clean-up in the Asset Manager: two steps, and never a form in progress."""

    def setUp(self):
        cache.clear()
        from dlux.models import SystemSettings

        SystemSettings.objects.all().delete()
        cache.clear()
        settings_row = SystemSettings.load()
        settings_row.is_configured = True
        settings_row.save()
        cache.clear()
        self.media_root = tempfile.mkdtemp(prefix='dlux-asset-prune-')
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.superuser = User.objects.create_superuser('root', 'r@x.com', 'pw')
        self.staff = User.objects.create_user('clerk', 'c@x.com', 'pw')
        self.url = reverse('manage_assets_prune')

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _aged_asset(self, name='old.png', color=(4, 4, 4), hours=48):
        from datetime import timedelta

        from django.utils import timezone

        asset, _ = create_managed_asset(image_upload(name, color), kind='image', namespace=PRODUCT_NS)
        ManagedAsset.objects.filter(pk=asset.pk).update(
            created_at=timezone.now() - timedelta(hours=hours),
        )
        return ManagedAsset.objects.get(pk=asset.pk)

    def _client(self):
        client = Client()
        client.force_login(self.superuser)
        return client

    def test_a_fresh_upload_is_never_pruned(self):
        from dlux.assets import prunable_assets

        create_managed_asset(image_upload('fresh.png'), kind='image', namespace=PRODUCT_NS)
        # Unreferenced, but it could be a picture on a form still being filled in.
        self.assertEqual(prunable_assets('image'), [])

    def test_an_aged_unreferenced_asset_is_a_candidate(self):
        from dlux.assets import prunable_assets

        asset = self._aged_asset()
        self.assertEqual([candidate.pk for candidate in prunable_assets('image')], [asset.pk])

    def test_a_referenced_asset_is_never_a_candidate(self):
        from dlux.assets import prunable_assets
        from dlux.models import SystemSettings

        asset = self._aged_asset()
        settings_row = SystemSettings.load()
        settings_row.logo_asset = asset
        settings_row.save()

        self.assertEqual(prunable_assets('image'), [])

    def test_preview_reports_without_deleting(self):
        asset = self._aged_asset()

        response = self._client().post(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['preview'])
        self.assertEqual(payload['count'], 1)
        self.assertIn(asset.title, payload['titles'])
        self.assertTrue(ManagedAsset.objects.filter(pk=asset.pk).exists())

    def test_confirming_deletes(self):
        asset = self._aged_asset()

        response = self._client().post(self.url, {'confirm': '1'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['deleted'], 1)
        self.assertFalse(ManagedAsset.objects.filter(pk=asset.pk).exists())

    def test_nothing_to_do_says_so(self):
        payload = self._client().post(self.url).json()
        self.assertEqual(payload['count'], 0)
        self.assertTrue(payload['message'])

    def test_the_manager_action_stays_superuser_only(self):
        client = Client()
        client.force_login(self.staff)
        self.assertEqual(client.post(self.url, {'confirm': '1'}).status_code, 403)


class ManagedAssetFormMixinTests(TestCase):
    """The mixin end to end — the path a project actually uses."""

    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix='dlux-asset-form-')
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_post_clean_does_not_assign_the_selection_to_the_foreign_key(self):
        """The regression a project found first.

        `ModelForm._post_clean` runs `construct_instance` before `save()`, and a
        picker cleans to an `AssetSelection`, not a `ManagedAsset` — assigning it
        raised "must be a ManagedAsset instance" and made the mixin unusable on
        any real ModelForm.
        """
        from django import forms

        from dlux.forms import ManagedAssetFormMixin
        from dlux.models import Scope

        class ScopeForm(ManagedAssetFormMixin, forms.ModelForm):
            class Meta:
                model = Scope
                fields = ['name']

        form = ScopeForm(data={'name': 'Branch'})
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save(commit=False)
        self.assertEqual(instance.name, 'Branch')
