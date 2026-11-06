# UI Integration

Use Dlux-native primitives before introducing a project-specific alternative. The
component catalog and import paths live in the
[Developer Guide](developer-guide.md#dlux-owned-ui-primitives).

**Contents**

- [Sections and dynamic modals](#sections-and-dynamic-modals) — modal contract,
  manager behaviour, [unsaved-changes guard](#unsaved-changes-guard),
  [dismissible dialogs](#dismissible-dialogs)
- [App preferences and app-owned settings](#app-preferences-and-app-owned-settings)
  — per-user and project-wide app data, Options tiles and cards, first-run setup
- [Global search](#global-search)
- [Search-and-add fields](#search-and-add-fields) — `DluxLookupField`
- [Inspector Shell](#inspector-shell) — builder editors
- [Tables, filters, and row actions](#tables-filters-and-row-actions)
- [Download helpers](#download-helpers)
- [Notifications](#notifications) — `notify()`, models, rules and `notification_config`
- [Activity logging](#activity-logging)
- [Tutorials and client behavior](#tutorials-and-client-behavior) — URL and JSON
  helpers, alert auto-close, Lux signature

## Sections and dynamic modals

Register small project-owned configuration or CRUD surfaces as sections and serve
modal content through the Dlux dynamic-modal contract. Modal endpoints return
`JsonResponse({"html": ...})`; returning raw HTML makes the client render the
response inline rather than opening the modal.

Keep authorization in the view as well as the card, action, or route discovery
metadata. Mutating actions are POST-only and require CSRF protection.

Manager deletes are guarded by related-record discovery. `manage_scopes`,
`manage_groups`, and `manage_sections` delete only records with no external
dependents; blocked deletes return the `related` payload the UI shows to explain
which records must be removed or unlinked first. Group preset deletion ignores
its `GroupProfile` sidecar and permission assignment M2M because those define the
preset itself, but users and membership history still block deletion.

The standalone `manage_sections` page renders its table directly; do not wrap
`{% render_table table %}` in a page-level card, because `DluxTable` already owns
the table surface. Its section form is a manage-only expandable editor above the
table. The normal browse state keeps the editor collapsed; the ribbon Add action
opens a blank form, a row Edit action opens the selected record's form, and
validation failures keep the editor expanded with bound errors. The Cancel action
removes only the add/edit state from the URL, preserving the active model and
filters.

Stacked dynamic-modal managers for `is_section` models use the same section
authorization: `dlux.view_sections` can open the list/detail surfaces, while
`dlux.manage_sections` can add, edit, and delete isolated section records. Their
row actions carry the modal delete endpoint in `data.delete_url`, so a delete
inside a manager posts to that manager record instead of a parent page's CRUD
handler.

A modal can be opened two ways, and the difference decides what Back does. A
section-manager modal opens on a *list* and navigates into a record, so its
`.dynamic-back-btn` returns to that list. A modal opened straight at one record —
a row action dispatching `dlux:dynamic_modal:open` with that record's URL, which
is how a modal-first project opens every view — has no list behind it, and there
Back closes the modal. Nothing is required of the caller; the helper compares the
URL it loaded against the one it was opened with.

Save behavior follows the modal surface. A successful form-only modal
(`DynamicModalManagerView.as_view(show_table=False)`) closes through a parent-page
refresh, so the originating list immediately includes the created or edited row.
A combined manager modal keeps its shell open and reloads its own table, and so
does a stacked manager (`manager=True`) at any depth — a modal that has navigated
past the surface it was opened on returns to that surface instead of reloading the
page behind it. Forms may set `refresh_parent = True` or `False` to override that
default; validation failures always replace the modal body with the bound form and
its errors.

Create forms that support successive entry should submit the secondary action as
`<button type="submit" name="save_add_more">`. The modal includes the clicked
submitter in the POST, recognizes that key as succession mode, refreshes the parent
list, and reopens a fresh create form. A form may also set `add_more = True` while
binding. Succession mode always outranks `refresh_parent`, including an explicit
`refresh_parent = True`; a normal Save still follows the surface default above.

With Entry clipboard enabled in Extra Features, eligible text fields support
manual snippets through an accessible clipboard-icon popover button beside the
sticky-form header switch; ribbons and Dlux reports are always excluded. Widget
attribute `data-dlux-entry-clipboard="false"` excludes a field or containing
element. Sticky forms continue to own automatic prefill and Save & Add More reuse
(see [Assisted entry](template-customization.md#assisted-entry)). Custom forms
without model capability markers receive the Assisted entry legend and clipboard
icon when enabled, without a sticky-reuse switch. Extending `form_base.html` alone
does not identify the model inside custom form markup. The popover uses icon
actions beside its field/search controls and compact snippet rows with
insert/replace actions; entry text opens a full-content view with Back. See
[Entry clipboard](entry-clipboard.md) for eligibility and storage rules.

When `manage_sections` has to build a layout for a section form with no
developer-provided Crispy helper, it renders every visible non-hidden field in a
two-column grid (`col-12 col-lg-6`) with the translated field label preserved on
the control. Selects, text inputs, date inputs, textareas, file fields, and Dlux
file widgets all use the same row rhythm.

BooleanFields named `is_active`, `active`, `enabled`, or `is_enabled` are treated
as footer controls and render as Dlux settings toggles. Generated section forms
place the Dlux Save action in that footer, with Cancel pointing back to the
table-only state. A custom form can opt another BooleanField into the same footer
by setting `field.dlux_footer = True`, `field.footer = True`,
`field.on_footer = True`, or widget attr `data-dlux-footer="true"`. Forms with
their own helper can expose `form.dlux_footer_bound_fields` to let Dlux append
the same footer without replacing the form's custom layout; if that helper
already supplies a submit control, Dlux appends only the footer fields and leaves
the form's actions alone.

System Settings -> Sidebar stores `sidebar_config.show_sections_manager`. When
false, the runtime hides the sidebar toolbar shortcut — and only that. The page
stays reachable, because `manage_sections` is offered in the sidebar and ribbon
builders as a configurable system item that an admin may have placed there
deliberately. Who may open it is a permission question, not a chrome one.

### Unsaved-changes guard

A modal form that sets `form.dlux_unsaved_guard = True` renders with
`data-dlux-unsaved-guard`, and `unsaved_guard.js` intercepts `hide.bs.modal` —
the single event behind the backdrop, the X button and Escape — when the form's
values differ from the snapshot taken after its initializers settle. The
`#dluxUnsavedModal` prompt offers:

- **Save** — submits through `requestSubmit` with the form's named submitter, so
  the form's own validation runs;
- **Discard** — closes and drops the edits;
- **Go back** — cancels the close and returns to the form.

Only one prompt is open at a time, and Save submits once, even though a click on a
dynamic modal's X raises `hide.bs.modal` twice (Bootstrap's dismiss handler and
`dynamic_modal`'s) and both reach the guard.

Project settings tiles ([`register_app_settings`](#settings-tiles-in-options))
are guarded by default: their form renders the marker unless it sets
`dlux_unsaved_guard = False`, so a `form_class` that only makes sense to close
freely can opt out.

Dirtiness is a value snapshot rather than an input listener on purpose: the
System Settings form rewrites its own hidden JSON carriers during init and live
preview, dispatching synthetic events that would otherwise mark it dirty
immediately. A scratch input that only wires a shared component (a builder's
icon field) carries `data-dlux-unsaved-ignore` and is left out of the snapshot;
see [Icon pickers in a builder](#icon-pickers-in-a-builder).

The prompt's "don't ask again" switch stores the `skip_unsaved_settings_prompt`
user preference; while it is set, a dirty close discards without prompting. This
is intentionally not a standalone Options toggle: the Options footer's
**Restore prompts** action clears the dismissal and shows the warning again (see
[Dismissible dialogs](#dismissible-dialogs)).

### Dismissible dialogs

Any prompt with a "don't show again" switch should register itself, so the
Options footer's **Restore prompts** action can bring it back. Without that, the
opt-out is a one-way door:

```python
from dlux.dialogs import register_dismissible_dialog

register_dismissible_dialog(
    id='archive.install_app',          # stable slug, [A-Za-z0-9._-], namespaced
    label='Install as app prompt',     # shown to developers/operators
    app_namespace='archive.pwa',       # preferences['app']['archive.pwa']
    app_preference_key='dismissed',    # ...['dismissed']
    description='The add-to-home-screen prompt.',
)
```

Call it once at startup (an `AppConfig.ready()` is the natural place). Dismissal
state can live in any of:

| Argument | Stored in |
| --- | --- |
| `preference_key` | a top-level key in `Profile.preferences` (Dlux-owned) |
| `app_namespace` + `app_preference_key` | `Profile.preferences['app'][<namespace>][<key>]` — the right home for project prompts |
| `profile_field` | a boolean field on `Profile` (Dlux-internal; projects cannot add fields to Dlux's `Profile`) |

At least one location is required, and `app_namespace` and `app_preference_key`
are given together. Registering the same `id` twice replaces the earlier entry,
so a module imported more than once does not accumulate duplicates.

`POST /sys/api/preferences/dialogs/reset/` (`reset_dialog_prompts`) clears every
registered dismissal for the current user and returns
`{"success": true, "reset": <n>, "registered": <n>}`. It is deliberately narrower
than `reset_preferences`: theme, density, language and every other preference are
left alone, and only the dismissed key is removed from an app namespace — other
keys in that namespace survive. Dlux registers two built-ins: the unsaved-changes
warning, and the first-login Initial User Setup modal.

## App preferences and app-owned settings

A project keeps its own UI state and configuration in two reserved, opaque
namespaces, and can surface the configuration in Options and first-run setup
without touching Dlux's own forms:

| Store | Scope | Written by | Read with |
| --- | --- | --- | --- |
| `Profile.preferences['app'][<ns>]` | one user | that user | `window.getAppPreference()` |
| `SystemSettings.extra_config['app'][<ns>]` | whole project | superusers | `get_app_system_config()` |

Settings tiles and Options cards are registered from `<yourapp>/dlux_options.py`.
Dlux autodiscovers and imports that module for every installed app; registration
is trusted Python run once at startup, and there is no HTTP, database or settings
path that injects a tile or card.

### Per-user app preferences

Downstream projects can persist their **own** per-user state (dashboard layouts,
saved views, collapsed panels, …) so it follows the user across browsers and
devices, without adding a model. It lives under a single **reserved top-level
key** in `Profile.preferences`:

```jsonc
// Profile.preferences
{
  "theme": "dark",                 // Dlux-owned keys (validated by Dlux)
  "app": {                          // reserved namespace — opaque to Dlux
    "myproject.dashboard.v1": { "order": [3,1,2], "hidden": ["kpis"] }
  }
}
```

Dlux never inspects the shape of anything under `app`; it only merges at the
namespace level and enforces the size cap. A namespace key is any string of up to
128 characters (dotted by convention); prefix it with your project to avoid
collisions.

- **Bulk write** — `POST /sys/api/preferences/update/` (`update_preferences`)
  with `{"app": {"<ns>": <value>}}` merges that namespace, preserving sibling
  namespaces and Dlux keys. A `null` value clears a namespace.
- **Targeted, concurrent-safe write** —
  `POST /sys/api/preferences/app/<namespace>/` (`update_app_preference`) with the
  namespace's new value as the JSON body writes *only* that namespace, so two tabs
  writing different namespaces do not clobber each other. A `null` body clears it.
  Returns `{status, namespace, value}`.
- **Size cap** — the whole `Profile.preferences` blob is inlined into every
  authenticated page as `window.USER_PREFS`, so a hard ceiling applies. Writes
  that would exceed it are rejected with **HTTP 413**. Default 64 KB; override
  with `settings.DLUX_MAX_PREFERENCES_BYTES` (never below 1 KB).

Browser helpers (global, defined alongside `window.updatePreferences`):

```js
// read (from the inlined window.USER_PREFS.app, no request)
const layout = window.getAppPreference('myproject.dashboard.v1', { order: [] });

// write just this namespace (targeted endpoint); returns the fetch Promise
window.updateAppPreference('myproject.dashboard.v1', layout)
  .then(res => { if (res.status === 413) { /* too large */ } });

// clear it
window.updateAppPreference('myproject.dashboard.v1', null);
```

`updateAppPreference()` mirrors a successful write into `window.USER_PREFS.app`,
so a later `getAppPreference()` sees it. `window.updatePreferences(data)` writes
Dlux-owned keys and also returns the `fetch` promise. Anything that navigates or
reloads after saving a preference must await it, or the navigation races the POST
and the new page renders the old value.

Both helpers resolve their endpoint through `window.dluxEndpoint()`, so they work
in mounted and language-prefixed projects; project scripts should do the same
(see [URL and JSON helpers](#url-and-json-helpers)).

`localStorage` remains a fine fallback/migration layer — read it if
`getAppPreference` returns your default, then write through to the namespace so
the value becomes cross-device.

### Project-wide app config

The global, project-wide counterpart of the per-user `app` namespace. Downstream
projects store opaque JSON under a reserved key in `SystemSettings.extra_config`:

```jsonc
// SystemSettings.extra_config
{ "app": { "myproject.settings": { "feature_x": true } } }
```

- **Write over HTTP** — `POST /sys/api/system-config/app/<namespace>/`
  (`update_app_system_config`) with the namespace's new value as the JSON body.
  It is **superuser-only** (non-superusers get 403), POST + CSRF, and
  namespace-scoped: only `extra_config['app'][<ns>]` is touched, so it can never
  reach Dlux's own settings or other keys. The namespace must match
  `[A-Za-z0-9._-]` (up to 128 characters). Writes are size-capped (**HTTP 413**;
  default 64 KB, override `settings.DLUX_MAX_SYSTEM_APP_CONFIG_BYTES`),
  **audit-logged**, and refresh the config cache. A `null` body clears the
  namespace.
- **Read** — `from dlux.utils import get_app_system_config`;
  `get_app_system_config('myproject.settings', default)`. It reads through the
  cached `get_system_config()`, where a stored namespace replaces only that
  namespace from `DLUX_CONFIG['extra']['app']`; the project's other namespaces
  stay.
- **Write from Python** — `from dlux.options import write_app_system_config`;
  `write_app_system_config('myproject.settings', {...}, request=None)` for
  server-side writes (migrations, management commands, signals). It applies the
  same namespace validation, size cap (raises `AppSystemConfigError`),
  persistence, and cache refresh as the endpoint, and audit-logs when a `request`
  is passed. Pass `value=None` to clear the namespace.
  `write_app_system_configs({namespace: value, ...}, request=None)` writes several
  namespaces in one save.

Single and grouped writers lock the authoritative settings row and update only
`extra_config`, preserving independent namespace and scalar-setting changes.
Core settings imports use supplied-key patch semantics by default; complete
forms and snapshot restores explicitly replace their groups. See
[Settings persistence contracts](system-configuration.md#settings-persistence-contracts).

Because it is opaque JSON written only by superusers into a walled-off key, it
cannot be used to tamper with security-relevant Dlux configuration. Card
templates that display this data get Django's auto-escaping — do **not** `|safe`
it.

### Settings tiles in Options

If a downstream app has project-level settings worth exposing, register a
settings surface with `register_app_settings()`. Dlux adds one tile per
registered namespace to the Options admin settings grid, visible to superusers
only. The tile opens a modal (`/sys/options/app-settings/<namespace>/`) that is
separate from `SystemSettingsForm` and saves only `extra_config['app'][namespace]`.

Simple built-in controls:

```python
# myapp/dlux_options.py
from dlux.options import register_app_settings

register_app_settings(
    namespace="myproject.catalog",
    title="Catalog Settings",
    description="Project-wide catalog defaults.",
    icon="bi-grid",
    fields=[
        {
            "name": "enabled",
            "type": "boolean",
            "label": "Enable catalog",
            "help_text": "Show catalog navigation and catalog-specific actions.",
            "default": True,
        },
        {
            "name": "default_view",
            "type": "choice",
            "label": "Default view",
            "choices": [("grid", "Grid"), ("table", "Table")],
            "default": "grid",
            "control": "selector",
            "variant": "toggle",
            "option_meta": {
                "grid": {"icon": "bi-grid"},
                "table": {"icon": "bi-table"},
            },
        },
        {
            "name": "page_size",
            "type": "integer",
            "label": "Default page size",
            "default": 24,
            "min_value": 1,
            "max_value": 200,
        },
    ],
)
```

| Argument | Default | Purpose |
| --- | --- | --- |
| `namespace` | required | The `extra_config['app']` key the tile saves (`[A-Za-z0-9._-]`, up to 128 characters). |
| `title` | required | Tile and modal heading; see translation below. |
| `description` | `''` | Text under the title. |
| `fields` / `form_class` | — | Built-in controls, or a custom form. Supply exactly one. |
| `defaults` | `{}` | Values used when the namespace holds none for a field. |
| `icon` | `'bi-sliders2'` | Bootstrap-Icons class. |
| `order` | `100` | Sort weight; lower sorts first. |
| `visible` | `None` | `callable(request) -> bool`; fails closed (a raising check hides the tile). |
| `group` | `None` | The [group tile](#grouping-several-settings-into-one-tile) to appear in. |
| `setup` | `True` | Include the tile in [first-run setup](#app-settings-in-first-run-setup). |

Supported field `type` values are `boolean`, `choice`, `multiple_choice`,
`char` (the default), `text`, `integer`, `number`, and `json`. `choice` and
`multiple_choice` require `choices`, and can use Dlux's selector widgets with
`control="selector"` and `variant="card"` or `"toggle"`. Other spec keys are
`required`, `min_value`/`max_value` (numbers), `max_length` (`char`), `rows`
(`text`) and `css_class` (the layout column). Existing unknown keys in the
namespace are preserved when the generated form saves, so adding or removing
surfaced fields does not wipe other app-owned data.

**Titles, descriptions and labels that follow the reader's language.** Pass a
lazy string — a plain `str` is resolved once, at import, and freezes the tile to
whichever language happened to be active when the worker booted:

```python
from django.utils.translation import gettext_lazy as _

register_app_settings(
    namespace="myproject.catalog",
    title=_("Catalog Settings"),                    # lazy: resolved per request
    description=_("Project-wide catalog defaults."),
    fields=[{"name": "enabled", "type": "boolean", "label": _("Enable catalog")}],
)
```

`title` and `description` accept a string, a lazy string, `f(request)`, or
`f()` — both callable shapes, because both read naturally and neither should be
a trap. A callable of any other shape raises at registration, where the mistake
is, rather than on the Options page later. Field `label` and `help_text` are
handed to the form field untouched, so a lazy value stays lazy there too.

If a title or description raises while the page is being built, the tile is
still shown with its namespace as the title and the error is logged: text is
cosmetic, and hiding a whole settings surface over it reads to an operator as
the page losing their settings. `visible()` is the exception and fails closed,
because that one is a permission decision.

Custom form escape hatch:

```python
from django import forms
from dlux.options import register_app_settings

class CatalogSettingsForm(forms.Form):
    label = forms.CharField(max_length=80)

    def to_app_config(self, current_value):
        value = dict(current_value or {})
        value["label"] = self.cleaned_data["label"].strip()
        return value

register_app_settings(
    namespace="myproject.catalog",
    title="Catalog Settings",
    form_class=CatalogSettingsForm,
    defaults={"label": "Catalog"},
)
```

The form receives `data` and `initial` (the stored value), plus whichever of
`request`, `namespace`, `current_value`, `settings_definition` and `prefix` its
`__init__` accepts by name or through `**kwargs`. `to_app_config(current_value)`
decides the saved value; without it, the cleaned data is merged into the stored
value.

### Grouping several settings into one tile

A project with several small settings surfaces can show them as one tile instead
of one tile each. Register the tile with `register_app_settings_group()` and
name it in each `register_app_settings(group=...)`:

```python
from dlux.options import register_app_settings, register_app_settings_group

register_app_settings_group(
    id="myproject.store",
    title=_("Store options"),
    description=_("Store-wide settings for the catalog and the till."),
    icon="bi-sliders",
    order=50,
)

register_app_settings(
    namespace="myproject.catalog", title=_("Catalog"),
    group="myproject.store", order=10, fields=[...],
)
register_app_settings(
    namespace="myproject.till", title=_("Point of sale"),
    group="myproject.store", order=20, form_class=TillSettingsForm,
)
```

Each grouped registration becomes a section of the tile's modal
(`/sys/options/app-settings-group/<group_id>/`), under the same `<h6>` section
headings core settings steps use, ordered by its own `order`, with its `title` as
the heading and its `description` beneath. Its form is built exactly as its own
tile would build it, with field names prefixed by
`app_settings_form_prefix(namespace)` so sections cannot clash. Every section
validates before anything is saved, and all of them land in **one** write of the
settings row through `write_app_system_configs({namespace: value, ...})` — never
one load-and-save per section. Each keeps its own `extra_config['app'][namespace]`,
so code reading a namespace does not change when it joins a group.

- A group whose `visible()` returns false or raises hides its tile (fail
  closed); a group with no visible sections shows no tile.
- A registration naming a group that was never registered keeps its own tile.
- `/sys/options/app-settings/<namespace>/` still opens one section on its own,
  for links that point at a single namespace.
- The group modal carries the [unsaved-changes guard](#unsaved-changes-guard)
  unless a section's form sets `dlux_unsaved_guard = False`.
- `registerAppPreview()` previews apply to standalone tiles; the group modal
  offers no Preview action.
- `get_visible_app_settings()` lists every registration;
  `get_visible_app_settings_tiles()` is the folded list the Options page draws.

### Previewing app settings

An app's settings preview is a page of its own, rendered by the server with the
unsaved app form — the same mechanism as core System Settings (see
[Unsaved previews](system-configuration.md#unsaved-previews)). The shared
app-settings template includes a hidden Preview action; registering the namespace
makes it available and names the page to render:

```javascript
const unregister = window.DluxSetupPreview.registerAppPreview('myproject.catalog', {
  path: '/catalog/',            // or (form) => '/catalog/?view=' + form.elements.default_view.value
  audience: '',                 // 'anonymous' to render a public page as a visitor sees it
});
```

Preview POSTs the app form to `system_settings_preview_draft` with
`_dlux_preview_kind=app`; the server builds it with `build_app_settings_form()`
and `get_app_settings_form_value()` exactly as a save would, places the value at
`extra_config['app'][<namespace>]` of a draft that is never saved, and renders
`path` with it in the popup. Anything the page reads through
`get_app_system_config()` shows the unsaved value; nothing is written.

`registerAppPreview()` throws without a `path`. The returned `unregister()`
removes the registration and hides the Preview action again.

### App settings in first-run setup

Every tile registered with `register_app_settings()` also appears in the setup
wizard, in a **Project Settings** step after Dlux's own (so it is the last step
and no Dlux step changes index). Each tile is one section of that step, built
with the same `build_app_settings_form()` its Options modal uses, with its field
names prefixed `app__<namespace>-` (non-alphanumerics become `_`) so sections
cannot clash with each other or with Dlux's fields. A custom `form_class` gets the
prefix through its `prefix` argument or `**kwargs`; one that accepts neither has
`form.prefix` set after construction, so markup its `__init__` builds would miss
it. A tile whose form cannot be built is logged and left out of setup; it stays
reachable from Options.

Sections validate with the rest of the wizard, and every section reports its
errors in the same round. On finish, each value comes from
`get_app_settings_form_value()` (so `to_app_config()` still decides it) and is
merged by `merge_app_system_config()` — the size and JSON checks
`write_app_system_config()` applies — into the row the wizard saves, in that one
save. A refused value is shown on its section and nothing is saved.

Pass `setup=False` to keep a tile out of setup, e.g. settings that only make sense
once data exists. The step appears only when at least one visible tile remains.

### Options-page cards

Downstream apps add cards to `/sys/options/` with `register_card()` in
`<yourapp>/dlux_options.py` — the only supported path:

```python
# myapp/dlux_options.py
from dlux.options import register_card


def _settings():
    from dlux.utils import get_app_system_config
    return get_app_system_config("myproject.settings", {})


register_card(
    id="myproject.dashboard",          # [A-Za-z0-9._-]; the data-options-card value, and the
                                       # slug for /sys/options/#dlux-option-<id> deep links
    title="Dashboard Layout",          # str, or callable(request)->str for i18n
    icon="bi-grid",                    # Bootstrap-Icons class(es)
    template_name="myapp/options/dashboard_card.html",  # rendered as the card *body*
    order=100,                          # lower sorts first
    superuser_only=False,               # or permission="myapp.change_thing"
    context_builder=lambda request: {"settings": _settings()},  # optional
    search_keywords=("layout", "تخطيط"),  # optional global-search synonyms
    visible=lambda request: _settings().get("enabled", True),   # optional, fail-closed
)
```

`visible` is an optional `callable(request)->bool` for **config-driven
visibility** — e.g. show the card only when a feature is enabled in
`extra_config`. It is evaluated server-side *after* `superuser_only`/`permission`,
and **fail-closed**: if it raises, the card is hidden.

The card is also a **global-search result**, deep-linking to
`/sys/options/#dlux-option-<id>`. Its entry is built per request — so the label
is whatever `title(request)` returns in the user's language, and the same
`superuser_only`/`permission`/`visible` gates decide who can find it. Matching
uses that label plus `search_keywords`, which are **not** translated: list the
synonyms for every language you ship.

Your template renders only the card body; Dlux supplies the surrounding card
chrome (heading, drag handle) and includes it in reordering/tabs like any
built-in card. The card body context is your `context_builder` output plus
`request`, `user`, and `DLUX_STRINGS`. Guarantees:

- **Server-side gating** — `superuser_only`/`permission` are enforced before the
  builder runs or the template renders.
- **Sandboxed** — a card that raises is logged and skipped; it can never blank
  the Options page.
- **Lifecycle hook** — after `options.js` initializes it dispatches
  `document`-level `dlux:options-ready` (`event.detail.cardIds` lists all
  rendered cards); attach your card's JS there instead of patching `options.js`.

### Auto-persisting a card control

Rather than wiring `updateAppPreference` by hand, mark any control inside your
card with `data-dlux-app-pref="<namespace>"`. On `change`, Dlux writes its value
to that per-user `app` namespace and fires a `document`-level
`dlux:app-pref-changed` event (`detail: {namespace, field, value}`) so you can
apply it live:

```html
<!-- scalar value -> USER_PREFS.app["myproject.catalog_layout"] = "table" -->
<select data-dlux-app-pref="myproject.catalog_layout">
  <option value="grid">Grid</option>
  <option value="table">Table</option>
</select>
```

```js
document.addEventListener('dlux:app-pref-changed', (e) => {
  if (e.detail.namespace === 'myproject.catalog_layout') applyCatalogLayout(e.detail.value);
});
```

A checkbox persists its `checked` state; other controls persist their `value`.
Add `data-dlux-app-pref-field="<key>"` to merge one field into an object-valued
namespace instead of replacing it. Controls in the initial page are bound
automatically; call `window.bindAppPrefControls(root)` after injecting new DOM.

Resolve the effective value app-side as *user pref → global default*, e.g.
`window.getAppPreference('myproject.catalog_layout', globalDefault)`, where the
global default comes from `get_app_system_config(...)`. Dlux's **Reset Defaults**
clears the `app` namespace along with the rest, so a reset falls back to the
global default.

## Global search

Global search has its own System Settings step and canonical `search_config`
JSON:

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `true` | Renders the titlebar control and enables its endpoint. |
| `display_mode` | `icon` | `icon` expands on focus; `always` keeps the field shown. |
| `include_data` | `false` | Also permits searching viewable data records. |

Below 768px, `always` intentionally uses the icon interaction too; activating
either mode opens the field and results below the titlebar instead of consuming
its width.

New code should read `search_config`; the titlebar receives it as the `search`
template context. Through v1.x, `titlebar_config.global_search_mode` (`disabled`,
`icon`, or `always`) and `titlebar_config.global_search_include_data` are still
accepted, and canonical saves are mirrored back to them; they are removed in v2.0
(see [Deprecation Countdown](deprecation-countdown.md#global-search-titlebar-aliases)).

The titlebar control is served by the `login_required` JSON endpoint
`global_search` (`/search/?q=…`). It returns permission-filtered, translated
results grouped by type. Result labels follow the viewer's language (resolved
with Dlux's own `get_current_language_code`: session preview → profile preference
→ session → config; the index is cached per language), so an Arabic UI returns
Arabic results and an Arabic query matches:

- **Pages** come from the global route discovery through the `search` profile,
  filtered by each route's inferred permissions. That profile accepts form pages,
  so an add page such as `chapter_add` is findable by name; id-bound pages
  (`chapter_edit`) are not, since a search result needs a URL that resolves
  without arguments.
- **Settings** are one result per System Settings step, each deep-linking to the
  same step-scoped dynamic modal the Options page uses (superuser-only). Selecting
  one dispatches `dlux:dynamic_modal:open` from `document.body` with
  `bubbles: true`; the modal helper listens on `document`, which also receives the
  element-dispatched events table row actions emit. Each settings result also
  carries a `fallback_url` pointing at the admin panel card
  (`#dlux-option-admin-panel`), used when the page has no dynamic-modal host so a
  click is never silently inert.
- **Options** are the Options-page user-preference cards (theme, language,
  accessibility, typography, densities, modal size, nav-bar mode, landing page,
  autofill), visible to every authenticated user, plus the cards apps register
  with [`register_card()`](#options-page-cards). Only cards the current
  configuration actually renders are indexed — a single-language install returns
  no Language result, a single-theme install no Theme result, and the same
  applies to `allow_user_home_url`, `allow_user_font_override`,
  `navbar.allow_user_mode_override`, and `sidebar.allow_user_density`.
- **Actions** are curated titlebar/nav shortcuts (My Profile, Options).
- **Data**, only when `search_config.include_data` is on **and** the request
  passes `?data=1`, searches `icontains` across the text fields of the project's
  real models (the activity-log model set plus User/Profile), gated by each
  model's `view` permission; scoped models are row-filtered automatically by
  `ScopedManager`. Fields whose names suggest secrets (password, token, hash, …)
  are skipped, and a numeric query also matches the primary key.

The component index is keyed on the sidebar cache version, which
`SystemSettings.refresh_cache()` bumps on save, so configuration changes take
effect at once. An Options result deep-links to `/sys/options/#dlux-option-<slug>`
and scrolls to the card. Under the tabbed Options layout the target card usually
sits in an inactive pane, so the deep link activates that pane before scrolling.
A `hashchange` handler re-runs the same logic, because selecting a second Options
result while already on the page changes only the hash and never reloads.

Two optional settings tune the data provider:

- `DLUX_SEARCH_DATA_MODELS` — an allowlist of `app_label.model` strings; when
  set, only these models are searched (otherwise the default heuristic set is
  used).
- `DLUX_SEARCH_DATA_URL_RESOLVER` — dotted path to a callable `obj → url` that
  produces the click-through URL for a data result. Without it, results link
  only when a `<model>_detail`, `<model>_update` or `<app_label>_<model>_detail`
  route exists, and are shown non-clickable otherwise.

## Search-and-add fields

A dropdown makes a reader scroll a register of hundreds; a free text box makes a
second "Acme Trading" the moment somebody types a space differently. A lookup
field (`DluxLookupField`) is the middle, and a form declares one field to get it:

```python
from dlux.forms import DluxLookupField

class InvoiceForm(forms.ModelForm):
    supplier = DluxLookupField(
        queryset=Party.objects.filter(kind='company', is_active=True),
        create={'kind': 'company', 'subtype': 'supplier'},
    )
```

That is the whole adoption. No companion fields, no `clean()`, no `save()`, no
template, no script.

**What is derived.** The queryset a `ModelChoiceField` already carries *is* the
search scope, so searching needs no configuration. Only `create` has to be
stated, because what a new row must be is not derivable from a queryset. Passing
the same mapping used to scope the queryset is usually right: it keeps a record
created here findable by the field that created it.

| `create` | Behaviour |
| --- | --- |
| omitted / `None` | **Search only** — the default. A name matching nothing is a validation error, and the control never offers to add. |
| `True` | Add a record carrying only the name. |
| `{...}` | Add a record carrying the name plus these values. |

Adding is opt-**in**: a field left as it comes searches a fixed list and nothing
else, which is what most fields want. On such a field a near miss is reported as
a suggestion — *"No entry called X. Did you mean Y?"* — and the consent box is
not rendered at all, because offering to add on a field that cannot add is a
dead end.

**What a typed name means**, in order — only the last is a new record:

1. an exact name (case- and space-insensitive) is *that* record, reused;
2. a name close to an existing one is refused, naming what it resembles;
3. anything else is new.

Case 2 is a question rather than a verdict, because two real bodies can have
near-identical names. The widget renders the suggestion as a one-click button
and a consent box beside it; a submit carrying that consent goes ahead. Consent
never duplicates an *exact* name — it answers "is this a typo?", not "make me a
second copy".

**Arabic.** Names are folded before comparison — hamzated alef to alef, `ة` to
`ه`, `ى` to `ي`, tatweel and harakat dropped — so the ways the script writes one
letter do not read as typos. `شركه النور` *is* `شركة النور`: reused exactly,
nothing to confirm. Latin text contains none of these, so other alphabets are
unaffected.

**Tuning.** The defaults lean towards catching typos, which is the right trade
when a false positive costs one click and a false negative costs a duplicate. A
register of part numbers or postcodes will want its own values.

| Argument | Default | Purpose |
| --- | --- | --- |
| `create` | `None` | What a new record must be, or search-only. |
| `search_field` | `'name'` | The attribute searched and written. |
| `near_ratio` | `0.90` | How alike two names must be to be treated as a typo. |
| `boilerplate_share` | `0.15` | A word on this share of the register stops distinguishing anything in it. |

**How it posts.** One field name carries both: a key when a row was picked, the
typed name otherwise, so tests and API callers can post either. `<name>__typed`
and `<name>__confirm` ride alongside and belong to the widget — a form never
declares them. Matching runs on the server, so a form posted without the script
resolves identically; the script only ranks the rows as you type.

**Notifications.** A record the field adds is logged like any other create, but
does not flash at the actor: adding it was a side effect of saving the form, not
a second act, and automatic CRUD would otherwise announce it as one. The parent
object's own banner is unaffected.

**Why a name that matched nothing is unsaved.** The field returns an *unsaved*
instance, and `dlux.patches` writes it immediately before the form's own object.
Validating a form must never write, or a form failing a later rule leaves a
record behind.

## Inspector Shell

Use the Dlux inspector shell for builder-style editors that need a selected
object, a contextual action row, and a compact field grid. Include
`dlux/helpers/inspector/css/main.css` and `dlux/helpers/inspector/js/main.js`,
then create it with `window.DluxInspectorShell.create(container, { adapter })`.
The Nav Bar, Sidebar and Ribbon builders run on it, as do the table-column
builder and the weather settings.

The adapter owns meaning and persistence. It may provide `getSelection()`,
`getTitle()`, `getSubtitle()`, `getBadge()`, `getActions()`, `getFields()`,
`clearSelection()`, and `commit()`. Actions render in the order returned by the
adapter; the shell adds a pinned Clear selection action by default. Field specs
cover `text`, `url`, `number`, `email`, `textarea`, `select`, `toggle`,
`localized-text`, and `custom`. Use `custom` for controls that already own their
own markup, such as the shared icon picker.

An action may be `type: 'toggle'`, rendered as a switch in the action row and
reporting the value it now holds to `onChange`. Use it for per-entry on/off state
that belongs beside the actions rather than among the fields.

The editor panel carries the selection's header and fields only, so it is hidden
whenever nothing is selected. An adapter that offers an action with no selection
(Nav Bar's Add Group) therefore renders an action row alone, not an empty card.

Fields flex into the row they are given: they share the available width evenly
and wrap once each would fall below `--dlux-inspector-field-min` (12rem). Set that
custom property on the host to change where they wrap; `fullWidth` fields and
`textarea`/`localized-text` still span the whole row.

Rendering is never persistence. `render()` may be called after selecting an item
without making the settings form dirty. Mutations should happen in action or
field callbacks, and persistence should happen through `commitOn`, by returning
`{ commit: true }`, or by calling the adapter's `commit()` from the shell event
flow. That separation is required for System Settings exit guards. A builder that
rewrites a hidden System Settings field calls
`window.DluxSetupPreview.applySystemSettingsPreview(form)`, which schedules a
re-render of the draft page behind the Options modal (see
[Unsaved previews](system-configuration.md#unsaved-previews)).

### Popover presentation

The default presentation is inline. Pass `presentation: 'popover'` when the
field editor should float over the builder instead of reserving form height; the
action row stays inline and the selected editor panel becomes an anchored
popover spanning the host's width. `actionsPlacement: 'panel'` moves the action
row inside the popover, above the fields.

Give a popover an anchor. `getAnchor()` returns the element the panel belongs to
— usually the selected row — and the shell places the panel just below it, or
just above it when there is no room below, never over it. The panel follows the
anchor on scroll and resize, and hides itself while the anchor is scrolled out of
view. Without an anchor the panel falls back to hanging off the bottom of the
shell host, which pins it to the top of the builder where it covers the first rows
of whatever sits below.

The panel is a popover, and a layer a field opens over it — an icon picker's
dropdown — is another. That layer floats outside the panel and is not confined by
it: it is not measured into the panel's placement, and it is never clipped or
resized to fit. The panel is correspondingly never given a height cap, because a
capped panel scrolls and a scrolling panel clips exactly that layer; when it is
too tall for either side it takes the roomier one and is nudged inside the visible
band whole. Placement measures the panel's own box, never its `scrollHeight` — an
out-of-flow layer inflates a scroll container's overflow without being part of it.

Room is measured inside whatever actually clips the panel — every scrolling or
`overflow: hidden` ancestor, intersected with the viewport — not the viewport
alone. In a dynamic modal (`.modal-dialog-scrollable` gives the body
`overflow-y: auto` and the content `overflow: hidden`) there is usually screen
below the modal but none inside it; measuring the viewport would put the panel
past the modal's edge, clipped out of sight and lengthening the modal's scroll
area. When the panel fits on neither side it caps its height to the roomier one
and scrolls its own content, so it degrades to cramped rather than invisible.

`dismissOnOutsideClick: true` clears the selection when a click lands outside the
shell. Pass `dismissIgnoreSelector` for the elements that *change* the selection
(the rows themselves): the handler runs in the capture phase, before the host's
own click handler, so an ignored click re-anchors the panel instead of dismissing
it.

### Builders on the shell

The **Nav Bar** builder is the reference adapter. It renders Add Group even with
no selected node, then adds Up, Down, Remove, and Move To Root for a selected
node; the shell pins Clear selection at the row end. Translated node names and the
optional URL field render as peer fields in the shell's responsive grid, so the
three share one row when space allows. Selecting a node only rerenders the
builder; adding, moving, removing, renaming, or changing the URL serializes
`navbar_config`. The Hierarchy Tree and Available Routes panes own matching
fixed/capped heights; their internal lists scroll inside those panes.

The Nav Bar editor is a popover anchored to the selected tree row: the action row
stays inline and the field panel floats just below the row it edits — or just
above it when there is no room below — so editing a node never pushes the panes
down and never covers the node itself. Clicking another row re-anchors the panel;
clicking anywhere else dismisses it. A node with no label in any language reads as
its untitled-group placeholder in both the tree and the header; its generated id
is not a name.

The **Sidebar** builder's template supplies one `data-builder-inspector-shell`
host above the shared fixed-height Selected/Available pane cards; the adapter owns
the whole action row — Add Group, Add, Remove, Add All, Remove All, then Move To
Root and Duplicate once something is selected, with Clear selection pinned at the
end — and the popover carries the per-language label fields and the entry icon as
peer fields in one row.

Only a *stored* sidebar entry has anything to edit, so an Available pane selection
gets the actions and no panel. Duplicate can clone a selected stored entry or
create a new empty copy of a selected group. Selecting or clearing an entry is
editor state only; persisting happens when the admin adds, removes, moves,
duplicates, renames, or changes an icon.

The **Ribbon** builder has no toolbar to hang actions off: a tab pill belongs to a
strip, and a strip belongs to a page, so a single row of actions at the top of the
builder would have nothing to act on. It passes `actionsPlacement: 'panel'`, so
the popover carries Restore and Remove for the strip that owns the selected entry,
a `type: 'toggle'` action for whether the tab is shown, and the pinned Clear
selection above the fields. Selecting a tab gives labels and an icon; selecting a
custom button gives labels, icon and destination; selecting a strip caption gives
the action row alone, which is how a strip whose split produces no tabs can still
be removed.

Before migrating another builder to the shell, write down its selection shape,
editable field specs, contextual actions, commit triggers, render-only selection
changes, and old DOM/function paths that can be removed after the migration.
Migrate one builder at a time; the Nav Bar is the reference case for splitting
`renderAll()` from `commitAndRender()` before replacing old inspector markup.

### Icon pickers in a builder

The entry icon uses the shared Dlux icon picker rather than a builder-local grid.
Because that picker is a server-rendered component, the template renders it once
into a hidden `data-builder-icon-picker-holder` and the inspector's `custom` field
borrows the node, returning it to the holder on the next render — the same node
throughout, so the picker keeps its bindings.

Builders borrow `dlux/helpers/icon_picker.html` in its collapsed (`inline=False`)
form rather than rendering a grid inline. The grid is ~600 buttons; an always-open
copy would rebuild all of them on every render of the inspector and fill the
popover instead of dropping over it. The shared field builds them only while open.
It reports a pick by writing to the form field its `field_name` names, so the
borrowing builder must render a hidden input carrying that name — without one the
pick updates the picker and reaches nothing else. Mark that input
`data-dlux-unsaved-ignore`: it holds the *selected* entry's icon, so selecting an
entry rewrites it, and the [unsaved-changes guard](#unsaved-changes-guard) would
otherwise read inspecting an entry as an edit.

Pass `allow_empty=True` where "no icon" is a real answer — a ribbon tab with no
override keeps the icon its page already supplies. Without it an emptied box and
Reset both write the default back, so an icon cannot be removed at all.

The grid drops below the field, or rises above it when the room below runs out,
measured against the box that actually clips it rather than the viewport — inside
a scrollable modal there is usually screen below the modal and none inside it.

## Tables, filters, and row actions

Prefer `DluxTable` for handwritten tables. It supplies the standard responsive
shell, density handling, pagination, empty state, and row-action contract.
`Table.Meta` can:

- opt out with `dlux_table = False`;
- force density with `dlux_density`;
- set `dlux_per_page` (with a single `dlux_per_page_options` value the footer
  shows no page-size picker);
- disable actions with `dlux_actions = False`;
- drop the footer toolbar with `dlux_show_footer = False`, which also stops
  pagination, so every row renders.

New list pages should use the [Ribbon](ribbon.md) (`{% dlux_ribbon %}`), which
derives the filter band from the FilterSet and is configurable by the
administrator. `setup_filter_helper()` remains for pages not yet migrated;
`advanced_filter_helper()` is removed (see
[Deprecation Countdown](deprecation-countdown.md#advanced_filter_helper)).

Render filters with `{% crispy filter.form %}`, not `{{ filter.form|crispy }}`:
the filter form helper owns the form tag, action controls, advanced-collapse
markup, and autosubmit data attributes. Use `setup_filter_helper()` for a plain
filter bar.

The Clear control reflects filter state, not table presentation state. `page`,
`per_page`, and `sort` never activate it.

The advanced panel's open/closed state persists per list page in `localStorage`
(`dluxFilterAdvanced:<path>#<advanced_target>`), so paginating or re-applying a
filter does not collapse a panel the user opened. The filter script still expands
the panel server-side whenever an advanced field holds a value; that takes
precedence over a stored collapsed state, so an active filter is never hidden.
Persistence rides on `filter_assets_scripts.html`, which `dlux/list_base.html`
already includes — a template that renders a filter bar without those assets
keeps the server-side behaviour only.

The global Layout setting selects context-menu, actions-column, or both row action
triggers. Custom tables should continue to provide `data-dlux-actions`; the column
trigger reuses that same payload.

## Download helpers

Use `fetch_file()` for controlled file downloads and `fetch_excel()` for XLSX
exports. They keep request handling, feedback, and activity logging aligned with
the platform. Do not implement a second browser download flow when these helpers
fit the operation.

## Notifications

Dlux notifications replace Django message storage for Dlux-owned notices with a
durable event pipeline. The public API:

```python
from dlux.notifications import notify

notify("Invoice approved.")
notify.success("Saved.")
notify.error("Could not delete record.", obj=record)
notify("Backup completed.", action="backup_complete", target_url="/sys/backup/")
notify.success(message_key="msg_password_changed")
notify.error("Export failed.", event_key=f"export:{job.pk}:failed")
```

Optional routing stays compact:

```python
notify(
    "Payroll batch exported.",
    obj=batch,
    action="export",
    category="reports",
    to="watchers",
    email=True,
)
```

For language-aware Dlux-owned notices, pass `message_key` and optional `title_key`
values from `DLUX_STRINGS`. The stored `DluxNotification.message` remains a fallback
for history/email, while flash notices, the titlebar drawer, and
`/sys/api/notifications/` resolve keyed text in the active request language at render
time. Legacy rows without metadata also rerender when the stored text exactly matches
a known Dlux/app/project translation value; interpolated and free-form messages remain
stored text.

Data model:

- `DluxNotification(ScopedModel)`: durable event content, level, category,
  source/action, source model/object metadata, target URL, request path, unique
  optional `event_key`, per-event badge eligibility, metadata, audience type, and
  expiry.
- `DluxNotificationState`: per-user read/dismiss/email state for each delivered notification.
- `DluxNotificationRule(ScopedModel)`: JSON match/delivery rules for
  persist/flash/badge/email/recipient routing and deliberate actor inclusion.
- `DluxNotificationWatch(ScopedModel)`: model-level watches per user/scope;
  object-level watches are not supported.

Automatic behavior:

- `ScopedModel` create/update/delete events are notification-capable by default unless
  the model sets `dlux_notify = False`. Successful automatic CRUD excludes the actor
  from durable delivery; configured create/delete flash feedback remains request-local
  and does not create an unread state or sidebar badge.
- Durable automatic CRUD routes to model watchers plus users returned by the object's
  `dlux_notification_recipients()` hook. Dlux requires active users, matching scope,
  the model's view permission, and any row-level `dlux_notification_visible_to()`
  check before creating recipient state. Permission makes a user eligible; it does not
  subscribe every permission holder.
- Updates use the activity-log diff payload, including existing sensitive-field
  masking, and default to quiet persisted summaries for recipients rather than actor
  flash.
- Generic modal/context-menu CRUD attaches route/surface metadata before the signal
  pipeline emits the event.
- Activity logs remain the audit source; notifications are user-facing delivery
  records, so an automatic event with no eligible recipient leaves no orphan
  notification row.
- Automatic CRUD uses `crud:activity:<pk>` as its durable event key. Other
  retryable/asynchronous callers should pass their own stable `event_key`; the
  database unique constraint is the idempotency boundary, while the existing
  two-second cache guard only suppresses same-request bursts.

Model tuning:

```python
class Invoice(ScopedModel):
    dlux_notify = {
        "watchable": True,
        "update": "summary",
        "flash": ["create", "delete"],
        "view_permission": "billing.view_invoice",
    }

    def dlux_notification_recipients(self, *, action, actor):
        return [self.owner, self.approver]

    def dlux_notification_visible_to(self, *, user, action, actor):
        return user in {self.owner, self.approver}


class TempCalculation(ScopedModel):
    dlux_notify = False
```

The standard `app_label.view_model` permission is required unless `view_permission`
names another permission. `dlux_notification_visible_to()` is an additional row-level
restriction, not a permission grant. A delivery rule may set `to` from `actor`,
`watchers`, `related`, `staff`, `users`, and `broadcast`; automatic sources still
remove the actor unless that rule explicitly sets `include_actor: true`.

System Settings store `notification_config` with:

- `enabled`: top-level master gate (default on), edited in the **Notifications** setup
  step. When off, `emit_notification_event()`, `get_flash_notifications()`, and
  `get_notification_context()` short-circuit, suppressing flash notices, the titlebar
  drawer/badge, emails, automatic CRUD notifications, and `notify(...)` — the same
  enable/disable pattern as the sidebar and nav bar.
- `flash`: `enabled`, `position`, `size`, `text_size`, `timeout_ms`, `max_visible`
- `drawer`: `enabled`, `badge_enabled`, `preview_limit`
- `bridge.django_messages_enabled`: optional compatibility bridge for host-project Django messages
- `email.enabled/default`: `enabled` is the master gate for notification email and
  remains disabled/server-coerced off unless Dlux email delivery is configured;
  `default` emails eligible persisted notifications only after that gate is on
- `retention.default_expiry_days`
- `automatic.scoped_model_crud`: master switch for automatic `ScopedModel` CRUD notification sources
- `automatic.create/delete`: per-action gates under the automatic CRUD source
- `automatic.update`: `off`, `summary`, or `full`; summary emits quiet changed-field
  summaries and full keeps richer update metadata
- `automatic.actor_flash_actions/watchable`: actor flash defaults and model-watch support
- `automatic.include_actor`: defaults to `false`; rules or model policy must
  deliberately opt successful automatic CRUD into durable self-notification

The separate `sidebar_config.show_notification_badges` flag controls whether
model-backed sidebar entries use each notification's existing
`source_model_key` to show per-section unread counters. It is independent from
`notification_config.drawer.badge_enabled`; the global notifications master
switch still disables both. Sidebar groups aggregate unique child model keys,
counts are scoped to the current user's undismissed/unexpired notification
states whose event has `badge_enabled=True`; a `badge: false` delivery rule keeps
the item in the drawer without increasing titlebar/sidebar counts. The notification
list API returns the same mapping as
`section_counts` for live updates.

Test trigger, available only with `DEBUG`:

- `/sys/debug/notifications/` creates test notifications for the current
  superuser/global-staff user when `settings.DEBUG` is true; outside DEBUG it returns
  404.
- Query examples: `?level=success`, `?level=all`, `?persist=0`, `?flash=0`, `?next=/sys/options/`.

The drawer routes are listed in the [Reference](reference.md#notifications).

## Activity logging

For a project action outside the automatic CRUD signals, call:

```python
from dlux import log_activity

log_activity("APPROVE", invoice, details={"source": "billing"})
```

The helper resolves the request actor, scope, IP, user agent, model metadata, and
active logging policy. It returns `None` when policy disables the event. Use
`category="user"` for business actions that belong in reports.

## Tutorials and client behavior

DjangoLux uses Driver.js for path-aware tours. Add project steps through
`window.get_custom_tutorial_steps(path)` from
`templates/dlux/includes/custom_scripts.html`. Return steps only for rendered,
permitted controls; an invisible selector is not a valid tutorial target.

For loading buttons, file inputs, icon pickers, toggles, choice selectors, and
dynamic modal lifecycle events, use the shipped Dlux components rather than raw
controls. This preserves RTL behavior, accessibility, CSP-safe external assets,
and the framework's event conventions.

### URL and JSON helpers

`dlux/base/js/base_head.js` defines these globals on every page built on
`dlux/base.html`:

| Global | Purpose |
| --- | --- |
| `window.DLUX_URL_PREFIX` | The path prefix Dlux is mounted under: `/` at the root, or e.g. `/en/` behind an i18n language prefix or a sub-path mount. |
| `window.DLUX_URLS` | Reversed Dlux route templates, such as `preferencesUpdate` and `appPreference`. |
| `window.dluxUrl(path)` | Rewrites a root-relative path onto that prefix; absolute and already-prefixed URLs pass through. |
| `window.dluxEndpoint(name, params, fallbackPath)` | Fills the `__param__` placeholders of a named template from `DLUX_URLS` (or `fallbackPath`), then prefixes it. |
| `window.dluxParseJson(text, fallback)` | Parses a JSON string, returning `fallback` when it is empty or invalid. |

Built-in preference, theme, language and table-density writes use the reversed
`preferencesUpdate` endpoint, and app-preference writes use the reversed
`appPreference` template, so they work under `/`, `/dlux/`, or an active i18n
prefix. Downstream JS should use `{% url %}` for concrete routes or these
helpers for Dlux route templates rather than posting directly to `/sys/api/...`.

Feature scripts use `dluxParseJson` instead of defining their own copy. Page data
for scripts goes through Django's `json_script` filter, never a hand-assembled
`<script type="application/json">`.

### Alert auto-close

`dlux/base/js/base_runtime.js` auto-hides only the `.alert` elements that opt in
with `data-autohide="true"`. Every other alert — modal notices, form warnings,
setup instructions, inline hints — stays until the user dismisses it, with no
attribute needed.

Default Django messages render through `dlux/notifications/messages.html`, which
stamps `data-autohide="true"` on each message, so flash notices fade out after the
Notifications step's flash timeout (`notification_config.flash.timeout_ms`,
default 3200 ms, carried as `data-dlux-flash-timeout` on the container; `0` keeps
them). `data-autoclose="false"` pins an alert that would otherwise auto-hide. The
runtime binds the alerts present when the page loads; alerts a script adds later
are not auto-hidden.

```html
<!-- fades out after the flash timeout (3200 ms outside a flash container) -->
<div class="alert alert-success" data-autohide="true">Saved.</div>

<!-- stays until the user dismisses it: no attribute needed -->
<div class="alert alert-info">
    This setup notice remains visible until the user resolves it.
</div>
```

Reserve `data-autohide="true"` for transient success/error notices. Alerts that
remain actionable after the first few seconds — validation blockers,
missing-secret warnings, setup/import instructions, or messages explaining why a
field must change before the form can submit — must not carry it.

The messages render as compact fixed flash notices rather than full-width
titlebar overlays. Authenticated pages use `.dlux-flash-container`, positioned
below `--header-height`; public auth pages pass `dlux_flash_mode='page'` to use
`.dlux-page-alert-container` near the viewport top. Both containers are
`pointer-events: none`, while visible alerts remain closeable, and
`.dlux-alert--closing` disables pointer events before the removal transition.

Profile password-change validation is modal-scoped: invalid submissions render
field errors inside `#resetPasswordModal`, reopen that modal on the response, and
do not enqueue the generic form-error flash.

### Lux signature

`dlux/system/js/signature.js` is the removable, client-only DjangoLux attribution
layer. It reads `<html data-dlux="DjangoLux X.Y.Z ...">`, prints one quiet console
credit on load, exposes non-enumerable `window.lux` / `window.dlux` console
getters, and reveals a compact `.dlux-signature-pop` visual credit when a user
types `dlux` on the page outside input, textarea, select, or contenteditable
targets. It makes no network calls and stores no data.
