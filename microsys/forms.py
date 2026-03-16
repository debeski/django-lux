# Imports of the required python modules and libraries
######################################################
from django import forms
from django.contrib.auth.models import Permission as Permissions
from django.contrib.auth.forms import UserCreationForm, UserChangeForm, PasswordChangeForm, SetPasswordForm
from django.contrib.auth import get_user_model
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Div, HTML, Submit, Row
from crispy_forms.bootstrap import FormActions
from PIL import Image
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from django.db.models import Q
from django.apps import apps
from django.forms.widgets import ChoiceWidget
from django.conf import settings
from .translations import get_strings

User = get_user_model()




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

class ProfileImageWidget(forms.ClearableFileInput):
    template_name = 'microsys/widgets/profile_image_widget.html'

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

        actions = FormActions(
            HTML(
                f"""
                <button type="button" class="btn btn-secondary rounded-pill ms-btn-prev" style="display: none;">
                    <i class="bi bi-arrow-right-circle text-light me-1 h4"></i> {s.get('btn_prev', 'السابق')}
                </button>
                <button type="button" class="btn btn-primary rounded-pill ms-btn-next">
                    {s.get('btn_next', 'التالي')} <i class="bi bi-arrow-left-circle text-light ms-1 h4"></i>
                </button>
                <button type="submit" class="btn btn-success rounded-pill ms-btn-submit" style="display: none;">
                    <i class="bi bi-person-plus-fill text-light me-1 h4"></i>
                    {s.get('btn_add', 'إضافة')}
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
            else:
                profile.scope = self.cleaned_data.get('scope')
            profile.save()
            
        return user


# Custom User Editing form layout
class CustomUserChangeForm(UserChangeForm):
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
        fields = ["username", "first_name", "last_name", "email", "is_staff", "permissions", "is_active"]

    def __init__(self, *args, **kwargs):
        self.user_context = kwargs.pop('user', None)
        user_instance = kwargs.get('instance')
        super().__init__(*args, **kwargs)
        
        Scope = apps.get_model('microsys', 'Scope')
        self.fields['scope'].queryset = Scope.objects.all()

        # Permission check
        if self.user_context and not self.user_context.is_superuser:
            user_perms = self.user_context.user_permissions.all() | Permissions.objects.filter(group__user=self.user_context)
            self.fields['permissions'].queryset = self.fields['permissions'].queryset.filter(id__in=user_perms.values_list('id', flat=True))

        # Initialize Profile Fields
        if user_instance and hasattr(user_instance, 'profile'):
            self.fields['phone'].initial = user_instance.profile.phone
            self.fields['scope'].initial = user_instance.profile.scope

        # Labels
        s = get_strings()
        self.fields['permissions'].widget.translations = s

        self.fields["username"].label = s.get('form_username', "اسم المستخدم")
        self.fields["email"].label = s.get('form_email', "البريد الإلكتروني")
        self.fields["first_name"].label = s.get('form_firstname', "الاسم الاول")
        self.fields["last_name"].label = s.get('form_lastname', "اللقب")
        self.fields["is_staff"].label = s.get('form_is_staff', "صلاحيات انشاء و تعديل المستخدمين")
        self.fields["is_active"].label = s.get('form_is_active', "الحساب مفعل")
        self.fields["phone"].label = s.get('form_phone', "رقم الهاتف")
        self.fields["scope"].label = s.get('form_scope', "النطاق")
        self.fields["permissions"].label = s.get('form_permissions', "الصلاحيات")
        
        # Help Texts
        # Help Texts
        self.fields["username"].help_text = s.get('help_username', "اسم المستخدم يجب أن يكون فريدًا...")
        self.fields["email"].help_text = s.get('help_email', "أدخل عنوان البريد الإلكتروني الصحيح (اختياري)")
        self.fields["is_active"].help_text = s.get('help_is_active', "يحدد ما إذا كان يجب اعتبار هذا الحساب نشطًا.")
        self.fields["is_staff"].help_text = s.get('help_is_staff', "يحدد ما إذا كان يمكن للمستخدم عرض وادارة المستخدمين.")
        self.fields["phone"].help_text = s.get('help_phone', "أدخل رقم الهاتف الصحيح...")
        self.fields["scope"].help_text = ""

        if user_instance:
            self.fields["permissions"].initial = user_instance.user_permissions.all()

        lock_scope = bool(
            self.user_context
            and not self.user_context.is_superuser
            and hasattr(self.user_context, 'profile')
            and self.user_context.profile.scope
        )

        # --- Foolproofing & Role-based logic ---
        if self.user_context and not self.user_context.is_superuser:
            # 1. Self-Editing Protection
            if self.user_context == user_instance:
                if self.user_context.is_staff:
                    self.fields['scope'].disabled = True
                    self.fields['is_staff'].disabled = True
                    self.fields['is_active'].disabled = True
                    self.fields['scope'].help_text = s.get('help_scope_self', "لا يمكنك تغيير نطاقك الخاص لمنع تجريد نفسك من صلاحيات المدير العام.")
                    self.fields['permissions'].queryset = self.fields['permissions'].queryset.exclude(codename='manage_staff')
            
        # 2. Scope Manager Restrictions
        if lock_scope:
             # Already handled above by general lock_scope check, but we need to ensure permissions are filtered
             self.fields['permissions'].queryset = self.fields['permissions'].queryset.exclude(codename='manage_staff')

        self.fields["email"].required = False

        # --- can_manage_staff logic ---
        if self.user_context and not self.user_context.is_superuser:
            if not self.user_context.has_perm('microsys.manage_staff'):
                self.fields['is_staff'].disabled = True
                self.fields['is_staff'].help_text = s.get('help_is_staff_no_perm', "ليس لديك صلاحية لتغيير وضع هذا المستخدم لمسؤول .")

        _attach_is_staff_permission(self, self.fields['permissions'].widget.attrs.get('id'))

        self.helper = FormHelper()
        self.helper.form_tag = False
        
        from microsys.utils import is_scope_enabled
        scope_visible = 'scope' in self.fields and getattr(self.fields['scope'].widget, 'input_type', '') != 'hidden' and is_scope_enabled()
        
        step_1_fields = [
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
            step_1_fields.append(Row(Field("scope", css_class="form-control")))
            
        step_1_div = Div(*step_1_fields, css_class="wizard-step wizard-step-1")
        
        step_2_fields = [
            HTML("<hr>"),
            Field("permissions", css_class="col-12")
        ]
        step_2_div = Div(*step_2_fields, css_class="wizard-step wizard-step-2", style="display: none;")

        actions = FormActions(
            HTML(
                f"""
                <button type="button" class="btn btn-secondary rounded-pill ms-btn-prev" style="display: none;">
                    <i class="bi bi-arrow-right-circle text-light me-1 h4"></i> {s.get('btn_prev', 'السابق')}
                </button>
                <button type="button" class="btn btn-primary rounded-pill ms-btn-next">
                    {s.get('btn_next', 'التالي')} <i class="bi bi-arrow-left-circle text-light ms-1 h4"></i>
                </button>
                <button type="submit" class="btn btn-success rounded-pill ms-btn-submit" style="display: none;">
                    <i class="bi bi-person-check-fill text-light me-1 h4"></i>
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
        
        self.helper.layout = Layout(step_1_div, step_2_div, actions)

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            user.user_permissions.set(self.cleaned_data["permissions"])
            
            # Save Profile fields
            Profile = apps.get_model('microsys', 'Profile')
            profile, created = Profile.all_objects.get_or_create(user=user)
            profile.phone = self.cleaned_data.get('phone')
            if self.user_context and not self.user_context.is_superuser and hasattr(self.user_context, 'profile') and self.user_context.profile.scope:
                profile.scope = self.user_context.profile.scope
            else:
                profile.scope = self.cleaned_data.get('scope')
            profile.save()
            
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
    languages = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
    )
    translations_override = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
    )

    class Meta:
        model = apps.get_model('microsys', 'SystemSettings')
        fields = ['name', 'name_en', 'logo', 'favicon', 'default_language', 'languages', 'translations_override']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        self._user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Determine language context from user or request
        user = self._user or (self.request.user if self.request else None)
        s = get_strings()
        
        # Support passing translations directly via kwargs in Dynamic Modal
        if hasattr(self, 'translations') and self.translations:
            s = self.translations

        
        # Languages and Translations Override
        self.fields['languages'].label = s.get('form_sys_languages', "اللغات المتوفرة (JSON)")
        self.fields['languages'].help_text = s.get('help_sys_languages', 'مثال: {"ar": "العربية", "en": "English"}')
        
        self.fields['translations_override'].label = s.get('form_sys_translations', "تجاوز الترجمات (JSON)")
        self.fields['translations_override'].help_text = s.get('help_sys_translations', 'مثال: {"ar": {"app_microsys": "النظام"}}')
        
        self.fields['name'].label = s.get('form_sys_name_ar', "اسم النظام (عربي)")
        self.fields['name_en'].label = s.get('form_sys_name_en', "اسم النظام (إنجليزي)")
        self.fields['default_language'].label = s.get('form_sys_default_lang', "اللغة الافتراضية")
        self.fields['logo'].label = s.get('form_sys_logo', "الشعار (Logo)")
        self.fields['favicon'].label = s.get('form_sys_favicon', "أيقونة الموقع (Favicon)")

        # Seed instance fields from config if not yet customized
        from django.conf import settings
        config = getattr(settings, 'MICROSYS_CONFIG', {})
        if not self.instance.name or self.instance.name == 'ادارة النظام':
             self.instance.name = config.get('name_ar', config.get('name', 'ادارة النظام'))
        if not self.instance.name_en:
             self.instance.name_en = config.get('name_en', '')
        if not self.instance.default_language or self.instance.default_language == 'ar':
             self.instance.default_language = config.get('default_language', 'ar')

        # Convert JSON to string for textarea
        if self.instance and self.instance.pk:
            import json
            if isinstance(self.instance.languages, dict):
                self.initial['languages'] = json.dumps(self.instance.languages, ensure_ascii=False, indent=2)
            if isinstance(self.instance.translations_override, dict):
                self.initial['translations_override'] = json.dumps(self.instance.translations_override, ensure_ascii=False, indent=2)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Div(Field('name', css_class='col-md-6'), css_class='col-md-6'),
                Div(Field('name_en', css_class='col-md-6'), css_class='col-md-6'),
            ),
            Row(
                Div(Field('logo', css_class='col-md-6'), css_class='col-md-6'),
                Div(Field('favicon', css_class='col-md-6'), css_class='col-md-6'),
                css_class='row'
            ),
            Row(Field('default_language', css_class='col-12')),
            HTML("<hr>"),
            Row(Field('languages', css_class='col-12 font-monospace', dir='ltr')),
            Row(Field('translations_override', css_class='col-12 font-monospace', dir='ltr')),
            HTML("<hr>"),
            Div(
                Submit('submit', s.get('btn_save', 'حفظ التعديلات'), css_class='btn btn-primary px-5 rounded-pill fw-bold'),
                css_class='text-center mt-4 mb-2'
            )
        )

    def clean_languages(self):
        data = self.cleaned_data.get('languages')
        if not data:
            return {}
        import json
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
        import json
        try:
            parsed = json.loads(data)
            if not isinstance(parsed, dict):
                raise ValidationError("Must be a valid JSON dictionary.")
            return parsed
        except json.JSONDecodeError:
            raise ValidationError("Invalid JSON format.")

