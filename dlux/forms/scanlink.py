"""Publish form for ScanLink installers.

The uploaded file becomes a protected `ManagedAsset` (kind `installer`), so the
SHA-256 the manifest advertises is the one computed from the stored bytes rather
than anything typed in. Operators provide the release metadata and active state.
"""
import re

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, Layout, Row
from django import forms

from ..assets import create_managed_asset
from ..models import ManagedAsset, ScanLinkRelease
from ..translations import get_strings
from ..widgets import DluxChoiceSelectorWidget
from .builders import (
    _bind_choice_selector_widget,
    _build_file_widget,
    build_file_field,
    build_settings_toggle_field,
)

VERSION_RE = re.compile(r'^\d+(\.\d+){0,3}$')


def _s():
    try:
        return get_strings()
    except Exception:
        return {}


class ScanLinkReleaseForm(forms.ModelForm):
    installer = forms.FileField(required=True)

    class Meta:
        model = ScanLinkRelease
        fields = ('version', 'arch', 'is_active', 'notes')

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user
        s = _s()
        self.fields['version'].label = s.get('scanlink_field_version', 'Version')
        self.fields['version'].help_text = s.get(
            'scanlink_field_version_help', 'Dotted version, for example 0.7.2.')
        self.fields['arch'].label = s.get('scanlink_field_arch', 'Architecture')
        self.fields['is_active'].label = s.get('scanlink_field_is_active', 'Advertise this release')
        self.fields['notes'].label = s.get('scanlink_field_notes', 'Notes')
        self.fields['installer'].label = s.get('scanlink_field_installer', 'Installer')
        self.fields['installer'].help_text = s.get(
            'scanlink_field_installer_help', 'The Windows .exe the workstations download.')

        self.fields['version'].widget.attrs.update({
            'class': 'form-control glass-input',
            'dir': 'ltr',
        })
        self.fields['notes'].widget.attrs.update({
            'class': 'form-control glass-input',
            'dir': 'auto',
        })
        self.fields['installer'].widget = _build_file_widget(
            field_label=self.fields['installer'].label,
            attrs={'accept': '.exe'},
        )
        _bind_choice_selector_widget(
            self.fields['arch'],
            DluxChoiceSelectorWidget(
                variant='chip',
                attrs={'class': 'dlux-scanlink-arch-selector'},
            ),
        )

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Div(
                    Field('version'),
                    Field('arch'),
                    build_settings_toggle_field(self, 'is_active', fill_height=False),
                    css_class='col-12 col-lg-6 dlux-scanlink-release-form__details',
                ),
                Div(
                    build_file_field('installer'),
                    css_class='col-12 col-lg-6 dlux-scanlink-release-form__installer',
                ),
                css_class='g-3 mx-0 align-items-stretch dlux-scanlink-release-form__grid',
            ),
        )

    def clean_installer(self):
        """Validate the upload here, not in save().

        `create_managed_asset` raises ValidationError, and a ValidationError from
        save() escapes the form as a 500 instead of becoming a field error the
        operator can read.
        """
        upload = self.cleaned_data.get('installer')
        from ..assets import validate_asset_upload
        from ..models import ManagedAsset as _Asset
        validate_asset_upload(upload, _Asset.KIND_INSTALLER)
        return upload

    def clean_version(self):
        version = str(self.cleaned_data.get('version') or '').strip()
        if not VERSION_RE.match(version):
            raise forms.ValidationError(
                _s().get('scanlink_version_invalid', 'Use a dotted numeric version, for example 0.7.2.')
            )
        return version

    def clean(self):
        cleaned = super().clean()
        version = cleaned.get('version')
        arch = cleaned.get('arch')
        if version and arch:
            clash = ScanLinkRelease.objects.filter(version=version, arch=arch)
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise forms.ValidationError(
                    _s().get(
                        'scanlink_release_duplicate',
                        'That version already exists for this architecture.',
                    )
                )
        return cleaned

    def save(self, commit=True):
        release = super().save(commit=False)
        upload = self.cleaned_data.get('installer')
        # Reuses the managed-asset pipeline: it validates the extension and size,
        # computes the checksum, and dedupes identical bytes.
        asset, _created = create_managed_asset(
            upload,
            kind=ManagedAsset.KIND_INSTALLER,
            user=self._user,
            title=f"ScanLink {self.cleaned_data.get('version')} ({self.cleaned_data.get('arch')})",
        )
        release.asset = asset
        if getattr(self._user, 'is_authenticated', False):
            release.created_by = self._user
        if commit:
            release.save()
        return release
