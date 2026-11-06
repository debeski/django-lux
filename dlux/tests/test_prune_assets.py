"""`dlux_prune_assets` must never delete an asset something still points at.

Deleting a file is not undoable, so the command is conservative by construction:
dry run unless `--apply`; references read from every relation to the asset model
(plain foreign keys such as the branding fields, hidden ones, many-to-manys) plus
the `ManagedAssetField` registry, through base managers so trashed records count;
the shared pool left alone; a run that cannot read a relation refuses rather than
treating its assets as unreferenced; and the row is deleted before the file, so a
refused delete leaves both intact.
"""
from io import StringIO
from unittest import mock

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.apps import apps
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import connection, models
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from dlux.assets import referenced_asset_ids
from dlux.managers import ScopedManager
from dlux.models import (
    ManagedAsset, ManagedFontFamily, ManagedFontVariant, ScanLinkRelease, SystemSettings,
)
from dlux.models.assets import SHARED_ASSET_NAMESPACE

BRANDING_FIELDS = ('logo_asset', 'login_logo_asset', 'favicon_asset', 'login_background_asset')


def _asset(namespace='catalog.product', kind='image', name='x.png'):
    asset = ManagedAsset(kind=kind, namespace=namespace)
    asset.file.save(name, ContentFile(b'x'), save=False)
    asset.save()
    return asset


def _stored(asset):
    return asset.file.storage.exists(asset.file.name)


def _run(*args, stderr=None):
    out = StringIO()
    call_command('dlux_prune_assets', *args, stdout=out, stderr=stderr or StringIO())
    return out.getvalue()


class PruneAssetsTests(TestCase):
    def test_a_dry_run_deletes_nothing(self):
        orphan = _asset()
        output = _run()
        self.assertIn('Dry run', output)
        self.assertTrue(ManagedAsset.objects.filter(pk=orphan.pk).exists())

    def test_apply_removes_an_unreferenced_asset_and_then_its_file(self):
        orphan = _asset()
        name = orphan.file.name
        with self.captureOnCommitCallbacks(execute=True):
            _run('--apply')
        self.assertFalse(ManagedAsset.objects.filter(pk=orphan.pk).exists())
        self.assertFalse(orphan.file.storage.exists(name))

    def test_fk_referenced_branding_assets_keep_their_row_and_file(self):
        # Plain ForeignKeys on SystemSettings, not declared ManagedAssetFields:
        # the registry alone never counted them, and --apply emptied a live logo.
        settings_row = SystemSettings.load()
        used = {}
        for field in BRANDING_FIELDS:
            used[field] = _asset(namespace='dlux.branding', name=f'{field}.png')
            setattr(settings_row, field, used[field])
        settings_row.save()

        preview = _run()
        with self.captureOnCommitCallbacks(execute=True):
            _run('--apply')

        for field, asset in used.items():
            with self.subTest(field=field):
                self.assertNotIn(asset.file.name, preview, 'a referenced asset is not a candidate')
                self.assertTrue(ManagedAsset.objects.filter(pk=asset.pk).exists())
                self.assertTrue(_stored(asset), 'the file of a referenced asset must survive')

    def test_font_variants_and_scanlink_releases_count_as_references(self):
        font = _asset(namespace='dlux.fonts', kind='font', name='probe.woff2')
        family = ManagedFontFamily.objects.create(slug='probe', family='Probe', label='Probe')
        ManagedFontVariant.objects.create(font=family, asset=font)
        installer = _asset(namespace='dlux.scanlink', kind='installer', name='probe.exe')
        ScanLinkRelease.objects.create(version='1.0.0', asset=installer)

        self.assertLessEqual({font.pk, installer.pk}, referenced_asset_ids())
        with self.captureOnCommitCallbacks(execute=True):
            _run('--apply')
        for asset in (font, installer):
            self.assertTrue(ManagedAsset.objects.filter(pk=asset.pk).exists())
            self.assertTrue(_stored(asset))

    def test_a_refused_delete_keeps_the_row_and_its_file(self):
        # A reference the scan did not see (added since, say): the database refuses
        # the row delete, and the file must not already be gone by then.
        used = _asset(namespace='dlux.branding')
        settings_row = SystemSettings.load()
        settings_row.logo_asset = used
        settings_row.save()

        errors = StringIO()
        with mock.patch(
            'dlux.management.commands.dlux_prune_assets.Command._referenced_ids',
            return_value=set(),
        ), self.captureOnCommitCallbacks(execute=True):
            output = _run('--apply', stderr=errors)

        self.assertTrue(ManagedAsset.objects.filter(pk=used.pk).exists())
        self.assertTrue(_stored(used))
        self.assertIn(f'kept #{used.pk}', errors.getvalue())
        self.assertIn('Deleted 0 of 1', output)

    def test_the_shared_pool_is_left_alone(self):
        shared = _asset(namespace=SHARED_ASSET_NAMESPACE)
        _run('--apply')
        self.assertTrue(
            ManagedAsset.objects.filter(pk=shared.pk).exists(),
            'the shared pool is curated; unreferenced is not evidence of unused',
        )

    def test_include_shared_opts_into_it(self):
        shared = _asset(namespace=SHARED_ASSET_NAMESPACE)
        _run('--apply', '--include-shared')
        self.assertFalse(ManagedAsset.objects.filter(pk=shared.pk).exists())

    def test_a_namespace_filter_scopes_the_run(self):
        keep = _asset(namespace='catalog.product')
        drop = _asset(namespace='catalog.service')
        _run('--apply', '--namespace', 'catalog.service')
        self.assertTrue(ManagedAsset.objects.filter(pk=keep.pk).exists())
        self.assertFalse(ManagedAsset.objects.filter(pk=drop.pk).exists())

    def test_a_kind_filter_scopes_the_run(self):
        image = _asset(kind='image')
        font = _asset(kind='font', name='x.woff2')
        _run('--apply', '--kind', 'font')
        self.assertTrue(ManagedAsset.objects.filter(pk=image.pk).exists())
        self.assertFalse(ManagedAsset.objects.filter(pk=font.pk).exists())

    def test_the_report_groups_by_namespace(self):
        _asset(namespace='catalog.product')
        _asset(namespace='catalog.service')
        output = _run()
        self.assertIn('catalog.product', output)
        self.assertIn('catalog.service', output)

    def test_an_unreadable_declaration_refuses_to_prune(self):
        orphan = _asset()
        broken = mock.Mock()
        broken.identity = 'app.model.field'
        broken.field_name = 'field'
        broken.model._base_manager.filter.side_effect = RuntimeError('no such table')
        with mock.patch(
            'dlux.management.commands.dlux_prune_assets.registered_asset_fields',
            return_value={'app.model.field': broken},
        ):
            with self.assertRaises(RuntimeError):
                _run('--apply')
        self.assertTrue(
            ManagedAsset.objects.filter(pk=orphan.pk).exists(),
            'a run that cannot count references must delete nothing',
        )

    def test_an_unreadable_relation_refuses_to_prune(self):
        orphan = _asset()
        broken = mock.Mock()
        broken.filter.side_effect = RuntimeError('no such table')
        with mock.patch.object(ScanLinkRelease._meta, 'base_manager', broken):
            with self.assertRaises(RuntimeError):
                _run('--apply')
        self.assertTrue(ManagedAsset.objects.filter(pk=orphan.pk).exists())


def _register_probe():
    """A model with a hidden FK to assets whose default manager hides trashed rows."""
    meta = type('Meta', (), {'app_label': 'dlux', 'db_table': 'dlux_test_prune_probe'})
    return type('PruneProbe', (models.Model,), {
        '__module__': __name__,
        'photo': models.ForeignKey(
            'dlux.ManagedAsset', on_delete=models.SET_NULL, null=True, related_name='+',
        ),
        'deleted_at': models.DateTimeField(null=True),
        'objects': ScopedManager(),
        'Meta': meta,
    })


def _unregister_probe():
    apps.all_models['dlux'].pop('pruneprobe', None)
    apps.clear_cache()


class HiddenAndTrashedReferenceTests(TransactionTestCase):
    """References no visible relation or default manager shows.

    The probe's FK is `SET_NULL`, so the database would not refuse the delete:
    only the reference count stands between `--apply` and a lost picture.
    """

    def setUp(self):
        super().setUp()
        # Only the relation walk is under test; other modules leave declarations
        # on isolated models behind, which would make the run (rightly) refuse.
        registry = mock.patch(
            'dlux.management.commands.dlux_prune_assets.registered_asset_fields', return_value={},
        )
        registry.start()
        self.addCleanup(registry.stop)
        self.addCleanup(_unregister_probe)
        self.Probe = _register_probe()
        with connection.schema_editor() as editor:
            editor.create_model(self.Probe)
        self.addCleanup(self._drop_probe)

    def _drop_probe(self):
        with connection.schema_editor() as editor:
            editor.delete_model(self.Probe)

    def test_a_hidden_relation_counts(self):
        used = _asset()
        record = self.Probe.objects.create(photo=used)
        _run('--apply')
        self.assertTrue(ManagedAsset.objects.filter(pk=used.pk).exists())
        self.assertTrue(_stored(used))
        record.refresh_from_db()
        self.assertEqual(record.photo_id, used.pk)

    def test_a_soft_deleted_record_still_holds_its_asset(self):
        used = _asset()
        record = self.Probe.objects.create(photo=used, deleted_at=timezone.now())
        self.assertFalse(self.Probe.objects.filter(pk=record.pk).exists(), 'hidden by its default manager')
        _run('--apply')
        self.assertTrue(ManagedAsset.objects.filter(pk=used.pk).exists())
        self.assertTrue(_stored(used))
        self.assertEqual(self.Probe._base_manager.get(pk=record.pk).photo_id, used.pk)
