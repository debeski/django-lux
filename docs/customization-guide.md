# Customization Guide

This guide focuses on the extension points you are most likely to use in a real project.

## Project Defaults with DLUX_CONFIG

`DLUX_CONFIG` is the code-owned seed layer that feeds `get_system_config()`. Use it for defaults that should live in source control.

```python
DLUX_CONFIG = {
    "system_names": {
        "en": "DjangoLux",
        "ar": "النظام",
    },
    "default_language": "en",
    "default_theme": "light",
    "home_url": "/accounts/profile/",
    "prevent_multiple_active_sessions": False,
    "languages": {
        "ar": {"name": "العربية", "dir": "rtl", "flag": "🇱🇾"},
        "en": {"name": "English", "dir": "ltr", "flag": "🇬🇧"},
    },
    "translations": {
        "en": {"app_dlux": "System"},
    },
    "sidebar": {
        "home_url_name": None,
        "entries": [],
        "enable_reorder": True,
        "show_toolbar": True,
    },
    "navbar": {
        "enabled": False,
        "default_mode": "hierarchy",
        "allow_user_mode_override": True,
        "hierarchy": {"nodes": []},
    },
}
```

Keep in mind:

- UI edits made through System Settings layer on top of these values
- runtime language and translation overrides can live in the database without deleting your code defaults
- `sidebar.enable_reorder` controls whether end users can save their own sidebar order
- `sidebar.show_toolbar` controls whether the runtime sidebar footer toolbar is rendered
- `navbar` seeds the optional authenticated Nav Bar before System Settings edits its runtime hierarchy
- flat keys remain the project-facing contract; grouped aliases such as `language_config`, `theme_config`, `layout_config`, and `public_root_config` are accepted, but Dlux flattens them back to the same runtime keys
- future settings should be added to an existing JSON config group or `extra_config` unless they need durable relational state

## Themes and Sidebar Runtime Controls

DjangoLux treats theme registration as a shared framework concern instead of a repeated hardcoded list.

What to know:

- the built-in theme registry lives in `dlux/themes.py`, and projects can append
  themes through `DLUX_CUSTOM_THEMES`
- that registry supplies theme names, labels, ordering, preview swatches, CSS asset paths, and the runtime allowlist
- base-template theme CSS inclusion follows the registry instead of a separate hand-maintained stylesheet list
- built-in entries are filtered against files in `dlux/static/dlux/themes/css`;
  project entries use Django's normal static-file discovery and deployment flow

For sidebar behavior defaults, the code-owned `DLUX_CONFIG["sidebar"]` layer can also seed:

- `enable_reorder`
- `show_toolbar`
- `show_icons`
- `show_notification_badges`
- `density`
- `allow_user_density`
- `collapse_mode`

Those defaults are then layered with runtime System Settings edits in the normal configuration flow.
`sidebar.show_notification_badges` is independent from
`notifications.drawer.badge_enabled`, so administrators can show either badge
surface without enabling the other.

## Project-Configured Custom Themes

Put a project-owned CSS file in one of your app's static directories, then
register it in Django settings:

```python
DLUX_CUSTOM_THEMES = [
    {
        "slug": "project_ocean",
        "label": "Project Ocean",
        "preview_color": "#0ea5e9",
        "css_path": "myapp/themes/project-ocean.css",
    },
]
```

Keep every theme rule scoped to the matching root class. A small theme can
override the core color tokens:

```css
:root.theme-project_ocean {
    --title: #0f172a;
    --body: #f0f9ff;
    --htitle: #0369a1;
    --hbody: #e0f2fe;
    --table-row: #f8fdff;
    --table-row-hover: #e0f2fe;
    --primal: #0ea5e9;
    --primal_dark: #0284c7;
    --primal-rgb: 14, 165, 233;
    --btn-primary-shadow: rgba(14, 165, 233, 0.4);
    --nav-item-color: #e0f2fe;
    --bg-gradient: linear-gradient(135deg, #f0f9ff, #bae6fd);
    --right-bg: var(--title);
    --primary-color: var(--primal);
    --bs-primary: var(--primal);
    --bs-primary-rgb: var(--primal-rgb);
}
```

Copying a bundled theme CSS file is the simplest starting point when the
project needs more detailed component overrides. Run `collectstatic` normally.
The theme then appears in setup/System Settings, the user theme picker when
overrides are enabled, and the fixed public-root theme control. New
installations allow all registered themes by default; an existing installation
leaves a newly registered theme disabled until an administrator enables it.

Each entry needs a unique lowercase `slug`, an exact six-digit `#RRGGBB`
preview color, and a safe relative `.css` static path. `label` is optional and
defaults to a title-cased slug. Project themes cannot replace built-in themes
with the same slug. Invalid entries are ignored. DjangoLux validates the
registry metadata, while Django's static deployment owns the CSS file itself;
a missing collected asset returns the usual static-file 404.

## Project-Configured Custom Fonts

Put project-owned WOFF2 files in one of your app's static directories, then
register the family in Django settings:

```python
DLUX_CUSTOM_FONTS = [
    {
        "slug": "project_sans",
        "family": "Project Sans",
        "label": "Project Sans",
        "variants": [
            {
                "weight": 400,
                "path": "myapp/fonts/project-sans-regular.woff2",
            },
            {
                "weight": 700,
                "path": "myapp/fonts/project-sans-bold.woff2",
            },
        ],
    },
]
```

Run `collectstatic` normally. The family then appears beside the bundled fonts
in Themes and Typography, where an administrator can allow it, make it a
language default, and expose it to user font selection. New installations allow
all registered fonts by default; an existing installation leaves a newly added
font disabled until an administrator enables it.

Each entry needs a unique lowercase `slug`, a CSS `family`, and at least one
WOFF2 variant with a weight from 100 through 900. A project font cannot replace
a bundled font with the same slug. Invalid entries are ignored.

## Nav Bar Hierarchy and Runtime Crumbs

The optional Nav Bar is controlled from Step 6 in setup/System Settings. The developer enables it, picks the default `hierarchy` or `history` mode, chooses whether Options may expose a personal style override, and builds static hierarchy nodes from the discovered route catalog. During first-launch setup, an enabled empty Nav Bar hierarchy can be seeded from the configured sidebar accordion structure.

The stored `navbar` block is normalized to this shape:

```python
{
    "enabled": False,
    "default_mode": "hierarchy",
    "allow_user_mode_override": True,
    "root": {"mode": "neutral", "url_name": ""},
    "hierarchy": {"nodes": []},
}
```

`root.mode` accepts `neutral`, `home`, or `route`. Neutral preserves the non-clickable translated Root crumb. Home follows the current system `home_url` dynamically, including later administrator changes. Route uses the discovered route named by `root.url_name`; missing routes fall back to neutral. A configured page root is clickable away from that page and acts as a display boundary: ancestors and the duplicate selected-route crumb are omitted for that page and its descendants, but the stored hierarchy tree is never reparented. History mode also excludes the selected root URL from recent entries.

Route nodes inherit discovered translated route labels unless the hierarchy editor gives them language-specific label overrides. Manual hierarchy nodes are useful for shared grouping labels such as a section or tab family; a manual node with no URL renders as text rather than a broken link.

Static route discovery cannot know an object title or the active tab for a dynamic page. For those views, pass `dlux_navbar_crumbs` in the template context:

```python
context["dlux_navbar_crumbs"] = [
    {"label_key": "documents", "url": documents_url},
    {"label": record.title, "url": record_url},
    {"label": active_tab_label, "url": active_tab_url},
]
```

Explicit runtime crumbs win over the System Settings hierarchy. If neither exists for the current route, Dlux falls back to the discovered route label; Dlux-owned system routes are grouped under an unclickable `System` crumb by default. Framework-owned Dlux pages can declare a `breadcrumb_parent` in `SYSTEM_ROUTE_META` to mirror their own page links for unplaced routes, so `/sys/backup/` resolves as `Root / System / Application Options / Backup & Restore` because the Options page links to it. Configurable Dlux system routes are available in the hierarchy builder, and explicit placement for the current route overrides that inferred parent chain. History mode stores one browser-session path trail, resolves known route labels in the active interface language, ignores query-string-only route changes, and keeps six recent non-root entries.

### Sidebar Permission Enforcement

Sidebar items are only visible to users who have the required view permission. There is no implicit staff fallback. Permissions are inferred automatically:

- **Class-based views**: `app_label.view_model_name` from the model.
- **Function-based views**: `app_label.view_model_name` from URL namespace and name pattern (e.g., `documents:file_list` → `documents.view_file`).
- **Explicit decorators**: `sidebar_permissions` or `permission_required` on the view take precedence.
- **System routes**: use internal tokens like `__dlux_user_directory__`, `__dlux_activity_log__`, and `__dlux_sections_view__`; Options uses `__dlux_authenticated__`.

If a user lacks the required permission, the sidebar item is hidden. Ensure staff users are granted the appropriate `app.view_model` permissions.

The system config layer now also supports governed theme exposure and titlebar layout defaults:

- `allowed_themes`: list of shipped theme slugs that remain selectable at runtime
- `allow_user_theme_override`: hides runtime theme pickers and ignores saved user theme preferences when false
- `titlebar.show_logo`
- `titlebar.show_home_button`
- `titlebar.show_language_switcher`: shows a single titlebar button that cycles through the available languages; only surfaces when `allow_user_language_override` is on and more than one language exists (the settings toggle is disabled otherwise)
- `titlebar.logo_treatment`: `none`, `plate`, `halo`, or `contrast`
- `titlebar.logo_treatment_shape`: `soft`, `pill`, or `square` for the `plate` treatment
- `titlebar.buttons_shape`: `circle`, `square`, or `squircle` for all titlebar action buttons; legacy `titlebar.home_shape` remains accepted as an alias
- `titlebar.user_hub_style`: `dropdown` keeps the current user-hub dropdown; `titlebar_actions` moves user shortcuts into the right-side titlebar action rail
- `titlebar.actions_order`: ordered keys for the titlebar rail; unknown keys are dropped and missing known keys are appended in the default order
- `titlebar.title_align`: `start`, `center`, or `end`
- `titlebar.title_size`: `sm`, `md`, or `lg`
- `titlebar.height`: `dense`, `balanced`, or `roomy`
- `titlebar.surface`: `default`, `muted`, or `glass`

The default action order is `notifications`, `home`, `profile`, `help`, `users`, `activity`, `reports`, `settings`, `auth`. Runtime visibility still follows the existing gates: disabled notification drawers omit `notifications`, hidden home buttons omit `home`, and users/activity/reports require the same authorization flags used by the dropdown. In `titlebar_actions` mode the `auth` action renders login for anonymous users and a CSRF-protected POST logout button for authenticated users.

Runtime precedence for the new appearance controls is:

- theme: saved `Profile.preferences["theme"]` only when the theme is allowed and user overrides are enabled, otherwise the system `default_theme`
- sidebar density: saved `Profile.preferences["sidebar_density"]` only when `sidebar.allow_user_density` is enabled, otherwise the system sidebar density
- sidebar collapsed state: ignored on desktop when `sidebar.collapse_mode` is `locked_expanded`

Sidebar collapse modes now mean:

- `icons`: desktop collapse keeps the icon rail
- `hidden`: desktop collapse fully hides the sidebar, similar to the mobile overlay behavior
- `locked_expanded`: desktop collapse is disabled and the titlebar toggle is suppressed on large screens

When adding or refining a theme, treat these as one framework surface:

- setup wizard theme choices
- options-page theme previews
- sidebar toolbar theme picker
- first-paint theme bootstrap
- theme-specific overrides for framework-owned cards, profile/activity surfaces, tutorial popovers, and options controls

## Settings Integration Helper

For most projects, the preferred low-friction settings integration path is:

```python
from dlux.utils import dlux_settings

dlux_settings(globals())
```

Use it near the end of your project `settings.py`.

The helper currently:

- prepends the required DjangoLux apps and companion packages
- inserts `django.middleware.locale.LocaleMiddleware` in the supported Django order when missing
- inserts `dlux.middleware.DluxMiddleware` after Django authentication middleware
- adds `dlux.context_processors.dlux_context`
- sets Crispy Bootstrap 5 defaults when absent
- adds `MESSAGE_TAGS[messages.ERROR] = "danger"` when the host project has not already provided its own mapping
- seeds `LANGUAGE_CODE`, `TIME_ZONE`, `USE_I18N`, `USE_TZ`, `FORMAT_MODULE_PATH`, and `DEFAULT_CHARSET` when the host project has not already set them

The helper intentionally does not set cookie names or a generic `BASE_URL`. Those remain host-project concerns.

If you need a nonstandard stack, you can still wire those settings manually, but the helper is the supported default path and the one `dlux_setup` / `dlux_doctor` now target.

## Translation Workflow

Project-level translations come from two places:

- app-local `translations.py` files containing `DLUX_STRINGS`
- runtime JSON overrides stored in `SystemSettings.language_config["translations_override"]` and exposed through the compatibility key `translations_override`

App-local example:

```python
DLUX_STRINGS = {
    "ar": {"my_key": "قيمة مخصصة"},
    "en": {"my_key": "Custom value"},
}
```

Template usage:

```django
{{ DLUX_STRINGS.my_key }}
```

Important behavior:

- DjangoLux auto-discovers `translations.py` across installed apps
- discovered translation languages are suggestions only; a language becomes available to users only after it is added to the language catalog in setup/System Settings
- setup/System Settings provides a source-tabbed translation matrix editor that groups keys by Dlux, installed app, project translations, or settings-only overrides
- the translation matrix saves only admin edits into `translations_override`; it never writes the merged discovered catalog back into System Settings
- forms, filters, tables, and some context-menu labels are translated automatically by startup patches
- language resolution is layered, so user preference and runtime defaults matter

### Table column headers (generic vs distinct)

A table column resolves its header from the first matching key, in priority
order: `tbl_{model}_{column}` → `label_{model}_{column}` → `tbl_{column}` →
`label_{column}` → the raw verbose name. So by default columns share a **generic**
key (`tbl_name`, `tbl_number`, `tbl_created_at`, …), and you make one **distinct**
by defining the **model-qualified** key:

```python
# A "name" column reads "Product Name" on the Product table, "Name" elsewhere.
DLUX_STRINGS = {"en": {"tbl_product_name": "Product Name"},
                "ar": {"tbl_product_name": "اسم المنتج"}}
```

Dlux ships one example: the User table's active column reads
`tbl_user_is_active` ("Account Active") in preference to the generic
`tbl_is_active` ("Active").

The same **model-qualified** priority applies to **form field labels** —
`form_{model}_{field}` / `label_{model}_{field}` are tried before the generic
`label_{field}` — so the User form's active toggle reads `form_user_is_active`
("Account Active") in preference to the generic `form_is_active`.

### Unified keys (aliases)

Duplicate keys that carried the exact same English *and* Arabic value have been
unified: one canonical key holds the value and the rest are **aliases**
(`dlux/translation_aliases.py`, applied in `get_strings()`). Aliased keys still
resolve — nothing breaks — and editing the canonical (or its
`translations_override`) changes them all at once. Two dev helpers report/apply
this: `scripts/find_duplicate_translations.py` (report, `--md`) and
`scripts/apply_tier1_unification.py` (`--apply`). An explicit
`translations_override` of an aliased key still wins.

### Translating dropdown *option* labels

Startup patches localize field **labels** and table cells, but the `<option>` labels of a
`ChoiceField` (a model's `choices`) are **not** translated automatically — they render with
the model's raw display strings. Use `translate_choices(choices, dlux_strings)`
(`from dlux.utils import translate_choices`), which maps each option's value to the
`choice_<value>` DLUX_STRINGS key:

```python
from dlux.translations import get_current_language_code, get_strings
from dlux.utils import translate_choices
from django import forms

def translate_choice_fields(form, request=None):
    strings = get_strings(get_current_language_code(request))
    for field in form.fields.values():
        if isinstance(field, forms.ModelChoiceField):
            continue  # options are DB objects, not translatable strings
        source = getattr(field, "choices", None) or getattr(field.widget, "choices", None)
        if source:
            field.widget.choices = translate_choices(list(source), strings)
```

Add the keys to `DLUX_STRINGS`, e.g. `"choice_draft": "مسودة"`, `"choice_issued": "صادرة"`.
`translate_choices` leaves the empty placeholder option (`value == ""`) untouched.

> **Gotcha — for django-filter `ChoiceField`s, write `widget.choices`, not `field.choices`.**
> Two traps compound here:
> 1. `set_first_choice()` (used by the filter helpers to put a label on the first option)
>    sets the placeholder on `field.choices`, but a django-filter `ChoiceField` **renders
>    from `widget.choices`**, which still holds the default `---------`. So the intended
>    first-choice label never shows unless you also update the widget.
> 2. Re-assigning `field.choices` makes the django-filter field **re-prepend** its empty
>    option, duplicating the placeholder.
>
> Assigning the translated list to `field.widget.choices` (as above) solves both: it is
> what actually renders, it preserves the single placeholder that `set_first_choice` put on
> `field.choices`, and — because only *labels* change, not values — field validation is
> unaffected. Also handles widget-only choice sources such as `NullBooleanSelect`
> (the yes/no/any boolean filter).

### Translating permission labels (group manager)

The grouped-permission widget (the "permission group manager") resolves each
checkbox label as `strings.get(f"perm_{codename}", str(permission))`. The
`Permission.__str__` override only translates the **verb** (`can_view` → عرض, etc.)
and leaves the **model name** as its English `verbose_name`, so a non-English group
manager shows mixed labels like "عرض Customer".

To fully translate a permission label (including the model name), add a
`perm_<codename>` key with the complete label:

```python
DLUX_STRINGS = {
    "ar": {
        "perm_view_invoice": "عرض الفواتير",
        "perm_issue_invoice": "إصدار (اعتماد) الفواتير",  # custom permissions too
    },
}
```

Cover the four CRUD codenames per model (`view_/add_/change_/delete_<model>`) plus
any custom `Meta.permissions`. English can be omitted — it falls back to Django's
default `str(permission)`. Note the model *group header* uses a separate key,
`model_<model_name>` (see the sidebar/model-label convention), so translate both.

## Setup Import and Export

Superusers can export the current System Settings payload from the Options System Settings card. The exported JSON uses the `django-lux.system-settings` format and is meant to be imported from step 1 of the setup/System Settings wizard in another development, staging, or local environment. Browser downloads are named `dlux-{project-slug}-{YYYY-MM-DD}.json`; the slug comes from the deployed project `BASE_DIR` folder name (generic container work-dir names such as `app`/`src`/`code` are skipped), falling back to the configured English system name (`system_names['en']`) when set, then to `project`.

The file contains the stable, flat DB-backed setup keys:

- `system_names`
- `languages`
- `translations_override`
- `home_url`
- theme, dynamic font, density, security, sidebar, Nav Bar, and titlebar settings
- notification, login, Client IP, public-root, registration, and reserved `extra_config` settings

Internally those values are stored in grouped JSON fields on `SystemSettings`, but exports stay flat for compatibility with older setup files. Imports accept both the flat keys and nested group aliases.

Logo and favicon values are exported as stored file names only. The JSON file does not embed binary media content, so those media files must already exist in the target environment if you want the imported file names to resolve.

For shipped starter projects, place an exported payload or direct settings dict at `BASE_DIR/config.json`. On an unconfigured system, `python manage.py migrator` applies the file immediately after database migrations, before the web service becomes ready. The setup view repeats the same row-locked check as a fallback for deployments that do not use `migrator`. A valid file bootstraps the singleton and marks setup complete; missing or invalid files leave manual setup available and produce an explicit migrator outcome. After setup has completed, the file is ignored until the project is reset to a fresh unconfigured state.

## Sections and Generated Components

Mark auxiliary models as sections when you want DjangoLux to manage them as system data.

```python
from django.db import models
from dlux.models import ScopedModel


class Department(ScopedModel):
    name = models.CharField(max_length=100)
    is_section = True
    form_exclude = ["internal_notes"]
    table_exclude = ["internal_notes", "created_at"]
```

If conventions are not enough, override the generated classes:

```python
class Department(ScopedModel):
    is_section = True

    model_classes_overrides = {
        "form": "myapp.forms.DepartmentAdminForm",
        "table": "myapp.tables.DepartmentTable",
    }

    @classmethod
    def get_filter_class_path(cls):
        return "myapp.filters.DepartmentFilter"
```

Use sections when you want discovery, a system-managed list screen, and minimal boilerplate.

### Model-name labels (sidebar, nav, section manager)

Every Dlux surface that shows a model's *name* — the sidebar entry, the page
title/breadcrumb, and the Section Manager tabs and headings — resolves it through
one shared order so they always agree on the same string:

1. `models_<model_name>` — the **plural** key (e.g. `models_department`)
2. `model_<model_name>` — the **singular** key (e.g. `model_department`)
3. the raw `Meta.verbose_name_plural` (English fallback)

Because of the fallback, translating **either** key makes the model resolve on
every surface — but for correct singular/plural copy you should provide both:

```python
DLUX_STRINGS = {
    "ar": {"model_department": "قسم",  "models_department": "الأقسام"},
    "en": {"model_department": "Department", "models_department": "Departments"},
}
```

`Meta.verbose_name`/`verbose_name_plural` are wrapped in lazy translators at
startup, so the fallback happens automatically anywhere those metas are rendered.
The canonical entry point is `dlux.translations.resolve_model_label(model)` if you
need the same label in your own code.

> **Gotcha — duplicate Save button in the Section Manager.** The section screen
> renders your form's crispy layout and then adds its own Save/Cancel action bar,
> **unless** your form already declares a submit control (Dlux auto-hides its bar
> then). It detects both a submit in `helper.layout` *and* one added via
> `helper.add_input(Submit(...))` (which lives on `helper.inputs`). If you want the
> Dlux-styled action bar, simply don't add your own submit; if you want your own,
> add it and the Dlux bar disappears.

## Dynamic Modals

Use `DynamicModalManagerView` when the CRUD flow should live inside a modal rather than the sections screen.

```python
from django.urls import path
from dlux.views import DynamicModalDeleteView, DynamicModalManagerView

urlpatterns = [
    path("zones/modal/", DynamicModalManagerView.as_view(model=Zone), name="zone_modal"),
    path("zones/modal/<int:pk>/", DynamicModalManagerView.as_view(model=Zone), name="zone_modal_edit"),
    path("zones/modal/delete/<int:pk>/", DynamicModalDeleteView.as_view(model=Zone), name="zone_modal_delete"),
]
```

Useful override points:

- `form_class`
- `template_name`
- `show_table`
- `show_form`
- `handles_save` on the form class
- `get_modal_context()` on the model
- `get_smart_view_context()` on the model (see Smart View Customization below)

> **Gotcha — `show_table` defaults to `True`, so add-forms show a records table too.**
> The default `DynamicModalManagerView` renders the *combined* table **and** form. For
> an add/edit modal that should show only the form, wire it as
> `DynamicModalManagerView.as_view(show_table=False)`. A convenient project pattern is a
> single reusable route reused for every scoped model:
>
> ```python
> path("app-modals/<str:app_label>/<str:model_name>/<str:pk>/",
>      DynamicModalManagerView.as_view(show_table=False), name="scoped_modal_manager"),
> ```
>
> (`pk="new"` for create; a real pk — a plain `<str:pk>` also matches numeric ids — for edit.)

> **Gotcha — reloading the parent list after a modal save.** On success the modal POST
> reloads the page **only** when the form sets `refresh_parent = True` (or `add_more`).
> Without it the list behind a form-only modal won't reflect the new/edited row. Set
> `refresh_parent = True` on the modal `ModelForm`.

> **Gotcha — opening edit/view/delete modals from a plain list page.** `DluxTable` rows
> dispatch bubbling `dlux:record:{view,edit,delete}` events. On a page **without** a
> section manager (`#sectionData`), the generic fallback (`context_menu/js/main.js`)
> navigates to `/{app}/{id}/edit|delete/` — routes a modal-only app doesn't have. To open
> a modal instead, add a listener on `document` (bubble phase, so it runs before the
> window-level fallback), call `event.preventDefault()` to opt out of that navigation, and
> open the modal via the documented event:
>
> ```js
> document.addEventListener("dlux:record:edit", function (e) {
>     e.preventDefault();
>     const id = e.detail.data.id;
>     document.body.dispatchEvent(new CustomEvent("dlux:dynamic_modal:open", {
>         detail: { data: { url: `/app-modals/${e.detail.data.app}/${e.detail.data.model}/${id}/` } },
>     }));
> });
> ```
>
> (View appends `?action=view`; delete POSTs to the `DynamicModalDeleteView` route with the
> CSRF token, then reloads.)

## Smart View Customization

The "Smart View" (the eye icon in sections or tables) generates a generic detail view by default. You can override the returned context or the visible fields by adding `get_smart_view_context` or `get_modal_context` to your model.

```python
class Zone(ScopedModel):
    name = models.CharField(max_length=100)

    def get_modal_context(self):
        """Override the Smart View / Detail Modal context."""
        return {
            "title": f"Zone: {self.name}",
            "fields": {
                "Title": self.name,
                "Status": "Active" if self.is_active else "Inactive",
                "Custom Field": self.get_custom_data(),
            },
            "related": collect_related_objects(self),
        }
```

If `get_modal_context` returns a dictionary with `fields`, those fields will be rendered as a definition list in the detail modal.

## Context Menu Integration

DjangoLux context menus are a reusable interaction layer, not just a cosmetic right-click menu. They can navigate directly, submit forms, or dispatch events that the rest of the UI responds to.

Basic HTML usage:

```html
<tr
  data-dlux-context="true"
  data-dlux-actions='[{"label": "Edit", "icon": "bi bi-pencil", "url": "/zones/1/edit/"}]'>
</tr>
```

Action types supported by the client script include:

- URL navigation
- event dispatch
- dividers
- form submission

Useful action keys include:

- `label`
- `icon`
- `url`
- `type`
- `event`
- `data`
- `dblclick`
- `textClass`
- `permission` or `permissions`

That gives you one consistent pattern for table rows, cards, custom list items, and long-press interactions on touch devices.

Example event action:

```json
{
  "label": "Edit",
  "icon": "bi bi-pencil",
  "type": "event",
  "event": "dlux:record:edit",
  "data": {
    "model": "zone",
    "id": 1,
    "name": "Warehouse A"
  }
}
```

Built-in record events:

- `dlux:record:view`
- `dlux:record:edit`
- `dlux:record:delete`

JavaScript integration example:

```javascript
document.addEventListener("dlux:record:edit", (event) => {
  console.log(event.detail.data);
});
```

Table integration example:

```python
import json


def get_actions(record):
    return json.dumps([
        {
            "label": "View",
            "icon": "bi bi-eye",
            "type": "event",
            "event": "dlux:record:view",
            "data": {"model": "department", "id": record.pk, "name": str(record)},
            "dblclick": True,
        },
        {"type": "divider"},
        {
            "label": "Delete",
            "icon": "bi bi-trash",
            "url": f"/departments/{record.pk}/delete/",
            "textClass": "text-danger",
        },
    ])
```

Use `filter_context_actions()` on the backend when actions should disappear for users who lack permissions.

For system-managed tables, context-menu integration is part of the normal ecosystem: section tables, user flows, and dynamic modal actions already build on the same model.

The System Settings **Layout → Table row actions** setting (`layout_config.row_actions_style`) controls how these row actions are triggered globally: `context` (default, right-click / long-press), `column` (a dedicated three-dot column, `.dlux-row-actions-trigger`), or `both`. The button-triggered menu reuses the very same `data-dlux-actions` payload, so custom tables get the actions column for free without changing how you declare actions. See [reference.md](reference.md) → `row_actions_style`.

## Loading Buttons

DjangoLux ships one reusable spinner-in-button primitive (`window.DluxLoadingButton`, loaded globally from `dlux/base.html`) so you never hand-roll the disable/spinner/restore dance again. It works on `<button>` and any clickable element, sets `aria-busy`, shows a Bootstrap `spinner-border-sm`, and restores the original content when done. By default it preserves the button's layout **in place** — it swaps a leading icon (e.g. dlux's `<i class="bi bi-save …">`) for the spinner and keeps the text, so icon-beside-text buttons don't reflow; pass an explicit `label` (or use task-polling, which streams status text) to switch to content-replace mode instead. Styling lives in `dlux/helpers/loading_button/css/main.css` (busy/done/error states, reduced-motion aware). There are four ways to use it:

**1. Promise API (your own JS).** Wrap any async action; the button shows the spinner for its lifetime and returns to normal on resolve, or flashes the error state on throw:

```javascript
DluxLoadingButton.run(button, async (handle) => {
    handle.update(DLUX_STRINGS.loading);          // optional progress label
    const res = await fetch('/do/something/', { method: 'POST' });
    if (!res.ok) throw new Error('failed');        // -> error state
    return { redirect: '/done/' };                 // optional: navigate on success
});
```

For full control over completion, use the low-level handle directly:

```javascript
const handle = DluxLoadingButton.start(button, { label: 'Saving…' });
handle.update('Step 2 of 3…', 66);   // change label / aria-valuenow
handle.done();                       // or handle.error('Something broke')
```

**2. Submit spinner (declarative).** Add `data-dlux-loading` to a submit button and it shows the spinner while its form posts (it cooperates with `prevent_double_submit`; the page navigates, so no restore is needed):

```html
<button type="submit" data-dlux-loading data-dlux-loading-label="Saving…">Save</button>
```

**3. Task-polling (declarative).** A button that starts a server task and polls until it finishes — no JavaScript required on your side:

```html
<button data-dlux-loading
        data-dlux-loading-start="{% url 'thing_rebuild' thing.pk %}"
        data-dlux-loading-poll="{% url 'thing_rebuild_status' thing.pk %}"
        data-dlux-loading-interval="1500"
        data-dlux-loading-label="Rebuilding…">Rebuild</button>
```

On click it POSTs `start` (CSRF-aware), then polls `poll` on the interval, reading this JSON contract from your view:

```json
{ "status": "processing", "progress": 40, "message": "Rebuilding 40%…" }
```

`status` drives the lifecycle: any of `complete/completed/done/success/finished/ok/ready` finishes the button (and follows an optional `redirect`); `error/failed/cancelled/aborted` puts it in the error state (showing `error` or `message`). `message`/`progress` update the live label. Omit `data-dlux-loading-start` to poll a URL directly without a kickoff POST. Tune with `data-dlux-loading-timeout` (ms) and the optional `data-dlux-loading-done-label` / `data-dlux-loading-done-icon` / `data-dlux-loading-redirect`.

**4. Custom event (declarative).** `data-dlux-loading-event="my:event"` makes the button go busy on click and dispatch your event with the handle attached, so a listener can run arbitrary async work and finish it:

```html
<button data-dlux-loading data-dlux-loading-event="app:recalculate">Recalculate</button>
```
```javascript
document.addEventListener('app:recalculate', async (e) => {
    const handle = e.detail.handle;
    try { await recalc(); handle.done(); }
    catch (err) { handle.error(err.message); }
});
```

Every transition also fires a bubbling DOM event on the button — `dlux:loading:start`, `dlux:loading:poll`, `dlux:loading:done`, `dlux:loading:error` — for cross-cutting hooks (analytics, toasts). Labels fall back to `DLUX_STRINGS.loading` / `loading_failed` / `loading_timeout`, all overridable per button via the `data-dlux-loading-*` attributes.

## Universal Fetcher and Excel Export

DjangoLux includes shared download and export helpers so projects do not have to rebuild file-serving and spreadsheet-export logic in every app.

### `fetch_file()`

Use `fetch_file()` when a view should download:

- one file from one record
- multiple files from one record
- multiple files from many records as a ZIP

```python
from dlux.fetcher import fetch_file


def download_invoice(request, pk):
    invoice = Invoice.objects.get(pk=pk)
    return fetch_file(request, invoice)


def download_invoice_pdf(request, pk):
    invoice = Invoice.objects.get(pk=pk)
    return fetch_file(request, invoice, file_type="pdf_file")


def bulk_download(request):
    invoices = Invoice.objects.filter(status="approved")
    return fetch_file(request, invoices)
```

Behavior to know:

- it introspects `FileField`s automatically
- it chooses a filename using model name, identifier-like fields, dates, and file-field names
- it serves a single file directly or creates a ZIP when multiple files are involved
- it logs downloads through the shared activity-log helper

### `fetch_excel()`

Use `fetch_excel()` when a queryset should become an `.xlsx` export with sensible defaults.

```python
from dlux.fetcher import fetch_excel


def export_invoices(request):
    qs = Invoice.objects.select_related("customer")
    return fetch_excel(
        request,
        qs,
        exclude_fields=["internal_notes"],
        hidden_fields=["created_by"],
        sheet_title="Invoices",
    )
```

Behavior to know:

- file/image columns are included but hidden by default
- auto-managed timestamp columns are hidden by default
- you can fully exclude fields or merely hide them
- exports are logged as `EXPORT` activity entries with filename and count metadata

## Activity Logging and Audit Trail

DjangoLux activity logging is broader than a single `log_user_action()` helper.

Automatic logging currently covers:

- login and logout events
- model creates, updates, and deletes through signals
- merged User/Profile audit history under a shared logical model name
- field-level diffs for updates
- masked sensitive values such as `password` and `backup_codes`
- download and export events triggered by the fetcher helpers

Important implementation details:

- `ActivityLog` inherits from `ScopedModel`, so logs carry audit fields and can participate in scope-aware filtering
- `ActivityLog.safe_log()` debounces duplicates within a short time window
- `UserActivityLog` remains importable only as a compatibility alias; new code should use `ActivityLog`
- middleware stores the current request and user in thread-local state so saves and signals can still know the actor
- durable user-presence reporting is split from the action log: `UserKnownDevice` groups a browser/device through a signed `dlux_device_id` cookie stored only as a hash, and `UserPresenceSession` records session-level first/last seen, request count, estimated seconds, IPs, browsers, and operating systems
- all IP observations for activity/security/reporting should use `dlux.utils.get_client_ip(request)` so System Settings proxy/header rules stay authoritative
- User Reports are intentionally permission-gated through user-directory access, target-management access, and activity-log access; do not expose equivalent project reports without matching backend checks

Manual logging stays simple:

```python
from dlux.utils import log_user_action


def maintenance_view(request, asset):
    log_user_action(
        request,
        "MAINTENANCE_LOG",
        instance=asset,
        details={"notes": "Oil changed"},
    )
```

Use the manual helper when the action is business-specific and not already covered by the built-in signal flows.

## 2FA Developer Integration

You can check if a user has enabled any Two-Factor Authentication method via their profile:

```python
def my_secure_view(request):
    if not request.user.profile.is_2fa_enabled:
        messages.warning(request, "Please enable 2FA to access this area.")
        return redirect('profile')
    # ...
```

Built-in 2FA intents include:
- `is_email_2fa_enabled`
- `is_phone_2fa_enabled`
- `is_totp_2fa_enabled`

The property `is_2fa_enabled` returns `True` if any of the above are active. Do not redirect users to `reverse('enable_2fa')` directly; `enable_2fa` is a POST-only mutator. The supported UI path is the profile security surface, or a custom POST-backed action that triggers the built-in 2FA flow.

For destructive security mutations in your own views, reuse the current-password backend guard:

```python
from dlux.guards import require_current_password


@login_required
@require_POST
def revoke_api_token(request, pk):
    if failure_response := require_current_password(request):
        return failure_response
    # continue destructive mutation
```

For direct TOTP state persistence, avoid routing through the full `Profile.save()` path:

```python
from dlux.utils import set_profile_totp_state


set_profile_totp_state(request.user.profile, raw_secret='BASE32SECRET', enabled=True)
set_profile_totp_state(request.user.profile, raw_secret='', enabled=False)
```

## Tutorial Engine Customization

DjangoLux uses [Driver.js](https://driverjs.com/) for its path-aware guided tours. Projects can register custom tutorial steps for their own views by providing a global JavaScript hook.

Recommended pattern:

1.  **Keep the built-in shell**: do not override `dlux/includes/tutorial.html` unless you are intentionally changing the framework-level tutorial runtime.
2.  **Register the Hook**: load one small project script that defines `window.get_custom_tutorial_steps(path)`.
3.  **Prefer global injection hooks**: in most projects, the cleanest place to register the script is `templates/dlux/includes/custom_scripts.html`, so the base template loads it automatically.
4.  **Return extra steps only**: your hook should return an array of Driver.js step objects for the current path, or `[]` when nothing extra is needed.

Minimal project wiring:

```django
{# templates/dlux/includes/custom_scripts.html #}
{% load static %}
<script src="{% static 'my_app/tutorial.js' %}" nonce="{{ request.csp_nonce }}"></script>
```

```javascript
window.get_custom_tutorial_steps = function(path) {
    if (path.includes('/my-app/dashboard/')) {
        return [
            { 
                element: '#tour-start-point', 
                popover: { 
                    title: 'Welcome!', 
                    description: 'This is your custom dashboard.', 
                    side: "bottom", 
                    align: 'start' 
                } 
            },
            { 
                element: '.bi-graph-up', 
                popover: { 
                    title: 'Analytics', 
                    description: 'Track your progress here.', 
                    side: "left" 
                } 
            }
        ];
    }
    return [];
};
```

The system automatically:

- merges your custom steps with the built-in path-aware defaults
- filters out steps whose target element is missing from the DOM
- keeps Driver.js loading, controls, translations, and button chrome inside the framework layer

That means project code normally only needs to supply selectors and popover content.

If your project needs translated strings inside the custom hook, `dlux/base.html` already exposes the resolved translation map on `window.DLUX_STRINGS`. A tiny helper is usually enough:

```javascript
function tr(key, fallback) {
    return (window.DLUX_STRINGS && window.DLUX_STRINGS[key]) || fallback;
}

window.get_custom_tutorial_steps = function(path) {
    if (!path.includes('/my-app/invoices/')) {
        return [];
    }

    return [
        {
            element: 'input[name="keyword"]',
            popover: {
                title: tr('search_title', 'Search'),
                description: tr('my_invoice_tour_search_desc', 'Search invoice records here.'),
                side: 'right',
                align: 'center',
            },
        },
    ];
};
```

Use this hook for project-specific additions. Use Dlux source edits only when the default tutorial engine itself needs to change for every project.

## Autofill and Sticky Forms

DjangoLux autofill can work without custom JavaScript if the form exposes the expected attributes.

Foreign-key autofill:

```python
self.fields["customer"].widget.attrs["data-autofill-source"] = "crm.Customer"
```

Sticky-form support:

```html
<form method="post" data-app-label="crm" data-model-name="invoice">
```

The helper that makes standard forms feel native is:

```python
from dlux.utils import set_field_attrs

set_field_attrs(form, request)
```

For list filters that need more than the basic one-row helper, use `advanced_filter_helper()` instead of hand-rolling a separate Crispy layout.

```python
from dlux.utils import advanced_filter_helper


advanced_filter_helper(
    my_filter,
    request=request,
    config={
        "fields": [
            {"name": "keyword", "placeholder_key": "search_placeholder"},
            {"name": "date__year", "col_class": "form-group col-auto"},
        ],
        "advanced_fields": [
            [
                {"name": "number"},
                {"name": "category"},
            ],
            [
                {"name": "date__gte", "range_label_key": "label_date", "range_direction": "from"},
                {"name": "date__lte", "range_label_key": "label_date", "range_direction": "to"},
            ],
        ],
        "buttons": [
            {
                "url": "{% url 'add_invoice' %}",
                "permission": "billing.add_invoice",
                "label_key": "btn_add",
                "icon": "bi bi-plus-lg me-2",
                "btn_class": "btn btn-primary w-100",
            },
        ],
        "clear_preserve_keys": ["sort", "page"],
    },
)
```

Behavior to know:

- the primary row keeps the pill-shaped search / clear control used by `setup_filter_helper()`
- the advanced rows live inside a Bootstrap collapse container
- field placeholders still flow through `set_field_attrs()`, so direction and translations follow the active request language
- route-level action buttons can be injected without rebuilding the filter layout by hand
- hidden state and clear-state can now be controlled separately:
  - `hidden_preserve_keys` or legacy `preserve_keys` decide what is re-submitted with the filter form
  - `clear_preserve_keys` decides what survives the clear button, defaulting to `sort` and `page`
  - views that need to keep extra contextual params such as `model` should pass them explicitly instead of relying on framework defaults

## Base Template and Global Injections

The normal extension point for project pages is the dlux base template:

```django
{% extends "dlux/base.html" %}
```

Two low-friction global injection hooks are available without overriding the entire base template:

- `templates/dlux/includes/custom_head.html`
- `templates/dlux/includes/custom_scripts.html`

Use them for global CSS, meta tags, analytics, shared JavaScript, or framework-approved hooks such as project tutorial extensions.

The same helper layer also fits well with fetch/export and context-menu-driven workflows, so forms, tables, downloads, and auditability can all share one system language instead of being implemented as unrelated project-level utilities.

### Global Footer

`dlux/base.html` renders a faint, very small footer pinned to the bottom of the viewport — intended for a copyright notice, a short description, or a credit line. Its colors derive from the active theme (so it flips correctly on dark themes), it is semi-transparent with a backdrop blur, `pointer-events:none` so it never blocks clicks on the content behind it, and it sits below the sidebar/navbar and Bootstrap modals/offcanvas.

**Turning it off.** Leaving the Footer text blank does *not* hide it — it falls back to the default line. To remove the built-in footer entirely, switch off **Show page footer** in *System Settings → Identity → Footer* (`layout_config.footer_enabled`). That toggle gates only the built-in footer; a dev `custom_footer.html` partial or a `footer` block override is explicit code and always renders regardless.

By default it shows `© <current year> <system display name>`. The content resolves in this order (most specific wins):

1. **Per page/section** — override the `footer` block in any template that extends `dlux/base.html`:

   ```django
   {% block footer %}{% endblock %}            {# remove the footer on this page #}
   ```

   ```django
   {% block footer %}
     <footer class="dlux-footer">My custom footer for this page</footer>
   {% endblock %}
   ```

2. **Site-wide replacement** — drop a `templates/dlux/includes/custom_footer.html` partial. Its rendered content replaces the default line everywhere, no dlux templates touched:

   ```django
   {# templates/dlux/includes/custom_footer.html #}
   <span class="dlux-footer__text">&copy; {% now "Y" %} Acme Corp · All rights reserved</span>
   ```

3. **System Settings (no code, admin-editable)** — in *System Settings → Identity → Footer*: **Show page footer** (on/off), **Footer text**, and an optional **Footer link text** + **Footer link URL**. Stored on `SystemSettings.layout_config` (`footer_enabled` / `footer_text` / `footer_link_text` / `footer_link_url`) and surfaced as `APP_CONFIG.appearance.*`; all participate in System Settings export/import. The footer text is HTML-escaped (plain text + Unicode symbols like `©`, not markup). The link URL is scheme-validated server-side — only `http(s)://`, `mailto:`, or a root-relative `/path` is kept; anything else (or a blank URL) renders no link. The link label falls back to the URL when **Footer link text** is blank. This is the recommended place for a per-deployment copyright/credit line and a single link, without touching templates.

4. **Code fallback** — set `footer_text` in your project `DLUX_STRINGS` for a translated default when no admin value is configured.

For a footer with rich HTML — multiple links, Bootstrap icons (`<i class="bi …">`), etc. — use option 1 or 2 (template paths render raw HTML); the admin Footer text/link fields are deliberately escaped/validated for safety.

To restyle without editing templates, override the CSS variables on `.dlux-footer` (e.g. in `custom_head.html`): `--dlux-footer-color`, `--dlux-footer-bg`, `--dlux-footer-border`.

### Appearance Toggles (Tables, Forms, Modals)

*System Settings → Layout* exposes layout toggles stored on
`SystemSettings.layout_config` (no migration; all surface as `APP_CONFIG.appearance.*`
and round-trip through export/import):

- **Sticky table headers** (`sticky_table_headers`, default on), **Resizable
  table columns** (`resizable_table_columns`, default on), and **Zebra striping**
  (`zebra_striping`, default on). `base.html` emits `data-dlux-sticky-header`,
  `data-dlux-table-resize`, and `data-dlux-zebra` on `<body>`. `tables.css` and
  `tables.js` scope sticky headers, visible resize dividers, browser-persisted
  proportional column widths, and alternating row shading under those flags.
  Resizing rebalances the other columns within a fixed table footprint, so a
  widened column cannot stretch the main content or viewport. Narrowed nowrap
  values are clipped with an ellipsis at their cell boundary instead of overlapping
  neighboring values. Individual table classes can opt out with
  `Meta.dlux_resizable_columns = False`.
- **Default Form Density** (`default_form_density`: `dense` / `balanced` / `roomy`)
  is independent of table density. `body[data-dlux-form-density]` overrides the
  `--dlux-form-*` variables in `form_fields.css` (row gutter, label margin,
  input/textarea min-height) — override those variables to retune the scale.
- **Default Modal Size** (`default_modal_size`: `compact` / `standard` / `wide`)
  maps to `APP_CONFIG.appearance.modal_size_class` (`modal-lg` / `modal-xl` /
  `modal-xl dlux-modal-wide`), applied to the shared `dynamic_modal.html` dialog.
  `wide` widens beyond `modal-xl` on ≥1200px via `.dlux-modal-wide` in `main.css`.

### Public Root Appearance and SEO

**Enable public root access** in *System Settings → Access & Security* is the master
switch for the anonymous public-root controls (`SystemSettings.public_root_config`).
While enabled, each control appears in its canonical category:

- **Public root theme** (`public_root_theme`, blank = inherit) forces a fixed
  theme for anonymous public-root visitors regardless of the system default
  (*Themes & Typography*).
- **Public root page title** / **meta description** (`public_root_title`,
  `public_root_meta_description`) emit a custom `<title>` and
  `<meta name="description">` only on the anonymous public index (*Identity*).
- **Show titlebar on public root** (`show_titlebar_on_public`, *Titlebar*) and
  **Show sidebar on public root** (`show_sidebar_on_public`, *Sidebar*) both
  default **off**.
  These replace the deprecated `titlebar_config.hide_on_public_unauthenticated_index`
  (legacy values migrate, inverted) and the old hardcoded behavior that hid the
  sidebar from every unauthenticated user. The shared `_is_public_index()` context
  helper drives `hide_titlebar_for_public_index`, `dlux_show_sidebar`, and
  `dlux_is_public_index` in `base.html`.

### Form Pages

If a page is primarily a form, prefer the dedicated form base instead of loading form-only assets through the global base hooks:

```django
{% extends "dlux/form_base.html" %}
```

`dlux/form_base.html` extends `dlux/base.html` and automatically loads the shared Dlux form bundle:

- `dlux/forms/css/form_fields.css`
- `dlux/forms/css/file_field.css`
- `dlux/forms/css/form_actions.css`
- `dlux/forms/js/file_field.js`
- the shared scan-link helper scripts used by the file widget

This keeps normal non-form pages free of form-only imports while giving full-page forms one consistent supported entrypoint.

### List and Filter Pages

If a page is primarily a list/filter surface, prefer the dedicated list base:

```django
{% extends "dlux/list_base.html" %}
```

`dlux/list_base.html` extends `dlux/base.html` and automatically loads the shared filter surface CSS:

- `dlux/forms/css/form_fields.css`
- `dlux/forms/css/form_actions.css`

That is the supported page-level entrypoint for Crispy filter helpers such as `setup_filter_helper()` and `advanced_filter_helper()`.

> **Gotcha — render the filter with the `{% crispy %}` tag, not the `|crispy` filter.**
> `setup_filter_helper()` / `advanced_filter_helper()` attach the whole layout (the
> pill-shaped search/clear controls, the collapsible advanced section, injected
> buttons, `form_method="get"`, and the `data-dlux-filter-autosubmit` attribute) as
> `filter.form.helper`. Only the crispy **tag** applies `form.helper`:
>
> ```django
> {% load crispy_forms_tags %}
> {% if filter %}
>     <div class="no-print mb-3">{% crispy filter.form %}</div>
> {% endif %}
> ```
>
> The `|crispy` **filter** (`{{ filter.form|crispy }}` / `as_crispy_form`) **ignores
> `form.helper`** and renders bare fields — no `<form>` tag, no advanced collapse, no
> autosubmit — so the helper silently appears to do nothing. (Note:
> `crispy_forms.utils.render_crispy_form()` *does* honor the helper, so a passing
> Python-side render check can mask a template that still uses the filter.)

> **Gotcha — `advanced_filter_helper()` always renders the advanced-toggle button.**
> The "advanced search" toggle is emitted even when `config` has no `advanced_fields`,
> so it points at an empty collapse (a dead button). Either give every filter at least
> one `advanced_fields` entry, or use `setup_filter_helper()` for filters that
> genuinely have only a primary row.

> **Tip — calling convention.** `advanced_filter_helper(self, request=request, config=…)`
> is typically called from the `FilterSet.__init__` (using
> `request = getattr(self, "request", None)`), which is where the reference projects
> wire it. Calling it from the view's `get_filterset()` also works, as long as you pass
> `request` explicitly.

For `django_tables2` usage on those pages, Dlux now auto-adopts the stock table rendering path and wraps the table in its own responsive shell. In practice that means:

- prefer `{% render_table table %}` directly instead of wrapping it in another `.table-responsive`
- stock templates such as `django_tables2/bootstrap5.html` are treated as framework-managed defaults
- explicit custom non-stock templates stay untouched unless you intentionally point them at the Dlux template
- built-in pagination, per-page controls, and translated empty states come from the framework-owned table template

Per-table escape hatches:

- set `dlux_table = False` in `Table.Meta` to opt out of the Dlux renderer
- set `dlux_density = "dense"`, `"balanced"`, or `"roomy"` in `Table.Meta` to force a specific density for one table

Preferred custom-table path:

```python
from dlux.tables import DluxTable


class InvoiceTable(DluxTable):
    class Meta(DluxTable.Meta):
        model = Invoice
        fields = ("number", "customer", "status", "created_at")
        dlux_per_page = 50
```

`DluxTable` gives handwritten tables the same renderer, sorting affordances, page-size controls, and default `dlux:record:view|edit|delete` row actions used by the generated Dlux tables. To customize the default actions, override `get_dlux_row_actions(self, record, base_actions)`. To disable them entirely, set `dlux_actions = False` in `Meta`.

If a page mixes list/filter and full form behavior, either:

- extend `dlux/form_base.html` and include `dlux/forms/filter_assets_head.html` in `extra_head`, or
- extend `dlux/list_base.html` and manually include the full form asset bundle when the page also hosts the Dlux file widget

### Embedded or Manual Filter Hosts

If a page renders a filter helper but cannot extend `dlux/list_base.html`, include:

- `dlux/forms/filter_assets_head.html`

### Embedded or Modal Forms

The shared form assets (`dlux/forms/assets_head.html` + `dlux/forms/assets_scripts.html`) are now loaded **globally and exactly once** by `dlux/base.html`, because the dynamic modal (`dlux/helpers/dynamic_modal.html`) can render a form on *any* page — not just pages that extend `dlux/form_base.html`. This means forms opened in the dynamic modal from a list or detail page are styled and wired up automatically, with no host-page setup required.

You therefore no longer need to manually include the form assets on embedded/modal-form host pages, and you should **not** add them to `templates/dlux/includes/custom_head.html` / `custom_scripts.html` — doing so would emit the same `<link>`/`<script>` tags twice. (`form_base.html` still references them via `{% include_once %}`, which dedupes against the global load.)

If you ever need to guarantee an asset partial loads at most once regardless of how many places pull it, use the `include_once` tag:

```django
{% load dlux_tags %}
{% include_once "dlux/forms/assets_head.html" %}
```

### File Field Template Override

Dlux now ships a framework-owned Crispy file-field bridge at:

- `templates/bootstrap5/layout/field_file.html`

and the underlying reusable form templates at:

- `dlux/forms/file_input.html`
- `dlux/forms/file_field.html`

If your project uses Crispy Bootstrap 5 and you want the Dlux file-field override to win automatically, make sure the Dlux template path is resolved before the package-default Crispy template in your Django template lookup order. The simplest reliable route is to keep Dlux earlier than `crispy_bootstrap5` in `INSTALLED_APPS` when you want Dlux to own that override globally.
