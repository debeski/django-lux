from django.conf import settings

if not settings.configured:
    settings.configure(
        SECRET_KEY='dlux-test-key',
        ALLOWED_HOSTS=['testserver', 'localhost'],
        INSTALLED_APPS=[
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'django.contrib.messages',
            'django.contrib.staticfiles',
            'crispy_forms',
            'crispy_bootstrap5',
            'django_filters',
            'django_tables2',
            'dlux',
        ],
        MIDDLEWARE=[
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'dlux.middleware.DluxMiddleware',
        ],
        ROOT_URLCONF='dlux.urls',
        TEMPLATES=[
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'APP_DIRS': True,
                'OPTIONS': {
                    'context_processors': [
                        'django.template.context_processors.request',
                        'django.contrib.auth.context_processors.auth',
                        'django.contrib.messages.context_processors.messages',
                        'dlux.context_processors.dlux_context',
                    ],
                },
            }
        ],
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        STATIC_URL='/static/',
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
        USE_TZ=True,
        CRISPY_ALLOWED_TEMPLATE_PACKS='bootstrap5',
        CRISPY_TEMPLATE_PACK='bootstrap5',
    )

    import django
    django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.template import Context, Template
from django.test import TestCase

from dlux.forms import CustomUserCreationForm, CustomUserPermissionsForm
from dlux.models import Profile
from dlux.models import SystemSettings

User = get_user_model()


class PermissionsUiTests(TestCase):
    def setUp(self):
        SystemSettings.load()
        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpass123',
        )

    def test_permissions_form_excludes_scaffold_infra_db_permissions(self):
        content_type = ContentType.objects.create(app_label='db', model='testmodel')
        permission = Permission.objects.create(
            name='Can view test model',
            codename='view_testmodel',
            content_type=content_type,
        )

        form = CustomUserPermissionsForm(instance=self.user, user=self.user)

        self.assertNotIn(permission.pk, form.fields['permissions'].queryset.values_list('pk', flat=True))

    def test_permissions_widget_skips_orphaned_content_type_permissions(self):
        content_type = ContentType.objects.create(app_label='orphaned_app', model='ghostmodel')
        permission = Permission.objects.create(
            name='Can view ghost model',
            codename='view_ghostmodel',
            content_type=content_type,
        )

        form = CustomUserPermissionsForm(instance=self.user, user=self.user)
        form.fields['permissions'].queryset = Permission.objects.filter(pk=permission.pk)
        form.fields['permissions'].widget._filtered_queryset = form.fields['permissions'].queryset

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertNotIn('Ghost Model', html)
        self.assertNotIn('orphaned_app', html)

    def test_manage_scopes_groups_with_staff_access_permissions(self):
        profile_type = ContentType.objects.get_for_model(Profile)
        manage_staff = Permission.objects.get(
            content_type=profile_type,
            codename='manage_staff',
        )
        manage_scopes = Permission.objects.get(
            content_type=profile_type,
            codename='manage_scopes',
        )

        form = CustomUserPermissionsForm(instance=self.user, user=self.user)
        widget = form.fields['permissions'].widget
        context = widget.get_context('permissions', [], {'id': 'id_permissions'})
        dlux_groups = context['widget']['grouped_perms']['dlux']['models']

        self.assertIn('staff_access', dlux_groups)
        profile_codenames = {
            option.get('codename')
            for option in dlux_groups.get('profile', {}).get('permissions', [])
        }
        self.assertNotIn(manage_scopes.codename, profile_codenames)

        staff_access_codenames = {
            option.get('codename')
            for option in dlux_groups['staff_access']['permissions']
        }
        self.assertIn(manage_staff.codename, staff_access_codenames)
        self.assertIn(manage_scopes.codename, staff_access_codenames)

    def test_profile_permissions_use_model_user_group_label(self):
        profile_type = ContentType.objects.get_for_model(Profile)
        permission = Permission.objects.create(
            name='Can view profile',
            codename='view_profile',
            content_type=profile_type,
        )

        form = CustomUserPermissionsForm(instance=self.user, user=self.user)
        form.fields['permissions'].queryset = Permission.objects.filter(pk=permission.pk)
        form.fields['permissions'].widget._filtered_queryset = form.fields['permissions'].queryset

        context = form.fields['permissions'].widget.get_context('permissions', [], {'id': 'id_permissions'})
        dlux_groups = context['widget']['grouped_perms']['dlux']['models']

        self.assertEqual(dlux_groups['profile']['name'], 'Users')

    def test_creation_form_renders_staff_tier_preview(self):
        form = CustomUserCreationForm(user=self.user)

        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('dl-staff-tier-preview', html)
        self.assertIn('Staff Tier Preview', html)
        self.assertIn('data-codename="manage_scopes"', html)
        self.assertIn('data-codename="manage_staff"', html)
        self.assertIn('Staff Tier &amp; Access', html)

    def test_permissions_form_preview_uses_target_tier_state(self):
        profile_type = ContentType.objects.get_for_model(Profile)
        manage_scopes = Permission.objects.get(content_type=profile_type, codename='manage_scopes')
        manage_staff = Permission.objects.get(content_type=profile_type, codename='manage_staff')
        target = User.objects.create_user(
            username='globalstaff',
            email='globalstaff@example.com',
            password='globalstaffpass123',
            is_staff=True,
        )
        target.user_permissions.add(manage_scopes, manage_staff)

        form = CustomUserPermissionsForm(instance=target, user=self.user)
        html = Template('{% load crispy_forms_tags %}{% crispy form %}').render(Context({'form': form}))

        self.assertIn('dl-staff-tier-preview', html)
        self.assertIn('Global Staff', html)
        self.assertIn('Can Assign Staff Roles', html)
