# Managed assets

DjangoLux provides a superuser-only Asset Manager dynamic modal, opened from the Options admin-panel action rail. Its `sys/assets/` endpoint returns modal JSON rather than a standalone page. It centralizes reusable branding images and WOFF2 font files while keeping each feature's semantic field in its own settings form.

## Storage and references

`ManagedAsset` stores the file through Django's default storage plus its type, MIME type, byte size, SHA-256 checksum, and image dimensions. Identical active uploads of the same type reuse the existing row. `SystemSettings.logo_asset`, `favicon_asset`, `login_logo_asset`, and `login_background_asset` are nullable `PROTECT` references.

The System Settings fields still appear as System Logo, Favicon, Login Logo, and Login Background. Their shared picker uses the standard Dlux file-card surface: the card opens the compatible saved-file library in a field-anchored overlay that does not reflow the form, while its compact toolbar provides open, upload, and clear actions. A direct upload is validated and registered as a reusable `ManagedAsset` when the settings are saved. Clearing detaches and never deletes the saved file.

Legacy `SystemSettings.logo` and `favicon` files remain readable for upgrade safety. Saving settings adopts a valid legacy file into `ManagedAsset` without copying it, then uses the protected relation. The separate login logo falls back to the system logo when unset.

## Upload policy

Only these formats are accepted:

- Images: GIF, ICO, JPEG, PNG, and WebP, verified with Pillow.
- Fonts: WOFF2 files with a WOFF2 signature.

CSS, JavaScript, SVG, HTML, and arbitrary attachment uploads are not supported. The default limits are 10 MB per image and 20 MB per font. Deployments can override them with `DLUX_ASSET_MAX_IMAGE_MB` and `DLUX_ASSET_MAX_FONT_MB`.

## Deletion guard

The Asset Manager shows the relationship usage report returned by `collect_related_objects()`. Its delete action is disabled while usages are visible, and database `PROTECT` relations remain authoritative if a usage changes between display and submission. Deleting an unused asset removes its storage object after the database transaction commits.

## UI-managed fonts

A WOFF2 upload can register a font family, stable slug, display label, weight, and normal/italic style. `ManagedFontFamily` and `ManagedFontVariant` feed the existing font registry and `@font-face` generator, so the font becomes available to System Settings through the normal allowed-font and default-font pipeline. Additional uploads can add or replace variants for the same family and weight/style.

System-settings JSON exports contain storage names, not file bytes. An import reattaches a referenced asset only when that storage object is available in the destination storage.

