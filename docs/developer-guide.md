# Developer Guide

This page explains how microSYS fits into a Django project and how to think about its moving parts before you start extending it.

## The Core Mental Model

microSYS is a Django app that combines four layers:

1. runtime configuration
2. generic discovery and generation
3. global patches for translation and scope behavior
4. reusable templates, views, and JavaScript for internal system workflows

If you keep those four layers in mind, the package becomes much easier to extend without fighting it.

## Configuration Layers

The runtime configuration comes from `get_system_config()` and is merged in this order:

1. package defaults
2. `settings.MICROSYS_CONFIG`
3. the database-backed `SystemSettings` singleton

Practical implications:

- use `MICROSYS_CONFIG` for project-owned defaults checked into source control
- use `SystemSettings` for live runtime edits from the UI
- expect the final resolved configuration to be the merged view, not one single source

## Core Models

The main system-level models are:

- `SystemSettings`
  Stores branding, theme, language, home URL, translations override, and sidebar configuration.

- `Scope` and `ScopeSettings`
  Represent the optional scope-isolation system and whether scoping is globally enabled.

- `ScopedModel`
  Gives inheriting models audit fields, actor tracking, soft-delete behavior, and automatic scope support.

- `Profile`
  Extends the user model with phone, profile picture, preferences, and 2FA state. Profiles are created automatically.

## Working with ScopedModel

Inheriting from `ScopedModel` is the main way to make a model feel native inside microSYS.

```python
from django.db import models
from microsys.models import ScopedModel


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

## Startup Patches and Zero-Boilerplate Behavior

`MicrosysConfig.ready()` applies the package's global behavior at startup. That includes:

- permission-label translation
- automatic scope handling for forms, filters, and tables
- automatic translation patches for forms, filters, tables, and some context-menu labels

That is why many microsys features feel "automatic" even when your model or form code looks ordinary.

A few practical consequences:

- you usually do not add `scope` manually to every form and filter
- translated labels often come from verbose names or translation keys without manual wiring
- opting out is explicit, such as excluding `scope` in form metadata when needed

## Discovery and Generated Components

microSYS leans heavily on naming conventions and runtime discovery.

The generic class resolver looks for model-adjacent classes in this order:

- convention-based imports such as `DepartmentForm`, `DepartmentTable`, and `DepartmentFilter`
- explicit model methods that return classes
- explicit dotted-path model methods
- runtime auto-generation

That same discovery model powers both sections and dynamic modal flows.

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

## Users, Profiles, and Permissions

The user side of microSYS has a few important defaults:

- every user gets a `Profile`
- preferences and 2FA state live on that profile
- the user-management flow uses the interactive modal wizard
- permission labels are translated dynamically instead of staying in raw Django English

If you extend user-facing workflows, treat `Profile` as part of the normal user contract rather than an optional extra.

## Translation and Scope Behavior

Two recent themes in microSYS are worth treating as first-class features, not side effects:

- translations are resolved with layered fallbacks, including user preferences, session state, config defaults, and runtime overrides
- scope behavior is auto-injected when enabled and removed when disabled

That means you should usually extend the system by leaning into those mechanisms rather than rebuilding them locally in each form, table, or view.

## Where to Go Next

- Use the [Customization Guide](customization-guide.md) when you are ready to wire your own translations, sections, modals, or template overrides.
- Use the [Reference](reference.md) when you need commands, endpoints, template tags, or helper names quickly.
