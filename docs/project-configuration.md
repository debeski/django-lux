# Project Configuration

Use this guide for configuration owned by a Django project. Runtime administrators can refine these defaults later in System Settings; see [System Configuration](system-configuration.md).

## `DLUX_CONFIG`

Set `DLUX_CONFIG` in the project settings module before calling `dlux_settings(globals())`. It supplies code-owned defaults beneath the database singleton, so it is the right place for a deployable baseline rather than per-user choices.

```python
DLUX_CONFIG = {
    "homepage_config": {
        "default_url": "/dashboard/",
        "allow_user_override": True,
    },
    "search_config": {"enabled": True, "display_mode": "icon"},
    "reports": {"exclude_models": ["billing.LedgerEntry"]},
    "extra": {"app": {"billing": {"warn_overdue_days": 30}}},
}
```

Use `homepage_config` and `search_config` for new work. v1.x still accepts the legacy homepage/public page and titlebar search aliases, but they are compatibility mirrors scheduled for removal in v2.0; see [Deprecation Countdown](deprecation-countdown.md).

Project-owned application settings belong below `extra_config['app'][namespace]` and should use a registered app settings tile instead of extending the core System Settings form. `extra_config` itself must not be seeded with framework defaults: doing so can overwrite host-project data.

## Themes and fonts

Register project-owned themes with `DLUX_CUSTOM_THEMES` and WOFF2 font families with `DLUX_CUSTOM_FONTS`. Registered items join the same registry used by setup, validation, allowlists, previews, and per-user selection; do not add a parallel selector or stylesheet loading path.

A rule that applies to one named theme (`:root.theme-dark .x`) lives in that theme's stylesheet under `dlux/static/dlux/themes/css/`, never in a feature stylesheet; feature CSS styles every theme through `--dlux-*` tokens whose defaults sit in `base/css/main.css`. `test_theme_tokens` enforces this for the package. Custom themes follow the same rule in their own CSS file.

A page links only the active theme's stylesheet: the server resolves the reader's theme (their preference, the scope or system default, or the forced public-page theme) and `base.html` emits that one `<link data-dlux-theme-css="<slug>">`. The other allowed themes are listed in an inert `<template id="dlux-theme-stylesheets">`, and `window.setTheme(slug)` loads the chosen sheet beside the active one before it switches, so a custom theme's CSS is fetched only by readers who use it. Project CSS keyed to one theme (`:root.theme-neon .x`) behaves as before. Script that needs another theme's rules without switching to it (a test, a preview) awaits `window.dluxLoadThemeStylesheet(slug)` first.

Each custom theme must have a stable slug, translated display name, and a static CSS path. Each custom font must identify its family and available WOFF2 variants. Keep assets inside the project static tree and test both LTR and RTL rendering. The exact accepted setting shapes and defaults are listed in [Deployment Configuration](deployment-configuration.md).

## Settings integration

The standard integration entry point is:

```python
from dlux.utils import dlux_settings

dlux_settings(globals())
```

It supplies Dlux apps, middleware, context processors, i18n defaults, Crispy Forms defaults, and URL support. Mount `dlux.urls` at the project root. Do not copy an old generated settings block: the helper is additive and version-aware.

To add a first-class framework setting, follow [Adding a System Setting](adding-system-settings.md); it must participate in the schema, normalization, forms, import/export, and tests.

## Reports and activity

Set report exclusions under `DLUX_CONFIG['reports']`. A model can also declare `dlux_report = False`. Use the public `log_activity(...)` API for project actions that should appear in user-facing reports; it observes the active logging policy and request scope. See [UI Integration](ui-integration.md#activity-logging).

## Related references

- [Translations](translation-guide.md)
- [UI Integration](ui-integration.md)
- [Template Customization](template-customization.md)
- [Developer Guide](developer-guide.md)
