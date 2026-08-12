"""Permission querysets and the grouped-permission widget."""

from django.contrib.auth.models import Permission as Permissions
from django.utils.safestring import mark_safe
from django.db.models import Q
from django.apps import apps
from django.forms.widgets import ChoiceWidget
from django.template.loader import render_to_string
from ..translations import get_strings


DLUX_PERMISSION_HELP_TEXTS = {
    'view_reports': (
        'help_perm_view_reports',
        'Allows viewing the reports overview and exporting report summaries.',
    ),
    'download_backup': (
        'help_perm_download_backup',
        'Allows building and downloading report backup ZIP archives.',
    ),
    'view_sections': (
        'help_perm_view_sections',
        'Allows opening the Sections screen and viewing the section hierarchy.',
    ),
    'manage_sections': (
        'help_perm_manage_sections',
        'Allows creating, editing, reordering, and deleting sections and subsections.',
    ),
    'view_activitylog': (
        'help_perm_view_activitylog',
        'Allows viewing activity-log pages and activity detail modals.',
    ),
    'manage_staff': (
        'help_perm_manage_staff',
        'Lets this staff user assign staff access to other users. It does not widen their own scope.',
    ),
    'manage_scopes': (
        'help_perm_manage_scopes',
        'Creates Global Staff access only when the user has no assigned scope.',
    ),
    'manage_groups': (
        'help_perm_manage_groups',
        'Lets this staff user create and edit permission groups (presets) and assign users to them.',
    ),
}


PERMISSION_UI_EXCLUDED_APP_LABELS = [
    'admin',
    'contenttypes',
    'sessions',
    'django_celery_beat',
    'health_check',
    'db',
    'corsheaders',
    'csp',
]


def get_assignable_permissions_queryset():
    # Delete permissions are intentionally assignable. Admins can grant
    # `delete_<model>` to trusted users so the row context-menu Delete entry and
    # the backend delete views (which already enforce `delete_<model>`) become
    # available to them; without a grant, only superusers can delete. Sensitive
    # deletes stay excluded by the clauses below: the auth user/group/permission
    # models, and every non-whitelisted dlux model (e.g. activitylog, scope,
    # systemsettings) except the section model.
    return Permissions.objects.exclude(
        Q(content_type__app_label__in=PERMISSION_UI_EXCLUDED_APP_LABELS) |
        (Q(content_type__app_label='dlux') & ~Q(codename__in=['manage_staff', 'manage_scopes', 'manage_groups', 'view_activitylog', 'view_reports', 'download_backup']) & ~Q(content_type__model='section')) |
        Q(content_type__app_label='auth', content_type__model__in=['group', 'user', 'permission'])
    )


def _get_assignable_permission_ids_for_user(user):
    if not user or getattr(user, 'is_superuser', False):
        return None

    cache_attr = '_dlux_assignable_permission_ids'
    if hasattr(user, cache_attr):
        return getattr(user, cache_attr)

    permission_ids = list(
        Permissions.objects.filter(
            Q(user=user) | Q(group__user=user)
        ).values_list('id', flat=True).distinct()
    )
    setattr(user, cache_attr, permission_ids)
    return permission_ids


def _apply_assignable_permission_filter(form, user):
    if not user or getattr(user, 'is_superuser', False):
        return
    permission_ids = _get_assignable_permission_ids_for_user(user)
    filtered_qs = form.fields['permissions'].queryset.filter(id__in=permission_ids)
    form.fields['permissions'].queryset = filtered_qs
    form.fields['permissions'].widget._filtered_queryset = filtered_qs


def _extract_permission_codenames(permissions):
    codenames = set()
    for permission in permissions or []:
        codename = getattr(permission, 'codename', None)
        if codename:
            codenames.add(str(codename))
    return codenames


class GroupedPermissionWidget(ChoiceWidget):
    template_name = 'dlux/users/grouped_permissions.html'
    allow_multiple_selected = True

    def add_extra_group(self, app_label, app_name, model_key, model_name, option):
        if not hasattr(self, 'extra_groups') or self.extra_groups is None:
            self.extra_groups = {}
        group = self.extra_groups.setdefault(app_label, {'name': app_name, 'models': {}})
        if app_name and not group.get('name'):
            group['name'] = app_name
        model_group = group['models'].setdefault(model_key, {'name': model_name, 'permissions': []})
        model_group['permissions'].append(option)

    def value_from_datadict(self, data, files, name):
        if hasattr(data, 'getlist'):
            return data.getlist(name)
        return data.get(name)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        s = getattr(self, 'translations', get_strings())

        # Permissions inherited from the user's selected preset groups (rendered
        # read-only, not submitted). Empty for the preset-definition form.
        inherited_ids = getattr(self, 'inherited_permission_ids', None) or set()

        # Get current selected values (as strings/ints)
        if value is None:
            value = []
        str_values = set(str(v) for v in value)
        
        # Access the queryset directly - prioritize field's current queryset over cached choices
        qs = None
        if hasattr(self, '_filtered_queryset'):
            # Use the explicitly set filtered queryset from the form
            qs = self._filtered_queryset.select_related('content_type').order_by('content_type__app_label', 'codename')
        elif hasattr(self.choices, 'queryset'):
            qs = self.choices.queryset.select_related('content_type').order_by('content_type__app_label', 'codename')
        else:
             choices = list(self.choices)
             choice_ids = [c[0] for c in choices if c[0]]
             qs = Permissions.objects.filter(id__in=choice_ids).select_related('content_type').order_by('content_type__app_label', 'codename')

        grouped_perms = {}
        
        for perm in qs:
            app_label = perm.content_type.app_label
            model_name = perm.content_type.model
            codename = perm.codename

            # Keep staff-delegation permissions together in the dedicated staff-access UI.
            if app_label == 'dlux' and codename in {'manage_staff', 'manage_scopes', 'manage_groups'}:
                model_name = 'staff_access'
                # Force model_verbose_name to match what _attach_is_staff_permission uses
                # "perm_staff_access" string usually "Staff Permissions"
                
            model_label_key = None
            model_label_fallback = None
            if app_label == 'dlux' and model_name == 'staff_access':
                model_label_key = 'perm_staff_access'
                model_label_fallback = "Staff Permissions"
            elif app_label == 'dlux' and model_name == 'profile':
                model_label_key = 'model_user'

            model_class = perm.content_type.model_class()
            if model_class is None and not (
                app_label == 'dlux' and model_name in {'staff_access', 'profile'}
            ):
                continue
            if model_class:
                # prefer plural verbose name if possible, or just verbose name
                # But here we want to use our translation keys if available
                default_verbose = str(model_class._meta.verbose_name)
            else:
                default_verbose = perm.content_type.name
            
            if model_label_key:
                model_verbose_name = s.get(model_label_key, model_label_fallback or default_verbose)
            else:
                # Try translation key 'model_modelname' (e.g. model_user)
                model_verbose_name = s.get(f"model_{model_name}", default_verbose)
            
            # Fetch verbose app name
            try:
                app_config = apps.get_app_config(app_label)
                default_app_verbose = app_config.verbose_name
            except LookupError:
                default_app_verbose = app_label.title()
            
            # Try translation key 'app_applabel' (e.g. app_dlux)
            app_verbose_name = s.get(f"app_{app_label}", default_app_verbose)

            action = 'other'
            codename = perm.codename
            if codename.startswith('view_'): action = 'view'
            elif codename.startswith('add_'): action = 'add'
            elif codename.startswith('change_'): action = 'change'
            elif codename.startswith('delete_'): action = 'delete'
            
            # Build option dict
            current_id = attrs.get('id', 'id_permissions') if attrs else 'id_permissions'

            # Translate permission label if possible
            # We use str(perm) to respect the dynamic translations 
            # applied in apps.py (which overrides Permission.__str__)
            perm_label = s.get(f"perm_{codename}", str(perm))

            # Dlux-owned permissions carry concise descriptions in the grouped UI.
            help_text = ""
            help_config = DLUX_PERMISSION_HELP_TEXTS.get(codename) if app_label == 'dlux' else None
            if help_config:
                help_key, help_default = help_config
                help_text = s.get(help_key, help_default)

            option = {
                'name': name,
                'value': perm.pk,
                'label': perm_label,
                'codename': codename,
                'selected': str(perm.pk) in str_values,
                'inherited': perm.pk in inherited_ids,
                'help_text': help_text,
                'attrs': {
                    'id': f"{current_id}_{perm.pk}",
                    'data_action': action,
                    'data_model': model_name,
                    'data_codename': codename,
                }
            }
            
            if app_label not in grouped_perms:
                grouped_perms[app_label] = {
                    'name': app_verbose_name,
                    'models': {}
                }
            
            if model_name not in grouped_perms[app_label]['models']:
                grouped_perms[app_label]['models'][model_name] = {
                    'name': model_verbose_name.title(),
                    'permissions': []
                }
            
            grouped_perms[app_label]['models'][model_name]['permissions'].append(option)
        
        action_order = {'view': 1, 'add': 2, 'change': 3, 'delete': 4, 'other': 5}
        for app_label, app_data in grouped_perms.items():
            for model_name, model_data in app_data['models'].items():
                model_data['permissions'].sort(
                    key=lambda x: action_order.get(x['attrs']['data_action'], 99)
                )

        extra_groups = getattr(self, 'extra_groups', None)
        if isinstance(extra_groups, dict):
            for app_label, app_data in extra_groups.items():
                if app_label not in grouped_perms:
                    grouped_perms[app_label] = {
                        'name': app_data.get('name', app_label.title()),
                        'models': {},
                    }

                target_app = grouped_perms[app_label]
                if app_data.get('name'):
                    # Check for translation override to prevent overwriting with hardcoded AppConfig name
                    translated_app = s.get(f"app_{app_label}")
                    if translated_app:
                        target_app['name'] = translated_app
                    else:
                        target_app['name'] = app_data['name']

                for model_name, model_data in app_data.get('models', {}).items():
                    target_model = target_app['models'].setdefault(
                        model_name,
                        {'name': model_data.get('name', model_name), 'permissions': []}
                    )

                    existing_ids = {
                        p.get('attrs', {}).get('id') for p in target_model['permissions']
                    }
                    for option in model_data.get('permissions', []):
                        opt_id = option.get('attrs', {}).get('id')
                        if opt_id and opt_id in existing_ids:
                            continue
                        target_model['permissions'].append(option)
            
        context['widget']['grouped_perms'] = grouped_perms
        context['widget']['staff_tier_preview'] = getattr(self, 'staff_tier_preview', None)
        # preset→permission map (json-serialisable) drives live inheritance in permissions.js
        context['widget']['group_permissions_map'] = getattr(self, 'group_permissions_map', None)
        context['DLUX_STRINGS'] = s  # Pass translations to template
        return context

    def render(self, name, value, attrs=None, renderer=None):
        from django.template.loader import render_to_string
        from django.utils.safestring import mark_safe
        
        context = self.get_context(name, value, attrs)
        return mark_safe(render_to_string(self.template_name, context))
