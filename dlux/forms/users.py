"""User creation, editing, permissions and profile forms."""

from types import SimpleNamespace
from django import forms
from django.contrib.auth.models import Permission as Permissions
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Div, HTML, Row
from crispy_forms.bootstrap import FormActions
from PIL import Image
from django.core.exceptions import ValidationError
from django.apps import apps
from ..translations import get_strings
from ..utils import (
    get_user_management_tier_state,
    get_user_scope,
    is_central_staff,
    is_scope_enabled,
)
from ..widgets import DluxMultipleChoiceSelectorWidget

from ._shared import User, _json_dump
from .auth import _apply_autocomplete_attrs
from .builders import _bind_choice_selector_widget, _build_archive_file_widget, _build_submit_actions, _build_wizard_actions, build_archive_file_field
from .permissions import GroupedPermissionWidget, _apply_assignable_permission_filter, _extract_permission_codenames, get_assignable_permissions_queryset


class ProfileImageWidget(forms.ClearableFileInput):
    template_name = 'dlux/users/profile_image_widget.html'


def _build_staff_tier_preview_catalog(strings):
    tier_examples = {
        'regular_user': get_user_management_tier_state(
            is_superuser=False,
            is_staff=False,
            scope=None,
            permission_codenames=set(),
        ),
        'superuser': get_user_management_tier_state(
            is_superuser=True,
            is_staff=True,
            scope=None,
            permission_codenames={'manage_scopes', 'manage_staff'},
        ),
        'global_staff': get_user_management_tier_state(
            is_superuser=False,
            is_staff=True,
            scope=None,
            permission_codenames={'manage_scopes'},
        ),
        'central_staff': get_user_management_tier_state(
            is_superuser=False,
            is_staff=True,
            scope=None,
            permission_codenames=set(),
        ),
        'scoped_staff': get_user_management_tier_state(
            is_superuser=False,
            is_staff=True,
            scope=SimpleNamespace(name=strings.get('form_scope', 'Scope')),
            permission_codenames=set(),
        ),
    }
    return {
        'preview_title': strings.get('staff_tier_preview', 'Staff Tier Preview'),
        'preview_caption': strings.get(
            'staff_tier_preview_caption',
            'Read-only summary based on staff access, scope, and selected permissions.',
        ),
        'delegation_badge_label': strings.get('tier_delegate_badge', 'Can Assign Staff Roles'),
        'tiers': {
            key: {
                'title': state['title'],
                'description': state['description'],
                'badge_classes': state['badge_classes'],
                'icon': state['icon'],
                'capabilities': state['capabilities'],
            }
            for key, state in tier_examples.items()
        },
        'warnings': {
            'needs_staff': strings.get(
                'tier_warning_needs_staff',
                'Staff-related permissions are selected, but staff access is not enabled yet.',
            ),
            'scoped_manage_scopes_conflict': strings.get(
                'tier_warning_scoped_manage_scopes',
                'Global Staff access is ineffective while a scope is assigned.',
            ),
        },
    }


def _configure_staff_tier_preview(form, *, fixed_scope=None, scope_locked=False):
    perm_field = form.fields.get('permissions')
    if not perm_field or not isinstance(perm_field.widget, GroupedPermissionWidget):
        return

    strings = getattr(perm_field.widget, 'translations', get_strings())
    instance = getattr(form, 'instance', None)
    initial_permissions = perm_field.initial
    if initial_permissions is None and instance is not None and getattr(instance, 'pk', None):
        initial_permissions = getattr(instance, 'user_permissions', None)
        if initial_permissions is not None:
            initial_permissions = initial_permissions.all()

    # Fold in permissions the user already inherits from preset groups so the
    # tier summary reflects effective (direct ∪ group) access, not just direct.
    combined_permissions = list(initial_permissions or [])
    if instance is not None and getattr(instance, 'pk', None):
        try:
            combined_permissions += list(
                Permissions.objects.filter(group__user=instance).distinct()
            )
        except Exception:
            pass
    initial_permissions = combined_permissions

    is_staff_value = bool(
        form.initial.get('is_staff')
        if 'is_staff' in getattr(form, 'initial', {})
        else getattr(getattr(form, 'instance', None), 'is_staff', getattr(form.fields.get('is_staff'), 'initial', False))
    )

    if fixed_scope is None and 'scope' in form.fields:
        fixed_scope = form.fields['scope'].initial

    preview_state = get_user_management_tier_state(
        is_superuser=bool(getattr(instance, 'is_superuser', False)),
        is_staff=is_staff_value,
        scope=fixed_scope,
        permission_codenames=_extract_permission_codenames(initial_permissions),
    )
    preview_config = {
        'catalog': _build_staff_tier_preview_catalog(strings),
        'initial_state': preview_state,
        'forced_superuser': bool(getattr(instance, 'is_superuser', False)),
        'scope_field_name': 'scope' if 'scope' in form.fields else '',
        'fixed_scope_active': bool(fixed_scope is not None),
        'fixed_scope_label': getattr(fixed_scope, 'name', '') if fixed_scope is not None else '',
        'scope_locked': bool(scope_locked),
    }
    perm_field.widget.staff_tier_preview = {
        'config_json': _json_dump(preview_config),
    }


def _maybe_add_group_presets_field(form, user_context, *, initial_groups=None):
    """
    Attach an optional ``groups`` preset selector to a user form, gated on the
    actor holding ``manage_groups`` (membership management is a manage_groups
    action). Rendered with the shared multi-select card selector. Returns True
    when the field was added. Non-breaking: actors without the permission — or
    systems with no presets defined — see the form exactly as before.
    """
    from ..utils import get_visible_group_presets

    can_assign = bool(
        user_context
        and (getattr(user_context, 'is_superuser', False)
             or user_context.has_perm('dlux.manage_groups'))
    )
    if not can_assign:
        return False

    presets = get_visible_group_presets(user_context)
    if not presets.exists():
        return False

    s = get_strings()
    field = forms.ModelMultipleChoiceField(
        queryset=presets,
        required=False,
        label=s.get('form_group_presets', 'Groups / Presets'),
        help_text=s.get(
            'help_group_presets',
            'Assign reusable permission presets. The user inherits every permission in the selected presets, on top of any permissions checked below.',
        ),
    )
    if initial_groups is not None:
        field.initial = initial_groups
    form.fields['groups'] = field
    _bind_choice_selector_widget(
        field,
        DluxMultipleChoiceSelectorWidget(variant='card', searchable=True),
    )

    # Feed preset→permission inheritance into the grouped-permission widget so it
    # can show which permissions come from the selected presets (checked + read-only
    # + badged, never submitted as direct). The map lets permissions.js recompute
    # this live as presets are toggled.
    perm_field = form.fields.get('permissions')
    if perm_field is not None and isinstance(perm_field.widget, GroupedPermissionWidget):
        group_perms = {
            str(group.pk): [perm.pk for perm in group.permissions.all()]
            for group in presets.prefetch_related('permissions')
        }
        perm_field.widget.group_permissions_map = group_perms
        inherited = set()
        if initial_groups is not None:
            for group in initial_groups:
                gid = getattr(group, 'pk', group)
                inherited.update(group_perms.get(str(gid), []))
        perm_field.widget.inherited_permission_ids = inherited
    return True


def _attach_is_staff_permission(form, widget_id=None):
    perm_field = form.fields.get('permissions')
    staff_field = form.fields.get('is_staff')
    if not perm_field or not staff_field:
        return
    if not isinstance(perm_field.widget, GroupedPermissionWidget):
        return

    try:
        app_config = apps.get_app_config('dlux')
        app_name = app_config.verbose_name
    except LookupError:
        app_name = 'dlux'

    current_value = False
    if getattr(form, 'instance', None) is not None and getattr(form.instance, 'pk', None):
        current_value = bool(getattr(form.instance, 'is_staff', False))
    elif 'is_staff' in form.initial:
        current_value = bool(form.initial.get('is_staff'))
    else:
        current_value = bool(getattr(staff_field, 'initial', False))

    field_id = widget_id or 'id_permissions'
    option_id = f"{field_id}_is_staff"

    # helper to check translations on widget
    s = getattr(perm_field.widget, 'translations', get_strings())

    option = {
        'name': 'is_staff',
        'value': 'on',
        'label': staff_field.label or s.get('form_is_staff', "Staff"),
        'selected': current_value,
        'help_text': staff_field.help_text,
        'attrs': {
            'id': option_id,
            'data_action': 'other',
            'data_model': 'staff',
            'data_codename': 'is_staff',
            'disabled': bool(getattr(staff_field, 'disabled', False)),
        }
    }

    perm_field.widget.add_extra_group(
        app_label='dlux',
        app_name=app_name,
        model_key='staff_access',
        model_name=s.get('perm_staff_access', 'Staff Permissions'),
        option=option,
    )


class CustomUserCreationForm(UserCreationForm):
    handles_save = True
    refresh_parent = True

    # Added fields from Profile
    phone = forms.CharField(max_length=15, required=False)
    scope = forms.ModelChoiceField(queryset=None, required=False, label="Scope")
    force_password_change = forms.BooleanField(required=False, initial=False)
    
    permissions = forms.ModelMultipleChoiceField(
        queryset=get_assignable_permissions_queryset(),
        required=False,
        widget=GroupedPermissionWidget,
        label="Permissions"
    )

    class Meta:
        model = User
        fields = ["username", "password1", "password2", "first_name", "last_name", "email", "is_staff", "is_active"]

    def __init__(self, *args, **kwargs):
        self.user_context = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        Scope = apps.get_model('dlux', 'Scope')
        self.fields['scope'].queryset = Scope.objects.all()

        # Permission check: Non-superusers can only assign permissions they already have
        _apply_assignable_permission_filter(self, self.user_context)

        lock_scope = bool(
            self.user_context
            and not self.user_context.is_superuser
            and hasattr(self.user_context, 'profile')
            and self.user_context.profile.scope
        )

        if lock_scope:
            # Security Fix: Hide manage_staff
            filtered_qs = self.fields['permissions'].queryset.exclude(codename='manage_staff')
            self.fields['permissions'].queryset = filtered_qs
            self.fields['permissions'].widget._filtered_queryset = filtered_qs
        
        # Central Staff restrictions: cannot assign scopes, cannot see manage_scopes permission
        # Also apply to any non-superuser without manage_scopes permission
        if self.user_context and not self.user_context.is_superuser:
            if not self.user_context.has_perm('dlux.manage_scopes'):
                # Hide scope field completely - Central Staff can only create scopeless users
                self.fields['scope'].widget = forms.HiddenInput()
                self.fields['scope'].required = False
                self.fields['scope'].initial = None
                self.fields['scope'].queryset = Scope.objects.none()
                # Hide manage_scopes permission - only superusers can create Global Staff
                filtered_qs = self.fields['permissions'].queryset.exclude(codename='manage_scopes')
                self.fields['permissions'].queryset = filtered_qs
                # Store filtered queryset for widget to use
                self.fields['permissions'].widget._filtered_queryset = filtered_qs
        
        self.fields["email"].required = False

        # can_manage_staff logic
        if self.user_context and not self.user_context.is_superuser:
            if not self.user_context.has_perm('dlux.manage_staff'):
                self.fields['is_staff'].disabled = True
                self.fields['is_staff'].initial = False
                self.fields['is_staff'].help_text = "You don't have permission to assign this user as staff."

        # Load translations
        s = get_strings()
        self.modal_heading = s.get('add_user', 'Add New User')
        
        # Inject translations into widget
        self.fields['permissions'].widget.translations = s

        self.fields["username"].label = s.get('form_username', "Username")
        self.fields["email"].label = s.get('form_email', "Email")
        self.fields["first_name"].label = s.get('form_firstname', "First Name")
        self.fields["last_name"].label = s.get('form_lastname', "Last Name")
        self.fields["is_staff"].label = s.get('form_is_staff', "Enable Staff Access")
        self.fields["password1"].label = s.get('form_password', "Password")
        self.fields["password2"].label = s.get('form_password_confirm', "Confirm Password")
        self.fields["is_active"].label = s.get('form_user_is_active', s.get('form_is_active', "Active"))
        self.fields["force_password_change"].label = s.get('form_force_password_change', "Require password change on first login")
        self.fields["phone"].label = s.get('form_phone', "Phone Number")
        self.fields["scope"].label = s.get('form_scope', "Scope")
        self.fields["permissions"].label = s.get('form_permissions', "Permissions")

        # Help Texts
        self.fields["username"].help_text = s.get('help_username', "Username must be unique. 150 characters or fewer. Letters, digits and @/./+/-/_ only.")
        self.fields["email"].help_text = s.get('help_email', "Enter a valid email address (optional).")
        self.fields["is_active"].help_text = s.get('help_is_active', "Designates whether this user should be treated as active.")
        self.fields["force_password_change"].help_text = s.get('help_force_password_change', "The new user must change this password before using the system.")
        self.fields["is_staff"].help_text = s.get('help_is_staff', "Enables staff access. The final tier depends on scope and selected permissions.")
        # No static requirement bullets: the live password-rules card (rendered
        # under the field on focus by system/js/password_rules.js) shows the active
        # criteria — configured strong rules or Django's defaults.
        self.fields["password1"].help_text = ''
        self.fields["password2"].help_text = s.get('help_password_match', "Enter the same password as before, for verification.")
        self.fields["phone"].help_text = s.get('help_phone', "Enter a valid phone number (optional).")
        _apply_autocomplete_attrs(
            self,
            {
                'username': 'username',
                'password1': 'new-password',
                'password2': 'new-password',
                'first_name': 'given-name',
                'last_name': 'family-name',
                'email': 'email',
                'phone': 'tel',
            },
        )

        # can_manage_staff logic message update
        if self.user_context and not self.user_context.is_superuser:
            if not self.user_context.has_perm('dlux.manage_staff'):
                 # ... existing disabled logic ...
                 self.fields['is_staff'].help_text = s.get('help_is_staff_no_perm', "You don't have permission to assign this user as staff.")

        _attach_is_staff_permission(self, self.fields['permissions'].widget.attrs.get('id'))
        fixed_scope = None
        scope_locked = False
        if self.user_context and not self.user_context.is_superuser:
            actor_scope = get_user_scope(self.user_context)
            if actor_scope is not None:
                fixed_scope = actor_scope
                scope_locked = True
        _configure_staff_tier_preview(self, fixed_scope=fixed_scope, scope_locked=scope_locked)

        # Optional reusable permission-preset selector (gated on manage_groups).
        _maybe_add_group_presets_field(self, self.user_context)


        self.helper = FormHelper()
        self.helper.form_tag = False
        
        from dlux.utils import is_scope_enabled
        scope_visible = 'scope' in self.fields and getattr(self.fields['scope'].widget, 'input_type', '') != 'hidden' and is_scope_enabled()

        step_1_fields = [
            Row(Field("username", css_class="form-control")),
            Row(Field("password1", css_class="form-control")),
            Row(Field("password2", css_class="form-control")),
            HTML("<hr>"),
            Row(
                Div(Field("first_name", css_class="form-control"), css_class="col-md-6"),
                Div(Field("last_name", css_class="form-control"), css_class="col-md-6"),
                css_class="row"
            ),
            Row(
                Div(Field("phone", css_class="form-control"), css_class="col-md-6"),
                Div(Field("email", css_class="form-control"), css_class="col-md-6"),
                css_class="row"
            ),
            Field("is_active"),
            Field("force_password_change"),
        ]
        
        if scope_visible:
            step_1_fields.append(Row(Field("scope", css_class="form-control")))
            
        step_1_div = Div(*step_1_fields, css_class="wizard-step wizard-step-1")
        
        step_2_fields = [HTML("<hr>")]
        if 'groups' in self.fields:
            step_2_fields.append(Field("groups", css_class="col-12"))
        step_2_fields.append(Field("permissions", css_class="col-12"))
        step_2_div = Div(*step_2_fields, css_class="wizard-step wizard-step-2 d-none")

        actions = _build_wizard_actions(
            s,
            submit_label=s.get('btn_add', 'Add'),
            submit_icon='bi-person-plus-fill',
        )

        self.helper.layout = Layout(step_1_div, step_2_div, actions)

    def save(self, commit=True):
        user = super().save(commit=False)
        # We need to save the user first to get an ID for the OneToOne relationship
        if commit:
            user.save()
            # Manually set permissions
            permissions = list(self.cleaned_data["permissions"])
            
            # Auto-grant auth.view_user permission when user is staff
            if user.is_staff:
                from django.contrib.auth.models import Permission
                try:
                    view_user_perm = Permission.objects.get(
                        content_type__app_label='auth',
                        codename='view_user'
                    )
                    if view_user_perm not in permissions:
                        permissions.append(view_user_perm)
                except Permission.DoesNotExist:
                    pass
            
            user.user_permissions.set(permissions)
            
            # Save Profile fields
            Profile = apps.get_model('dlux', 'Profile')
            # Check if profile already exists (via signal) or create it
            profile, created = Profile.all_objects.get_or_create(user=user)
            profile.phone = self.cleaned_data.get('phone')
            user_scope = get_user_scope(self.user_context)
            if self.user_context and not self.user_context.is_superuser and user_scope:
                profile.scope = user_scope
            elif self.cleaned_data.get('scope'):
                profile.scope = self.cleaned_data.get('scope')
            # If empty scope, we do not overwrite since signal may have auto-assigned one
            preferences = dict(profile.preferences or {})
            if self.cleaned_data.get('force_password_change'):
                preferences['force_password_change'] = True
            else:
                preferences.pop('force_password_change', None)
            profile.preferences = preferences
            profile.save()

            # Sync any selected permission presets (live group membership + audit).
            if 'groups' in self.fields:
                from dlux.utils import set_user_group_presets
                set_user_group_presets(
                    user,
                    self.cleaned_data.get('groups') or [],
                    actor=self.user_context,
                    manageable_groups=self.fields['groups'].queryset,
                )

        return user


class CustomUserChangeForm(UserChangeForm):
    handles_save = True
    refresh_parent = True

    phone = forms.CharField(max_length=15, required=False)
    scope = forms.ModelChoiceField(queryset=None, required=False, label="Scope")

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]

    def __init__(self, *args, **kwargs):
        self.user_context = kwargs.pop('user', None)
        user_instance = kwargs.get('instance')
        super().__init__(*args, **kwargs)
        
        Scope = apps.get_model('dlux', 'Scope')
        self.fields['scope'].queryset = Scope.objects.all()

        # Initialize Profile Fields
        if user_instance and hasattr(user_instance, 'profile'):
            self.fields['phone'].initial = user_instance.profile.phone
            self.fields['scope'].initial = user_instance.profile.scope

        # Labels
        s = get_strings()
        self.modal_heading = s.get('edit_user_label', 'Edit User')

        self.fields["username"].label = s.get('form_username', "Username")
        self.fields["email"].label = s.get('form_email', "Email")
        self.fields["first_name"].label = s.get('form_firstname', "First Name")
        self.fields["last_name"].label = s.get('form_lastname', "Last Name")
        self.fields["is_active"].label = s.get('form_user_is_active', s.get('form_is_active', "Active"))
        self.fields["phone"].label = s.get('form_phone', "Phone Number")
        self.fields["scope"].label = s.get('form_scope', "Scope")
        
        self.fields["username"].help_text = s.get('help_username', "Username must be unique. 150 characters or fewer. Letters, digits and @/./+/-/_ only.")
        self.fields["email"].help_text = s.get('help_email', "Enter a valid email address (optional).")
        self.fields["is_active"].help_text = s.get('help_is_active', "Designates whether this user should be treated as active.")
        self.fields["phone"].help_text = s.get('help_phone', "Enter a valid phone number (optional).")
        self.fields["scope"].help_text = ""
        _apply_autocomplete_attrs(
            self,
            {
                'username': 'username',
                'first_name': 'given-name',
                'last_name': 'family-name',
                'email': 'email',
                'phone': 'tel',
            },
        )

        if self.user_context and not self.user_context.is_superuser:
            if self.user_context == user_instance:
                if self.user_context.is_staff:
                    self.fields['scope'].disabled = True
                    self.fields['is_active'].disabled = True
                    self.fields['scope'].help_text = s.get('help_scope_self', "You cannot change your own scope to prevent removing your own admin access.")
            
            # Central Staff: cannot edit scope of any user (can only edit scopeless users)
            if is_central_staff(self.user_context):
                target_scope = getattr(user_instance.profile, 'scope', None) if user_instance and hasattr(user_instance, 'profile') else None
                if target_scope is not None:
                    # Cannot edit scoped users at all - hide scope field
                    self.fields['scope'].widget = forms.HiddenInput()
                else:
                    # Can edit scopeless user but cannot assign a scope - hide scope field
                    self.fields['scope'].widget = forms.HiddenInput()
                    self.fields['scope'].initial = None

        self.fields["email"].required = False

        self.helper = FormHelper()
        self.helper.form_tag = False
        
        from dlux.utils import is_scope_enabled
        scope_visible = 'scope' in self.fields and getattr(self.fields['scope'].widget, 'input_type', '') != 'hidden' and is_scope_enabled()
        
        layout_fields = [
            Row(Field("username", css_class="form-control")),            
            HTML("<hr>"),
            Row(
                Div(Field("first_name", css_class="form-control"), css_class="col-md-6"),
                Div(Field("last_name", css_class="form-control"), css_class="col-md-6"),
                css_class="row"
            ),
            Row(
                Div(Field("phone", css_class="form-control"), css_class="col-md-6"),
                Div(Field("email", css_class="form-control"), css_class="col-md-6"),
                css_class="row"
            ),
            Field("is_active")
        ]
        
        if scope_visible:
            layout_fields.append(Row(Field("scope", css_class="form-control")))

        actions = _build_submit_actions(
            s,
            submit_label=s.get('btn_update', 'Update'),
            submit_icon='bi-person-check-fill',
        )
        
        self.helper.layout = Layout(*layout_fields, actions)

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            
            # Save Profile fields
            Profile = apps.get_model('dlux', 'Profile')
            profile, created = Profile.all_objects.get_or_create(user=user)
            profile.phone = self.cleaned_data.get('phone')
            user_scope = get_user_scope(self.user_context)
            if self.user_context and not self.user_context.is_superuser and user_scope:
                profile.scope = user_scope
            else:
                if 'scope' in self.changed_data:
                    profile.scope = self.cleaned_data.get('scope')
            profile.save()
            
        return user


class CustomUserPermissionsForm(UserChangeForm):
    handles_save = True
    refresh_parent = True

    permissions = forms.ModelMultipleChoiceField(
        queryset=get_assignable_permissions_queryset(),
        required=False,
        widget=GroupedPermissionWidget,
        label="Permissions"
    )

    class Meta:
        model = User
        fields = ["is_staff", "permissions"]

    def __init__(self, *args, **kwargs):
        self.user_context = kwargs.pop('user', None)
        user_instance = kwargs.get('instance')
        super().__init__(*args, **kwargs)

        s = get_strings()
        self.modal_heading = s.get('edit_permissions_label', 'Edit Permissions')
        self.fields['permissions'].widget.translations = s

        _apply_assignable_permission_filter(self, self.user_context)

        self.fields["is_staff"].label = s.get('form_is_staff', "Enable Staff Access")
        self.fields["is_staff"].help_text = s.get('help_is_staff', "Enables staff access. The final tier depends on scope and selected permissions.")
        self.fields["permissions"].label = s.get('form_permissions', "Permissions")

        if user_instance:
            self.fields["permissions"].initial = user_instance.user_permissions.all()

        lock_scope = bool(
            self.user_context
            and not self.user_context.is_superuser
            and hasattr(self.user_context, 'profile')
            and self.user_context.profile.scope
        )

        if self.user_context and not self.user_context.is_superuser:
            if self.user_context == user_instance and self.user_context.is_staff:
                self.fields['is_staff'].disabled = True
                filtered_qs = self.fields['permissions'].queryset.exclude(codename='manage_staff')
                self.fields['permissions'].queryset = filtered_qs
                self.fields['permissions'].widget._filtered_queryset = filtered_qs

            if not self.user_context.has_perm('dlux.manage_staff'):
                self.fields['is_staff'].disabled = True
                self.fields['is_staff'].help_text = s.get(
                    'help_is_staff_no_perm',
                    "You don't have permission to change this user's staff status.",
                )

        if lock_scope:
            filtered_qs = self.fields['permissions'].queryset.exclude(codename='manage_staff')
            self.fields['permissions'].queryset = filtered_qs
            self.fields['permissions'].widget._filtered_queryset = filtered_qs
        
        # Central Staff (and any non-superuser without manage_scopes): cannot assign manage_scopes permission
        # Only superusers can create Global Staff by assigning manage_scopes
        if self.user_context and not self.user_context.is_superuser:
            if not self.user_context.has_perm('dlux.manage_scopes'):
                filtered_qs = self.fields['permissions'].queryset.exclude(codename='manage_scopes')
                self.fields['permissions'].queryset = filtered_qs
                # Store filtered queryset for widget to use
                self.fields['permissions'].widget._filtered_queryset = filtered_qs

        _attach_is_staff_permission(self, self.fields['permissions'].widget.attrs.get('id'))
        preview_scope = getattr(getattr(user_instance, 'profile', None), 'scope', None)
        _configure_staff_tier_preview(self, fixed_scope=preview_scope, scope_locked=True)

        # Optional reusable permission-preset selector (gated on manage_groups).
        initial_groups = None
        if user_instance and getattr(user_instance, 'pk', None):
            initial_groups = user_instance.groups.all()
        _maybe_add_group_presets_field(self, self.user_context, initial_groups=initial_groups)

        self.helper = FormHelper()
        self.helper.form_tag = False
        layout_fields = []
        if 'groups' in self.fields:
            layout_fields.append(Field("groups", css_class="col-12"))
        layout_fields.append(Field("permissions", css_class="col-12"))
        self.helper.layout = Layout(
            *layout_fields,
            _build_submit_actions(
                s,
                submit_label=s.get('btn_update', 'Update'),
                submit_icon='bi-shield-check',
            ),
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            permissions = list(self.cleaned_data["permissions"])
            
            # Central Staff cannot assign manage_scopes permission
            if self.user_context and is_central_staff(self.user_context):
                from dlux.utils import strip_manage_scopes_permissions
                permissions = strip_manage_scopes_permissions(permissions)
            
            # Auto-grant auth.view_user permission when user is staff
            if user.is_staff:
                from django.contrib.auth.models import Permission
                try:
                    view_user_perm = Permission.objects.get(
                        content_type__app_label='auth',
                        codename='view_user'
                    )
                    if view_user_perm not in permissions:
                        permissions.append(view_user_perm)
                except Permission.DoesNotExist:
                    pass

            user.user_permissions.set(permissions)

            # Sync any selected permission presets (live group membership + audit).
            if 'groups' in self.fields:
                from dlux.utils import set_user_group_presets
                set_user_group_presets(
                    user,
                    self.cleaned_data.get('groups') or [],
                    actor=self.user_context,
                    manageable_groups=self.fields['groups'].queryset,
                )
        return user


class UserModalForm:
    """
    Smart proxy form for the Dynamic Modal system.
    Delegates to CustomUserCreationForm (create) or CustomUserChangeForm (edit)
    based on whether an instance with a PK is provided.
    """
    handles_save = True  # Tells DynamicModalManagerView to call save(commit=True) directly
    refresh_parent = True # Tells dynamic_modals.js to reload the page on success

    def __new__(cls, *args, user=None, **kwargs):
        instance = kwargs.get('instance')

        if instance and instance.pk:
            # Edit mode — use change form
            form_cls = CustomUserChangeForm
        else:
            # Create mode — use creation form
            form_cls = CustomUserCreationForm
            # Remove instance for creation form (UserCreationForm doesn't expect it)
            kwargs.pop('instance', None)

        kwargs['user'] = user
        form = form_cls(*args, **kwargs)
        form.handles_save = True
        # Ensure no <form> tag in modal context (modal template provides it)
        if hasattr(form, 'helper'):
            form.helper.form_tag = False
        return form


class UserProfileEditForm(forms.ModelForm):
    # Add fields from profile
    phone = forms.CharField(max_length=15, required=False, label="Phone Number")
    profile_picture = forms.ImageField(required=False, label="Profile Picture")

    handles_save = True  # Indicate to DynamicModalManagerView to call save(commit=True) directly
    refresh_parent = True # Force page reload on success

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']

    def __init__(self, *args, user=None, **kwargs):
        # Extract instance and pop 'user' before super().__init__
        user_instance = kwargs.get('instance')
        self.user_context = user
        super().__init__(*args, **kwargs)
        
        s = get_strings()

        if user_instance and hasattr(user_instance, 'profile'):
            self.fields['phone'].initial = user_instance.profile.phone
            self.fields['profile_picture'].initial = user_instance.profile.profile_picture

        self.fields['username'].disabled = True
        self.fields['username'].label = s.get('form_username', "Username")
        self.fields['first_name'].label = s.get('form_firstname', "First Name")
        self.fields['last_name'].label = s.get('form_lastname', "Last Name")
        self.fields['email'].label = s.get('form_email', "Email")
        self.fields['phone'].label = s.get('form_phone', "Phone Number")
        self.fields['profile_picture'].label = s.get('form_profile_pic', "Profile Picture")
        self.fields['profile_picture'].widget = _build_archive_file_widget(
            attrs={'accept': 'image/*'},
            field_label=self.fields['profile_picture'].label,
        )

        
        self.fields["email"].required = False
        _apply_autocomplete_attrs(
            self,
            {
                'username': 'username',
                'first_name': 'given-name',
                'last_name': 'family-name',
                'email': 'email',
                'phone': 'tel',
            },
        )

        self.helper = FormHelper()
        self.helper.form_tag = False
        
        layout_blocks = [
            build_archive_file_field("profile_picture"),
            Row(Field("username", css_class="form-control")),            
            HTML("<hr>"),
            Row(
                Div(Field("first_name", css_class="form-control"), css_class="col-md-6"),
                Div(Field("last_name", css_class="form-control"), css_class="col-md-6"),
                css_class="row"
            ),
            Row(
                Div(Field("phone", css_class="form-control"), css_class="col-md-6"),
                Div(Field("email", css_class="form-control"), css_class="col-md-6"),
                css_class="row"
            ),
            HTML("<hr>"),
            FormActions(
                HTML(
                    f"""
                    <button type="submit" class="btn btn-success rounded-pill">
                        <i class="bi bi-save text-light me-1 h4"></i>
                        {s.get('btn_update', 'Update')}
                    </button>
                    """
                ),
                HTML(
                    f"""
                    <button type="button" class="btn btn-danger rounded-pill" data-bs-dismiss="modal">
                        <i class="bi bi-x-circle text-light me-1 h4"></i> {s.get('btn_cancel', 'Cancel')}
                    </button>
                    """
                )
            )
        ]
        
        self.helper.layout = Layout(*layout_blocks)

    def clean_profile_picture(self):
        profile_picture = self.cleaned_data.get('profile_picture')
        if profile_picture:
            try:
                # Just check if it can be opened by Pillow
                img = Image.open(profile_picture)
                # No need to verify() and raise error for size anymore
                # as the model handles resizing automatically.
                # However, we must reset the file pointer for further use.
                if hasattr(profile_picture, 'seek'):
                    profile_picture.seek(0)
            except Exception:
                raise ValidationError("Invalid image file.")
        return profile_picture

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            
            Profile = apps.get_model('dlux', 'Profile')
            profile, created = Profile.all_objects.get_or_create(user=user)
            
            profile.phone = self.cleaned_data.get('phone')
            if self.cleaned_data.get('profile_picture'):
                profile.profile_picture = self.cleaned_data.get('profile_picture')
            profile.save()
            
        return user
