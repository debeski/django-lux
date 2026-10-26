from dlux.tests.harness import setup_test_environment

setup_test_environment()

import json
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from dlux.api.table_columns import user_table_columns
from dlux.models import Profile, SystemSettings
from dlux.tests.test_table_columns import ColumnFixtureTable, _TableColumnTestSupport
from dlux.utils.user_table_columns import PREFERENCE_KEY, TOKEN_SALT


class UserTableColumnTests(_TableColumnTestSupport, TestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(username='column-owner', password='test-only')
        self.other = get_user_model().objects.create_user(username='column-other')
        self.factory = RequestFactory()
        self.configure({'hidden': ['email'], 'order': ['first_name', 'username', 'computed']})

    def table(self, user=None):
        request = self.factory.get('/')
        request.user = get_user_model().objects.get(pk=(user or self.user).pk)
        request.session = {}
        return ColumnFixtureTable([], request=request)

    def token(self, table=None):
        return parse_qs(urlsplit((table or self.table()).dlux_user_columns_url).query)['token'][0]

    def send(self, value=None, *, token=None, user=None, method='POST'):
        token = token or self.token()
        url = reverse('user_table_columns')
        if method == 'GET':
            request = self.factory.get(url, {'token': token})
        else:
            request = self.factory.post(url, json.dumps({'token': token, 'preferences': value}), content_type='application/json')
        request.user = user or self.user
        request.session = {}
        return user_table_columns(request)

    def test_save_reorders_and_hides_only_for_owner(self):
        self.assertEqual(self.send({'hidden': ['username'], 'order': ['computed', 'first_name', 'username']}).status_code, 200)
        owner = self.table()
        self.assertEqual([c.name for c in owner.columns], ['computed', 'first_name'])
        self.assertEqual([c.name for c in self.table(self.other).columns], ['first_name', 'username', 'computed'])

    def test_admin_hidden_and_developer_hidden_cannot_be_requested(self):
        for name in ['email', 'internal', 'scope', 'dlux_row_actions', 'not_a_column']:
            with self.subTest(name=name):
                self.assertEqual(self.send({'order': [name]}).status_code, 400)
        html = json.loads(self.send(method='GET').content)['html']
        self.assertNotIn('data-column-name="email"', html)
        self.assertNotIn('data-column-name="internal"', html)

    def test_new_admin_restriction_applies_to_old_dialog_and_stored_preferences(self):
        old_token = self.token()
        self.send({'order': ['computed', 'username', 'first_name']})
        self.configure({'hidden': ['email', 'computed']})
        self.assertEqual(self.send({'order': ['computed']}, token=old_token).status_code, 400)
        self.assertNotIn('computed', [c.name for c in self.table().columns])
        self.assertNotIn('data-column-name="computed"', json.loads(self.send(token=old_token, method='GET').content)['html'])

    def test_rejects_forged_and_other_user_tokens(self):
        token = self.token()
        self.assertEqual(self.send({}, token=token+'tampered').status_code, 403)
        self.assertEqual(self.send({}, token=token, user=self.other).status_code, 403)

    def test_expired_dialog_requires_reload(self):
        token = self.token()
        with patch('django.core.signing.time.time', return_value=99999999999):
            self.assertEqual(self.send({}, token=token).status_code, 403)

    def test_login_and_post_only_mutation(self):
        self.assertEqual(self.send({}, user=AnonymousUser()).status_code, 302)
        self.assertEqual(self.send(method='GET').status_code, 200)
        self.assertFalse(Profile.all_objects.get(user=self.user).preferences.get(PREFERENCE_KEY))
        request = self.factory.put(reverse('user_table_columns'))
        request.user = self.user
        self.assertEqual(user_table_columns(request).status_code, 405)

    def test_csrf_protects_save(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        with self.modify_settings(MIDDLEWARE={'append': 'django.middleware.csrf.CsrfViewMiddleware'}):
            response = client.post(reverse('user_table_columns'), {'token': self.token(), 'preferences': '{}'})
        self.assertEqual(response.status_code, 403)

    def test_rejects_all_hidden_and_invalid_shapes(self):
        for value in [[], {'hidden': ['first_name', 'username', 'computed']}, {'hidden': 'username'},
                      {'headers': {}}, {'order': [{}]}, {'reset': 'false'}]:
            with self.subTest(value=value):
                self.assertEqual(self.send(value).status_code, 400)

    def test_restore_removes_only_this_table_override(self):
        profile = Profile.all_objects.get(user=self.user)
        profile.preferences = {'theme': 'dark', PREFERENCE_KEY: {'another-table': {'hidden': ['x']}}}
        profile.save(update_fields=['preferences'])
        token = self.token()
        profile.refresh_from_db()
        previous = profile.preferences
        self.send({'hidden': ['username']}, token=token)
        self.assertEqual(self.send({'reset': True}, token=token).status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.preferences, previous)

    def test_default_selection_removes_override(self):
        self.send({'hidden': ['username']})
        self.send({'order': ['first_name', 'username', 'computed'], 'hidden': []})
        self.assertFalse(Profile.all_objects.get(user=self.user).preferences.get(PREFERENCE_KEY))

    def test_stored_corrupt_overlay_cannot_widen_visibility_or_hide_everything(self):
        table = self.table()
        profile = Profile.all_objects.get(user=self.user)
        profile.preferences = {PREFERENCE_KEY: {table.dlux_user_columns_key: {
            'order': ['internal', 'email', 'computed'], 'hidden': ['first_name', 'username', 'computed']}}}
        profile.save(update_fields=['preferences'])
        self.assertEqual([c.name for c in self.table().columns], ['computed'])

    def test_preference_cap_is_enforced_without_losing_previous_settings(self):
        profile = Profile.all_objects.get(user=self.user)
        profile.preferences = {'app': {'example': 'x' * 1100}}
        profile.save(update_fields=['preferences'])
        with self.settings(DLUX_MAX_PREFERENCES_BYTES=1024):
            self.assertEqual(self.send({'hidden': ['username']}).status_code, 413)
        profile.refresh_from_db()
        self.assertNotIn(PREFERENCE_KEY, profile.preferences)

    def test_signed_catalog_has_no_rows_or_sensitive_values(self):
        payload = signing.loads(self.token(), salt=TOKEN_SALT)
        self.assertEqual(set(payload), {'user', 'key', 'model', 'columns'})
        self.assertNotIn('password', [c['name'] for c in payload['columns']])
        self.assertNotIn('email', [c['name'] for c in payload['columns']])

    def test_generic_table_mixin_can_bind_request_after_table_construction(self):
        request = self.factory.get('/')
        request.user = self.user
        request.session = {}
        with patch('dlux.middleware.get_current_request', return_value=request):
            table = ColumnFixtureTable([])
        self.assertTrue(table.dlux_user_columns_url)

    def test_modal_multipart_save_after_csrf_has_consumed_the_post_stream(self):
        request = self.factory.post(reverse('user_table_columns'), {
            'token': self.token(), 'preferences': json.dumps({'hidden': ['username']})})
        request.user = self.user
        request.session = {}
        self.assertTrue(request.POST)
        self.assertEqual(user_table_columns(request).status_code, 200)

    def test_added_developer_column_keeps_existing_preferences(self):
        import django_tables2 as tables
        baseline = self.table()
        self.send({'hidden': ['username'], 'order': ['computed', 'first_name', 'username']})
        request = self.factory.get('/')
        request.user = get_user_model().objects.get(pk=self.user.pk)
        request.session = {}
        changed = ColumnFixtureTable([], request=request, extra_columns=[('new_column', tables.Column())])
        self.assertEqual(changed.dlux_user_columns_key, baseline.dlux_user_columns_key)
        self.assertEqual([c.name for c in changed.columns], ['computed', 'first_name', 'new_column'])

    def test_prefixed_table_variants_have_separate_personal_keys(self):
        request = self.factory.get('/')
        request.user = self.user
        request.session = {}
        other = ColumnFixtureTable([], request=request, prefix='other-')
        self.assertNotEqual(other.dlux_user_columns_key, self.table().dlux_user_columns_key)

    def test_admin_can_disable_personal_layouts_and_revoke_existing_dialogs(self):
        token = self.token()
        self.send({'hidden':['username']}, token=token)
        self.configure({'hidden':['email'], 'user_columns':False})
        self.assertFalse(getattr(self.table(), 'dlux_user_columns_url', None))
        self.assertIn('username', [column.name for column in self.table().columns])
        self.assertEqual(self.send({}, token=token).status_code, 403)
        self.assertEqual(self.send(token=token, method='GET').status_code, 403)

    def test_admin_personal_layout_flag_accepts_boolean_tokens(self):
        from dlux.system.table_columns import normalize_tables_config
        for value in (False, 'false', 'off', 0):
            normalized = normalize_tables_config({'columns':{'auth.user':{'user_columns':value}}})
            self.assertIs(normalized['columns']['auth.user']['user_columns'], False)
