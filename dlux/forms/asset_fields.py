"""Public API for putting a `ManagedAssetField` on a form.

Two jobs, because a picker is both a widget and a save-time decision:

`apply_asset_pickers()` swaps a model's `ManagedAssetField`s for configured
`AssetPickerField`s. It lives here rather than in the model field's
`formfield()` because `dlux.models` importing `dlux.forms` closes an import
cycle through `dlux.widgets`.

`resolve_asset_selection()` turns what the picker returned into the asset the
record should point at — creating one from an upload, keeping a chosen one,
clearing, or adopting a legacy file that predates the library. Until 1.9 this
was a private method on the System Settings form, where nothing else could
reach it; that form now calls this function like any other caller.

`ManagedAssetFormMixin` does both: drop it on a ModelForm and the pickers
render and resolve themselves.
"""
from pathlib import Path

from ..assets import adopt_stored_asset, create_managed_asset
from ..models.asset_field import ManagedAssetField
from .assets import AssetPickerField, AssetSelection


def resolve_asset_selection(
    selection,
    current_asset=None,
    *,
    kind='image',
    namespace='',
    legacy_file=None,
    user=None,
    commit=True,
):
    """The asset a record should point at, given what the picker returned.

    The order matters and is the whole contract:

    1. An **upload** wins — the operator just chose a file.
    2. A **chosen** asset is used as-is.
    3. **Clear** means clear.
    4. Otherwise the current asset stands. A form step that did not render this
       field must not blank it, which is why an omitted selection is a no-op
       rather than a clear.
    5. Only if there is no current asset does a **legacy file** get adopted —
       the one-time migration off a plain ``ImageField``, done in place.

    ``commit=False`` answers the question without writing anything, for a form
    that is previewing rather than saving.
    """
    if not isinstance(selection, AssetSelection):
        selection = AssetSelection(omitted=True)

    if selection.upload:
        if not commit:
            return current_asset
        asset, _created = create_managed_asset(
            selection.upload,
            kind=kind,
            namespace=namespace,
            title=Path(str(getattr(selection.upload, 'name', '') or '')).stem,
            user=user,
        )
        return asset

    if selection.asset is not None:
        return selection.asset
    if selection.clear:
        return None
    if current_asset is not None:
        return current_asset
    if commit and legacy_file:
        return adopt_stored_asset(
            legacy_file,
            user=user,
            namespace=namespace,
            title=Path(str(getattr(legacy_file, 'name', '') or '')).stem,
        )
    return None


def managed_asset_fields(model):
    """Every ``ManagedAssetField`` declared on ``model``."""
    return [field for field in model._meta.get_fields()
            if isinstance(field, ManagedAssetField)]


def build_asset_picker(field, **kwargs):
    """The `AssetPickerField` a `ManagedAssetField` should render as.

    Built here rather than in the model field's `formfield()`: `dlux.models`
    importing `dlux.forms` closes an import cycle through `dlux.widgets`, and
    the guard in `test_import_graph` rejects it. Direction of travel is forms →
    models, never back.
    """
    kwargs.setdefault('label', field.verbose_name)
    kwargs.setdefault('required', not field.blank)
    kwargs.setdefault('help_text', field.help_text)
    return AssetPickerField(
        kind=field.kind,
        namespace=field.namespace,
        reads=field.reads,
        identity=field.identity,
        **kwargs,
    )


def apply_asset_pickers(form, capture=''):
    """Swap every `ManagedAssetField` on the form's model for its picker.

    The counterpart to a project's own `apply_dlux_file_widgets`: a plain
    `ModelForm` would otherwise render a foreign key as a select of asset ids.
    `capture` ('environment' or 'user') makes a phone open the camera instead of
    the file chooser.
    """
    model = getattr(getattr(form, '_meta', None), 'model', None)
    if model is None:
        return form
    for field in managed_asset_fields(model):
        if field.name not in form.fields:
            continue
        existing = form.fields[field.name]
        form.fields[field.name] = build_asset_picker(
            field,
            label=existing.label or field.verbose_name,
            required=existing.required,
            help_text=existing.help_text or field.help_text,
            capture=capture,
        )
        # A bound form re-renders from `initial`; the picker reads the asset
        # itself, not its id.
        current = form.initial.get(field.name)
        if current is not None and not hasattr(current, 'pk'):
            form.initial[field.name] = getattr(form.instance, field.name, None)
    return form


def apply_asset_selections(form, instance, *, user=None, commit=True, legacy_files=None):
    """Resolve every asset field on ``instance`` from ``form.cleaned_data``.

    ``legacy_files`` maps a field name to the old ``FileField`` value it
    replaces, so a project migrating off one adopts it on first save::

        apply_asset_selections(form, product, legacy_files={'image': product.image})
    """
    legacy_files = legacy_files or {}
    for field in managed_asset_fields(type(instance)):
        name = field.name
        if name not in form.cleaned_data:
            continue
        setattr(instance, name, resolve_asset_selection(
            form.cleaned_data.get(name),
            getattr(instance, name, None),
            kind=field.kind,
            namespace=field.namespace,
            legacy_file=legacy_files.get(name),
            user=user,
            commit=commit,
        ))
    return instance


class ManagedAssetFormMixin:
    """Resolve a model's asset fields on save, with nothing to write per form.

    ``legacy_asset_files`` names the plain file field each asset field replaces,
    for a model part-way through the migration::

        class ProductForm(ManagedAssetFormMixin, forms.ModelForm):
            legacy_asset_files = {'image_asset': 'image'}
    """

    #: ``{asset field name: legacy file field name}``
    legacy_asset_files = {}
    #: '' | 'environment' | 'user' — passed to every picker this form renders.
    asset_capture = ''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_asset_pickers(self, capture=self.asset_capture)

    def _post_clean(self):
        """Keep `construct_instance` away from the picker's value.

        A picker cleans to an `AssetSelection`, not a `ManagedAsset`, and
        `ModelForm._post_clean` would assign it straight onto the foreign key —
        "must be a ManagedAsset instance". The value is hidden for the length of
        that call and put back afterwards; `save()` is what turns it into a real
        asset, because only it knows whether this is a commit.
        """
        model = getattr(getattr(self, '_meta', None), 'model', None)
        names = [field.name for field in managed_asset_fields(model)] if model else []
        stashed = {name: self.cleaned_data.pop(name) for name in names if name in self.cleaned_data}
        try:
            super()._post_clean()
        finally:
            self.cleaned_data.update(stashed)

    def _asset_user(self):
        user = getattr(self, '_user', None) or getattr(getattr(self, 'request', None), 'user', None)
        return user if getattr(user, 'is_authenticated', False) else None

    def _asset_legacy_files(self, instance):
        return {
            asset_field: getattr(instance, legacy_field, None)
            for asset_field, legacy_field in (self.legacy_asset_files or {}).items()
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        apply_asset_selections(
            self, instance,
            user=self._asset_user(),
            commit=commit,
            legacy_files=self._asset_legacy_files(instance),
        )
        if commit:
            instance.save()
            self.save_m2m()
        return instance
