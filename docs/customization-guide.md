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
    "home_url": "/sys/",
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
- `get_modal_context()` on the model

## Context Menu Events

microSYS context menus can navigate directly or dispatch events.

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

Use `filter_context_actions()` on the backend when actions should disappear for users who lack permissions.

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

## Activity Logging Hook

When you need a manual audit entry, use `log_user_action()` instead of creating log rows directly.

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

That keeps logging behavior consistent with the rest of the system.
