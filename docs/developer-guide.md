# Developer Guide

This page explains how DjangoLux fits into a Django project and how to think about its moving parts before you start extending it.

## The Core Mental Model

DjangoLux is a Django app that combines seven layers:

1. runtime configuration
2. generic discovery and generation
3. global patches for translation and scope behavior
4. reusable templates, views, and JavaScript for internal system workflows
5. audit and governance infrastructure
6. data-movement and productivity utilities
7. generated-Compose deployment and verified package activation

If you keep those layers in mind, the package becomes much easier to extend without fighting it.

## Configuration Layers

The runtime configuration comes from `get_system_config()` and is merged in this order:

1. package defaults
2. `settings.DLUX_CONFIG`
3. the database-backed `SystemSettings` singleton

Practical implications:

- use `DLUX_CONFIG` for project-owned defaults checked into source control
- use `SystemSettings` for live runtime edits from the UI
- expect the final resolved configuration to be the merged view, not one single source

To **add a new first-class setting** to the `SystemSettings` pipeline (schema →
normalizer → export whitelist → form → runtime), follow the step-by-step procedure
and trap list in [`adding-system-settings.md`](adding-system-settings.md). To store
**project-owned** config without touching the framework, use the
`extra_config['app']` namespace documented in [`reference.md`](reference.md).

## Core Models

The main system-level models are:

- `SystemSettings`
  Stores branding plus grouped runtime policy for language, themes, typography,
  authentication, email, registration, notifications, navigation, logging, and
  the profile/onboarding surface.

- `Scope` and `ScopeSettings`
  Represent the optional scope-isolation system and whether scoping is globally enabled. `ScopeSettings.auto_create_user_scope` enables automatic creation of a dedicated `Scope` for every newly registered user. `Scope.default_theme` provides an allowed-theme fallback for users in that scope who have not selected a valid personal theme; it is ignored while scopes are disabled.

- `ScopedModel`
  Gives inheriting models audit fields, actor tracking, soft-delete behavior, and automatic scope support.

- `Profile`
  Extends the user model with phone, profile picture, preferences, and 2FA state. Profiles are created automatically.

- `ActivityLog`, `DluxNotification*`, and backup/restore run models
  Persist the audit, user-delivery, report, and recovery control planes.

- `DluxUpdateState` and `DluxUpdateRun`
  Persist the active/baked/previous release state and serialized check/apply/
  rollback history for generated Compose deployments. They do not make Dlux an
  out-of-process Django app; the active release is still imported in-process.

## Working with ScopedModel

Inheriting from `ScopedModel` is the main way to make a model feel native inside DjangoLux.

```python
from django.db import models
from dlux.models import ScopedModel


class Department(ScopedModel):
    name = models.CharField(max_length=100)
```

What you get automatically:

- `scope`
- `created_at`
- `updated_at`
- `created_by`
- `updated_by`
- `deleted_at`
- `deleted_by`

Behavior to remember:

- `save()` auto-assigns actor fields from the current request user
- `save()` can also inherit scope from the current user's profile
- `delete()` becomes a soft-delete
- `objects` is scope-aware and hides soft-deleted rows
- `all_objects` is the raw escape hatch
- When `ScopeSettings.auto_create_user_scope` is enabled, new users automatically receive their own dedicated scope

## Startup Patches and Zero-Boilerplate Behavior

`DluxConfig.ready()` applies the package's global behavior at startup. That includes:

- permission-label translation
- automatic scope handling for forms, filters, and tables
- automatic translation patches for forms, filters, tables, and some context-menu labels

That is why many dlux features feel "automatic" even when your model or form code looks ordinary.

### The `ready()` Phase: Behind the Magic

When `DluxConfig.ready()` runs at startup, it applies several global monkey-patches to Django's core components to enable the "Zero-Boilerplate" experience.

#### 1. Automatic Scope Injection
Through `dlux.patches.apply_scoped_patches()`, the system intercepts the `__init__` methods of `ModelForm`, `FilterSet`, and `Table` (from `django-tables2`).
- **Discovery**: It checks if the underlying model inherits from `ScopedModel`.
- **Injection**: If so, it automatically adds a `scope` field/filter/column if one hasn't been explicitly defined or excluded.
- **Access Control**: It locks the field for non-superusers, ensuring they cannot change their assigned scope.

#### 2. Universal Translation Patches
Through `apply_global_translation_patches()`, the system:
- **Monkey-patches `gettext`**: Every call to Django's translation utilities (including `_()`) first checks the `DLUX_STRINGS` dictionary and runtime overrides before falling back to local PO files.
- **Translates Model Meta**: Automatically wraps `verbose_name` and `verbose_name_plural` of ALL models in the project with lazy translators that look up keys in `dlux` (`model_<name>` / `models_<name>`). Each falls back to the *other* key before the raw name, so a model translated with only one key still resolves on every surface (sidebar, nav, section manager). The canonical helper is `dlux.translations.resolve_model_label(model)` — the single entry point components share so they always agree on the label (order: plural → singular → raw).
- **Translates Permissions**: Dynamic labels in the user management UI are generated by translating the "Can add/view/delete" strings in real-time.

#### 3. Auth Redirect Defaults
If `LOGIN_REDIRECT_URL` or `LOGOUT_REDIRECT_URL` are missing from your `settings.py`, DjangoLux injects its own defaults to ensure a smooth out-of-the-box flow.

A few practical consequences:

- you usually do not add `scope` manually to every form and filter
- translated labels often come from verbose names or translation keys without manual wiring
- opting out is explicit, such as excluding `scope` in form metadata when needed

## Discovery and Generated Components

DjangoLux leans heavily on naming conventions and runtime discovery.

The generic class resolver looks for model-adjacent classes in this order:

- convention-based imports such as `DepartmentForm`, `DepartmentTable`, and `DepartmentFilter`
- explicit model methods that return classes
- explicit dotted-path model methods
- runtime auto-generation

That same discovery model powers both sections and dynamic modal flows.

It also connects to the surrounding UI systems:

- sidebar discovery for runtime navigation
- sidebar permission inference (see below)
- context-menu actions attached to generated tables
- autofill metadata attached to generated or patched form fields
- generic modal/list/detail views that expect convention-friendly classes

### Route Discovery And Feature Profiles

Discovery is global and excludes nothing. `discover_routes()` walks the URLconf
once per language and returns every named route, classified rather than filtered.
Each navigation feature then reads that shared catalog through its own profile
(`discover_routes_for(profile)`), so one feature's rules can never quietly
narrow another's. Profiles are declared in `dlux/system/constants.py`.

Each route is classified into one `action`:

| Action | Matched by | Example |
| --- | --- | --- |
| `page` | anything not matched below | `chapter_list` |
| `form` | `add` / `create` route-name token | `chapter_add` |
| `edit` | `edit` / `update` route-name token | `chapter_edit` |
| `async` | `ajax` route-name token | `chapter_ajax_search` |
| `api` | `api` as an exact token, or an API-looking callback | `catalog:api:records` |
| `machinery` | auth/2FA/setup/modal names, paths and namespaces | `verify_otp_login` |

Which profile accepts which action:

| Profile | Accepts | Needs a reversible URL |
| --- | --- | --- |
| `sidebar` | `page`, `form` | yes |
| `navbar` | `page`, `form`, `edit` | no |
| `navbar_root` | `page` | yes |
| `search` | `page`, `form` | yes |
| `landing` | `page` | yes |

Two consequences worth knowing. A **form page** (`chapter_add`) is a real
destination: it is searchable, placeable in the Nav Bar hierarchy, and offered in
the sidebar builder behind the *Show form pages* toggle — but it is never added
to a zero-config sidebar and cannot be a landing page or a Nav Bar root. An
**id-bound page** (`chapter_edit`, `chapter_detail`) cannot be reversed without
arguments, so every feature that needs a real href drops it; only the Nav Bar
hierarchy accepts it, because its nodes match on route name and a URL-less crumb
renders as plain text.

API endpoints are excluded from every navigation profile. `api` is matched as an
exact token across the full URL namespace/name and resolved path, including
suffixes such as `records_api`, nested names such as `catalog:api:records`, and
callback class or function names such as `RecordsAPIView`. Ordinary names that
merely contain the letters, such as `rapid_report`, remain discoverable. Stored
sidebar/Nav Bar trees and imported/exported settings are sanitized by the same
rule; when an old API hierarchy node contains valid page children, those children
are kept.

#### Overriding discovery per view

Set these on the view callback when the inferred classification is wrong:

```python
class ChapterAddView(CreateView):
    dlux_exclude = ('search',)      # hide from search only
    dlux_include = ('landing',)     # offer despite the profile's action rules
```

Both accept a profile name, an iterable of names, or `True` for every profile.
`dlux_exclude` always wins over `dlux_include`. The released
`view.sidebar_exclude = True` still works and hides the view from every feature.

### Sidebar Permission Inference

Sidebar items are only visible to users who have the required view permission. The permission for each item is inferred in this order:

1. **Explicit decorator**: `sidebar_permissions` or `permission_required` on the view callback — used as-is.
2. **System route meta**: items in `SYSTEM_ROUTE_META` (e.g., `manage_users`, `options_view`) use their declared `__dlux_*` permission tokens.
3. **Model-based inference**: for class-based views with a model, the permission is `app_label.view_model_name`.
4. **URL pattern inference**: for function-based views without a model, the app label comes from the URL namespace (or callback module) and the model name from the URL name prefix (e.g., `documents:outgoing_list` → `documents.view_outgoing`).
5. **No inference**: if none of the above produce a permission, the item is hidden from non-superusers.

This means staff users will only see sidebar items for models they have explicit `app.view_model` permissions for. Ensure users are granted the appropriate permissions.

## Dlux-owned UI primitives

Dlux-owned screens must reuse the framework primitive before falling back to a raw Django widget or generic Bootstrap structure:

- `DluxFileInput` from `dlux.widgets` for ordinary file uploads. Inside Crispy layouts, use `build_archive_file_field()` so the file card, validation output, drag/drop behavior, toolbar, and translations stay intact. Do not write a raw `<input type="file">` in a Dlux-owned template.
- `AssetPickerField` from `dlux.forms.assets` when a field can select a reusable `ManagedAsset` or register a direct upload. Its file card opens the saved-file library as a dropdown popover and keeps upload/open/clear in the standard toolbar.
- `DluxChoiceSelectorWidget` and `DluxMultipleChoiceSelectorWidget` from `dlux.widgets` for card, chip, searchable single-choice, and multi-choice controls.
- Dlux icon picker through `dlux/helpers/icon_picker.html` and `initIconPickers()` for Bootstrap Icons fields inside System Settings/setup surfaces. It is lazy-rendered, searchable, keyboard-closeable, and shares the same `ICON_SUGGESTIONS` catalog as the sidebar builder. The grid opens as a popover anchored under the field (the asset picker library's geometry) and closes on an outside click or Escape; pass `inline: True` in the include context for the older in-flow disclosure that pushes the following fields down.
- `build_settings_toggle_field()` and `build_email_toggle_field()` from `dlux.forms` for settings switches; do not hand-build Bootstrap switch markup.
- `DluxTable` from `dlux.tables`, or the `dlux-table-shell` / `dlux-table-scroll` / `dlux-data-table` structure, for Dlux-owned data grids.
- The universal dynamic-modal protocol (`data-dynamic-modal`, JSON `{html}` fragments, and `data-dlux-modal-footer`) for modal workflows, and `window.DluxLoadingButton` for asynchronous button state.
- `data-dlux-context` plus the Dlux row-action schema for context menus, and `data-dlux-tooltip` for themed accessible tooltips instead of one-off menu/tooltip implementations.
- `from dlux.notifications import notify` for user-facing success, warning, and error feedback so drawer/history behavior remains consistent.

### Markup wrappers

Four wrappers cover the structural markup that used to be copy-pasted. Three are
block tags from `dlux_tags` (`{% load dlux_tags %}` first), one is a plain
include:

```html
{% dlux_table_shell density="balanced" class="" %}
  <table class="table table-hover align-middle dlux-data-table">…</table>
{% enddlux_table_shell %}

{% dlux_card tag="section" class="my-card" attrs="data-x" %}…{% enddlux_card %}

{% dlux_alert level="warning" class="my-notice" role="status" attrs="data-y" %}
  …
{% enddlux_alert %}

{% include 'dlux/tables/empty_row.html' with colspan=4 text=DLUX_STRINGS.x padding=3 %}
```

`dlux/tables/pair_table.html` renders the repeated label/count breakdown grid:
pass `rows`, `label_header`, `count_header`, and `empty_text`.

Options-page cards use their own wrapper, which owns the reorder handle and the
icon heading:

```html
{% dlux_option_card slug="theme" icon="bi-palette" title=DLUX_STRINGS.themes desc=DLUX_STRINGS.theme_desc %}
  …card body…
{% enddlux_option_card %}
```

`slug` becomes `data-options-card` (the reorder/deep-link key). Pass `attrs` for
extras such as `data-options-deeplink`. Cards registered through
`dlux.options.register_card()` are rendered through the same wrapper.

Block tags render their body into the partial as `content`, so the wrapper stays
editable markup (`dlux/tables/shell.html`, `dlux/base/card.html`,
`dlux/notifications/alert.html`) rather than HTML built in Python. Use them for
new markup; do not hand-write `dlux-table-shell`/`dlux-table-scroll` pairs.

The reusable form CSS and JavaScript are loaded by `dlux/forms/assets_head.html` and `dlux/forms/assets_scripts.html`. Keep new primitives compatible with those global, idempotent initializers so they also work after dynamic-modal replacement.

## Sections vs Dynamic Modals

Use sections when:

- the model is a simple auxiliary or lookup dataset
- you want a list + filter + modal CRUD flow with minimal code
- the model belongs in the system navigation automatically

Use dynamic modals when:

- the CRUD flow should be embedded inside another screen
- you need form-only, list-only, or read-only modal behavior
- the model should be managed from a custom trigger instead of the sections page

In both cases, the discovery system is the same. What changes is the entry point and the surrounding UI.

### Pinning buttons to the modal footer

The dynamic modal owns its header, scrolling body, and persistent footer. AJAX partials should return body content only: do not add another `.modal-header`, `.modal-body`, or `.modal-footer`, and use the trigger's `data-modal-title` for the single shell title. Legacy fragments that still return Bootstrap modal chrome are normalized automatically; their embedded title is promoted to the shell, non-title header context stays in the body, and their footer actions are pinned.

Built-in action bars (auto-form buttons, multi-step wizard controls, the System Settings wizard bar, and `_build_submit_actions` bars) are detected and moved into the pinned footer automatically.

For a **custom modal template** (a view that sets `template_name`, or a custom options screen), mark your own button container with `data-dlux-modal-footer` to have it pinned the same way:

```html
<form method="post" action="{{ request.path }}">
  {% csrf_token %}
  {% crispy form %}

  <!-- This bar is lifted into the sticky modal footer automatically -->
  <div class="d-flex justify-content-end gap-2" data-dlux-modal-footer>
    <button type="submit" class="btn btn-primary">Save</button>
    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
  </div>
</form>
```

Notes:

- The marked container takes priority over the built-in bars.
- Its buttons are associated to the modal form via the `form=` attribute, so AJAX submit interception and multi-step wizard navigation still work after relocation.
- The element is physically moved out of the modal body, so any custom JS for those buttons should use document-level event delegation rather than querying the modal body after load.

## Users, Profiles, and Permissions

The user side of DjangoLux has a few important defaults:

- every user gets a `Profile`
- preferences and 2FA state live on that profile
- the user-management flow uses the interactive modal wizard
- permission labels are translated dynamically instead of staying in raw Django English

If you extend user-facing workflows, treat `Profile` as part of the normal user contract rather than an optional extra.

## Translation and Scope Behavior

Two recent themes in DjangoLux are worth treating as first-class features, not side effects:

- translations are resolved with layered fallbacks, including user preferences, session state, config defaults, and runtime overrides
- scope behavior is auto-injected when enabled and removed when disabled

That means you should usually extend the system by leaning into those mechanisms rather than rebuilding them locally in each form, table, or view.

## Audit, Interaction, and Utility Subsystems

DjangoLux also includes a few subsystems that make it feel larger than a normal "app with some templates":

- Activity logging:
  the system captures login/logout, CRUD, merged User/Profile changes, diffs, and download/export events through signals and shared logging helpers.
- Context menus:
  generated or custom tables can emit URL actions or decoupled `dlux:record:*` events, which lets the UI layer stay interactive without hard-wiring custom JavaScript everywhere.
- Fetch/export helpers:
  `fetch_file()` and `fetch_excel()` provide package-level download/export behavior instead of every project reimplementing file handling and Excel generation.
- Productivity helpers:
  autofill, sticky forms, filter setup, and reusable list templates push common back-office UX patterns into shared infrastructure.

That cluster of subsystems is a big part of why DjangoLux should be treated like an internal platform layer, not just a widget library.

## vNext Tables and Filter Pages

If you are wiring a normal list screen today, the supported path is:

- extend `dlux/list_base.html`
- call `setup_filter_helper()` or `advanced_filter_helper()` in the view
- render the table with `{% render_table table %}` and do not wrap it in another `.table-responsive`
- prefer `dlux.tables.DluxTable` for handwritten tables

The current table contract is:

- stock `django_tables2` templates and no-template tables are auto-adopted into the Dlux renderer
- explicit non-stock custom templates are left alone unless you point them at the Dlux template yourself
- density precedence is `Table.Meta.dlux_density` -> `Profile.preferences["table_density"]` -> `SystemSettings.default_table_density` -> `balanced`
- page-size precedence is `Table.Meta.dlux_per_page` -> request `per_page` -> `Profile.preferences["table_page_size"]` -> `20`
- built-in per-page controls and the density switcher live in the framework-owned footer
- tables with forced `dlux_density` intentionally hide the footer density switcher
- default row actions are `dlux:record:view`, `dlux:record:edit`, and `dlux:record:delete`
- disable default row actions with `Meta.dlux_actions = False`
- customize the action list with `get_dlux_row_actions(self, record, base_actions)`

Typical handwritten table:

```python
from dlux.tables import DluxTable


class InvoiceTable(DluxTable):
    class Meta(DluxTable.Meta):
        model = Invoice
        fields = ("number", "customer", "status", "created_at")
        dlux_density = "balanced"
        dlux_per_page = 50
```

Filter pages also have a clearer contract now:

- `setup_filter_helper()` and `advanced_filter_helper()` default to inline placeholder labels for filter bars
- if you want normal external labels instead, pass `inline_labels=False`
- if a page cannot extend `dlux/list_base.html`, include `dlux/forms/filter_assets_head.html`

For Arabic keyword search, use `arabic_search_q()` instead of hand-rolled `icontains` chains so أ/ا, ي/ى, ة/ه, ق/غ, diacritics, and Arabic-Indic digits all match interchangeably:

```python
from dlux.utils import arabic_search_q


class DecreeFilter(django_filters.FilterSet):
    keyword = django_filters.CharFilter(method="filter_keyword", label="")

    def filter_keyword(self, queryset, name, value):
        return queryset.filter(
            arabic_search_q(value, ["title", "keywords", "category__name"])
        )
```

For the full contract and more examples, use:

- [Reference](reference.md)
- [Customization Guide](customization-guide.md)

## Where to Go Next

- Use the [Customization Guide](customization-guide.md) when you are ready to wire your own translations, sections, modals, or template overrides.
- Use the [Reference](reference.md) when you need commands, endpoints, template tags, or helper names quickly.
