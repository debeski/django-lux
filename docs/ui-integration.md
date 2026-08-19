# UI Integration

Use Dlux-native primitives before introducing a project-specific alternative. The component catalog and import paths live in the [Developer Guide](developer-guide.md#dlux-owned-ui-primitives).

## Sections and dynamic modals

Register small project-owned configuration or CRUD surfaces as sections and serve modal content through the Dlux dynamic-modal contract. Modal endpoints return `JsonResponse({"html": ...})`; returning raw HTML makes the client render the response inline rather than opening the modal.

Keep authorization in the view as well as the card, action, or route discovery metadata. Mutating actions are POST-only and require CSRF protection.

## Tables, filters, and row actions

Prefer `DluxTable` for handwritten tables. It supplies the standard responsive shell, density handling, pagination, empty state, and row-action contract. `Table.Meta` can opt out with `dlux_table = False`, force density with `dlux_density`, set `dlux_per_page`, or disable actions with `dlux_actions = False`.

Render filters with `{% crispy filter.form %}`, not `{{ filter.form|crispy }}`: the filter form helper owns the form tag, action controls, advanced-collapse markup, and autosubmit data attributes. Use `setup_filter_helper()` when there are no advanced fields; `advanced_filter_helper()` deliberately renders an advanced-toggle control.

The global Layout setting selects context-menu, actions-column, or both row action triggers. Custom tables should continue to provide `data-dlux-actions`; the column trigger reuses that same payload.

## Download helpers

Use `fetch_file()` for controlled file downloads and `fetch_excel()` for XLSX exports. They keep request handling, feedback, and activity logging aligned with the platform. Do not implement a second browser download flow when these helpers fit the operation.

## Activity logging

For a project action outside the automatic CRUD signals, call:

```python
from dlux import log_activity

log_activity("APPROVE", invoice, details={"source": "billing"})
```

The helper resolves the request actor, scope, IP, user agent, model metadata, and active logging policy. It returns `None` when policy disables the event. Use `category="user"` for business actions that belong in reports.

## Tutorials and client behavior

DjangoLux uses Driver.js for path-aware tours. Add project steps through `window.get_custom_tutorial_steps(path)` from `templates/dlux/includes/custom_scripts.html`. Return steps only for rendered, permitted controls; an invisible selector is not a valid tutorial target.

For loading buttons, file inputs, icon pickers, toggles, choice selectors, and dynamic modal lifecycle events, use the shipped Dlux components rather than raw controls. This preserves RTL behavior, accessibility, CSP-safe external assets, and the framework's event conventions.
