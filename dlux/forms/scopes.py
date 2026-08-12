"""Scope and permission-preset (group) forms."""

from django import forms
from django.contrib.auth.models import Group
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, HTML
from django.apps import apps
from ..translations import get_strings
from ..themes import get_theme_options
from ..utils import (
    get_effective_allowed_themes,
    get_system_config,
    get_user_scope,
    is_scope_enabled,
)
from ..widgets import DluxMultipleChoiceSelectorWidget

from .builders import _bind_choice_selector_widget, _build_submit_only_actions
from .permissions import GroupedPermissionWidget, _apply_assignable_permission_filter, get_assignable_permissions_queryset


class ScopeForm(forms.ModelForm):
    default_theme = forms.ChoiceField(required=True, choices=())

    class Meta:
        model = apps.get_model('dlux', 'Scope')
        fields = ['name', 'description', 'default_theme']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        s = get_strings()
        # But scope form often used in modals?
        # If we have request in kwargs we can use it, but typically ModelForms don't get request.
        # Fallback to default is okay for now or we can inject request if needed.
        self.fields['name'].label = s.get('form_scope_name', "Scope Name")
        self.fields['description'].label = s.get('form_scope_description', "Description")
        self.fields['description'].required = False
        self.fields['description'].widget.attrs.update({'rows': 3})
        layout_fields = [
            Field('name', css_class='col-12'),
            Field('description', css_class='col-12'),
        ]
        config = get_system_config()
        allowed_themes = list(get_effective_allowed_themes(config))
        if is_scope_enabled() and len(allowed_themes) > 1:
            theme_options = get_theme_options(s, allowed_themes)
            self.fields['default_theme'].choices = [
                (theme['slug'], theme['label']) for theme in theme_options
            ]
            stored_theme = getattr(self.instance, 'default_theme', '')
            system_default = config.get('default_theme', '')
            self.initial['default_theme'] = (
                stored_theme if stored_theme in allowed_themes
                else system_default if system_default in allowed_themes
                else allowed_themes[0]
            )
            self.fields['default_theme'].label = s.get(
                'form_scope_default_theme',
                'Default Theme',
            )
            self.fields['default_theme'].help_text = s.get(
                'help_scope_default_theme',
                'Used when a user in this scope has not selected a personal theme.',
            )
            layout_fields.append(Field('default_theme', css_class='col-12'))
        else:
            self.fields.pop('default_theme', None)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(*layout_fields)


class GroupPresetForm(forms.ModelForm):
    """
    Create/edit a reusable permission PRESET — a Django auth ``Group`` plus its
    dlux ``GroupProfile`` sidecar. Reuses the assignable-permission machinery so
    a preset can only bundle permissions the acting admin is allowed to grant.
    """
    handles_save = True

    description = forms.CharField(max_length=255, required=False)
    scope = forms.ModelChoiceField(queryset=None, required=False, label="Scope")
    permissions = forms.ModelMultipleChoiceField(
        queryset=get_assignable_permissions_queryset(),
        required=False,
        widget=GroupedPermissionWidget,
        label="Permissions",
    )

    class Meta:
        model = Group
        fields = ['name']

    def __init__(self, *args, **kwargs):
        self.user_context = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        from dlux.utils import is_scope_enabled

        s = get_strings()
        self.fields['permissions'].widget.translations = s

        Scope = apps.get_model('dlux', 'Scope')
        self.fields['scope'].queryset = Scope.objects.all()

        # Restrict assignable permissions to what the actor may grant.
        _apply_assignable_permission_filter(self, self.user_context)

        # Preload from the existing preset (permissions + profile metadata).
        if self.instance and self.instance.pk:
            self.fields['permissions'].initial = self.instance.permissions.all()
            profile = getattr(self.instance, 'dlux_profile', None)
            if profile is not None:
                self.fields['description'].initial = profile.description
                self.fields['scope'].initial = profile.scope_id

        # Scope handling: hidden when scopes are disabled (presets are global);
        # locked to the actor's own scope for scoped non-superusers.
        actor_scope = get_user_scope(self.user_context) if self.user_context else None
        self._scope_enabled = is_scope_enabled()
        if not self._scope_enabled:
            self.fields['scope'].widget = forms.HiddenInput()
            self.fields['scope'].queryset = Scope.objects.none()
            self.fields['scope'].initial = None
        elif self.user_context and not self.user_context.is_superuser and actor_scope is not None:
            self.fields['scope'].initial = actor_scope.pk
            self.fields['scope'].disabled = True
            self.fields['scope'].queryset = Scope.objects.filter(pk=actor_scope.pk)

        self.fields['name'].label = s.get('form_group_name', 'Group Name')
        self.fields['description'].label = s.get('form_group_description', 'Description')
        self.fields['scope'].label = s.get('form_scope', 'Scope')
        self.fields['permissions'].label = s.get('form_permissions', 'Permissions')
        self.modal_heading = s.get('manage_groups_label', 'Manage Groups')

        self.helper = FormHelper()
        self.helper.form_tag = False
        layout_fields = [
            Field('name', css_class='col-12'),
            Field('description', css_class='col-12'),
            Field('scope', css_class='col-12') if self._scope_enabled else Field('scope'),
            HTML("<hr>"),
            Field('permissions', css_class='col-12'),
        ]
        self.helper.layout = Layout(
            *layout_fields,
            _build_submit_only_actions(
                s,
                submit_label=s.get('btn_save', 'Save'),
                submit_icon='bi-people-fill',
            ),
        )

    def save(self, commit=True):
        group = super().save(commit=False)
        if commit:
            group.save()
            group.permissions.set(self.cleaned_data.get('permissions') or [])
            GroupProfile = apps.get_model('dlux', 'GroupProfile')
            actor = self.user_context if getattr(self.user_context, 'pk', None) else None
            profile, _created = GroupProfile.objects.get_or_create(
                group=group, defaults={'created_by': actor},
            )
            profile.description = self.cleaned_data.get('description') or ''
            # cleaned_data holds the locked initial for disabled scope fields, and
            # None when scopes are off — so this is always the intended value.
            profile.scope = self.cleaned_data.get('scope')
            profile.updated_by = actor
            profile.save()
        return group


class GroupMembersForm(forms.Form):
    """
    Add/remove members of a single permission preset. ``members`` is initialised
    to the preset's current membership (within the actor's manageable set); on
    save the difference is reconciled through ``set_group_members`` so native
    ``group.user_set`` and the ``GroupMembership`` audit rows stay in sync.
    """
    handles_save = True

    members = forms.ModelMultipleChoiceField(queryset=None, required=False)

    def __init__(self, *args, **kwargs):
        self.user_context = kwargs.pop('user', None)
        self.group = kwargs.pop('group', None)
        super().__init__(*args, **kwargs)
        from dlux.utils import get_manageable_users_queryset

        s = get_strings()
        manageable = get_manageable_users_queryset(self.user_context)
        self.fields['members'].queryset = manageable
        self.fields['members'].label = s.get('group_members_label', 'Members')
        if self.group is not None and getattr(self.group, 'pk', None):
            self.fields['members'].initial = manageable.filter(
                groups=self.group
            ).values_list('pk', flat=True)
        _bind_choice_selector_widget(
            self.fields['members'],
            DluxMultipleChoiceSelectorWidget(variant='card', searchable=True),
        )
        self.modal_heading = s.get('group_members_label', 'Members')

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field('members', css_class='col-12'),
            _build_submit_only_actions(
                s,
                submit_label=s.get('btn_save', 'Save'),
                submit_icon='bi-people-fill',
            ),
        )

    def save(self):
        from dlux.utils import set_group_members
        set_group_members(
            self.group,
            self.cleaned_data.get('members') or [],
            actor=self.user_context,
            manageable_users=self.fields['members'].queryset,
        )
        return self.group
