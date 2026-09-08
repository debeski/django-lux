"""`dlux_prune_assets` must never delete an asset something still points at.

Deleting a file is not undoable, so the command is conservative by construction:
dry run unless `--apply`, references read from the `ManagedAssetField` registry
(the same declarations the upload endpoint trusts), the shared pool left alone,
and a run that cannot read a declared model refuses rather than treating its
assets as unreferenced.
"""
from io import StringIO

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase

from dlux.models import ManagedAsset, SystemSettings
from dlux.models.assets import SHARED_ASSET_NAMESPACE


def _asset(namespace='catalog.product', kind='image', name='x.png'):
    asset = ManagedAsset(kind=kind, namespace=namespace)
    asset.file.save(name, ContentFile(b'x'), save=False)
    asset.save()
    return asset


def _run(*args):
    out = StringIO()
    call_command('dlux_prune_assets', *args, stdout=out, stderr=StringIO())
    return out.getvalue()


class PruneAssetsTests(TestCase):
    def test_a_dry_run_deletes_nothing(self):
        orphan = _asset()
        output = _run()
        self.assertIn('Dry run', output)
        self.assertTrue(ManagedAsset.objects.filter(pk=orphan.pk).exists())

    def test_apply_removes_an_unreferenced_asset(self):
        orphan = _asset()
        _run('--apply')
        self.assertFalse(ManagedAsset.objects.filter(pk=orphan.pk).exists())

    def test_a_referenced_asset_is_never_deleted(self):
        # SystemSettings.logo_asset is a real declared ManagedAssetField.
        used = _asset(namespace='dlux.branding')
        settings_row = SystemSettings.load()
        settings_row.logo_asset = used
        settings_row.save()

        _run('--apply')
        self.assertTrue(
            ManagedAsset.objects.filter(pk=used.pk).exists(),
            'an asset a declared field points at must survive',
        )

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
        from unittest import mock

        orphan = _asset()
        broken = mock.Mock()
        broken.identity = 'app.model.field'
        broken.field_name = 'field'
        broken.model._default_manager.filter.side_effect = RuntimeError('no such table')
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
