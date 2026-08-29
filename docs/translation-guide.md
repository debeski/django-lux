# Translations

DjangoLux uses `DLUX_STRINGS` dictionaries in `translations.py` files. The runtime merges package, installed-app, project, and database override strings for the current language; database overrides are for administrator edits, not a copy of the entire discovered catalog.

## Project strings

Create a project or app `translations.py`:

```python
DLUX_STRINGS = {
    "en": {"billing_invoice": "Invoice"},
    "ar": {"billing_invoice": "فاتورة"},
}
```

Use stable semantic keys. Do not put raw HTML in translated form help or notification strings: Crispy help text is unescaped. Translate labels and option values separately when their meaning differs by context.

## Administrator overrides

The Localization editor shows discovered keys by source. It persists only edited values in `language_config.translations_override`; code-owned values remain the fallback. This makes imports portable and lets a project upgrade its source catalog without copying stale rows into the database.

Language catalogs define the display name, direction, and optional flag. A language is available to users only after an administrator includes it in the system catalog. Keep the source string complete for both LTR and RTL languages; CSS handles direction, while prose needs a deliberate translation.

## Labels and permissions

Model, section, route, and permission labels resolve through the same catalog. Provide project keys for custom models and actions rather than hard-coding English in a template or view. Per-language sidebar/Navbar labels are optional overrides: a blank value falls back to the discovered translated route name.

## Verification

Check an English and an Arabic request after adding strings. Verify that controls with directional meaning mirror correctly, especially navigation arrows, action rails, table pagination, and titlebar/sidebars. See [Developer Guide](developer-guide.md#translation-and-scope-behavior) for the runtime resolver and [Template Customization](template-customization.md) for direction-safe template patterns.
