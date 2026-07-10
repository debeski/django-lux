from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase

from dlux import data_reset as dr

User = get_user_model()
AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


def _configured():
    from dlux.models import SystemSettings
    SystemSettings.objects.all().delete()
    cache.clear()
    ss = SystemSettings.load()
    ss.is_configured = True
    ss.save()
    cache.clear()


class ResetEligibilityTests(TestCase):
    def test_critical_models_are_excluded(self):
        for label in ('dlux.systemsettings', 'dlux.dluxupdatestate', 'dlux.dluxupdaterun',
                      'auth.group', 'auth.permission', 'contenttypes.contenttype', 'sessions.session'):
            self.assertFalse(dr.is_reset_eligible(apps.get_model(label)), label)

    def test_user_and_scoped_models_are_eligible(self):
        self.assertTrue(dr.is_reset_eligible(User))
        self.assertTrue(dr.is_reset_eligible(apps.get_model('dlux.ActivityLog')))

    def test_scoped_detection(self):
        self.assertTrue(dr.is_scoped(apps.get_model('dlux.ActivityLog')))
        self.assertFalse(dr.is_scoped(User))


class ResetCatalogTests(TestCase):
    def test_catalog_shape_and_user_protection(self):
        su = User.objects.create_superuser('root', 'r@x.com', 'pw')
        User.objects.create_user('joe', 'j@x.com', 'pw')
        catalog = dr.build_reset_catalog(su)
        keys = {c['key'] for c in catalog}
        self.assertNotIn('dlux.systemsettings', keys)
        self.assertIn('auth.user', keys)
        user_entry = next(c for c in catalog if c['key'] == 'auth.user')
        # Only joe is deletable — root (superuser + acting user) is protected.
        self.assertEqual(user_entry['count'], 1)
        self.assertFalse(user_entry['scoped'])

    def test_labels_are_translated_never_raw_keys(self):
        from dlux.translations import get_strings
        su = User.objects.create_superuser('root', 'r@x.com', 'pw')
        catalog = dr.build_reset_catalog(su, get_strings('ar'))
        # No label may be a raw "app.model" key (a dot signals an unresolved label).
        self.assertEqual([c['label'] for c in catalog if '.' in c['label']], [])
        by_key = {c['key']: c['label'] for c in catalog}
        self.assertEqual(by_key.get('dlux.dluxnotification'), 'الإشعارات')
        self.assertEqual(by_key.get('dlux.trusteddevice'), 'الأجهزة الموثوقة')


class ResetExecutionTests(TestCase):
    def test_scoped_model_is_soft_deleted(self):
        su = User.objects.create_superuser('root', 'r@x.com', 'pw')
        from dlux.middleware import _thread_locals
        _thread_locals.user = su
        AL = apps.get_model('dlux.ActivityLog')
        for _ in range(3):
            AL.all_objects.create(action='T', model_name='x', category='user')
        active_before = AL.objects.count()
        all_before = AL.all_objects.count()

        results = dr.execute_reset(su, ['dlux.activitylog'])
        self.assertEqual(results[0]['status'], 'soft_deleted')
        self.assertEqual(AL.objects.count(), 0)               # no active rows left
        self.assertEqual(AL.all_objects.count(), all_before)   # rows kept (recoverable)
        self.assertEqual(AL.all_objects.filter(deleted_at__isnull=False).count(), active_before)

    def test_non_scoped_hard_delete_protects_superuser_and_self(self):
        su = User.objects.create_superuser('root', 'r@x.com', 'pw')
        other_super = User.objects.create_superuser('root2', 'r2@x.com', 'pw')
        joe = User.objects.create_user('joe', 'j@x.com', 'pw')

        results = dr.execute_reset(su, ['auth.user'])
        self.assertEqual(results[0]['status'], 'deleted')
        self.assertTrue(User.objects.filter(pk=su.pk).exists())          # acting user kept
        self.assertTrue(User.objects.filter(pk=other_super.pk).exists())  # superusers kept
        self.assertFalse(User.objects.filter(pk=joe.pk).exists())         # non-superuser removed

    def test_ineligible_model_is_skipped(self):
        su = User.objects.create_superuser('root', 'r@x.com', 'pw')
        results = dr.execute_reset(su, ['dlux.systemsettings'])
        self.assertEqual(results[0]['status'], 'skipped')


class ResetEndpointTests(TestCase):
    def setUp(self):
        _configured()
        self.su = User.objects.create_superuser('root', 'r@x.com', 'pw12345!')
        self.joe = User.objects.create_user('joe', 'j@x.com', 'pw')

    def _client(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_preview_requires_superuser_and_password(self):
        # non-superuser
        self.assertEqual(self._client(self.joe).post('/sys/admin/data-reset/preview/', {'current_password': 'pw'}, **AJAX).status_code, 403)
        # wrong password
        r = self._client(self.su).post('/sys/admin/data-reset/preview/', {'current_password': 'nope'}, **AJAX)
        self.assertEqual(r.status_code, 400)
        # correct
        r2 = self._client(self.su).post('/sys/admin/data-reset/preview/', {'current_password': 'pw12345!'}, **AJAX)
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.json()['models'])

    def test_execute_gated_and_works(self):
        client = self._client(self.su)
        # no models
        self.assertEqual(client.post('/sys/admin/data-reset/execute/', {'current_password': 'pw12345!'}, **AJAX).status_code, 400)
        # execute soft-delete on a scoped model
        AL = apps.get_model('dlux.ActivityLog')
        r = client.post('/sys/admin/data-reset/execute/',
                        {'current_password': 'pw12345!', 'models': ['dlux.activitylog']}, **AJAX)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'success')
        # non-superuser blocked
        self.assertEqual(self._client(self.joe).post('/sys/admin/data-reset/execute/',
                         {'current_password': 'pw', 'models': ['dlux.activitylog']}, **AJAX).status_code, 403)
