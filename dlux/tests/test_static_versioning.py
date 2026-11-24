"""Static URLs change with every release.

A generated stack's proxy serves /static/ as immutable for a year, so a plain
{% static %} project script kept its old copy in the browser after an upgrade
(found upgrading Trademarks to DjangoLux 1.16.5). dlux_settings() now swaps
Django's default static storage for VersionedStaticFilesStorage, whose URLs
carry ?v=<DjangoLux version>-<project version>.
"""
from dlux.tests.harness import setup_test_environment

setup_test_environment()

import json
import tempfile
from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase, override_settings

from dlux import __version__
from dlux.static_storage import release_revision
from dlux.templatetags.dlux_tags import dlux_static
from dlux.utils.settings import DEFAULT_STATIC_BACKEND, VERSIONED_STATIC_BACKEND, dlux_settings

VERSIONED_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': VERSIONED_STATIC_BACKEND},
}


def _settings_scope(**extra):
    return {'INSTALLED_APPS': [], 'MIDDLEWARE': [], 'TEMPLATES': [], **extra}


class DluxSettingsStorageTests(SimpleTestCase):
    def test_a_project_without_storages_gets_versioned_static_files(self):
        scope = _settings_scope()
        dlux_settings(scope)
        self.assertEqual(scope['STORAGES']['staticfiles']['BACKEND'], VERSIONED_STATIC_BACKEND)
        self.assertEqual(scope['STORAGES']['default']['BACKEND'], 'django.core.files.storage.FileSystemStorage')

    def test_the_default_static_backend_is_swapped_and_the_rest_kept(self):
        """Decrees sets STORAGES with its own default storage and Django's static one."""
        storages = {
            'default': {'BACKEND': 'documents.storage.DocumentStorage'},
            'staticfiles': {'BACKEND': DEFAULT_STATIC_BACKEND, 'OPTIONS': {'location': '/app/staticfiles'}},
        }
        scope = _settings_scope(STORAGES=storages)
        dlux_settings(scope)
        self.assertEqual(scope['STORAGES']['default'], {'BACKEND': 'documents.storage.DocumentStorage'})
        self.assertEqual(scope['STORAGES']['staticfiles'], {
            'BACKEND': VERSIONED_STATIC_BACKEND, 'OPTIONS': {'location': '/app/staticfiles'},
        })
        self.assertEqual(storages['staticfiles']['BACKEND'], DEFAULT_STATIC_BACKEND, 'the project dict is not mutated')

    def test_a_chosen_static_backend_and_the_opt_out_are_respected(self):
        manifest = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'
        scope = _settings_scope(STORAGES={'default': {}, 'staticfiles': {'BACKEND': manifest}})
        dlux_settings(scope)
        self.assertEqual(scope['STORAGES']['staticfiles']['BACKEND'], manifest)

        scope = _settings_scope(DLUX_VERSIONED_STATIC=False)
        dlux_settings(scope)
        self.assertNotIn('STORAGES', scope)


@override_settings(STORAGES=VERSIONED_STORAGES, STATIC_URL='/static/', DEBUG=False)
class VersionedStaticUrlTests(SimpleTestCase):
    def setUp(self):
        release_revision.cache_clear()
        self.addCleanup(release_revision.cache_clear)

    def _static(self, path):
        return Template("{% load static %}{% static path %}").render(Context({'path': path}))

    def test_static_urls_carry_the_release(self):
        self.assertEqual(self._static('documents/js/phase4_cases.js'), f'/static/documents/js/phase4_cases.js?v={__version__}')

    def test_the_project_version_joins_the_release(self):
        with tempfile.TemporaryDirectory() as base:
            Path(base, 'release-manifest.json').write_text(json.dumps({'version': '2.2.2'}), encoding='utf-8')
            with self.settings(BASE_DIR=base):
                release_revision.cache_clear()
                url = self._static('documents/js/phase4_cases.js')
        self.assertEqual(url, f'/static/documents/js/phase4_cases.js?v={__version__}-2.2.2')

    def test_dlux_static_adds_no_second_version(self):
        url = dlux_static('dlux/base/js/lazy.js')
        self.assertEqual(url, f'/static/dlux/base/js/lazy.js?v={__version__}')
        self.assertEqual(url.count('v='), 1)


@override_settings(STATIC_URL='/static/', DEBUG=False)
class DluxStaticWithoutVersionedStorageTests(SimpleTestCase):
    def test_dlux_static_still_versions_on_django_default_storage(self):
        release_revision.cache_clear()
        self.assertEqual(dlux_static('dlux/base/js/lazy.js'), f'/static/dlux/base/js/lazy.js?v={__version__}')
