# UI Integration

Use Dlux-native primitives before introducing a project-specific alternative. The component catalog and import paths live in the [Developer Guide](developer-guide.md#dlux-owned-ui-primitives).

## Sections and dynamic modals

Register small project-owned configuration or CRUD surfaces as sections and serve modal content through the Dlux dynamic-modal contract. Modal endpoints return `JsonResponse({"html": ...})`; returning raw HTML makes the client render the response inline rather than opening the modal.

Keep authorization in the view as well as the card, action, or route discovery metadata. Mutating actions are POST-only and require CSRF protection.

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
A combined manager modal keeps its shell open and reloads its own table. Forms may
set `refresh_parent = True` or `False` to override that default; validation failures
always replace the modal body with the bound form and its errors.

Create forms that support successive entry should submit the secondary action as
`<button type="submit" name="save_add_more">`. The modal includes the clicked
submitter in the POST, recognizes that key as succession mode, refreshes the parent
list, and reopens a fresh create form. A form may also set `add_more = True` while
binding. Succession mode always outranks `refresh_parent`, including an explicit
`refresh_parent = True`; a normal Save still follows the surface default above.

## Tables, filters, and row actions

Prefer `DluxTable` for handwritten tables. It supplies the standard responsive shell, density handling, pagination, empty state, and row-action contract. `Table.Meta` can opt out with `dlux_table = False`, force density with `dlux_density`, set `dlux_per_page`, or disable actions with `dlux_actions = False`.

New list pages should use the [Ribbon](ribbon.md) (`{% dlux_ribbon %}`), which derives the filter band from the FilterSet and is configurable by the administrator. The helpers below remain for pages not yet migrated; `advanced_filter_helper()` is removed in v1.9.0.

Render filters with `{% crispy filter.form %}`, not `{{ filter.form|crispy }}`: the filter form helper owns the form tag, action controls, advanced-collapse markup, and autosubmit data attributes. Use `setup_filter_helper()` when there are no advanced fields; `advanced_filter_helper()` deliberately renders an advanced-toggle control.

The Clear control reflects filter state, not table presentation state. `page`, `per_page`, and `sort` never activate it, including when `advanced_filter_helper()` receives a custom `clear_preserve_keys`; that configuration controls the reset URL and does not redefine which query parameters count as filters.

The advanced panel's open/closed state persists per list page in `localStorage` (`dluxFilterAdvanced:<path>#<advanced_target>`), so paginating or re-applying a filter does not collapse a panel the user opened. The helper still expands the panel server-side whenever an advanced field holds a value; that takes precedence over a stored collapsed state, so an active filter is never hidden. Persistence rides on `filter_assets_scripts.html`, which `dlux/list_base.html` already includes — a template that renders a filter bar without those assets keeps the server-side behaviour only.

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
