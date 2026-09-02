from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase

from dlux.admin_actions import data_reset as dr

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


class ResetChildModelTests(TestCase):
    """A model that is only a line of another record is never offered."""

    def test_cascade_child_is_detected_and_excluded(self):
        # ManagedFontVariant belongs to a ManagedFontFamily by a required CASCADE FK.
        variant = apps.get_model('dlux.ManagedFontVariant')
        family = apps.get_model('dlux.ManagedFontFamily')
        self.assertIs(dr.cascade_parent(variant), family)
        self.assertFalse(dr.is_reset_eligible(variant))
        self.assertTrue(dr.is_reset_eligible(family))

    def test_user_is_never_treated_as_a_parent(self):
        # Devices cascade from a user, but clearing users is not how an operator
        # clears devices — they stay selectable in their own right.
        device = apps.get_model('dlux.TrustedDevice')
        self.assertIsNone(dr.cascade_parent(device))
        self.assertTrue(dr.is_reset_eligible(device))

    def test_scoped_model_is_never_a_line(self):
        self.assertIsNone(dr.cascade_parent(apps.get_model('dlux.ActivityLog')))

    def test_child_is_absent_from_the_catalog_and_refused_by_execute(self):
        su = User.objects.create_superuser('root', 'r@x.com', 'pw')
        keys = {c['key'] for c in dr.build_reset_catalog(su)}
        self.assertNotIn('dlux.managedfontvariant', keys)
        result = dr.execute_reset(su, ['dlux.managedfontvariant'])[0]
        self.assertEqual(result['status'], 'skipped')
        self.assertEqual(result['reason'], 'not_eligible')


class ResetPermanentModeTests(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser('root', 'r@x.com', 'pw')
        from dlux.middleware import _thread_locals
        _thread_locals.user = self.su
        self.AL = apps.get_model('dlux.ActivityLog')

    def _rows(self, live=2, trashed=3):
        from django.utils import timezone
        # Creating the superuser above logs its own activity row; start from zero
        # so the counts below are exactly what this test wrote.
        self.AL.all_objects.all().delete()
        for _ in range(live):
            self.AL.all_objects.create(action='LIVE', model_name='x', category='user')
        for _ in range(trashed):
            self.AL.all_objects.create(action='OLD', model_name='x', category='user',
                                       deleted_at=timezone.now())

    def test_mode_normalization_defaults_to_soft(self):
        self.assertEqual(dr.normalize_mode(None), dr.RESET_MODE_SOFT)
        self.assertEqual(dr.normalize_mode('nonsense'), dr.RESET_MODE_SOFT)
        self.assertEqual(dr.normalize_mode('PERMANENT'), dr.RESET_MODE_PERMANENT)

    def test_permanent_hard_deletes_scoped_rows_and_empties_the_bin(self):
        self._rows(live=2, trashed=3)
        results = dr.execute_reset(self.su, ['dlux.activitylog'], mode=dr.RESET_MODE_PERMANENT)
        entry = next(r for r in results if r['key'] == 'dlux.activitylog')
        self.assertEqual(entry['status'], 'deleted')
        self.assertEqual(entry['deleted'], 5)          # live + already soft-deleted
        self.assertEqual(self.AL.all_objects.count(), 0)

    def test_soft_mode_leaves_the_bin_alone(self):
        self._rows(live=2, trashed=3)
        results = dr.execute_reset(self.su, ['dlux.activitylog'])
        entry = next(r for r in results if r['key'] == 'dlux.activitylog')
        self.assertEqual(entry['status'], 'soft_deleted')
        self.assertEqual(entry['deleted'], 2)           # only the live rows
        self.assertEqual(self.AL.all_objects.count(), 5)

    def test_catalog_reports_the_recycle_bin_separately(self):
        self._rows(live=2, trashed=3)
        entry = next(c for c in dr.build_reset_catalog(self.su) if c['key'] == 'dlux.activitylog')
        self.assertEqual(entry['count'], 2)
        self.assertEqual(entry['trashed'], 3)

    def test_finished_signal_carries_the_run(self):
        self._rows(live=1, trashed=0)
        seen = {}

        def receiver(sender, **kwargs):
            seen.update(kwargs)

        dr.data_reset_finished.connect(receiver)
        try:
            dr.execute_reset(self.su, ['dlux.activitylog'], mode=dr.RESET_MODE_PERMANENT)
        finally:
            dr.data_reset_finished.disconnect(receiver)
        self.assertEqual(seen.get('mode'), dr.RESET_MODE_PERMANENT)
        self.assertEqual(seen.get('models'), ['dlux.activitylog'])
        self.assertEqual(seen.get('actor'), self.su)
        self.assertTrue(seen.get('results'))

    def test_a_failing_receiver_never_fails_the_reset(self):
        self._rows(live=1, trashed=0)

        def boom(sender, **kwargs):
            raise RuntimeError('receiver exploded')

        dr.data_reset_finished.connect(boom)
        try:
            results = dr.execute_reset(self.su, ['dlux.activitylog'])
        finally:
            dr.data_reset_finished.disconnect(boom)
        self.assertEqual(results[0]['status'], 'soft_deleted')


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

    def test_permanent_mode_requires_the_typed_word(self):
        client = self._client(self.su)
        base = {'current_password': 'pw12345!', 'models': ['dlux.activitylog'], 'mode': 'permanent'}
        # missing
        self.assertEqual(client.post('/sys/admin/data-reset/execute/', base, **AJAX).status_code, 400)
        # wrong
        self.assertEqual(client.post('/sys/admin/data-reset/execute/',
                                     dict(base, confirm_permanent='yes'), **AJAX).status_code, 400)
        # the English default, case-insensitively
        r = client.post('/sys/admin/data-reset/execute/', dict(base, confirm_permanent='delete'), **AJAX)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['mode'], 'permanent')

    def test_unknown_mode_falls_back_to_soft_and_needs_no_word(self):
        r = self._client(self.su).post('/sys/admin/data-reset/execute/',
                                       {'current_password': 'pw12345!', 'models': ['dlux.activitylog'],
                                        'mode': 'obliterate'}, **AJAX)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['mode'], 'soft')
