# Customization Guide

This page is the integration map for projects that extend DjangoLux. Each topic now has a focused reference so operational documentation and API patterns can evolve independently.

## Configuration and language

- [Project Configuration](project-configuration.md) — `DLUX_CONFIG`, canonical homepage/search settings, app namespaces, custom themes/fonts, and the settings helper.
- [Translations](translation-guide.md) — `DLUX_STRINGS`, administrator overrides, translated labels, and RTL verification.
- [Adding a System Setting](adding-system-settings.md) — the contributor checklist for a first-class System Settings field.

## UI and behavior

- [UI Integration](ui-integration.md) — sections, dynamic modals, Dlux tables, filters, row actions, downloads, activity logging, tutorials, and components.
- [Template and Form Customization](template-customization.md) — extension partials, page bases, form footers, assets, public page chrome, and assisted entry.
- [Developer Guide](developer-guide.md) — framework mental model, discovery, model behavior, public component catalog, and implementation contracts.

## Extension rules

Use Dlux primitives before creating a local equivalent: `DluxFileInput`/`AssetPickerField`, Dlux choice widgets, icon picker, toggle builders, `DluxTable`, dynamic-modal responses, and loading buttons already carry theme, RTL, accessibility, and lifecycle behavior.

Keep UI visibility and backend authorization in sync. Return `JsonResponse({"html": ...})` from dynamic-modal endpoints, make mutations POST-only, and do not put raw HTML in translated or form-help strings.
