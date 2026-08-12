from dataclasses import dataclass

from django import forms
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import OperationalError, ProgrammingError, transaction
from ..translations import get_strings
from ..widgets import DluxFileInput

from ..assets import (
    FONT_FAMILY_RE,
    FONT_SLUG_RE,
    create_managed_asset,
    register_managed_font,
    validate_asset_upload,
)


@dataclass
class AssetSelection:
    asset: object = None
    upload: object = None
    clear: bool = False
    omitted: bool = False


class AssetPickerWidget(DluxFileInput):
    needs_multipart_form = True

    def __init__(self, *, kind='image', attrs=None):
        self.kind = kind
        self.legacy_url = ''
        self.legacy_name = ''
        self.asset_choices = None
        super().__init__(attrs=attrs)

    def set_asset_choices(self, assets):
        self.asset_choices = list(assets) if assets is not None else None

    def _compatible_assets(self):
        if self.asset_choices is not None:
            return list(self.asset_choices)
        Asset = apps.get_model('dlux', 'ManagedAsset')
        try:
            # Savepoint: on a bootstrap-from-empty database this table does not
            # exist yet, and on PostgreSQL catching the error is not enough — the
            # server-side transaction stays aborted and takes the next statement
            # in the enclosing atomic block down with it.
            with transaction.atomic():
                return list(Asset.objects.filter(kind=self.kind, is_active=True).order_by('title', 'pk'))
        except (AssertionError, OperationalError, ProgrammingError):
            return []

    def value_from_datadict(self, data, files, name):
        asset_name = f'{name}_asset'
        upload_name = f'{name}_upload'
        clear_name = f'{name}_clear'
        return {
            'asset_id': data.get(asset_name),
            'upload': files.get(upload_name),
            'clear': str(data.get(clear_name) or '').lower() in {'1', 'true', 'on', 'yes'},
            'omitted': asset_name not in data and upload_name not in files and clear_name not in data,
        }

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        assets = self._compatible_assets()
        current = None
        selected_id = ''
        if isinstance(value, AssetSelection):
            current = value.asset
            selected_id = str(getattr(current, 'pk', '') or '')
        elif isinstance(value, dict):
            selected_id = str(value.get('asset_id') or '')
            if selected_id.isdigit():
                current = next((asset for asset in assets if str(asset.pk) == selected_id), None)
        elif getattr(value, 'pk', None):
            current = value
            selected_id = str(value.pk)

        strings = get_strings()

        widget = context['widget']
        widget.update({
            'asset_picker': True,
            'field_label': self.field_label,
            'show_scan': False,
            'empty_meta': strings.get('asset_picker_empty_meta', 'Choose a saved file or use upload.'),
            'choose_existing_action': strings.get('asset_choose_existing', 'Choose asset'),
            'search_assets': strings.get('asset_search', 'Search assets'),
            'library_empty': strings.get('asset_library_empty', 'No compatible reusable assets yet.'),
            'kind': self.kind,
            'assets': assets,
            'current_asset': current,
            'selected_id': selected_id,
            'asset_input_name': f'{name}_asset',
            'upload_input_name': f'{name}_upload',
            'clear_input_name': f'{name}_clear',
            'legacy_url': self.legacy_url if current is None else '',
            'legacy_name': self.legacy_name if current is None else '',
            'accept': '.woff2,font/woff2' if self.kind == 'font' else '.gif,.ico,.jpeg,.jpg,.png,.webp,image/gif,image/jpeg,image/png,image/webp,image/x-icon',
        })
        initial_name = getattr(current, 'title', '') or (self.legacy_name if current is None else '')
        initial_url = getattr(current, 'url', '') or (self.legacy_url if current is None else '')
        widget.update({
            'is_initial': bool(initial_name),
            'display_name': initial_name,
            'file_url': initial_url,
            'icon_class': 'bi bi-file-earmark-image-fill' if self.kind == 'image' else 'bi bi-file-earmark-font-fill',
        })
        return context


class AssetPickerField(forms.Field):
    def __init__(self, *, kind='image', **kwargs):
        kwargs.setdefault('required', False)
        kwargs['widget'] = AssetPickerWidget(kind=kind)
        self.kind = kind
        super().__init__(**kwargs)

    def clean(self, value):
        value = value if isinstance(value, dict) else {}
        if value.get('omitted'):
            return AssetSelection(omitted=True)

        upload = value.get('upload')
        if upload:
            validate_asset_upload(upload, self.kind)
            return AssetSelection(upload=upload)

        if value.get('clear'):
            return AssetSelection(clear=True)

        asset_id = str(value.get('asset_id') or '').strip()
        if asset_id:
            Asset = apps.get_model('dlux', 'ManagedAsset')
            asset = Asset.objects.filter(pk=asset_id, kind=self.kind, is_active=True).first()
            if asset is None:
                raise ValidationError("Choose an available compatible asset.")
            return AssetSelection(asset=asset)

        return AssetSelection()


class ManagedAssetUploadForm(forms.Form):
    title = forms.CharField(max_length=150, required=False)
    kind = forms.ChoiceField(choices=(('image', 'Image'), ('font', 'WOFF2 Font')))
    file = forms.FileField()
    font_slug = forms.CharField(max_length=50, required=False)
    font_family = forms.CharField(max_length=100, required=False)
    font_label = forms.CharField(max_length=100, required=False)
    font_weight = forms.TypedChoiceField(
        choices=tuple((weight, str(weight)) for weight in range(100, 901, 100)),
        coerce=int,
        initial=400,
        required=False,
    )
    font_style = forms.ChoiceField(
        choices=(('normal', 'Normal'), ('italic', 'Italic')),
        initial='normal',
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        strings = get_strings()
        labels = {
            'title': strings.get('asset_field_title', 'Name'),
            'kind': strings.get('asset_field_kind', 'File type'),
            'file': strings.get('asset_field_file', 'File'),
            'font_slug': strings.get('asset_field_font_slug', 'Font slug'),
            'font_family': strings.get('asset_field_font_family', 'CSS family'),
            'font_label': strings.get('asset_field_font_label', 'Display label'),
            'font_weight': strings.get('asset_field_font_weight', 'Weight'),
            'font_style': strings.get('asset_field_font_style', 'Style'),
        }
        for field_name, label in labels.items():
            self.fields[field_name].label = label
        self.fields['kind'].choices = (
            ('image', strings.get('asset_kind_image', 'Image')),
            ('font', strings.get('asset_kind_font', 'WOFF2 font')),
        )
        self.fields['font_style'].choices = (
            ('normal', strings.get('asset_font_style_normal', 'Normal')),
            ('italic', strings.get('asset_font_style_italic', 'Italic')),
        )
        self.fields['file'].widget = DluxFileInput(
            field_label=self.fields['file'].label,
            attrs={'accept': '.gif,.ico,.jpeg,.jpg,.png,.webp,.woff2'},
        )
        for field_name in ('title', 'font_slug', 'font_family', 'font_label'):
            self.fields[field_name].widget.attrs['class'] = 'form-control glass-input'
        for field_name in ('kind', 'font_weight', 'font_style'):
            self.fields[field_name].widget.attrs['class'] = 'form-select glass-input'

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get('kind')
        upload = cleaned.get('file')
        if upload and kind:
            try:
                validate_asset_upload(upload, kind)
            except ValidationError as exc:
                self.add_error('file', exc)
        if kind == 'font':
            slug = str(cleaned.get('font_slug') or '').strip().lower()
            family = str(cleaned.get('font_family') or '').strip()
            if not FONT_SLUG_RE.fullmatch(slug):
                self.add_error('font_slug', "Use a lowercase slug beginning with a letter.")
            if not FONT_FAMILY_RE.fullmatch(family):
                self.add_error('font_family', "Enter a valid CSS font family name.")
            if not cleaned.get('font_weight'):
                self.add_error('font_weight', "Choose a font weight.")
        return cleaned

    def save(self, *, user=None):
        asset, created = create_managed_asset(
            self.cleaned_data['file'],
            kind=self.cleaned_data['kind'],
            title=self.cleaned_data.get('title', ''),
            user=user,
        )
        font = None
        if self.cleaned_data['kind'] == 'font':
            font, _variant = register_managed_font(
                asset,
                slug=self.cleaned_data['font_slug'],
                family=self.cleaned_data['font_family'],
                label=self.cleaned_data.get('font_label', ''),
                weight=self.cleaned_data['font_weight'],
                style=self.cleaned_data.get('font_style') or 'normal',
                user=user,
            )
        return asset, created, font
