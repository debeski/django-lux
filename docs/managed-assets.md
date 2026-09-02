# Managed assets

DjangoLux provides a superuser-only Asset Manager dynamic modal, opened from the Options admin-panel action rail. The *library* it manages is not superuser-only: any model can hold an asset through `ManagedAssetField`, and the field's own permission decides who may add to it — see [Using an asset field in a project](#using-an-asset-field-in-a-project). Its `sys/assets/` endpoint returns modal JSON rather than a standalone page. It centralizes reusable branding images and WOFF2 font files while keeping each feature's semantic field in its own settings form.

The modal uses fixed Dlux Ribbon tabs that are not part of the configurable list-page Ribbon Builder:

- **Images** shows only the image grid. **Upload images** stays in the modal footer, opens a multi-file chooser, and uploads immediately after selection. Image names come from their files and can be changed in place by selecting the displayed name; renaming does not change the stable asset slug or stored filename.
- **Fonts** keeps its metadata in two desktop rows, followed by a full-width file row and a family/variant list. Its upload action stays with that form, and the modal footer is hidden on this tab.

Tab links use `asset_tab=images|fonts`. Modal-internal navigation preserves the original manager URL for delete routing while successful uploads reload the selected tab. Unknown tab values resolve to Images.

## Using an asset field in a project

`ManagedAssetField` is the file field to reach for whenever a model holds an image or a font. It costs what an `ImageField` costs:

```python
from dlux.models import ManagedAssetField, ScopedModel

class Product(ScopedModel):
    image = ManagedAssetField(kind='image')
```

That is a `ManagedAsset` foreign key with `null=True`, `blank=True` and `on_delete=PROTECT` already set — an asset in use cannot be deleted out from under a record — plus the two things a picker needs: the **kind** of file that belongs there and the **namespace** it lives in.

The form side is one mixin. It swaps each asset field for its picker and resolves the selection on save:

```python
from dlux.forms import ManagedAssetFormMixin

class ProductForm(ManagedAssetFormMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'image']
```

Use `build_asset_field('image')` to place it in a crispy layout, the same way `build_file_field` places a plain file field. Set `asset_capture = 'environment'` on the form and a phone opens the camera rather than the file chooser.

Without the mixin, call `apply_asset_pickers(form)` and `apply_asset_selections(form, instance)` directly. The picker is built in the form layer rather than by the model field's `formfield()` because `dlux.models` importing `dlux.forms` closes an import cycle through `dlux.widgets`.

### Namespaces

Every asset carries a namespace, and a picker lists only the namespaces its field is declared to read. That is what keeps branding off a product form and product photos out of the branding picker, without anyone remembering to filter. It defaults to the owning model's `app_label.modelname`.

A field that should *see* another pool without writing into it says so:

```python
image_override = ManagedAssetField(
    kind='image',
    namespace='public_catalog.listing',
    reads=['catalog.product'],
)
```

`namespace` is where an upload lands; `reads` widens what the picker lists and never widens what it writes. An asset id posted from outside the read set is refused during `clean()`, not merely hidden in the UI. De-duplication is keyed on `(namespace, checksum)` rather than the checksum alone — matching globally would hand one pool's row, title and all, to a caller who uploaded the same bytes into another.

Namespaces dlux owns: `dlux.systemsettings` (branding), `dlux.fonts`, `dlux.scanlink`, and `dlux.shared`.

**`dlux.shared` is read by every picker, automatically.** A file uploaded straight through the Asset Manager's Images tab lands there, because it belongs to no single model — an admin putting a file in the library by hand is doing it so a form can use it, and having to name which form in advance would defeat the point. No field has to list it in `reads`.

An asset whose `namespace` column is empty predates the column and belongs to whatever its kind defaults to — `dlux.systemsettings` for an image, `dlux.fonts` for a font, `dlux.scanlink` for an installer. `effective_namespace` resolves it, a picker matches those rows when it reads that default, and `save()` writes a concrete value the first time the row is touched. This is why the upgrade needs no data migration: one stamped default would have been wrong for two of the three kinds.

### Instant upload and who may do it

Choosing a file uploads it immediately and the form then carries only an asset id. The picker posts the field it belongs to as `app_label.modelname.fieldname`, and the server resolves that against its own registry of declared fields to decide the namespace, the accepted kind, and the permission. The identity is an identifier, never a grant: a forged or renamed value resolves to nothing and is refused, and nothing in the request body can choose where a file lands.

**Whoever may add or change the record may add its picture** — the field's own `add_`/`change_` permission is the gate. There is deliberately no `add_managedasset` permission to invent, seed and grant to every role that already holds `change_product`. A picker built by hand with no field identity gets no instant upload and stays superuser-only, which is what the System Settings branding pickers do.

### Migrating off an ImageField

Keep the existing `ImageField` and add the asset field beside it, then name the pair on the form:

```python
class ProductForm(ManagedAssetFormMixin, forms.ModelForm):
    legacy_asset_files = {'image_asset': 'image'}
```

The first save with no asset chosen adopts the stored file into the library **in place** — the bytes are not copied, the existing storage name becomes the asset's file. Read through the asset and fall back to the legacy field until the backfill is complete.

## Storage and references

`ManagedAsset` stores the file through Django's default storage plus its namespace, type, MIME type, byte size, SHA-256 checksum, and image dimensions. Identical active uploads of the same type *in the same namespace* reuse the existing row. Files are written to `dlux/assets/<kind>/<namespace>/`; changing that path affects new saves only, so existing files keep their stored names. `SystemSettings.logo_asset`, `favicon_asset`, `login_logo_asset`, and `login_background_asset` are nullable `PROTECT` references.

The System Settings fields still appear as System Logo, Favicon, Login Logo, and Login Background. Their shared picker uses the standard Dlux file-card surface: the card opens the compatible saved-file library in a field-anchored overlay that does not reflow the form, while its compact toolbar provides open, upload, and clear actions. A direct image upload is validated and registered immediately through the `sys/assets/upload/` endpoint (the pre-1.9 `sys/setup/assets/upload/` route still resolves). The returned asset replaces the pending browser file and is added to every compatible picker on the open form, so later setup steps can select it without saving settings first. Asset Manager image uploads publish the same browser event to open pickers. Clearing detaches and never deletes the saved file.

Legacy `SystemSettings.logo` and `favicon` files remain readable for upgrade safety. Saving settings adopts a valid legacy file into `ManagedAsset` without copying it, then uses the protected relation. The separate login logo falls back to the system logo when unset.

## Upload policy

Only these formats are accepted:

- Images: GIF, ICO, JPEG, PNG, and WebP, verified with Pillow.
- Fonts: WOFF2 files with a WOFF2 signature.

CSS, JavaScript, SVG, HTML, and arbitrary attachment uploads are not supported. The default limits are 10 MB per image and 20 MB per font. Deployments can override them with `DLUX_ASSET_MAX_IMAGE_MB` and `DLUX_ASSET_MAX_FONT_MB`.

## Cleaning up unused files

Each tab has a **Clean up unused** action that removes every asset in it that nothing references. It previews what would go before deleting anything, and leaves alone anything uploaded within the last 24 hours: instant upload registers an asset the moment a file is chosen, so a shorter grace period would delete a picture out of a record somebody is still writing. `PROTECT` re-checks each delete, so a reference added between the preview and the confirmation blocks that row rather than the whole run.

## Image deletion guard

The Images tab shows the relationship usage report returned by `collect_related_objects()`. Its delete action is disabled while usages are visible, and database `PROTECT` relations remain authoritative if a usage changes between display and submission. Deleting an unused image removes its storage object after the database transaction commits.

## UI-managed fonts

A WOFF2 upload can register a font family, stable slug, display label, weight, and normal/italic style. `ManagedFontFamily` and `ManagedFontVariant` feed the existing font registry and `@font-face` generator, so the font becomes available to System Settings through the normal allowed-font and default-font pipeline. Additional uploads can add or replace variants for the same family and weight/style.

System-settings JSON exports contain storage names, not file bytes. An import reattaches a referenced asset only when that storage object is available in the destination storage.
