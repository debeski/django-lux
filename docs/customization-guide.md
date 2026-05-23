# Customization Guide

This guide focuses on the extension points you are most likely to use in a real project.

## Project Defaults with MICROSYS_CONFIG

`MICROSYS_CONFIG` is the code-owned seed layer that feeds `get_system_config()`. Use it for defaults that should live in source control.

```python
MICROSYS_CONFIG = {
    "system_names": {
        "en": "microSYS",
        "ar": "النظام",
    },
    "default_language": "en",
    "default_theme": "light",
    "home_url": "/accounts/profile/",
    "languages": {
        "ar": {"name": "العربية", "dir": "rtl", "flag": "🇱🇾"},
        "en": {"name": "English", "dir": "ltr", "flag": "🇬🇧"},
    },
    "translations": {
        "en": {"app_microsys": "System"},
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

## Themes and Sidebar Runtime Controls

microSYS now treats theme registration as a shared framework concern instead of a repeated hardcoded list.

What to know:

- the official theme registry lives in `microsys/themes.py`
- that registry supplies theme names, labels, ordering, preview swatches, CSS asset paths, and the runtime allowlist
- base-template theme CSS inclusion follows the registry instead of a separate hand-maintained stylesheet list
- the active runtime list is filtered against the actual files present in `microsys/static/microsys/themes/css`, so stray registry entries do not become selectable unless their CSS exists

For sidebar behavior defaults, the code-owned `MICROSYS_CONFIG["sidebar"]` layer can also seed:

- `enable_reorder`
- `show_toolbar`
- `show_icons`
- `density`
- `allow_user_density`
- `collapse_mode`

Those defaults are then layered with runtime System Settings edits in the normal configuration flow.

## Nav Bar Hierarchy and Runtime Crumbs

The optional Nav Bar is controlled from Step 5 in setup/System Settings. The developer enables it, picks the default `hierarchy` or `history` mode, chooses whether Options may expose a personal style override, and builds static hierarchy nodes from the discovered route catalog. During first-launch setup, an enabled empty Nav Bar hierarchy can be seeded from the configured sidebar accordion structure.

The stored `navbar` block is normalized to this shape:

```python
{
    "enabled": False,
    "default_mode": "hierarchy",
    "allow_user_mode_override": True,
    "hierarchy": {"nodes": []},
}
```

Route nodes inherit discovered translated route labels unless the hierarchy editor gives them language-specific label overrides. Manual hierarchy nodes are useful for shared grouping labels such as a section or tab family; a manual node with no URL renders as text rather than a broken link.

Static route discovery cannot know an object title or the active tab for a dynamic page. For those views, pass `microsys_navbar_crumbs` in the template context:

```python
context["microsys_navbar_crumbs"] = [
    {"label_key": "documents", "url": documents_url},
    {"label": record.title, "url": record_url},
    {"label": active_tab_label, "url": active_tab_url},
]
```

Explicit runtime crumbs win over the System Settings hierarchy. If neither exists for the current route, Microsys falls back to `Root / Current View`. Microsys-owned system routes are grouped automatically under an unclickable `System` crumb instead of being placed from the hierarchy builder. History mode stores one browser-session path trail, resolves known route labels in the active interface language, ignores query-string-only route changes, and keeps six recent non-root entries.

### Sidebar Permission Enforcement

Sidebar items are only visible to users who have the required view permission. There is no implicit staff fallback. Permissions are inferred automatically:

- **Class-based views**: `app_label.view_model_name` from the model.
- **Function-based views**: `app_label.view_model_name` from URL namespace and name pattern (e.g., `documents:file_list` → `documents.view_file`).
- **Explicit decorators**: `sidebar_permissions` or `permission_required` on the view take precedence.
- **System routes**: use internal tokens like `__ms_user_directory__`, `__ms_activity_log__`, and `__ms_sections_view__`; Options uses `__ms_authenticated__`.

If a user lacks the required permission, the sidebar item is hidden. Ensure staff users are granted the appropriate `app.view_model` permissions.

The system config layer now also supports governed theme exposure and titlebar layout defaults:

- `allowed_themes`: list of shipped theme slugs that remain selectable at runtime
- `allow_user_theme_override`: hides runtime theme pickers and ignores saved user theme preferences when false
- `titlebar.show_logo`
- `titlebar.show_home_button`
- `titlebar.home_shape`: `circle`, `square`, or `squircle`
- `titlebar.title_align`: `start`, `center`, or `end`
- `titlebar.title_size`: `sm`, `md`, or `lg`
- `titlebar.height`: `dense`, `balanced`, or `roomy`
- `titlebar.surface`: `default`, `muted`, or `glass`

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
from microsys.utils import microsys_settings

microsys_settings(globals())
```

Use it near the end of your project `settings.py`.

The helper currently:

- prepends the required MicroSys apps and companion packages
- inserts `django.middleware.locale.LocaleMiddleware` in the supported Django order when missing
- inserts `microsys.middleware.MicrosysMiddleware` after Django authentication middleware
- adds `microsys.context_processors.microsys_context`
- sets Crispy Bootstrap 5 defaults when absent
- adds `MESSAGE_TAGS[messages.ERROR] = "danger"` when the host project has not already provided its own mapping
- seeds `LANGUAGE_CODE`, `TIME_ZONE`, `USE_I18N`, `USE_TZ`, `FORMAT_MODULE_PATH`, and `DEFAULT_CHARSET` when the host project has not already set them

The helper intentionally does not set cookie names or a generic `BASE_URL`. Those remain host-project concerns.

If you need a nonstandard stack, you can still wire those settings manually, but the helper is the supported default path and the one `microsys_setup` / `microsys_check` now target.

## Translation Workflow

Project-level translations come from two places:

- app-local `translations.py` files containing `MS_TRANSLATIONS`
- runtime JSON overrides stored in `SystemSettings.translations_override`

App-local example:

```python
MS_TRANSLATIONS = {
    "ar": {"my_key": "قيمة مخصصة"},
    "en": {"my_key": "Custom value"},
}
```

Template usage:

```django
{{ MS_TRANS.my_key }}
```

Important behavior:

- microSYS auto-discovers `translations.py` across installed apps
- discovered translation languages are suggestions only; a language becomes available to users only after it is added to the language catalog in setup/System Settings
- setup/System Settings provides a source-tabbed translation matrix editor that groups keys by Microsys, installed app, project translations, or settings-only overrides
- the translation matrix saves only admin edits into `SystemSettings.translations_override`
- forms, filters, tables, and some context-menu labels are translated automatically by startup patches
- language resolution is layered, so user preference and runtime defaults matter

## Setup Import and Export

Superusers can export the current System Settings payload from the Options System Settings card. The exported JSON uses the `django-microsys.system-settings` format and is meant to be imported from step 1 of the setup/System Settings wizard in another development, staging, or local environment.

The file contains the stable DB-backed setup fields:

- `system_names`
- `languages`
- `translations_override`
- `home_url`
- theme, density, security, sidebar, Nav Bar, and titlebar settings

Logo and favicon values are exported as stored file names only. The JSON file does not embed binary media content, so those media files must already exist in the target environment if you want the imported file names to resolve.

## Sections and Generated Components

Mark auxiliary models as sections when you want microSYS to manage them as system data.

```python
from django.db import models
from microsys.models import ScopedModel


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

## Dynamic Modals

Use `DynamicModalManagerView` when the CRUD flow should live inside a modal rather than the sections screen.

```python
from django.urls import path
from microsys.views import DynamicModalDeleteView, DynamicModalManagerView

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
- `handles_save` on the form class
- `get_modal_context()` on the model
- `get_smart_view_context()` on the model (see Smart View Customization below)

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

microSYS context menus are a reusable interaction layer, not just a cosmetic right-click menu. They can navigate directly, submit forms, or dispatch events that the rest of the UI responds to.

Basic HTML usage:

```html
<tr
  data-micro-context="true"
  data-micro-actions='[{"label": "Edit", "icon": "bi bi-pencil", "url": "/zones/1/edit/"}]'>
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
  "event": "micro:record:edit",
  "data": {
    "model": "zone",
    "id": 1,
    "name": "Warehouse A"
  }
}
```

Built-in record events:

- `micro:record:view`
- `micro:record:edit`
- `micro:record:delete`

JavaScript integration example:

```javascript
document.addEventListener("micro:record:edit", (event) => {
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
            "event": "micro:record:view",
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

## Universal Fetcher and Excel Export

microSYS includes shared download and export helpers so projects do not have to rebuild file-serving and spreadsheet-export logic in every app.

### `fetch_file()`

Use `fetch_file()` when a view should download:

- one file from one record
- multiple files from one record
- multiple files from many records as a ZIP

```python
from microsys.fetcher import fetch_file


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
from microsys.fetcher import fetch_excel


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

microSYS activity logging is broader than a single `log_user_action()` helper.

Automatic logging currently covers:

- login and logout events
- model creates, updates, and deletes through signals
- merged User/Profile audit history under a shared logical model name
- field-level diffs for updates
- masked sensitive values such as `password` and `backup_codes`
- download and export events triggered by the fetcher helpers

Important implementation details:

- `UserActivityLog` inherits from `ScopedModel`, so logs carry audit fields and can participate in scope-aware filtering
- `UserActivityLog.safe_log()` debounces duplicates within a short time window
- middleware stores the current request and user in thread-local state so saves and signals can still know the actor

Manual logging stays simple:

```python
from microsys.utils import log_user_action


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
from microsys.guards import require_current_password


@login_required
@require_POST
def revoke_api_token(request, pk):
    if failure_response := require_current_password(request):
        return failure_response
    # continue destructive mutation
```

For direct TOTP state persistence, avoid routing through the full `Profile.save()` path:

```python
from microsys.utils import set_profile_totp_state


set_profile_totp_state(request.user.profile, raw_secret='BASE32SECRET', enabled=True)
set_profile_totp_state(request.user.profile, raw_secret='', enabled=False)
```

## Tutorial Engine Customization

microSYS uses [Driver.js](https://driverjs.com/) for its path-aware guided tours. Projects can register custom tutorial steps for their own views by providing a global JavaScript hook.

Recommended pattern:

1.  **Keep the built-in shell**: do not override `microsys/includes/tutorial.html` unless you are intentionally changing the framework-level tutorial runtime.
2.  **Register the Hook**: load one small project script that defines `window.get_custom_tutorial_steps(path)`.
3.  **Prefer global injection hooks**: in most projects, the cleanest place to register the script is `templates/microsys/includes/custom_scripts.html`, so the base template loads it automatically.
4.  **Return extra steps only**: your hook should return an array of Driver.js step objects for the current path, or `[]` when nothing extra is needed.

Minimal project wiring:

```django
{# templates/microsys/includes/custom_scripts.html #}
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

If your project needs translated strings inside the custom hook, `microsys/base.html` already exposes the resolved translation map on `window.__MS_TRANS`. A tiny helper is usually enough:

```javascript
function tr(key, fallback) {
    return (window.__MS_TRANS && window.__MS_TRANS[key]) || fallback;
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

Use this hook for project-specific additions. Use Microsys source edits only when the default tutorial engine itself needs to change for every project.

## Autofill and Sticky Forms

microSYS autofill can work without custom JavaScript if the form exposes the expected attributes.

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
from microsys.utils import set_field_attrs

set_field_attrs(form, request)
```

For list filters that need more than the basic one-row helper, use `advanced_filter_helper()` instead of hand-rolling a separate Crispy layout.

```python
from microsys.utils import advanced_filter_helper


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

The normal extension point for project pages is the microsys base template:

```django
{% extends "microsys/base.html" %}
```

Two low-friction global injection hooks are available without overriding the entire base template:

- `templates/microsys/includes/custom_head.html`
- `templates/microsys/includes/custom_scripts.html`

Use them for global CSS, meta tags, analytics, shared JavaScript, or framework-approved hooks such as project tutorial extensions.

The same helper layer also fits well with fetch/export and context-menu-driven workflows, so forms, tables, downloads, and auditability can all share one system language instead of being implemented as unrelated project-level utilities.

### Form Pages

If a page is primarily a form, prefer the dedicated form base instead of loading form-only assets through the global base hooks:

```django
{% extends "microsys/form_base.html" %}
```

`microsys/form_base.html` extends `microsys/base.html` and automatically loads the shared Microsys form bundle:

- `microsys/forms/css/form_fields.css`
- `microsys/forms/css/file_field.css`
- `microsys/forms/css/form_actions.css`
- `microsys/forms/js/file_field.js`
- the shared scan-link helper scripts used by the file widget

This keeps normal non-form pages free of form-only imports while giving full-page forms one consistent supported entrypoint.

### List and Filter Pages

If a page is primarily a list/filter surface, prefer the dedicated list base:

```django
{% extends "microsys/list_base.html" %}
```

`microsys/list_base.html` extends `microsys/base.html` and automatically loads the shared filter surface CSS:

- `microsys/forms/css/form_fields.css`
- `microsys/forms/css/form_actions.css`

That is the supported page-level entrypoint for Crispy filter helpers such as `setup_filter_helper()` and `advanced_filter_helper()`.

For `django_tables2` usage on those pages, Microsys now auto-adopts the stock table rendering path and wraps the table in its own responsive shell. In practice that means:

- prefer `{% render_table table %}` directly instead of wrapping it in another `.table-responsive`
- stock templates such as `django_tables2/bootstrap5.html` are treated as framework-managed defaults
- explicit custom non-stock templates stay untouched unless you intentionally point them at the Microsys template
- built-in pagination, per-page controls, and translated empty states come from the framework-owned table template

Per-table escape hatches:

- set `microsys_table = False` in `Table.Meta` to opt out of the Microsys renderer
- set `microsys_density = "dense"`, `"balanced"`, or `"roomy"` in `Table.Meta` to force a specific density for one table

Preferred custom-table path:

```python
from microsys.tables import MicrosysTable


class InvoiceTable(MicrosysTable):
    class Meta(MicrosysTable.Meta):
        model = Invoice
        fields = ("number", "customer", "status", "created_at")
        microsys_per_page = 50
```

`MicrosysTable` gives handwritten tables the same renderer, sorting affordances, page-size controls, and default `micro:record:view|edit|delete` row actions used by the generated Microsys tables. To customize the default actions, override `get_microsys_row_actions(self, record, base_actions)`. To disable them entirely, set `microsys_actions = False` in `Meta`.

If a page mixes list/filter and full form behavior, either:

- extend `microsys/form_base.html` and include `microsys/forms/filter_assets_head.html` in `extra_head`, or
- extend `microsys/list_base.html` and manually include the full form asset bundle when the page also hosts the Microsys file widget

### Embedded or Manual Filter Hosts

If a page renders a filter helper but cannot extend `microsys/list_base.html`, include:

- `microsys/forms/filter_assets_head.html`

### Embedded or Modal Forms

If a page hosts an embedded form or modal form but does not itself extend `microsys/form_base.html`, include the shared form assets on the host page:

- `microsys/forms/assets_head.html`
- `microsys/forms/assets_scripts.html`

Example:

```django
{% block extra_head %}
    {% include "microsys/forms/assets_head.html" %}
{% endblock %}

{% block scripts %}
    {{ block.super }}
    {% include "microsys/forms/assets_scripts.html" %}
{% endblock %}
```

### File Field Template Override

Microsys now ships a framework-owned Crispy file-field bridge at:

- `templates/bootstrap5/layout/field_file.html`

and the underlying reusable form templates at:

- `microsys/forms/file_input.html`
- `microsys/forms/file_field.html`

If your project uses Crispy Bootstrap 5 and you want the Microsys file-field override to win automatically, make sure the Microsys template path is resolved before the package-default Crispy template in your Django template lookup order. The simplest reliable route is to keep Microsys earlier than `crispy_bootstrap5` in `INSTALLED_APPS` when you want Microsys to own that override globally.
