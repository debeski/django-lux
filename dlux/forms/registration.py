"""Public self-registration form."""

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class PublicRegistrationForm(forms.Form):
    email = forms.EmailField(
        label=_("Email"),
        max_length=254,
        widget=forms.EmailInput(attrs={'autocomplete': 'email'}),
    )
    password1 = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    password2 = forms.CharField(
        label=_("Confirm password"),
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    first_name = forms.CharField(
        label=_("First name"),
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={'autocomplete': 'given-name'}),
    )
    last_name = forms.CharField(
        label=_("Last name"),
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={'autocomplete': 'family-name'}),
    )
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'autocomplete': 'off', 'tabindex': '-1'}),
    )
    # Optional agreement checkbox; made required per-request when the operator
    # enables `registration_require_consent`. The label + policy links are
    # rendered in the template (register.html), not here.
    consent = forms.BooleanField(required=False)

    def __init__(self, *args, require_consent=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.require_consent = bool(require_consent)

    def clean_email(self):
        return str(self.cleaned_data['email']).strip().lower()

    def clean_consent(self):
        agreed = bool(self.cleaned_data.get('consent'))
        if self.require_consent and not agreed:
            raise ValidationError(_("You must agree to continue."))
        return agreed

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get('password1')
        password2 = cleaned.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', _("The two password fields did not match."))
        if password1:
            validate_password(password1)
        return cleaned
