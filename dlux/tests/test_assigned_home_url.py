from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from dlux.discovery import build_user_home_url_options
from dlux.forms import CustomUserChangeForm, GroupPresetForm
from dlux.models import GroupProfile, Profile, SystemSettings
from dlux.utils import get_group_home_urls, resolve_assigned_home_url, resolve_user_home_url, set_group_home_url
from dlux.utils.config import normalize_profile_config

User = get_user_model()


class AssignedHomeUrlTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser('hadmin', 'ha@example.com', 'pw12345678')
        self.user = User.objects.create_user('huser', 'hu@example.com', 'pw12345678')
        self.user.profile.is_configured = True
        self.user.profile.save()
        self._allow(True)
        user_pages = [o['value'] for o in build_user_home_url_options(self.user)]
        self.assertGreaterEqual(len(user_pages), 2)
        self.page_a, self.page_b = user_pages[:2]
        admin_only = (
            {o['value'] for o in build_user_home_url_options(self.admin)} - set(user_pages)
        )
        self.admin_only_page = sorted(admin_only)[0]

    def _allow(self, enabled):
        settings = SystemSettings.load()
        settings.profile_config = normalize_profile_config({'allow_user_home_url': enabled})
        settings.is_configured = True
        settings.save()
        cache.delete('SystemSettings')

    def _group(self, name, home_url, is_active=True):
        group = Group.objects.create(name=name)
        GroupProfile.objects.create(group=group, is_active=is_active)
        set_group_home_url(name, home_url)
        self.user.groups.add(group)
        return group

    def _assign(self, url):
        Profile.all_objects.filter(user=self.user).update(preferences={'admin_home_url': url})

    def _reload(self):
        return User.objects.get(pk=self.user.pk)

    def test_precedence_user_pick_then_admin_user_then_group(self):
        self._group('Beta', self.page_a)
        self._group('Alpha', self.page_b)
        self.assertEqual(resolve_user_home_url(self._reload()), self.page_b)

        self._assign(self.page_a)
        self.assertEqual(resolve_user_home_url(self._reload()), self.page_a)

        Profile.all_objects.filter(user=self.user).update(
            preferences={'admin_home_url': self.page_a, 'user_home_url': self.page_b},
        )
        self.assertEqual(resolve_user_home_url(self._reload()), self.page_b)

    def test_disabled_setting_ignores_assignments(self):
        self._assign(self.page_a)
        self._group('Alpha', self.page_b)
        self._allow(False)
        self.assertEqual(resolve_user_home_url(self._reload()), '')

    def test_inactive_group_and_inaccessible_page_are_skipped(self):
        self._group('Alpha', self.page_a, is_active=False)
        self._group('Beta', self.admin_only_page)
        self.assertEqual(resolve_assigned_home_url(self._reload()), '')
        self._group('Gamma', self.page_b)
        self.assertEqual(resolve_assigned_home_url(self._reload()), self.page_b)

    def test_user_form_offers_and_saves_assignment(self):
        form = CustomUserChangeForm(instance=self.user, user=self.admin)
        values = [value for value, _label in form.fields['assigned_home_url'].choices]
        self.assertIn(self.page_a, values)
        self.assertNotIn(self.admin_only_page, values)

        data = {
            'username': self.user.username, 'first_name': '', 'last_name': '',
            'email': '', 'is_active': 'on', 'phone': '', 'scope': '',
            'assigned_home_url': self.admin_only_page,
        }
        self.assertFalse(CustomUserChangeForm(data=data, instance=self.user, user=self.admin).is_valid())
        data['assigned_home_url'] = self.page_a
        form = CustomUserChangeForm(data=data, instance=self.user, user=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(Profile.all_objects.get(user=self.user).preferences['admin_home_url'], self.page_a)

    def test_forms_hide_field_when_setting_disabled(self):
        self._allow(False)
        self.assertNotIn('assigned_home_url', CustomUserChangeForm(instance=self.user, user=self.admin).fields)
        self.assertNotIn('home_url', GroupPresetForm(user=self.admin).fields)

    def test_group_form_saves_members_landing_page(self):
        form = GroupPresetForm(
            data={'name': 'Clerks', 'description': '', 'scope': '', 'permissions': [], 'home_url': self.page_a},
            user=self.admin,
        )
        self.assertTrue(form.is_valid(), form.errors)
        group = form.save()
        self.assertEqual(get_group_home_urls(), {'Clerks': self.page_a})

        form = GroupPresetForm(
            data={'name': 'Tellers', 'description': '', 'scope': '', 'permissions': [], 'home_url': self.page_a},
            instance=group, user=self.admin,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(get_group_home_urls(), {'Tellers': self.page_a})

        client = Client()
        client.force_login(self.admin)
        client.post(reverse('delete_group', args=[group.pk]))
        self.assertEqual(get_group_home_urls(), {})

    def test_user_cannot_write_or_reset_away_the_assignment(self):
        self._assign(self.page_a)
        client = Client()
        client.force_login(self.user)
        client.post(reverse('update_preferences'), {'admin_home_url': self.page_b})
        self.assertEqual(Profile.all_objects.get(user=self.user).preferences['admin_home_url'], self.page_a)
        client.post(reverse('reset_preferences'))
        self.assertEqual(Profile.all_objects.get(user=self.user).preferences, {'admin_home_url': self.page_a})

    def test_login_lands_on_group_page_and_options_names_it(self):
        self._group('Alpha', self.page_a)
        client = Client()
        response = client.post(reverse('login'), {'username': 'huser', 'password': 'pw12345678'})
        self.assertEqual(response['Location'], self.page_a)
        client.force_login(self.user)
        html = client.get(reverse('options_view')).content.decode()
        self.assertIn('Set by your administrator', html)
