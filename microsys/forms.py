# Imports of the required python modules and libraries
######################################################
import json
from types import MethodType

from django import forms
from django.contrib.auth.models import Permission as Permissions
from django.contrib.auth.forms import UserCreationForm, UserChangeForm, PasswordChangeForm, SetPasswordForm
from django.contrib.auth import get_user_model
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Div, HTML, Submit, Row
from crispy_forms.bootstrap import FormActions
from PIL import Image
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from django.db.models import Q
from django.apps import apps
from django.forms.widgets import ChoiceWidget
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from .constants import (
    DEFAULT_HOME_URL,
    DEFAULT_SIDEBAR_COLLAPSE_MODE,
    DEFAULT_SIDEBAR_DENSITY,
    DEFAULT_TABLE_DENSITY,
    LEGACY_HOME_URL,
    SIDEBAR_COLLAPSE_MODE_CHOICES,
    SIDEBAR_COLLAPSE_MODE_VALUES,
    SIDEBAR_DENSITY_CHOICES,
    SIDEBAR_DENSITY_VALUES,
    TABLE_DENSITY_CHOICES,
    TABLE_DENSITY_VALUES,
    TITLEBAR_ALIGN_CHOICES,
    TITLEBAR_ALIGN_VALUES,
    TITLEBAR_HEIGHT_CHOICES,
    TITLEBAR_HEIGHT_VALUES,
    TITLEBAR_HOME_SHAPE_CHOICES,
    TITLEBAR_HOME_SHAPE_VALUES,
    TITLEBAR_SIZE_CHOICES,
    TITLEBAR_SIZE_VALUES,
    TITLEBAR_SURFACE_CHOICES,
    TITLEBAR_SURFACE_VALUES,
)
from .translations import get_strings, get_current_language_code
from .themes import get_theme_choices, get_theme_options, is_valid_theme, normalize_allowed_themes
from .utils import default_titlebar_config, has_section_models, normalize_sidebar_behavior, normalize_titlebar_config
from .widgets import MicrosysChoiceSelectorWidget

User = get_user_model()

THEME_CHOICES = get_theme_choices()


def _json_dump(value, **kwargs):
    return json.dumps(value, cls=DjangoJSONEncoder, **kwargs)


def _system_settings_sidebar_tools_available(cleaned_data):
    allowed_themes = cleaned_data.get('allowed_themes') or []
    theme_picker_enabled = bool(cleaned_data.get('allow_user_theme_override', True)) and len(allowed_themes) > 1
    density_picker_enabled = bool(cleaned_data.get('sidebar_allow_user_density', True))
    reorder_enabled = bool(cleaned_data.get('sidebar_enable_reorder', True))
    return bool(theme_picker_enabled or density_picker_enabled or reorder_enabled or has_section_models())


def _bind_choice_selector_widget(field, widget):
    widget.choices = field.choices
    field.widget = widget




def _attach_is_staff_permission(form, widget_id=None):
    perm_field = form.fields.get('permissions')
    staff_field = form.fields.get('is_staff')
    if not perm_field or not staff_field:
        return
    if not isinstance(perm_field.widget, GroupedPermissionWidget):
        return

    try:
        app_config = apps.get_app_config('microsys')
        app_name = app_config.verbose_name
    except LookupError:
        app_name = 'microsys'

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
        'label': staff_field.label or s.get('form_is_staff', "مسؤول"),
        'selected': current_value,
        'help_text': staff_field.help_text,
        'attrs': {
            'id': option_id,
            'data_action': 'other',
            'data_model': 'staff',
            'disabled': bool(getattr(staff_field, 'disabled', False)),
        }
    }

    perm_field.widget.add_extra_group(
        app_label='microsys',
        app_name=app_name,
        model_key='staff_access',
        model_name=s.get('perm_staff_access', 'صلاحيات الإدارة'),
        option=option,
    )


def _get_ui_direction():
    return 'rtl' if get_current_language_code().startswith('ar') else 'ltr'


def _build_cancel_button_html(strings):
    return f"""
    <button type="button" class="btn btn-danger rounded-pill" data-bs-dismiss="modal">
        <i class="bi bi-x-circle text-light me-1 h4"></i> {strings.get('btn_cancel', 'Cancel')}
    </button>
    """


def _wrap_modal_action_buttons(*buttons):
    direction = _get_ui_direction()
    button_html = ''.join(buttons)
    return FormActions(
        HTML(
            f"""
            <div class="d-flex flex-wrap justify-content-end gap-2 ms-modal-form-actions" dir="{direction}">
                {button_html}
            </div>
            """
        )
    )


def _build_wizard_actions(strings, submit_label, submit_icon):
    direction = _get_ui_direction()
    prev_icon = 'bi-arrow-right-circle' if direction == 'rtl' else 'bi-arrow-left-circle'
    next_icon = 'bi-arrow-left-circle' if direction == 'rtl' else 'bi-arrow-right-circle'

    return _wrap_modal_action_buttons(
        _build_cancel_button_html(strings),
        f"""
        <button type="button" class="btn btn-secondary rounded-pill ms-btn-prev" style="display: none;">
            <i class="bi {prev_icon} text-light me-1 h4"></i> {strings.get('btn_prev', 'Previous')}
        </button>
        """,
        f"""
        <button type="button" class="btn btn-primary rounded-pill ms-btn-next">
            {strings.get('btn_next', 'Next')} <i class="bi {next_icon} text-light ms-1 h4"></i>
        </button>
        """,
        f"""
        <button type="submit" class="btn btn-success rounded-pill ms-btn-submit" style="display: none;">
            <i class="bi {submit_icon} text-light me-1 h4"></i> {submit_label}
        </button>
        """,
    )


def _build_submit_actions(strings, submit_label, submit_icon, submit_class='btn btn-success rounded-pill'):
    return _wrap_modal_action_buttons(
        _build_cancel_button_html(strings),
        f"""
        <button type="submit" class="{submit_class}">
            <i class="bi {submit_icon} text-light me-1 h4"></i> {submit_label}
        </button>
        """,
    )

class ProfileImageWidget(forms.ClearableFileInput):
    template_name = 'microsys/widgets/profile_image_widget.html'


def _apply_autocomplete_attrs(form, mapping):
    for field_name, autocomplete in mapping.items():
        field = form.fields.get(field_name)
        if field is None or not autocomplete:
            continue
        field.widget.attrs['autocomplete'] = autocomplete


def _build_archive_file_widget(field_label="", show_scan=False, attrs=None):
    widget = forms.ClearableFileInput(attrs=attrs or {})
    widget.template_name = 'microsys/forms/file_input.html'

    widget_attrs = dict(widget.attrs or {})
    existing_class = str(widget_attrs.get('class', '') or '').strip()
    widget_attrs['class'] = f"{existing_class} archive-file-input".strip()
    widget.attrs = widget_attrs

    def _get_context(self, name, value, attrs):
        context = forms.ClearableFileInput.get_context(self, name, value, attrs)
        data = context["widget"]
        data["field_label"] = field_label
        data["show_scan"] = show_scan

        if value and hasattr(value, "url"):
            data["file_url"] = value.url
            data["display_name"] = getattr(value, "name", "").split("/")[-1] or str(value)
            display_name = data["display_name"].lower()
            if display_name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico")):
                data["icon_class"] = "bi bi-file-earmark-image-fill"
            else:
                data["icon_class"] = "bi bi-file-earmark-fill"
        else:
            data["file_url"] = ""
            data["display_name"] = ""
            data["icon_class"] = "bi bi-file-earmark-arrow-up-fill"

        return context

    widget.get_context = MethodType(_get_context, widget)
    return widget

class GroupedPermissionWidget(ChoiceWidget):
    template_name = 'microsys/users/grouped_permissions.html'
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
        
        # Get current selected values (as strings/ints)
        if value is None:
            value = []
        str_values = set(str(v) for v in value)
        
        # Access the queryset directly
        qs = None
        if hasattr(self.choices, 'queryset'):
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

            # --- Mapping manage_staff and view_activity_log to is_staff UI ---
            if app_label == 'microsys' and codename in ['manage_staff', 'view_activity_log']:
                model_name = 'staff_access'
                # Force model_verbose_name to match what _attach_is_staff_permission uses
                # "perm_staff_access" string usually "صلاحيات الإدارة"
                
            # Use real verbose name from model class if available
            if app_label == 'microsys' and model_name == 'staff_access':
                model_verbose_name = s.get('perm_staff_access', "صلاحيات الإدارة")
            elif app_label == 'microsys' and model_name == 'profile':
                model_verbose_name = s.get('perm_manage_users', "إدارة المستخدمين")
            # elif app_label == 'auth' and model_name == 'section':
            #     model_verbose_name = "إدارة الأقسام الفرعية"
            # else:
            model_class = perm.content_type.model_class()
            if model_class:
                # prefer plural verbose name if possible, or just verbose name
                # But here we want to use our translation keys if available
                default_verbose = str(model_class._meta.verbose_name)
            else:
                default_verbose = perm.content_type.name
            
            # Try translation key 'model_modelname' (e.g. model_user)
            # Override for specific known models if needed, though they should be in translations now
            model_verbose_name = s.get(f"model_{model_name}", default_verbose)
            
            # Fetch verbose app name
            try:
                app_config = apps.get_app_config(app_label)
                default_app_verbose = app_config.verbose_name
            except LookupError:
                default_app_verbose = app_label.title()
            
            # Try translation key 'app_applabel' (e.g. app_microsys)
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

            # Special Help Text for manage_staff
            help_text = ""
            if codename == 'manage_staff':
                 help_text = s.get('help_perm_manage_staff', "Grants the user permission to assign other users as staff.")

            option = {
                'name': name,
                'value': perm.pk,
                'label': perm_label,
                'codename': codename,
                'selected': str(perm.pk) in str_values,
                'help_text': help_text,
                'attrs': {
                    'id': f"{current_id}_{perm.pk}",
                    'data_action': action,
                    'data_model': model_name
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
        context['MS_TRANS'] = s  # Pass translations to template
        return context

    def render(self, name, value, attrs=None, renderer=None):
        from django.template.loader import render_to_string
        from django.utils.safestring import mark_safe
        
        context = self.get_context(name, value, attrs)
        return mark_safe(render_to_string(self.template_name, context))



# Custom User Creation form layout
class CustomUserCreationForm(UserCreationForm):
    handles_save = True
    refresh_parent = True

    # Added fields from Profile
    phone = forms.CharField(max_length=15, required=False)
    scope = forms.ModelChoiceField(queryset=None, required=False, label="النطاق")
    
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permissions.objects.exclude(
            Q(codename__regex=r'^(delete_)') |
            Q(content_type__app_label__in=[
                'admin',
                'contenttypes',
                'sessions',
                'django_celery_beat',
            ]) |
            (Q(content_type__app_label='microsys') & ~Q(codename='manage_staff') & ~Q(codename='view_activity_log') & ~Q(content_type__model='section')) |
            Q(content_type__app_label='auth', content_type__model__in=['group', 'user', 'permission'])
        ),
        required=False,
        widget=GroupedPermissionWidget,
        label="الصلاحيات"
    )

    class Meta:
        model = User
        fields = ["username", "password1", "password2", "first_name", "last_name", "email", "is_staff", "is_active"]

    def __init__(self, *args, **kwargs):
        self.user_context = kwargs.pop('user', None) # Renamed to avoid calling it self.user which conflicts with instance in some contexts? No wait, self.user in init usually refers to request.user passed in view
        super().__init__(*args, **kwargs)
        
        Scope = apps.get_model('microsys', 'Scope')
        self.fields['scope'].queryset = Scope.objects.all()

        # Permission check: Non-superusers can only assign permissions they already have
        if self.user_context and not self.user_context.is_superuser:
            user_perms = self.user_context.user_permissions.all() | Permissions.objects.filter(group__user=self.user_context)
            self.fields['permissions'].queryset = self.fields['permissions'].queryset.filter(id__in=user_perms.values_list('id', flat=True))

        lock_scope = bool(
            self.user_context
            and not self.user_context.is_superuser
            and hasattr(self.user_context, 'profile')
            and self.user_context.profile.scope
        )

        if lock_scope:
            # Security Fix: Hide manage_staff
            self.fields['permissions'].queryset = self.fields['permissions'].queryset.exclude(codename='manage_staff')
        
        self.fields["email"].required = False

        # can_manage_staff logic
        if self.user_context and not self.user_context.is_superuser:
            if not self.user_context.has_perm('microsys.manage_staff'):
                self.fields['is_staff'].disabled = True
                self.fields['is_staff'].initial = False
                self.fields['is_staff'].help_text = "ليس لديك صلاحية لتعيين هذا المستخدم كمسؤول."

        # Load translations
        s = get_strings()
        self.modal_heading = s.get('add_user', 'Add New User')
        
        # Inject translations into widget
        self.fields['permissions'].widget.translations = s

        self.fields["username"].label = s.get('form_username', "اسم المستخدم")
        self.fields["email"].label = s.get('form_email', "البريد الإلكتروني")
        self.fields["first_name"].label = s.get('form_firstname', "الاسم")
        self.fields["last_name"].label = s.get('form_lastname', "اللقب")
        self.fields["is_staff"].label = s.get('form_is_staff', "صلاحيات انشاء و تعديل المستخدمين")
        self.fields["password1"].label = s.get('form_password', "كلمة المرور")
        self.fields["password2"].label = s.get('form_password_confirm', "تأكيد كلمة المرور")
        self.fields["is_active"].label = s.get('form_is_active', "تفعيل الحساب")
        self.fields["phone"].label = s.get('form_phone', "رقم الهاتف")
        self.fields["scope"].label = s.get('form_scope', "النطاق")
        self.fields["permissions"].label = s.get('form_permissions', "الصلاحيات")

        # Help Texts
        self.fields["username"].help_text = s.get('help_username', "اسم المستخدم يجب أن يكون فريدًا...")
        self.fields["email"].help_text = s.get('help_email', "أدخل عنوان البريد الإلكتروني الصحيح (اختياري)")
        self.fields["is_active"].help_text = s.get('help_is_active', "يحدد ما إذا كان يجب اعتبار هذا الحساب نشطًا.")
        self.fields["is_staff"].help_text = s.get('help_is_staff', "يحدد ما إذا كان يمكن للمستخدم تسجيل الدخول إلى هذا الموقع الإداري.")
        self.fields["password1"].help_text = s.get('help_password_common', "كلمة المرور يجب ألا تكون مشابهة...")
        self.fields["password2"].help_text = s.get('help_password_match', "أدخل نفس كلمة المرور السابقة للتحقق.")
        self.fields["phone"].help_text = s.get('help_phone', "أدخل رقم الهاتف الصحيح...")
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
            if not self.user_context.has_perm('microsys.manage_staff'):
                 # ... existing disabled logic ...
                 self.fields['is_staff'].help_text = s.get('help_is_staff_no_perm', "ليس لديك صلاحية لتعيين هذا المستخدم كمسؤول.")

        _attach_is_staff_permission(self, self.fields['permissions'].widget.attrs.get('id'))


        self.helper = FormHelper()
        self.helper.form_tag = False
        
        from microsys.utils import is_scope_enabled
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
            Field("is_active")
        ]
        
        if scope_visible:
            step_1_fields.append(Row(Field("scope", css_class="form-control")))
            
        step_1_div = Div(*step_1_fields, css_class="wizard-step wizard-step-1")
        
        step_2_fields = [
            HTML("<hr>"),
            Field("permissions", css_class="col-12")
        ]
        step_2_div = Div(*step_2_fields, css_class="wizard-step wizard-step-2", style="display: none;")

        actions = _build_wizard_actions(
            s,
            submit_label=s.get('btn_add', 'إضافة'),
            submit_icon='bi-person-plus-fill',
        )

        self.helper.layout = Layout(step_1_div, step_2_div, actions)

    def save(self, commit=True):
        user = super().save(commit=False)
        # We need to save the user first to get an ID for the OneToOne relationship
        if commit:
            user.save()
            # Manually set permissions
            user.user_permissions.set(self.cleaned_data["permissions"])
            
            # Save Profile fields
            Profile = apps.get_model('microsys', 'Profile')
            # Check if profile already exists (via signal) or create it
            profile, created = Profile.all_objects.get_or_create(user=user)
            profile.phone = self.cleaned_data.get('phone')
            if self.user_context and not self.user_context.is_superuser and hasattr(self.user_context, 'profile') and self.user_context.profile.scope:
                profile.scope = self.user_context.profile.scope
            elif self.cleaned_data.get('scope'):
                profile.scope = self.cleaned_data.get('scope')
            # If empty scope, we do not overwrite since signal may have auto-assigned one
            profile.save()
            
        return user


# Custom User Editing form layout
class CustomUserChangeForm(UserChangeForm):
    handles_save = True
    refresh_parent = True

    phone = forms.CharField(max_length=15, required=False)
    scope = forms.ModelChoiceField(queryset=None, required=False, label="النطاق")

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]

    def __init__(self, *args, **kwargs):
        self.user_context = kwargs.pop('user', None)
        user_instance = kwargs.get('instance')
        super().__init__(*args, **kwargs)
        
        Scope = apps.get_model('microsys', 'Scope')
        self.fields['scope'].queryset = Scope.objects.all()

        # Initialize Profile Fields
        if user_instance and hasattr(user_instance, 'profile'):
            self.fields['phone'].initial = user_instance.profile.phone
            self.fields['scope'].initial = user_instance.profile.scope

        # Labels
        s = get_strings()
        self.modal_heading = s.get('edit_user_label', 'Edit User')

        self.fields["username"].label = s.get('form_username', "اسم المستخدم")
        self.fields["email"].label = s.get('form_email', "البريد الإلكتروني")
        self.fields["first_name"].label = s.get('form_firstname', "الاسم الاول")
        self.fields["last_name"].label = s.get('form_lastname', "اللقب")
        self.fields["is_active"].label = s.get('form_is_active', "الحساب مفعل")
        self.fields["phone"].label = s.get('form_phone', "رقم الهاتف")
        self.fields["scope"].label = s.get('form_scope', "النطاق")
        
        self.fields["username"].help_text = s.get('help_username', "اسم المستخدم يجب أن يكون فريدًا...")
        self.fields["email"].help_text = s.get('help_email', "أدخل عنوان البريد الإلكتروني الصحيح (اختياري)")
        self.fields["is_active"].help_text = s.get('help_is_active', "يحدد ما إذا كان يجب اعتبار هذا الحساب نشطًا.")
        self.fields["phone"].help_text = s.get('help_phone', "أدخل رقم الهاتف الصحيح...")
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
                    self.fields['scope'].help_text = s.get('help_scope_self', "لا يمكنك تغيير نطاقك الخاص لمنع تجريد نفسك من صلاحيات المدير العام.")

        self.fields["email"].required = False

        self.helper = FormHelper()
        self.helper.form_tag = False
        
        from microsys.utils import is_scope_enabled
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
            submit_label=s.get('btn_update', 'تحديث'),
            submit_icon='bi-person-check-fill',
        )
        
        self.helper.layout = Layout(*layout_fields, actions)

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            
            # Save Profile fields
            Profile = apps.get_model('microsys', 'Profile')
            profile, created = Profile.all_objects.get_or_create(user=user)
            profile.phone = self.cleaned_data.get('phone')
            if self.user_context and not self.user_context.is_superuser and hasattr(self.user_context, 'profile') and self.user_context.profile.scope:
                profile.scope = self.user_context.profile.scope
            else:
                if 'scope' in self.changed_data:
                    profile.scope = self.cleaned_data.get('scope')
            profile.save()
            
        return user


class CustomUserPermissionsForm(UserChangeForm):
    handles_save = True
    refresh_parent = True

    permissions = forms.ModelMultipleChoiceField(
        queryset=Permissions.objects.exclude(
            Q(codename__regex=r'^(delete_)') |
            Q(content_type__app_label__in=[
                'admin',
                'contenttypes',
                'sessions',
                'django_celery_beat',
            ]) |
            (Q(content_type__app_label='microsys') & ~Q(codename='manage_staff') & ~Q(codename='view_activity_log') & ~Q(content_type__model='section')) |
            Q(content_type__app_label='auth', content_type__model__in=['group', 'user', 'permission'])
        ),
        required=False,
        widget=GroupedPermissionWidget,
        label="الصلاحيات"
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

        if self.user_context and not self.user_context.is_superuser:
            user_perms = self.user_context.user_permissions.all() | Permissions.objects.filter(group__user=self.user_context)
            self.fields['permissions'].queryset = self.fields['permissions'].queryset.filter(
                id__in=user_perms.values_list('id', flat=True)
            )

        self.fields["is_staff"].label = s.get('form_is_staff', "صلاحيات انشاء و تعديل المستخدمين")
        self.fields["is_staff"].help_text = s.get('help_is_staff', "يحدد ما إذا كان يمكن للمستخدم عرض وادارة المستخدمين.")
        self.fields["permissions"].label = s.get('form_permissions', "الصلاحيات")

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
                self.fields['permissions'].queryset = self.fields['permissions'].queryset.exclude(codename='manage_staff')

            if not self.user_context.has_perm('microsys.manage_staff'):
                self.fields['is_staff'].disabled = True
                self.fields['is_staff'].help_text = s.get(
                    'help_is_staff_no_perm',
                    "ليس لديك صلاحية لتغيير وضع هذا المستخدم لمسؤول .",
                )

        if lock_scope:
            self.fields['permissions'].queryset = self.fields['permissions'].queryset.exclude(codename='manage_staff')

        _attach_is_staff_permission(self, self.fields['permissions'].widget.attrs.get('id'))

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("permissions", css_class="col-12"),
            _build_submit_actions(
                s,
                submit_label=s.get('btn_update', 'تحديث'),
                submit_icon='bi-shield-check',
            ),
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            user.user_permissions.set(self.cleaned_data["permissions"])
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


# Custom User Reset Password form layout
class ResetPasswordForm(SetPasswordForm):
    username = forms.CharField(label="Username", widget=forms.TextInput(attrs={"readonly": "readonly"}))

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        s = get_strings()
        self.fields['username'].initial = user.username
        self.fields['username'].label = s.get('form_username', "Username")
        
        self.helper = FormHelper()
        self.fields["new_password1"].label = s.get('form_new_password', "New Password")
        self.fields['new_password1'].help_text = mark_safe(s.get('help_password_common', "Password should not be similar to..."))

        self.fields["new_password2"].label = s.get('form_confirm_new_password', "Confirm New Password")
        self.fields['new_password2'].help_text = s.get('help_password_match', "Enter the same password as...")
        _apply_autocomplete_attrs(
            self,
            {
                'username': 'username',
                'new_password1': 'new-password',
                'new_password2': 'new-password',
            },
        )
        self.helper.layout = Layout(
            Div(
                Field('username', css_class='col-md-12'),
                Field('new_password1', css_class='col-md-12'),
                Field('new_password2', css_class='col-md-12'),
                css_class='row'
            ),
            Submit('submit', s.get('btn_change_password', 'Change Password'), css_class='btn btn-danger rounded-pill'),
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
        return user


class UserProfileEditForm(forms.ModelForm):
    # Add fields from profile
    phone = forms.CharField(max_length=15, required=False, label="رقم الهاتف")
    profile_picture = forms.ImageField(required=False, label="الصورة الشخصية", widget=ProfileImageWidget)

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
        self.fields['username'].label = s.get('form_username', "اسم المستخدم")
        self.fields['first_name'].label = s.get('form_firstname', "الاسم الاول")
        self.fields['last_name'].label = s.get('form_lastname', "اللقب")
        self.fields['email'].label = s.get('form_email', "البريد الالكتروني")
        self.fields['phone'].label = s.get('form_phone', "رقم الهاتف")
        self.fields['profile_picture'].label = s.get('form_profile_pic', "الصورة الشخصية")

        
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
            Field("profile_picture"),
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
                        {s.get('btn_update', 'تحديث')}
                    </button>
                    """
                ),
                HTML(
                    f"""
                    <button type="button" class="btn btn-danger rounded-pill" data-bs-dismiss="modal">
                        <i class="bi bi-x-circle text-light me-1 h4"></i> {s.get('btn_cancel', 'إلغـــاء')}
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
            
            Profile = apps.get_model('microsys', 'Profile')
            profile, created = Profile.all_objects.get_or_create(user=user)
            
            profile.phone = self.cleaned_data.get('phone')
            if self.cleaned_data.get('profile_picture'):
                profile.profile_picture = self.cleaned_data.get('profile_picture')
            profile.save()
            
        return user


class CustomPasswordChangeForm(PasswordChangeForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        s = get_strings()
        
        # Current Password
        self.fields['old_password'].label = s.get('form_old_password', "Current Password")
        self.fields['old_password'].widget.attrs.pop('dir', None) # Remove fixed RTL 
        
        # New Password 1
        self.fields['new_password1'].label = s.get('form_new_password', "New Password")
        self.fields['new_password1'].help_text = mark_safe(s.get('help_password_common', "Password should not be similar to..."))
        self.fields['new_password1'].widget.attrs.pop('dir', None)

        # New Password 2
        self.fields['new_password2'].label = s.get('form_confirm_new_password', "Confirm New Password")
        self.fields['new_password2'].help_text = s.get('help_password_match', "Enter the same password as...")
        self.fields['new_password2'].widget.attrs.pop('dir', None)
        _apply_autocomplete_attrs(
            self,
            {
                'old_password': 'current-password',
                'new_password1': 'new-password',
                'new_password2': 'new-password',
            },
        )

class ScopeForm(forms.ModelForm):
    class Meta:
        model = apps.get_model('microsys', 'Scope')
        fields = ['name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        s = get_strings()
        # But scope form often used in modals?
        # If we have request in kwargs we can use it, but typically ModelForms don't get request.
        # Fallback to default is okay for now or we can inject request if needed.
        self.fields['name'].label = s.get('form_scope_name', "اسم النطاق")
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field('name', css_class='col-12'),
        )


class SystemSettingsForm(forms.ModelForm):
    home_url_discovered = forms.ChoiceField(
        required=False,
        choices=(),
    )
    default_language = forms.ChoiceField(
        required=True,
        widget=forms.HiddenInput(),
    )
    default_theme = forms.ChoiceField(
        required=True,
        choices=[(value, value) for value, _, _ in THEME_CHOICES],
        widget=forms.HiddenInput(),
    )
    allowed_themes = forms.MultipleChoiceField(
        required=False,
        choices=[(value, value) for value, _, _ in THEME_CHOICES],
    )
    allow_user_theme_override = forms.BooleanField(
        required=False,
        initial=True,
    )
    allow_user_language_override = forms.BooleanField(
        required=False,
        initial=True,
    )
    default_table_density = forms.ChoiceField(
        required=True,
        choices=TABLE_DENSITY_CHOICES,
        widget=forms.HiddenInput(),
    )
    languages = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
    )
    translations_override = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
    )
    sidebar_config = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    sidebar_enable_reorder = forms.BooleanField(
        required=False,
        initial=True,
    )
    sidebar_enable_toolbar = forms.BooleanField(
        required=False,
        initial=True,
    )
    sidebar_show_icons = forms.BooleanField(
        required=False,
        initial=True,
    )
    sidebar_density = forms.ChoiceField(
        required=False,
        choices=SIDEBAR_DENSITY_CHOICES,
        widget=forms.HiddenInput(),
    )
    sidebar_allow_user_density = forms.BooleanField(
        required=False,
        initial=True,
    )
    sidebar_collapse_mode = forms.ChoiceField(
        required=False,
        choices=SIDEBAR_COLLAPSE_MODE_CHOICES,
        initial=DEFAULT_SIDEBAR_COLLAPSE_MODE,
    )
    titlebar_show_logo = forms.BooleanField(
        required=False,
        initial=True,
    )
    titlebar_show_title = forms.BooleanField(
        required=False,
        initial=True,
    )
    titlebar_show_home_button = forms.BooleanField(
        required=False,
        initial=True,
    )
    titlebar_home_shape = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_HOME_SHAPE_CHOICES,
        initial='circle',
    )
    titlebar_title_align = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_ALIGN_CHOICES,
        initial='start',
    )
    titlebar_title_size = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_SIZE_CHOICES,
        initial='md',
    )
    titlebar_height = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_HEIGHT_CHOICES,
        initial='balanced',
    )
    titlebar_surface = forms.ChoiceField(
        required=False,
        choices=TITLEBAR_SURFACE_CHOICES,
        initial='default',
    )
    email_2fa = forms.BooleanField(
        required=False,
        initial=False,
    )
    public_root = forms.BooleanField(
        required=False,
        initial=False,
    )

    class Meta:
        model = apps.get_model('microsys', 'SystemSettings')
        fields = [
            'name',
            'name_en',
            'logo',
            'favicon',
            'home_url',
            'default_language',
            'default_theme',
            'allowed_themes',
            'allow_user_theme_override',
            'allow_user_language_override',
            'default_table_density',
            'email_2fa',
            'public_root',
            'languages',
            'translations_override',
            'sidebar_config',
            'titlebar_config',
        ]

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        self._user = kwargs.pop('user', None)
        self.mode = kwargs.pop('mode', 'modal')
        super().__init__(*args, **kwargs)
        self.refresh_parent = True
        self.extra_form_class = 'ms-system-setup-form'
        self.single_step_mode = False
        self.single_step_index = None
        s = get_strings()
        if hasattr(self, 'translations') and self.translations:
            s = self.translations

        if self.mode != 'setup' and self.request is not None:
            raw_step = self.request.GET.get('step')
            try:
                parsed_step = int(raw_step)
            except (TypeError, ValueError):
                parsed_step = None
            if parsed_step in (0, 1, 2, 3):
                self.single_step_mode = True
                self.single_step_index = parsed_step

        from microsys.discovery import discover_sidebar_catalog, sanitize_sidebar_config
        from microsys.utils import get_system_config

        config = get_system_config()
        current_languages = dict(config.get('languages', {}))
        if isinstance(getattr(self.instance, 'languages', None), dict):
            current_languages.update(self.instance.languages)
        current_languages = {
            code: payload if isinstance(payload, dict) else {'name': str(payload)}
            for code, payload in current_languages.items()
            if payload
        }
        if not current_languages:
            current_languages = {
                'ar': {'name': 'العربية', 'dir': 'rtl', 'flag': '🇱🇾'},
                'en': {'name': 'English', 'dir': 'ltr', 'flag': '🇬🇧'},
            }

        self.fields['default_language'].choices = [
            (code, payload.get('name', code) if isinstance(payload, dict) else str(payload))
            for code, payload in current_languages.items()
        ]
        discovered_theme_choices = [(value, value) for value, _, _ in get_theme_choices()]
        self.fields['default_theme'].choices = discovered_theme_choices
        self.fields['allowed_themes'].choices = discovered_theme_choices

        self.fields['languages'].label = s.get('form_sys_languages', "اللغات المتوفرة (JSON)")
        self.fields['languages'].help_text = s.get('help_sys_languages', 'مثال: {"ar": "العربية", "en": "English"}')
        self.fields['translations_override'].label = s.get('form_sys_translations', "تجاوز الترجمات (JSON)")
        self.fields['translations_override'].help_text = s.get('help_sys_translations', 'مثال: {"ar": {"app_microsys": "النظام"}}')
        self.fields['name'].label = s.get('form_sys_name_ar', "اسم النظام (عربي)")
        self.fields['name_en'].label = s.get('form_sys_name_en', "اسم النظام (إنجليزي)")
        self.fields['home_url'].required = False
        self.fields['home_url'].label = s.get('form_sys_home_url', "الرابط الرئيسي")
        self.fields['home_url'].help_text = s.get('help_sys_home_url', 'يمكنك كتابة مسار مخصص مثل / أو /finance/ أو رابط كامل إذا أردت.')
        self.fields['home_url'].widget.attrs.update({
            'class': 'form-control glass-input',
            'dir': 'ltr',
            'placeholder': DEFAULT_HOME_URL,
        })
        self.fields['home_url_discovered'].label = s.get('form_sys_home_url_discovered', "اختر من الصفحات المكتشفة")
        self.fields['home_url_discovered'].help_text = s.get('help_sys_home_url_discovered', 'اختياري: اختر صفحة مكتشفة لتعبئة الرابط الرئيسي تلقائياً، أو اتركه فارغاً واكتب رابطاً مخصصاً.')
        self.fields['home_url_discovered'].widget.attrs.update({
            'class': 'form-select glass-input',
        })
        self.fields['default_language'].label = s.get('form_sys_default_lang', "اللغة الافتراضية")
        self.fields['default_theme'].label = s.get('form_sys_default_theme', "المظهر الافتراضي")
        self.fields['allowed_themes'].label = s.get('form_sys_allowed_themes', 'Allowed themes')
        self.fields['allowed_themes'].help_text = s.get(
            'help_sys_allowed_themes',
            'Choose which themes are available in this project. The default theme must remain enabled.',
        )
        self.fields['allow_user_theme_override'].label = s.get('form_sys_allow_user_theme_override', 'Allow user theme override')
        self.fields['allow_user_theme_override'].help_text = s.get(
            'help_sys_allow_user_theme_override',
            'Allow users to switch between the allowed themes at runtime from Options and the sidebar toolbar.',
        )
        self.fields['allow_user_language_override'].label = s.get('form_sys_allow_user_language_override', 'Allow user language override')
        self.fields['allow_user_language_override'].help_text = s.get(
            'help_sys_allow_user_language_override',
            'Allow users to change their display language from Options. When disabled, the system default language is enforced.',
        )
        self.fields['default_table_density'].label = s.get('form_sys_default_table_density', "الكثافة الافتراضية للجداول")
        self.fields['default_table_density'].help_text = s.get(
            'help_sys_default_table_density',
            'اختر كثافة الجداول الافتراضية للمستخدمين الجدد، مع إمكانية تجاوزها لاحقاً من صفحة الخيارات.',
        )
        self.fields['logo'].label = s.get('form_sys_logo', "الشعار (Logo)")
        self.fields['favicon'].label = s.get('form_sys_favicon', "أيقونة الموقع (Favicon)")
        self.fields['logo'].widget = _build_archive_file_widget(
            attrs={'accept': 'image/*'},
            field_label=self.fields['logo'].label,
        )
        self.fields['favicon'].widget = _build_archive_file_widget(
            attrs={'accept': 'image/*'},
            field_label=self.fields['favicon'].label,
        )
        self.fields['sidebar_config'].label = s.get('form_sys_sidebar', "إعدادات الشريط الجانبي")
        self.fields['sidebar_enable_reorder'].label = s.get('form_sys_sidebar_enable_reorder', 'Enable sidebar reorder')
        self.fields['sidebar_enable_reorder'].help_text = s.get(
            'help_sys_sidebar_enable_reorder',
            'Show the quick reorder control in the sidebar toolbar so users can rearrange sidebar items from the UI.',
        )
        self.fields['sidebar_enable_toolbar'].label = s.get('form_sys_sidebar_enable_toolbar', 'Enable sidebar toolbar')
        self.fields['sidebar_enable_toolbar'].help_text = s.get(
            'help_sys_sidebar_enable_toolbar',
            'Show the sidebar toolbar that contains the quick theme picker, reorder toggle, and dynamic section manager shortcut.',
        )
        self.fields['sidebar_show_icons'].label = s.get('form_sys_sidebar_show_icons', 'Show sidebar icons')
        self.fields['sidebar_show_icons'].help_text = s.get(
            'help_sys_sidebar_show_icons',
            'Show icons beside sidebar items and folders in the expanded sidebar.',
        )
        self.fields['sidebar_density'].label = s.get('form_sys_sidebar_density', 'Sidebar density')
        self.fields['sidebar_density'].help_text = s.get(
            'help_sys_sidebar_density',
            'Choose the default row density for the sidebar.',
        )
        self.fields['sidebar_density'].choices = (
            ('dense', s.get('table_density_dense', 'Dense')),
            (DEFAULT_SIDEBAR_DENSITY, s.get('table_density_balanced', 'Balanced')),
            ('roomy', s.get('table_density_roomy', 'Roomy')),
        )
        self.fields['sidebar_allow_user_density'].label = s.get('form_sys_sidebar_allow_user_density', 'Allow user sidebar density override')
        self.fields['sidebar_allow_user_density'].help_text = s.get(
            'help_sys_sidebar_allow_user_density',
            'Allow users to change sidebar density from the sidebar toolbar at runtime.',
        )
        self.fields['sidebar_collapse_mode'].label = s.get('form_sys_sidebar_collapse_mode', 'Desktop collapse mode')
        self.fields['sidebar_collapse_mode'].help_text = s.get(
            'help_sys_sidebar_collapse_mode',
            'Choose how the sidebar behaves when collapsed on large screens.',
        )
        self.fields['sidebar_collapse_mode'].choices = (
            ('icons', s.get('sidebar_collapse_icons', 'Icons only')),
            ('hidden', s.get('sidebar_collapse_hidden', 'Hide completely')),
            ('locked_expanded', s.get('sidebar_collapse_locked_expanded', 'Always expanded')),
        )
        self.fields['titlebar_show_title'].label = s.get('form_sys_titlebar_show_title', 'Show titlebar title')
        self.fields['titlebar_show_logo'].label = s.get('form_sys_titlebar_show_logo', 'Show titlebar logo')
        self.fields['titlebar_show_home_button'].label = s.get('form_sys_titlebar_show_home_button', 'Show titlebar home button')
        self.fields['titlebar_home_shape'].label = s.get('form_sys_titlebar_home_shape', 'Home button shape')
        self.fields['titlebar_title_align'].label = s.get('form_sys_titlebar_title_align', 'Title alignment')
        self.fields['titlebar_title_size'].label = s.get('form_sys_titlebar_title_size', 'Title size')
        self.fields['titlebar_height'].label = s.get('form_sys_titlebar_height', 'Titlebar height')
        self.fields['titlebar_surface'].label = s.get('form_sys_titlebar_surface', 'Titlebar surface')
        self.fields['titlebar_show_title'].help_text = s.get(
            'help_sys_titlebar_show_title',
            'Show the system title in the titlebar.',
        )
        self.fields['titlebar_show_logo'].help_text = s.get(
            'help_sys_titlebar_show_logo',
            'Show the configured branding logo beside the title.',
        )
        self.fields['titlebar_show_home_button'].help_text = s.get(
            'help_sys_titlebar_show_home_button',
            'Show the quick Home button in the titlebar.',
        )
        self.fields['titlebar_home_shape'].choices = (
            ('circle', s.get('titlebar_home_shape_circle', 'Circle')),
            ('square', s.get('titlebar_home_shape_square', 'Square')),
            ('squircle', s.get('titlebar_home_shape_squircle', 'Squircle')),
        )
        self.fields['titlebar_title_align'].choices = (
            ('start', s.get('titlebar_align_start', 'Start')),
            ('center', s.get('titlebar_align_center', 'Center')),
            ('end', s.get('titlebar_align_end', 'End')),
        )
        self.fields['titlebar_title_size'].choices = (
            ('sm', s.get('titlebar_size_sm', 'Small')),
            ('md', s.get('titlebar_size_md', 'Medium')),
            ('lg', s.get('titlebar_size_lg', 'Large')),
        )
        self.fields['titlebar_height'].choices = (
            ('dense', s.get('titlebar_height_dense', 'Dense')),
            ('balanced', s.get('titlebar_height_balanced', 'Balanced')),
            ('roomy', s.get('titlebar_height_roomy', 'Roomy')),
        )
        self.fields['titlebar_surface'].choices = (
            ('default', s.get('titlebar_surface_default', 'Default')),
            ('muted', s.get('titlebar_surface_muted', 'Muted')),
            ('glass', s.get('titlebar_surface_glass', 'Glass')),
        )
        self.fields['email_2fa'].label = s.get('form_sys_email_2fa', 'Enable Email 2FA')
        self.fields['email_2fa'].help_text = s.get(
            'help_sys_email_2fa',
            'Allow users to enable two-factor authentication via email. Requires a working EMAIL_HOST in Django settings.',
        )
        self.fields['public_root'].label = s.get('form_sys_public_root', 'Public Root Access')
        self.fields['public_root'].help_text = s.get(
            'help_sys_public_root',
            'Allow anonymous (non-logged-in) users to access the root URL (/). When enabled, the system will not force-redirect to login.',
        )
        self.sidebar_sections_manager_available = bool(has_section_models())
        _bind_choice_selector_widget(
            self.fields['default_table_density'],
            MicrosysChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'dense': {
                        'icon': 'bi-list',
                        'description': s.get('table_density_dense_desc', 'Fits more rows on screen with tighter spacing.'),
                    },
                    'balanced': {
                        'icon': 'bi-table',
                        'description': s.get('table_density_balanced_desc', 'Comfortable default for everyday admin work.'),
                    },
                    'roomy': {
                        'icon': 'bi-layout-text-window-reverse',
                        'description': s.get('table_density_roomy_desc', 'Uses larger rows and more breathing room.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['sidebar_density'],
            MicrosysChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'dense': {
                        'icon': 'bi-list-ul',
                        'description': s.get('sidebar_density_dense_desc', 'Tighter rows and spacing for a denser sidebar.'),
                    },
                    'balanced': {
                        'icon': 'bi-layout-sidebar-inset',
                        'description': s.get('sidebar_density_balanced_desc', 'The default balance between density and readability.'),
                    },
                    'roomy': {
                        'icon': 'bi-distribute-vertical',
                        'description': s.get('sidebar_density_roomy_desc', 'Larger row height and spacing for a more relaxed sidebar.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['sidebar_collapse_mode'],
            MicrosysChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'icons': {
                        'icon': 'bi-layout-sidebar-inset',
                        'description': s.get('sidebar_collapse_icons_desc', 'Collapse to an icon rail on desktop.'),
                    },
                    'hidden': {
                        'icon': 'bi-eye-slash',
                        'description': s.get('sidebar_collapse_hidden_desc', 'Collapse to a fully hidden desktop sidebar.'),
                    },
                    'locked_expanded': {
                        'icon': 'bi-lock',
                        'description': s.get('sidebar_collapse_locked_expanded_desc', 'Disable desktop collapsing and keep the sidebar open.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_home_shape'],
            MicrosysChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'circle': {
                        'icon': 'bi-circle',
                        'description': s.get('titlebar_home_shape_circle_desc', 'Round button silhouette.'),
                    },
                    'square': {
                        'icon': 'bi-square',
                        'description': s.get('titlebar_home_shape_square_desc', 'Sharp square edges.'),
                    },
                    'squircle': {
                        'icon': 'bi-app-indicator',
                        'description': s.get('titlebar_home_shape_squircle_desc', 'Soft rounded square edges.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_title_align'],
            MicrosysChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'start': {
                        'icon': 'bi-text-left',
                        'description': s.get('titlebar_align_start_desc', 'Pin the title to the start side.'),
                    },
                    'center': {
                        'icon': 'bi-text-center',
                        'description': s.get('titlebar_align_center_desc', 'Keep the title visually centered.'),
                    },
                    'end': {
                        'icon': 'bi-text-right',
                        'description': s.get('titlebar_align_end_desc', 'Pin the title to the end side.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_title_size'],
            MicrosysChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'sm': {
                        'surface_label': 'S',
                        'description': s.get('titlebar_size_sm_desc', 'Compact title sizing.'),
                    },
                    'md': {
                        'surface_label': 'M',
                        'description': s.get('titlebar_size_md_desc', 'Balanced default title sizing.'),
                    },
                    'lg': {
                        'surface_label': 'L',
                        'description': s.get('titlebar_size_lg_desc', 'Larger, more prominent title sizing.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_height'],
            MicrosysChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'dense': {
                        'surface_label': 'D',
                        'description': s.get('titlebar_height_dense_desc', 'Tighter vertical titlebar spacing.'),
                    },
                    'balanced': {
                        'surface_label': 'B',
                        'description': s.get('titlebar_height_balanced_desc', 'Default titlebar spacing.'),
                    },
                    'roomy': {
                        'surface_label': 'R',
                        'description': s.get('titlebar_height_roomy_desc', 'More breathing room inside the titlebar.'),
                    },
                },
            ),
        )
        _bind_choice_selector_widget(
            self.fields['titlebar_surface'],
            MicrosysChoiceSelectorWidget(
                variant='toggle',
                option_meta={
                    'default': {
                        'surface_label': 'Df',
                        'description': s.get('titlebar_surface_default_desc', 'Standard titlebar surface styling.'),
                    },
                    'muted': {
                        'surface_label': 'Mu',
                        'description': s.get('titlebar_surface_muted_desc', 'Lower-contrast titlebar surface.'),
                    },
                    'glass': {
                        'surface_label': 'Gl',
                        'description': s.get('titlebar_surface_glass_desc', 'Blurred glass-style surface effect.'),
                    },
                },
            ),
        )
        project_config = getattr(settings, 'MICROSYS_CONFIG', {})
        if (not getattr(self.instance, 'is_configured', False)) and (not self.instance.name or self.instance.name in {'ادارة النظام', 'إدارة النظام'}):
             seeded_name_ar = project_config.get('name_ar', '')
             if seeded_name_ar in {'ادارة النظام', 'إدارة النظام'}:
                 seeded_name_ar = ''
             self.instance.name = seeded_name_ar
        self.initial['name'] = self.instance.name or ''
        if not self.instance.name_en:
             self.instance.name_en = project_config.get('name_en', '')
        self.initial['name_en'] = self.instance.name_en or ''
        if not self.instance.default_language:
             self.instance.default_language = config.get('default_language', 'en')
        self.initial['default_language'] = self.instance.default_language or config.get('default_language', 'en')
        if not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False):
            self.instance.default_theme = config.get('default_theme', 'light')
        elif not getattr(self.instance, 'default_theme', None):
            self.instance.default_theme = config.get('default_theme', 'light')
        self.initial['default_theme'] = self.instance.default_theme or config.get('default_theme', 'light')
        initial_allowed_themes = normalize_allowed_themes(
            (
                config.get('allowed_themes')
                if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
                else getattr(self.instance, 'allowed_themes', None)
            ) or config.get('allowed_themes')
        )
        self.initial['allowed_themes'] = list(initial_allowed_themes)
        self.initial['allow_user_theme_override'] = bool(
            config.get('allow_user_theme_override', True)
            if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
            else getattr(self.instance, 'allow_user_theme_override', config.get('allow_user_theme_override', True))
        )
        self.initial['allow_user_language_override'] = bool(
            config.get('allow_user_language_override', True)
            if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
            else getattr(self.instance, 'allow_user_language_override', config.get('allow_user_language_override', True))
        )
        if (
            not getattr(self.instance, 'pk', None)
            and not getattr(self.instance, 'is_configured', False)
        ) or getattr(self.instance, 'default_table_density', None) not in TABLE_DENSITY_VALUES:
            self.instance.default_table_density = config.get('default_table_density', DEFAULT_TABLE_DENSITY)
        self.initial['default_table_density'] = self.instance.default_table_density or config.get('default_table_density', DEFAULT_TABLE_DENSITY)
        instance_home_url = str(self.instance.home_url or '').strip()
        if (
            not getattr(self.instance, 'is_configured', False)
            and instance_home_url == LEGACY_HOME_URL
        ):
            instance_home_url = ''

        current_home_url = (
            instance_home_url
            or config.get('home_url', '')
            or project_config.get('home_url', '')
            or DEFAULT_HOME_URL
        )
        self.initial['home_url'] = current_home_url

        if self.instance and self.instance.pk:
            if isinstance(self.instance.languages, dict):
                self.initial['languages'] = _json_dump(self.instance.languages, ensure_ascii=False, indent=2)
            if isinstance(self.instance.translations_override, dict):
                self.initial['translations_override'] = _json_dump(self.instance.translations_override, ensure_ascii=False, indent=2)
        if isinstance(getattr(self.instance, 'sidebar_config', None), dict) and self.instance.sidebar_config:
            sidebar_config = sanitize_sidebar_config(self.instance.sidebar_config, allow_system_items=True)
            sidebar_config['home_url_name'] = None
            self.initial['sidebar_config'] = _json_dump(sidebar_config, ensure_ascii=False)
        initial_titlebar_config = normalize_titlebar_config(
            (
                config.get('titlebar', {})
                if (not getattr(self.instance, 'pk', None) and not getattr(self.instance, 'is_configured', False))
                else getattr(self.instance, 'titlebar_config', None)
            ) or config.get('titlebar', {})
        )

        if not self.initial.get('languages'):
            self.initial['languages'] = _json_dump(config.get('languages', {}), ensure_ascii=False, indent=2)
        if not self.initial.get('translations_override'):
            self.initial['translations_override'] = _json_dump(config.get('translations', {}), ensure_ascii=False, indent=2)
        if not self.initial.get('default_language'):
            self.initial['default_language'] = config.get('default_language', 'en')
        if not self.initial.get('default_theme'):
            self.initial['default_theme'] = config.get('default_theme', 'light')
        if not self.initial.get('allowed_themes'):
            self.initial['allowed_themes'] = list(normalize_allowed_themes(config.get('allowed_themes')))
        if self.initial.get('default_table_density') not in TABLE_DENSITY_VALUES:
            self.initial['default_table_density'] = config.get('default_table_density', DEFAULT_TABLE_DENSITY)
        self.initial['email_2fa'] = bool(
            getattr(self.instance, 'email_2fa', False)
            or config.get('email_2fa', False)
        )
        self.initial['public_root'] = bool(
            getattr(self.instance, 'public_root', False)
            or config.get('public_root', False)
        )
        self.fields['name'].widget.attrs['placeholder'] = ''

        if not self.initial.get('sidebar_config'):
            sidebar_config = sanitize_sidebar_config(config.get('sidebar', {}), allow_system_items=True)
            if not isinstance(sidebar_config, dict):
                sidebar_config = normalize_sidebar_behavior({
                    'home_url_name': None,
                    'entries': [],
                })
            sidebar_config.setdefault('entries', [])
            sidebar_config = normalize_sidebar_behavior(sidebar_config)
            sidebar_config['home_url_name'] = None
            self.initial['sidebar_config'] = _json_dump(sidebar_config, ensure_ascii=False)

        try:
            initial_sidebar_config = json.loads(self.initial.get('sidebar_config') or '{}')
        except (TypeError, ValueError):
            initial_sidebar_config = {}
        if not isinstance(initial_sidebar_config, dict):
            initial_sidebar_config = {}

        self.initial['sidebar_enable_reorder'] = bool(initial_sidebar_config.get('enable_reorder', True))
        self.initial['sidebar_enable_toolbar'] = bool(initial_sidebar_config.get('show_toolbar', True))
        self.initial['sidebar_show_icons'] = bool(initial_sidebar_config.get('show_icons', True))
        self.initial['sidebar_density'] = initial_sidebar_config.get('density', DEFAULT_SIDEBAR_DENSITY)
        self.initial['sidebar_allow_user_density'] = bool(initial_sidebar_config.get('allow_user_density', True))
        self.initial['sidebar_collapse_mode'] = initial_sidebar_config.get('collapse_mode', DEFAULT_SIDEBAR_COLLAPSE_MODE)
        self.initial['titlebar_show_title'] = bool(initial_titlebar_config.get('show_title', True))
        self.initial['titlebar_show_logo'] = bool(initial_titlebar_config.get('show_logo', True))
        self.initial['titlebar_show_home_button'] = bool(initial_titlebar_config.get('show_home_button', True))
        self.initial['titlebar_home_shape'] = initial_titlebar_config.get('home_shape', 'circle')
        self.initial['titlebar_title_align'] = initial_titlebar_config.get('title_align', 'start')
        self.initial['titlebar_title_size'] = initial_titlebar_config.get('title_size', 'md')
        self.initial['titlebar_height'] = initial_titlebar_config.get('height', 'balanced')
        self.initial['titlebar_surface'] = initial_titlebar_config.get('surface', 'default')

        catalog_lang = self.initial.get('default_language') or self.instance.default_language or config.get('default_language', 'en')
        public_sidebar_catalog = discover_sidebar_catalog(lang_code=catalog_lang, include_system_items=False)
        self.sidebar_catalog = discover_sidebar_catalog(lang_code=catalog_lang, include_system_items=True)
        self.sidebar_catalog_fallback = discover_sidebar_catalog(lang_code='en', include_system_items=True)
        seen_home_urls = set()
        home_url_choices = [('', s.get('form_sys_home_url_custom', 'Use a custom URL'))]
        home_url_option_meta = {
            '': {
                'description': s.get('home_url_custom_desc', 'Keep a custom titlebar home URL instead of a discovered page.'),
            }
        }
        for entry in public_sidebar_catalog:
            url_name = entry.get('url_name')
            if not url_name:
                continue
            try:
                resolved_url = reverse(url_name)
            except NoReverseMatch:
                continue
            if resolved_url in seen_home_urls:
                continue
            seen_home_urls.add(resolved_url)
            entry_label = str(entry.get('label') or entry.get('group_label') or url_name).strip()
            home_url_choices.append((resolved_url, entry_label))
            home_url_option_meta[resolved_url] = {
                'description': str(entry.get('group_label') or '').strip(),
                'secondary': url_name,
                'search_text': f"{entry_label} {url_name} {resolved_url}",
            }
        self.fields['home_url_discovered'].choices = home_url_choices
        self.fields['home_url_discovered'].widget.option_meta = home_url_option_meta
        self.initial['home_url_discovered'] = current_home_url if current_home_url in seen_home_urls else ''

        self.language_picker_html = render_to_string(
            'microsys/includes/language_previews.html',
            {
                'selected_language': self.initial.get('default_language', 'en'),
                'picker_mode': 'setup',
                'input_id': 'id_default_language',
                'MS_TRANS': s,
                'languages': current_languages,
                'label': self.fields['default_language'].label,
            },
        )

        self.theme_picker_html = render_to_string(
            'microsys/includes/theme_settings_matrix.html',
            {
                'selected_theme': self.initial.get('default_theme', 'light'),
                'picker_mode': 'setup',
                'input_id': 'id_default_theme',
                'allowed_input_name': 'allowed_themes',
                'allowed_themes': set(self.initial.get('allowed_themes', [])),
                'MS_TRANS': s,
                'MICROSYS_THEMES': get_theme_options(s),
                'label': self.fields['default_theme'].label,
                'help_text': self.fields['allowed_themes'].help_text,
            },
        )

        self.sidebar_builder_html = render_to_string(
            'microsys/includes/sidebar_builder.html',
            {
                'sidebar_catalog': self.sidebar_catalog,
                'sidebar_catalog_json': _json_dump(self.sidebar_catalog, ensure_ascii=False),
                'sidebar_catalog_fallback_json': _json_dump(self.sidebar_catalog_fallback, ensure_ascii=False),
                'sidebar_config_json': self.initial.get('sidebar_config', '{}'),
                'mode': self.mode,
                'MS_TRANS': s,
            },
        )

        modal_desc = s.get('system_settings_modal_desc', 'حدّث العلامة التجارية واللغات والشريط الجانبي من نافذة الإعدادات.')
        intro_html = ''
        if self.mode != 'setup':
            intro_html = (
                f"<div class='ms-system-settings-intro mb-4'>"
                f"<p class='text-muted mb-0'>{modal_desc}</p>"
                f"</div>"
            )

        self.helper = FormHelper()
        self.helper.form_tag = False

        def _step_style(index):
            if self.single_step_mode and self.single_step_index != index:
                return 'display: none;'
            if not self.single_step_mode and index > 0:
                return 'display: none;'
            return None

        self.helper.layout = Layout(
            HTML(
                (
                    f"<div class='ms-system-settings-shell mode-{self.mode}'>"
                    f"{intro_html}"
                )
            ),
            Div(
                HTML(f"<div class='mb-3'><span class='badge rounded-pill text-bg-primary'>{s.get('system_setup_step1', 'الخطوة 1')}</span></div>"),
                Row(
                    Div(Field('name', css_class='col-md-6'), css_class='col-md-6'),
                    Div(Field('name_en', css_class='col-md-6'), css_class='col-md-6'),
                ),
                Row(
                    Div(Field('logo', css_class='col-md-6'), css_class='col-md-6'),
                    Div(Field('favicon', css_class='col-md-6'), css_class='col-md-6'),
                    css_class='row'
                ),
                Row(
                    Div(
                        HTML(self.language_picker_html),
                        Field('default_language'),
                        css_class='col-lg-6'
                    ),
                    Div(
                        HTML(self.theme_picker_html),
                        Field('default_theme'),
                        css_class='col-lg-6'
                    ),
                ),
                Row(
                    Div(Field('allow_user_theme_override'), css_class='col-lg-6'),
                    Div(Field('home_url_discovered'), css_class='col-lg-6'),
                ),
                Row(
                    Div(Field('home_url', dir='ltr'), css_class='col-lg-6'),
                    Div(Field('email_2fa'), css_class='col-lg-6'),
                ),
                Row(
                    Div(Field('public_root'), css_class='col-lg-6'),
                ),
                css_class='wizard-step',
                style=_step_style(0),
            ),
            Div(
                HTML(f"<div class='mb-3'><span class='badge rounded-pill text-bg-primary'>{s.get('system_setup_step2', 'الخطوة 2')}</span></div>"),
                Row(
                    Div(Field('allow_user_language_override'), css_class='col-lg-6'),
                ),
                Row(Field('languages', css_class='col-12 font-monospace', dir='ltr')),
                Row(Field('translations_override', css_class='col-12 font-monospace', dir='ltr')),
                css_class='wizard-step',
                style=_step_style(1),
            ),
            Div(
                HTML(f"<div class='mb-3'><span class='badge rounded-pill text-bg-primary'>{s.get('system_setup_step3', 'الخطوة 3')}</span></div>"),
                HTML(
                    f"<div class='d-none' data-sidebar-tooling-state "
                    f"data-sections-manager-available=\"{'true' if self.sidebar_sections_manager_available else 'false'}\"></div>"
                ),
                Row(
                    Div(Field('sidebar_enable_reorder'), css_class='col-lg-6'),
                    Div(Field('sidebar_enable_toolbar'), css_class='col-lg-6'),
                ),
                Row(
                    Div(Field('sidebar_show_icons'), css_class='col-lg-6'),
                    Div(Field('sidebar_allow_user_density'), css_class='col-lg-6'),
                ),
                Row(
                    Div(Field('sidebar_density'), css_class='col-lg-6'),
                    Div(Field('sidebar_collapse_mode'), css_class='col-lg-6'),
                ),
                HTML(
                    f"<div class='alert alert-warning small mb-3{' d-none' if self.initial.get('sidebar_enable_toolbar', True) else ''}' "
                    f"data-sidebar-toolbar-note>"
                    f"{s.get('sidebar_toolbar_disable_note', 'Disabling the sidebar toolbar also removes the only built-in shortcut to Dynamic Sections Manager. If you still want UI access, enable system items in the sidebar builder and add Section Management to your sidebar.')}"
                    f"</div>"
                ),
                HTML(self.sidebar_builder_html),
                Field('sidebar_config'),
                css_class='wizard-step',
                style=_step_style(2),
            ),
            Div(
                HTML(f"<div class='mb-3'><span class='badge rounded-pill text-bg-primary'>{s.get('system_setup_step4', 'الخطوة 4')}</span></div>"),
                Row(
                    Div(Field('default_table_density'), css_class='col-lg-6'),
                ),
                HTML(f"<h6 class='fw-bold mb-3'>{s.get('titlebar_settings_title', 'إعدادات شريط العنوان')}</h6>"),
                Row(
                    Div(Field('titlebar_show_title'), css_class='col-lg-4'),
                    Div(Field('titlebar_show_logo'), css_class='col-lg-4'),
                    Div(Field('titlebar_show_home_button'), css_class='col-lg-4'),
                ),
                Row(
                    Div(Field('titlebar_title_align'), css_class='col-lg-6'),
                    Div(Field('titlebar_title_size'), css_class='col-lg-6'),
                ),
                Row(
                    Div(Field('titlebar_home_shape'), css_class='col-lg-6'),
                    Div(Field('titlebar_height'), css_class='col-lg-6'),
                ),
                Row(
                    Div(Field('titlebar_surface'), css_class='col-lg-12'),
                ),
                css_class='wizard-step',
                style=_step_style(3),
            ),
            FormActions(
                Submit(
                    'submit',
                    s.get('btn_save', 'حفظ التعديلات'),
                    css_class='btn btn-primary px-5 rounded-pill fw-bold ms-btn-submit'
                ),
                css_class=(
                    'd-flex justify-content-end align-items-center gap-2 mt-4'
                    if self.single_step_mode
                    else 'd-flex justify-content-between align-items-center gap-2 mt-4'
                ),
            ) if self.single_step_mode else FormActions(
                HTML(
                    f"<button type='button' class='btn btn-outline-secondary rounded-pill px-4 ms-btn-prev'>"
                    f"{s.get('btn_prev', 'السابق')}</button>"
                ),
                HTML(
                    f"<button type='button' class='btn btn-outline-primary rounded-pill px-4 ms-btn-next'>"
                    f"{s.get('btn_next', 'التالي')}</button>"
                ),
                Submit(
                    'submit',
                    s.get('btn_save', 'حفظ التعديلات'),
                    css_class='btn btn-primary px-5 rounded-pill fw-bold ms-btn-submit'
                ),
                css_class='d-flex justify-content-between align-items-center gap-2 mt-4',
            ),
            HTML("</div>")
        )

    def clean_languages(self):
        data = self.cleaned_data.get('languages')
        if not data:
            return {}
        try:
            parsed = json.loads(data)
            if not isinstance(parsed, dict):
                raise ValidationError("Must be a valid JSON dictionary.")
            return parsed
        except json.JSONDecodeError:
            raise ValidationError("Invalid JSON format.")

    def clean_translations_override(self):
        data = self.cleaned_data.get('translations_override')
        if not data:
            return {}
        try:
            parsed = json.loads(data)
            if not isinstance(parsed, dict):
                raise ValidationError("Must be a valid JSON dictionary.")
            return parsed
        except json.JSONDecodeError:
            raise ValidationError("Invalid JSON format.")

    def clean_default_theme(self):
        value = self.cleaned_data.get('default_theme') or 'light'
        if not is_valid_theme(value):
            raise ValidationError("Invalid theme choice.")
        return value

    def clean_allowed_themes(self):
        values = self.cleaned_data.get('allowed_themes') or []
        if not values:
            raise ValidationError("At least one theme must remain enabled.")
        normalized = list(normalize_allowed_themes(values))
        if not normalized:
            raise ValidationError("At least one theme must remain enabled.")
        return normalized

    def clean_default_table_density(self):
        value = self.cleaned_data.get('default_table_density') or DEFAULT_TABLE_DENSITY
        if value not in TABLE_DENSITY_VALUES:
            raise ValidationError("Invalid table density choice.")
        return value

    def clean_sidebar_density(self):
        value = self.cleaned_data.get('sidebar_density') or DEFAULT_SIDEBAR_DENSITY
        if value not in SIDEBAR_DENSITY_VALUES:
            raise ValidationError("Invalid sidebar density choice.")
        return value

    def clean_sidebar_collapse_mode(self):
        value = self.cleaned_data.get('sidebar_collapse_mode') or DEFAULT_SIDEBAR_COLLAPSE_MODE
        if value not in SIDEBAR_COLLAPSE_MODE_VALUES:
            raise ValidationError("Invalid sidebar collapse mode.")
        return value

    def clean_titlebar_home_shape(self):
        value = self.cleaned_data.get('titlebar_home_shape') or 'circle'
        if value not in TITLEBAR_HOME_SHAPE_VALUES:
            raise ValidationError("Invalid titlebar home shape.")
        return value

    def clean_titlebar_title_align(self):
        value = self.cleaned_data.get('titlebar_title_align') or 'start'
        if value not in TITLEBAR_ALIGN_VALUES:
            raise ValidationError("Invalid title alignment.")
        return value

    def clean_titlebar_title_size(self):
        value = self.cleaned_data.get('titlebar_title_size') or 'md'
        if value not in TITLEBAR_SIZE_VALUES:
            raise ValidationError("Invalid title size.")
        return value

    def clean_titlebar_height(self):
        value = self.cleaned_data.get('titlebar_height') or 'balanced'
        if value not in TITLEBAR_HEIGHT_VALUES:
            raise ValidationError("Invalid titlebar height.")
        return value

    def clean_titlebar_surface(self):
        value = self.cleaned_data.get('titlebar_surface') or 'default'
        if value not in TITLEBAR_SURFACE_VALUES:
            raise ValidationError("Invalid titlebar surface.")
        return value

    def clean_home_url(self):
        value = str(self.cleaned_data.get('home_url') or '').strip()
        discovered_value = str(self.cleaned_data.get('home_url_discovered') or '').strip()
        return value or discovered_value or getattr(settings, 'MICROSYS_CONFIG', {}).get('home_url') or DEFAULT_HOME_URL

    def clean_sidebar_config(self):
        from microsys.discovery import sanitize_sidebar_config

        data = self.cleaned_data.get('sidebar_config')
        if not data:
            return {'home_url_name': None, 'entries': []}
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            raise ValidationError("Invalid sidebar JSON format.")
        if not isinstance(parsed, dict):
            raise ValidationError("Sidebar configuration must be a valid JSON object.")
        entries = parsed.get('entries', [])
        if not isinstance(entries, list):
            raise ValidationError("Sidebar entries must be a list.")
        return sanitize_sidebar_config({
            'home_url_name': None,
            'entries': entries,
        }, allow_system_items=True)

    def clean(self):
        cleaned = super().clean()
        allowed_themes = cleaned.get('allowed_themes') or []
        default_theme = cleaned.get('default_theme') or 'light'
        if allowed_themes and default_theme not in allowed_themes:
            self.add_error('default_theme', "Default theme must remain allowed.")

        sidebar = cleaned.get('sidebar_config')
        if isinstance(sidebar, dict):
            sidebar['enable_reorder'] = bool(cleaned.get('sidebar_enable_reorder', True))
            sidebar['show_toolbar'] = bool(cleaned.get('sidebar_enable_toolbar', True))
            sidebar['show_icons'] = bool(cleaned.get('sidebar_show_icons', True))
            sidebar['density'] = cleaned.get('sidebar_density', DEFAULT_SIDEBAR_DENSITY)
            sidebar['allow_user_density'] = bool(cleaned.get('sidebar_allow_user_density', True))
            sidebar['collapse_mode'] = cleaned.get('sidebar_collapse_mode', DEFAULT_SIDEBAR_COLLAPSE_MODE)
            if not _system_settings_sidebar_tools_available(cleaned):
                sidebar['show_toolbar'] = False
                cleaned['sidebar_enable_toolbar'] = False
            sidebar = normalize_sidebar_behavior(sidebar)
            cleaned['sidebar_config'] = sidebar
            cleaned['sidebar_collapse_mode'] = sidebar.get('collapse_mode', DEFAULT_SIDEBAR_COLLAPSE_MODE)
        cleaned['titlebar_config'] = normalize_titlebar_config({
            'show_title': bool(cleaned.get('titlebar_show_title', True)),
            'show_logo': bool(cleaned.get('titlebar_show_logo', True)),
            'show_home_button': bool(cleaned.get('titlebar_show_home_button', True)),
            'home_shape': cleaned.get('titlebar_home_shape', 'circle'),
            'title_align': cleaned.get('titlebar_title_align', 'start'),
            'title_size': cleaned.get('titlebar_title_size', 'md'),
            'height': cleaned.get('titlebar_height', 'balanced'),
            'surface': cleaned.get('titlebar_surface', 'default'),
        })
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.is_configured = True
        instance.sidebar_config = self.cleaned_data.get('sidebar_config', {'home_url_name': None, 'entries': []})
        instance.allowed_themes = self.cleaned_data.get('allowed_themes', list(normalize_allowed_themes()))
        instance.allow_user_theme_override = bool(self.cleaned_data.get('allow_user_theme_override', True))
        instance.allow_user_language_override = bool(self.cleaned_data.get('allow_user_language_override', True))
        instance.titlebar_config = self.cleaned_data.get('titlebar_config', default_titlebar_config())
        fallback_home = getattr(settings, 'MICROSYS_CONFIG', {}).get('home_url') or DEFAULT_HOME_URL
        instance.home_url = self.cleaned_data.get('home_url') or fallback_home
        if isinstance(instance.sidebar_config, dict):
            instance.sidebar_config['home_url_name'] = None

        if commit:
            instance.save()
        return instance
