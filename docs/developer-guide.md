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
- **Disabled scopes**: Resolved CRUD and section forms remove both the injected field and any matching nodes in a custom Crispy layout. A form helper may therefore include `scope` unconditionally; Dlux clones shared helpers before pruning them so a later settings change can re-enable the field safely.

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
destination: it is searchable, placeable in the Navbar hierarchy, and offered in
the sidebar builder behind the *Show form pages* toggle — but it is never added
to a zero-config sidebar and cannot be a landing page or a Navbar root. An
**id-bound page** (`chapter_edit`, `chapter_detail`) cannot be reversed without
arguments, so every feature that needs a real href drops it; only the Navbar
hierarchy accepts it, because its nodes match on route name and a URL-less crumb
renders as plain text.

API endpoints are excluded from every navigation profile. `api` is matched as an
exact token across the full URL namespace/name and resolved path, including
suffixes such as `records_api`, nested names such as `catalog:api:records`, and
callback class or function names such as `RecordsAPIView`. Ordinary names that
merely contain the letters, such as `rapid_report`, remain discoverable. Stored
sidebar/Navbar trees and imported/exported settings are sanitized by the same
rule; when an old API hierarchy node contains valid page children, those children
are kept.

Known entries in `SYSTEM_ROUTE_META` use that metadata's `group_key` before model
app-label inference, so `manage_users` remains in the dlux System group even
though the page is backed by `auth.User`.

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

- `DluxFileInput` from `dlux.widgets` for ordinary file uploads. Inside Crispy layouts, use `build_file_field()` so the file card, validation output, drag/drop behavior, toolbar, and translations stay intact. Do not write a raw `<input type="file">` in a Dlux-owned template.
- `DluxLookupField` from `dlux.forms` when a ForeignKey has more rows than a dropdown should hold, or when readers would otherwise create a second record for one that already exists. It renders a box you type into, reuses an exact name, refuses a near miss with what it resembles, and — given `create` — adds a record that genuinely is new. Do not hand-build a `<datalist>` and a hidden key beside a text input.
- `ManagedAssetField` from `dlux.models` for **any** model image or font — not `ImageField`. It supplies the picker, the instant permission-checked upload and the namespace that keeps one pool out of another's picker; pair it with `ManagedAssetFormMixin` from `dlux.forms` and place it with `build_asset_field()`. See `docs/managed-assets.md`.
- `AssetPickerField` from `dlux.forms` when a form field selects a reusable `ManagedAsset` without a model field behind it. Its file card opens the saved-file library as a dropdown popover and keeps upload/open/clear in the standard toolbar.
- `DluxChoiceSelectorWidget` and `DluxMultipleChoiceSelectorWidget` from `dlux.widgets` for card, chip, searchable single-choice, and multi-choice controls.
- Dlux icon picker through `dlux/helpers/icon_picker.html` and `initIconPickers()` for Bootstrap Icons fields inside System Settings/setup surfaces, including sidebar entry icons. It is lazy-rendered, searchable, keyboard-closeable, and owns the shared Bootstrap Icons catalog. The grid opens as a popover anchored under the field (the asset picker library's geometry) and closes on an outside click or Escape; pass `inline: True` in the include context for the older in-flow disclosure that pushes the following fields down.
- Dlux inspector shell through `dlux/helpers/inspector/css/main.css` and `dlux/helpers/inspector/js/main.js` for builder-style editors. `window.DluxInspectorShell.create(container, { adapter })` owns the bordered inspector surface, action row, pinned Clear selection action, and responsive field grid; the adapter owns the selected object, supported actions, field specs, mutation, and commit behavior.
- `build_settings_toggle_field()` and `build_email_toggle_field()` from `dlux.forms` for settings switches; do not hand-build Bootstrap switch markup. For a server-locked toggle, set `field.disabled = True` and `field.dlux_lock_reason`: the builder applies the shared dimmed dependent state, `aria-disabled`, and a Dlux tooltip to the whole card.
- `DluxTable` from `dlux.tables`, or the `dlux-table-shell` / `dlux-table-scroll` / `dlux-data-table` structure, for Dlux-owned data grids.
- Compact auxiliary tables inside System Settings that do not need the full `DluxTable` shell must still own a surface. Use the setup theme tokens such as `--dlux-setup-item-bg` and `--dlux-setup-item-border`; do not leave the body transparent against the modal. A sticky auxiliary header must layer `--dlux-table-header-surface` over an opaque `--table-row` backdrop so scrolling content cannot bleed through translucent theme gradients.
- The universal dynamic-modal protocol (`data-dynamic-modal`, JSON `{html}` fragments, and `data-dlux-modal-footer`) for modal workflows, and `window.DluxLoadingButton` for asynchronous button state.
- `data-dlux-context` plus the Dlux row-action schema for context menus, and `data-dlux-tooltip` for themed accessible tooltips instead of one-off menu/tooltip implementations.
- `from dlux.notifications import notify` for user-facing success, warning, and error feedback so drawer/history behavior remains consistent. Supply a stable `event_key` for retryable background events; automatic CRUD already keys durable delivery to its activity-log row and does not persist success back to the actor.

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

### Template comment audit

The repository utility scans HTML templates recursively for malformed short
comments that Django would leak as text: a wrong `%}` closer such as
`{# note %}`, or an unclosed `{# note`. It lists every match with its file and
line range and asks before removing anything:

```bash
python scripts/find_template_comments.py
python scripts/find_template_comments.py dlux/templates project/templates
python scripts/find_template_comments.py --include-valid
```

Use `--check` for a read-only CI-style run; it exits with status 1 when comments
exist. Use `--remove` for an explicit non-interactive cleanup. Correctly closed
`{# ... #}` and `{% comment %}...{% endcomment %}` comments are server-stripped
and omitted by default; `--include-valid` adds them to the inventory/removal.
Recursive scans skip dependency, generated-output, cache, and `.xpose`
directories by default; additional directory names can be excluded with
repeatable `--exclude` flags.

### Authenticated-page scroll boundaries

On authenticated screens, `#mainContent` is the viewport-height scroll pane; the
document itself must have no vertical scroll range. A Backup & Restore regression
showed why this distinction matters: its grid's overflow reached the document
scroller even though `document.body.scrollHeight` still matched the viewport.
After the inner pane reached its end, another wheel gesture scrolled the document,
revealing the transparent `<html>` canvas as a white block and moving the sidebar.

For a feature root that uses grid layout inside this shell, establish a page-local
layout boundary:

```css
.feature-page {
    contain: layout;
    display: grid;
}
```

Keep the boundary on the feature root, not `#mainContent`: global containment can
change the containing block for page overlays. Do not add wrappers as direct
children of a grid root unless they are meant to be another row. Browser coverage
must inspect `document.scrollingElement`, scroll `#mainContent` to its end, then
wheel once more and confirm the document remains at zero and the sidebar stays
under the titlebar. `tests-e2e/backup_page.test.mjs` is the reference guard.

## The list page

`dlux/list_page.html` is the framework's arrangement of a records screen: the
Ribbon, then the table, inside a `.dlux-list-page` wrapper. It extends
`dlux/list_base.html`, so the filter assets come with it.

```python
class InvoiceListView(SingleTableMixin, FilterView):
    template_name = "dlux/list_page.html"
    model = Invoice
    table_class = InvoiceTable
    filterset_class = InvoiceFilter
```

The context it reads:

| Key | Purpose |
| --- | --- |
| `ribbon` | the header band; `RibbonMixin` puts it there |
| `table` | rendered with `{% render_table %}` — no card wrapper, `DluxTable` owns its shell |
| `page_title` | the `<title>` |
| `extra_styles` | stylesheet paths, loaded through `dlux_static` |
| `extra_scripts` | script paths, loaded deferred with the page's CSP nonce |

Blocks, for a screen that needs more than the arrangement:

- `list_before_table` — a tab strip, a summary band, an expanding editor
- `list_body` — replaces `{% render_table table %}` outright
- `list_after_table` — totals, per-page switches, anything under the grid
- `list_modals` — page-owned modal markup, outside the wrapper
- `list_page_attrs` — attributes on the wrapper, for a project's own data hooks

This is a starting arrangement, not a constraint. The Ribbon and the table are
components: a screen that wants two columns, or the table somewhere else
entirely, sets its own `template_name` and places `{% dlux_ribbon %}` and
`{% render_table table %}` itself. Two things stay with the Ribbon either way —
the filter form renders inside it, and its own layout and buttons are what the
Ribbon builder in System Settings edits.

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

### The stacked manager modal

`DynamicModalManagerView.as_view(model=Warehouse, manager=True)` turns one route
into a self-contained manager: a list, a form and a detail view that replace each
other *inside* the modal, each under its own Ribbon, and none of which touches the
page behind it.

```python
path(
    "balances/warehouses/manage/",
    DynamicModalManagerView.as_view(
        model=Warehouse,
        manager=True,
        manager_icon="bi bi-building",
    ),
    name="warehouse_manager",
),
```

The route must not take a `pk` in its path — the three surfaces are addressed on
the one URL:

| URL | Surface | Ribbon |
| --- | --- | --- |
| `…/manage/` | the records list | title + Add |
| `…/manage/?action=add` | a create form | title + Back |
| `…/manage/?id=<pk>` | that record's form | record name + Back |
| `…/manage/?id=<pk>&action=view` | that record's detail | record name + Edit + Back |

`manager_title`, `manager_subtitle`, `manager_icon` and `manager_add_label`
override the ribbon copy; the title otherwise comes from the model's translated
`verbose_name_plural`. Ordinary models keep normal Django model permissions: the
list needs `view`, a form needs `add` or `change`, and Add appears only for a
user who may add. A model marked `is_section = True` uses section permissions in
manager mode instead: `dlux.view_sections` for read surfaces and
`dlux.manage_sections` for add/change/delete surfaces.

Rows address the manager's own surfaces because the view sets
`table.dlux_modal_manager_url`; the default row actions read it, and a table with
its own `get_dlux_row_actions` can read it too rather than pointing at a
record route that would navigate the page underneath. Delete actions also carry
`data.delete_url` for `/sys/modals/delete/<app>/<model>/<pk>/`, which keeps
modal-manager deletes independent from any CRUD listener on the page behind it.

Back is the framework's Back control: `btn btn-outline-secondary rounded-pill
dlux-back-link` with `bi bi-arrow-left`. Author a back arrow pointing left, as the
page reads in LTR, and give the control `dlux-back-link` — `base/css` mirrors the
icon under `[dir="rtl"]`, the same idiom as the table pagination chevrons.

A save in manager mode never refreshes the parent page — it returns to the
manager's list, which is also what a save does anywhere the modal has navigated
deeper than the surface it was opened on.

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
- Nothing is pinned when the body also carries a records list (`data-dlux-modal-list`, which the combined form+table template sets and a custom modal template can set itself): in the footer the form's Save would read as the submit for the table above it, so the action bar stays under its own form.

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

## Guided Tutorial Contract

The built-in tutorial reads the same resolved `window.DLUX_STRINGS` object as the rest of the active page. Do not add a tutorial-only JSON payload or global translation object. The previous implementation did both: step text requested unprefixed names such as `sidebar_title` even though the catalog key was `tut_sidebar_title`, while the control bar read a nonexistent `window.TUT_STRINGS`. Both paths silently reached their English literals even when the page language was Arabic.

Keep these invariants when extending the framework tour:

- pass exact catalog keys, including the `tut_` prefix, to the tutorial text helper
- define every new `tut_*` key in every shipped language; `test_translation_coverage.py` scans the tutorial JavaScript and enforces this
- target stable component classes or `data-*` hooks; candidates are resolved when the tour starts and only rendered elements become steps
- avoid assigning two descriptions to the same target; the resolver collapses duplicate elements
- keep Driver.js positioning LTR internally, but derive popover content, control direction, and alignment from the document `dir`

The browser regression in `tests-e2e/tutorial.test.mjs` changes a real user preference to Arabic, reloads Options, starts the real tour, and verifies Arabic step text, translated controls, RTL presentation, and current component coverage.

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
- add `RibbonMixin` to the view (see [Ribbon](ribbon.md)); on pages not yet migrated, call `setup_filter_helper()` or `advanced_filter_helper()`
- render the table with `{% render_table table %}` and do not wrap it in another `.table-responsive`
- prefer `dlux.tables.DluxTable` for handwritten tables

The current table contract is:

- stock `django_tables2` templates and no-template tables are auto-adopted into the Dlux renderer
- explicit non-stock custom templates are left alone unless you point them at the Dlux template yourself
- density precedence is `Table.Meta.dlux_density` -> `Profile.preferences["table_density"]` -> `SystemSettings.default_table_density` -> `balanced`
- page-size precedence is `Table.Meta.dlux_per_page` -> request `per_page` -> `Profile.preferences["table_page_size"]` -> `20`
- built-in per-page controls and the density switcher live in the framework-owned footer
- tables with forced `dlux_density` intentionally hide the footer density switcher
- `Meta.dlux_show_footer = False` (or the `dlux_show_footer=False` constructor kwarg) removes the footer entirely and renders every row, because the footer owns the paging controls
- dynamic modal manager tables set that kwarg themselves: a modal has no room for the toolbar and its paging links would navigate the page underneath
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
- [Project Configuration](project-configuration.md)
- [Translations](translation-guide.md)
- [UI Integration](ui-integration.md)
- [Template Customization](template-customization.md)

## Where to Go Next

- Use the [Customization Guide](customization-guide.md) when you are ready to wire your own extensions; it links to the focused translation, UI, project-configuration, and template references.
- Use the [Reference](reference.md) when you need commands, endpoints, template tags, or helper names quickly.
