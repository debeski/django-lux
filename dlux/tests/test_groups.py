from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from dlux.forms import GroupPresetForm, GroupMembersForm
from dlux.models import GroupProfile, GroupMembership, Scope, ScopeSettings, SystemSettings
from dlux.utils import (
    can_manage_group_preset,
    get_visible_group_presets,
    set_group_members,
    set_user_group_presets,
)

User = get_user_model()


def _assignable_perms():
    """Two dlux permissions that survive get_assignable_permissions_queryset()."""
    return (
        Permission.objects.get(content_type__app_label='dlux', codename='view_reports'),
        Permission.objects.get(content_type__app_label='dlux', codename='download_backup'),
    )


class GroupPresetCoreTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.member = User.objects.create_user('member', 'member@example.com', 'pw')
        self.p_view, self.p_down = _assignable_perms()

    def _make_preset(self, name='Warehouse Staff', perms=None):
        perms = perms if perms is not None else [self.p_view, self.p_down]
        form = GroupPresetForm(
            data={'name': name, 'description': 'desc', 'scope': '',
                  'permissions': [p.pk for p in perms]},
            user=self.admin,
        )
        self.assertTrue(form.is_valid(), form.errors)
        return form.save()

    def test_preset_form_creates_group_profile_and_permissions(self):
        grp = self._make_preset()
        self.assertTrue(GroupProfile.objects.filter(group=grp).exists())
        self.assertIsNone(grp.dlux_profile.scope)  # global
        self.assertEqual(grp.permissions.count(), 2)

    def test_live_membership_grants_permissions_via_has_perm(self):
        grp = self._make_preset()
        set_user_group_presets(self.member, [grp], actor=self.admin)
        member = User.objects.get(pk=self.member.pk)
        self.assertTrue(member.has_perm('dlux.view_reports'))
        self.assertTrue(member.has_perm('dlux.download_backup'))
        gm = GroupMembership.objects.get(user=self.member, group=grp)
        self.assertEqual(gm.assigned_by_id, self.admin.pk)
        self.assertIsNotNone(gm.assigned_at)

    def test_editing_preset_propagates_to_members(self):
        grp = self._make_preset()
        set_user_group_presets(self.member, [grp], actor=self.admin)
        # Narrow the preset to a single permission.
        form = GroupPresetForm(
            data={'name': grp.name, 'description': 'desc', 'scope': '',
                  'permissions': [self.p_view.pk]},
            instance=grp, user=self.admin,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        member = User.objects.get(pk=self.member.pk)
        self.assertTrue(member.has_perm('dlux.view_reports'))
        self.assertFalse(member.has_perm('dlux.download_backup'))

    def test_reconcile_removes_membership_and_audit(self):
        grp = self._make_preset()
        set_user_group_presets(self.member, [grp], actor=self.admin)
        set_user_group_presets(self.member, [], actor=self.admin)
        member = User.objects.get(pk=self.member.pk)
        self.assertFalse(member.groups.filter(pk=grp.pk).exists())
        self.assertFalse(GroupMembership.objects.filter(user=self.member, group=grp).exists())

    def test_group_members_form_adds_and_removes(self):
        grp = self._make_preset()
        add = GroupMembersForm(data={'members': [self.member.pk]}, group=grp, user=self.admin)
        self.assertTrue(add.is_valid(), add.errors)
        add.save()
        self.assertTrue(grp.user_set.filter(pk=self.member.pk).exists())
        self.assertTrue(GroupMembership.objects.filter(user=self.member, group=grp).exists())
        # Empty selection removes them.
        rem = GroupMembersForm(data={'members': []}, group=grp, user=self.admin)
        self.assertTrue(rem.is_valid(), rem.errors)
        rem.save()
        self.assertFalse(grp.user_set.filter(pk=self.member.pk).exists())

    def test_non_member_user_unaffected(self):
        """Non-breaking: a user in no preset has no extra permissions."""
        self._make_preset()
        member = User.objects.get(pk=self.member.pk)
        self.assertFalse(member.has_perm('dlux.view_reports'))
        self.assertEqual(member.groups.count(), 0)


class PresetInheritanceWidgetTests(TestCase):
    """The permission widget marks preset-derived perms as read-only 'inherited'
    and never writes them to the user's direct permissions."""

    def setUp(self):
        from dlux.models import GroupProfile
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.target = User.objects.create_user('t', 't@example.com', 'pw')
        self.p_view = Permission.objects.get(content_type__app_label='dlux', codename='view_reports')
        self.p_down = Permission.objects.get(content_type__app_label='dlux', codename='download_backup')
        self.group = Group.objects.create(name='Preset A')
        self.group.permissions.add(self.p_view)
        GroupProfile.objects.create(group=self.group)
        self.target.groups.add(self.group)          # inherited: view_reports
        self.target.user_permissions.add(self.p_down)  # direct: download_backup

    def test_widget_marks_inherited_permissions(self):
        from dlux.forms import CustomUserPermissionsForm
        form = CustomUserPermissionsForm(instance=self.target, user=self.admin)
        widget = form.fields['permissions'].widget
        self.assertIn(self.p_view.pk, widget.inherited_permission_ids)
        self.assertNotIn(self.p_down.pk, widget.inherited_permission_ids)
        self.assertEqual(widget.group_permissions_map[str(self.group.pk)], [self.p_view.pk])

        import re
        html = str(form['permissions'])
        inherited_tag = re.search(r'<input[^>]*value="%d"[^>]*>' % self.p_view.pk, html).group(0)
        self.assertIn('disabled', inherited_tag)   # read-only
        self.assertIn('checked', inherited_tag)    # shown granted
        self.assertIn('data-direct-checked="false"', inherited_tag)

    def test_inherited_permission_is_not_stored_as_direct_on_save(self):
        from dlux.forms import CustomUserPermissionsForm
        # A browser omits disabled (inherited) checkboxes, so only the direct one posts.
        post = {'permissions': [str(self.p_down.pk)], 'groups': [str(self.group.pk)], 'is_staff': 'on'}
        form = CustomUserPermissionsForm(post, instance=self.target, user=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        target = User.objects.get(pk=self.target.pk)
        direct = set(target.user_permissions.values_list('codename', flat=True))
        self.assertNotIn('view_reports', direct)   # stays group-only
        self.assertIn('download_backup', direct)   # direct grant preserved
        target = User.objects.get(pk=target.pk)
        self.assertTrue(target.has_perm('dlux.view_reports'))     # still granted via group
        self.assertTrue(target.has_perm('dlux.download_backup'))


class GroupPresetScopeVisibilityTests(TestCase):
    def setUp(self):
        settings = ScopeSettings.load()
        settings.is_enabled = True
        settings.save()
        self.scope_a = Scope.objects.create(name='Scope A')
        self.scope_b = Scope.objects.create(name='Scope B')
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'pw')

        self.global_preset = Group.objects.create(name='Global Preset')
        GroupProfile.objects.create(group=self.global_preset, scope=None)
        self.a_preset = Group.objects.create(name='A Preset')
        GroupProfile.objects.create(group=self.a_preset, scope=self.scope_a)
        self.b_preset = Group.objects.create(name='B Preset')
        GroupProfile.objects.create(group=self.b_preset, scope=self.scope_b)

    def _scoped_staff(self, scope):
        user = User.objects.create_user('scoped', 'scoped@example.com', 'pw', is_staff=True)
        user.profile.scope = scope
        user.profile.save()
        return User.objects.get(pk=user.pk)

    def test_superuser_sees_all_presets(self):
        visible = set(get_visible_group_presets(self.admin).values_list('name', flat=True))
        self.assertEqual(visible, {'Global Preset', 'A Preset', 'B Preset'})

    def test_scoped_staff_sees_global_plus_own_scope(self):
        staff = self._scoped_staff(self.scope_a)
        visible = set(get_visible_group_presets(staff).values_list('name', flat=True))
        self.assertEqual(visible, {'Global Preset', 'A Preset'})

    def test_scoped_staff_cannot_manage_global_or_other_scope(self):
        staff = self._scoped_staff(self.scope_a)
        self.assertTrue(can_manage_group_preset(staff, self.a_preset))
        self.assertFalse(can_manage_group_preset(staff, self.global_preset))
        self.assertFalse(can_manage_group_preset(staff, self.b_preset))


class GroupPresetPublicRegistrationDefaultViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.client.login(username='admin', password='pw')
        self.group = Group.objects.create(name='Public Default Preset')
        GroupProfile.objects.create(group=self.group)

    def test_toggle_public_registration_default_is_post_only(self):
        response = self.client.get(
            reverse('toggle_group_public_registration_default', args=[self.group.pk])
        )

        self.assertEqual(response.status_code, 405)
        self.assertFalse(self.group.dlux_profile.is_public_registration_default)

    def test_toggle_public_registration_default_marks_group_profile(self):
        response = self.client.post(
            reverse('toggle_group_public_registration_default', args=[self.group.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.group.dlux_profile.refresh_from_db()
        self.assertTrue(self.group.dlux_profile.is_public_registration_default)
        self.assertIn('Public default', response.json()['html'])


class GroupPresetDeleteViewTests(TestCase):
    def setUp(self):
        settings = SystemSettings.load()
        settings.is_configured = True
        settings.save()
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.member = User.objects.create_user('member', 'member@example.com', 'pw')
        self.client.login(username='admin', password='pw')
        self.p_view, self.p_down = _assignable_perms()

    def test_delete_group_allows_definition_only_preset(self):
        group = Group.objects.create(name='Unused Preset')
        group.permissions.add(self.p_view, self.p_down)
        GroupProfile.objects.create(group=group, description='definition metadata')

        response = self.client.post(reverse('delete_group', args=[group.pk]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertFalse(Group.objects.filter(pk=group.pk).exists())
        self.assertFalse(GroupProfile.objects.filter(group_id=group.pk).exists())

    def test_delete_group_blocks_and_reports_member_links(self):
        group = Group.objects.create(name='Used Preset')
        GroupProfile.objects.create(group=group)
        set_user_group_presets(self.member, [group], actor=self.admin)

        response = self.client.post(reverse('delete_group', args=[group.pk]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertTrue(payload['related'])
        self.assertTrue(Group.objects.filter(pk=group.pk).exists())
