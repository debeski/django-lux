"""Authentication, password reset and password change forms."""

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordForm
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Div, Submit
from django.core.exceptions import ValidationError
from ..translations import get_strings
from ..utils import get_system_config

from ._shared import User
from .builders import build_settings_toggle_field


class DluxAuthenticationForm(AuthenticationForm):
    """
    Preserve normal username login while allowing verified public-registration
    projects to accept email in the username field.
    """

    def clean(self):
        raw_username = self.cleaned_data.get('username')
        if raw_username and '@' in raw_username:
            from ..auth.registration import public_registration_config

            if public_registration_config().get('enabled'):
                match = User._default_manager.filter(email__iexact=str(raw_username).strip()).first()
                if match:
                    self.cleaned_data['username'] = match.get_username()
        return super().clean()


def _apply_autocomplete_attrs(form, mapping):
    for field_name, autocomplete in mapping.items():
        field = form.fields.get(field_name)
        if field is None or not autocomplete:
            continue
        field.widget.attrs['autocomplete'] = autocomplete


class DluxPasswordMustChangeMixin:
    unchanged_password_error_code = 'password_unchanged'

    def clean(self):
        cleaned_data = super().clean()
        password = self.cleaned_data.get('new_password2')
        user = getattr(self, 'user', None)
        if password and user is not None and user.check_password(password):
            s = get_strings()
            self.add_error(
                'new_password2',
                ValidationError(
                    s.get('err_password_unchanged', 'New password must be different from the current password.'),
                    code=self.unchanged_password_error_code,
                ),
            )
        return cleaned_data


class ResetPasswordForm(DluxPasswordMustChangeMixin, SetPasswordForm):
    username = forms.CharField(label="Username", widget=forms.TextInput(attrs={"readonly": "readonly"}))

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        s = get_strings()
        self.fields['username'].initial = user.username
        self.fields['username'].label = s.get('form_username', "Username")
        
        self.helper = FormHelper()
        self.fields["new_password1"].label = s.get('form_new_password', "New Password")
        # Live password-rules card replaces the static requirement bullets.
        self.fields['new_password1'].help_text = ''

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


class CustomPasswordChangeForm(DluxPasswordMustChangeMixin, PasswordChangeForm):
    sign_out_other_sessions = forms.BooleanField(required=False, initial=False)

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        from dlux.utils import get_system_config

        s = get_strings()
        
        # Current Password
        self.fields['old_password'].label = s.get('form_old_password', "Current Password")
        self.fields['old_password'].widget.attrs.pop('dir', None) # Remove fixed RTL 
        
        # New Password 1
        self.fields['new_password1'].label = s.get('form_new_password', "New Password")
        # Live password-rules card replaces the static requirement bullets.
        self.fields['new_password1'].help_text = ''
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

        self.helper = FormHelper()
        self.helper.form_tag = False
        layout_fields = ['old_password', 'new_password1', 'new_password2']
        if get_system_config().get('prevent_multiple_active_sessions', False):
            self.fields.pop('sign_out_other_sessions', None)
        else:
            self.fields['sign_out_other_sessions'].label = s.get(
                'form_sign_out_other_sessions',
                'Sign out of all other signed-in devices',
            )
            self.fields['sign_out_other_sessions'].help_text = s.get(
                'help_sign_out_other_sessions',
                'Keep this device signed in and end every other active session after your password changes.',
            )
            layout_fields.append(build_settings_toggle_field(self, 'sign_out_other_sessions'))
        self.helper.layout = Layout(*layout_fields)
