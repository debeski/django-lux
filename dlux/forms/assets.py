from dataclasses import dataclass

from django import forms
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import OperationalError, ProgrammingError, transaction
from django.urls import reverse
from ..translations import get_strings
from ..models.assets import SHARED_ASSET_NAMESPACE
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

    def __init__(self, *, kind='image', namespace='', reads=(), identity='', capture='', attrs=None):
        self.kind = kind
        self.namespace = namespace or ''
        self.reads = tuple(reads or ())
        #: `app_label.modelname.fieldname`. The upload endpoint resolves this
        #: against its own registry — it is an identifier, never a grant.
        self.identity = identity or ''
        #: '' | 'environment' | 'user'. Set it and a phone opens the camera
        #: instead of the file chooser.
        self.capture = capture or ''
        self.legacy_url = ''
        self.legacy_name = ''
        self.asset_choices = None
        super().__init__(attrs=attrs)

    def set_asset_choices(self, assets):
        self.asset_choices = list(assets) if assets is not None else None

    def readable_namespaces(self):
        """The write namespace, this field's `reads`, and always the shared pool.

        Anything uploaded straight through the Asset Manager lands in
        `dlux.shared` and is offered everywhere: an admin putting a file in the
        library by hand is doing it so a form can use it, and having to name
        which form in advance would defeat the point.
        """
        if not self.namespace:
            return ()
        namespaces = [self.namespace]
        namespaces.extend(ns for ns in self.reads if ns not in namespaces)
        if SHARED_ASSET_NAMESPACE not in namespaces:
            namespaces.append(SHARED_ASSET_NAMESPACE)
        return tuple(namespaces)

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
                queryset = Asset.objects.filter(kind=self.kind, is_active=True)
                queryset = self._narrow_to_namespaces(queryset)
                return list(queryset.order_by('title', 'pk'))
        except (AssertionError, OperationalError, ProgrammingError):
            return []

    def _narrow_to_namespaces(self, queryset):
        """Restrict a queryset to what this field may read.

        A row whose namespace is empty predates the column and belongs to
        whatever its kind defaults to, so it is matched when that default is one
        of the namespaces being read — and only then.
        """
        from django.db.models import Q

        from ..models.assets import default_namespace_for_kind

        namespaces = self.readable_namespaces()
        if not namespaces:
            # A hand-built picker that names no namespace still sees everything,
            # which is what it saw before the column existed.
            return queryset
        condition = Q(namespace__in=namespaces)
        if default_namespace_for_kind(self.kind) in namespaces:
            condition |= Q(namespace='')
        return queryset.filter(condition)

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
            # One endpoint for every kind now: fonts used to have no instant
            # upload at all and fell back to carrying the file on form submit.
            'asset_upload_url': reverse('managed_asset_picker_upload'),
            'asset_field_identity': self.identity,
            'asset_namespace': self.namespace,
            'capture': self.capture,
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
    """Choose a reusable ``ManagedAsset``, or add one by uploading it now.

    ``namespace`` is the pool an upload lands in and ``reads`` widens what the
    picker lists without widening what it writes. ``identity``
    (``app_label.modelname.fieldname``) is what the upload endpoint resolves to
    decide whether this user may write to that pool; a field built by hand
    without one gets no instant upload and falls back to the form-submit path.
    """

    def __init__(self, *, kind='image', namespace='', reads=(), identity='', capture='', **kwargs):
        kwargs.setdefault('required', False)
        kwargs['widget'] = AssetPickerWidget(
            kind=kind, namespace=namespace, reads=reads, identity=identity, capture=capture,
        )
        self.kind = kind
        self.namespace = namespace or ''
        self.reads = tuple(reads or ())
        self.identity = identity or ''
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
            queryset = Asset.objects.filter(pk=asset_id, kind=self.kind, is_active=True)
            # Re-checked here and not only in the picker: the id arrives in the
            # POST body, so a namespace the field cannot read must be refused
            # rather than merely hidden.
            asset = self.widget._narrow_to_namespaces(queryset).first()
            if asset is None:
                raise ValidationError("Choose an available compatible asset.")
            return AssetSelection(asset=asset)

        return AssetSelection()


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not isinstance(data, (list, tuple)):
            data = [data] if data else []
        files = [super(MultipleFileField, self).clean(item, initial) for item in data]
        if self.required and not files:
            raise ValidationError(self.error_messages['required'], code='required')
        return files


class ManagedImageUploadForm(forms.Form):
    file = MultipleFileField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        strings = get_strings()
        self.fields['file'].label = strings.get('asset_field_file', 'File')
        self.fields['file'].widget.attrs.update({
            'accept': '.gif,.ico,.jpeg,.jpg,.png,.webp,image/gif,image/jpeg,image/png,image/webp,image/x-icon',
            'class': 'visually-hidden',
            'data-managed-image-input': '',
        })

    def clean_file(self):
        uploads = self.cleaned_data['file']
        for upload in uploads:
            validate_asset_upload(upload, 'image')
        return uploads

    def save(self, *, user=None, namespace=''):
        assets = []
        created_count = 0
        for upload in self.cleaned_data['file']:
            asset, created = create_managed_asset(upload, kind='image', user=user, namespace=namespace)
            assets.append(asset)
            created_count += int(created)
        return assets, created_count


class ManagedFontUploadForm(forms.Form):
    title = forms.CharField(max_length=150, required=False)
    file = forms.FileField(widget=DluxFileInput)
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
            'file': strings.get('asset_field_file', 'File'),
            'font_slug': strings.get('asset_field_font_slug', 'Font slug'),
            'font_family': strings.get('asset_field_font_family', 'CSS family'),
            'font_label': strings.get('asset_field_font_label', 'Display label'),
            'font_weight': strings.get('asset_field_font_weight', 'Weight'),
            'font_style': strings.get('asset_field_font_style', 'Style'),
        }
        for field_name, label in labels.items():
            self.fields[field_name].label = label
        self.fields['font_style'].choices = (
            ('normal', strings.get('asset_font_style_normal', 'Normal')),
            ('italic', strings.get('asset_font_style_italic', 'Italic')),
        )
        self.fields['file'].widget = DluxFileInput(
            field_label=self.fields['file'].label,
            attrs={'accept': '.woff2,font/woff2'},
        )
        for field_name in ('title', 'font_slug', 'font_family', 'font_label'):
            self.fields[field_name].widget.attrs['class'] = 'form-control glass-input'
        for field_name in ('font_weight', 'font_style'):
            self.fields[field_name].widget.attrs['class'] = 'form-select glass-input'

    def clean(self):
        cleaned = super().clean()
        upload = cleaned.get('file')
        if upload:
            try:
                validate_asset_upload(upload, 'font')
            except ValidationError as exc:
                self.add_error('file', exc)
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
        with transaction.atomic():
            asset, created = create_managed_asset(
                self.cleaned_data['file'],
                kind='font',
                title=self.cleaned_data.get('title', ''),
                user=user,
            )
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
