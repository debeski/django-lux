# Customization Guide

This guide focuses on the extension points you are most likely to use in a real project.

## Project Defaults with MICROSYS_CONFIG

`MICROSYS_CONFIG` is the code-owned seed layer that feeds `get_system_config()`. Use it for defaults that should live in source control.

```python
MICROSYS_CONFIG = {
    "name_en": "microSYS",
    "name_ar": "النظام",
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
    },
}
```

Keep in mind:

- UI edits made through System Settings layer on top of these values
- runtime language and translation overrides can live in the database without deleting your code defaults

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
- forms, filters, tables, and some context-menu labels are translated automatically by startup patches
- language resolution is layered, so user preference and runtime defaults matter

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

The property `is_2fa_enabled` returns `True` if any of the above are active. To force 2FA setup, redirect the user to `reverse('enable_2fa')`.

## Tutorial Engine Customization

microSYS uses [Driver.js](https://driverjs.com/) for its path-aware guided tours. Projects can register custom tutorial steps for their own views by providing a global JavaScript hook.

1.  **Register the Hook**: Add a script to your page (or via `custom_scripts.html`) that defines `window.get_custom_tutorial_steps`.
2.  **Define Steps**: Return an array of Driver.js step objects.

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

The system automatically filters out steps where the target element is missing and merges your steps with the system defaults.

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

## Base Template and Global Injections

The normal extension point for project pages is the microsys base template:

```django
{% extends "microsys/base.html" %}
```

Two low-friction global injection hooks are available without overriding the entire base template:

- `templates/microsys/includes/custom_head.html`
- `templates/microsys/includes/custom_scripts.html`

Use them for global CSS, meta tags, analytics, or shared JavaScript.

The same helper layer also fits well with fetch/export and context-menu-driven workflows, so forms, tables, downloads, and auditability can all share one system language instead of being implemented as unrelated project-level utilities.
