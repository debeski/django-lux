# UI Integration

Use Dlux-native primitives before introducing a project-specific alternative. The component catalog and import paths live in the [Developer Guide](developer-guide.md#dlux-owned-ui-primitives).

## Sections and dynamic modals

Register small project-owned configuration or CRUD surfaces as sections and serve modal content through the Dlux dynamic-modal contract. Modal endpoints return `JsonResponse({"html": ...})`; returning raw HTML makes the client render the response inline rather than opening the modal.

Keep authorization in the view as well as the card, action, or route discovery metadata. Mutating actions are POST-only and require CSRF protection.

Manager deletes are guarded by related-record discovery. `manage_scopes`,
`manage_groups`, and `manage_sections` delete only records with no external
dependents; blocked deletes return the `related` payload the UI shows to explain
which records must be removed or unlinked first. Group preset deletion ignores
its `GroupProfile` sidecar and permission assignment M2M because those define the
preset itself, but users and membership history still block deletion.
The standalone `manage_sections` page renders its table directly; do not wrap
`{% render_table table %}` in a page-level card, because `DluxTable` already owns
the table surface.
Its section form is a manage-only expandable editor above the table. The normal
browse state keeps the editor collapsed; the ribbon Add action opens a blank
form, a row Edit action opens the selected record's form, and validation failures
keep the editor expanded with bound errors. The Cancel action removes only the
add/edit state from the URL, preserving the active model and filters.
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
page behind it. Forms may
set `refresh_parent = True` or `False` to override that default; validation failures
always replace the modal body with the bound form and its errors.

Create forms that support successive entry should submit the secondary action as
`<button type="submit" name="save_add_more">`. The modal includes the clicked
submitter in the POST, recognizes that key as succession mode, refreshes the parent
list, and reopens a fresh create form. A form may also set `add_more = True` while
binding. Succession mode always outranks `refresh_parent`, including an explicit
`refresh_parent = True`; a normal Save still follows the surface default above.

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
builders as a configurable system item: 404ing the route left an entry an admin
had deliberately placed there answering 404 on every click. Who may open it is a
permission question, not a chrome one.

The Sidebar builder runs on the same inspector shell as the Nav Bar. Its template
supplies one `data-builder-inspector-shell` host above the shared fixed-height
Selected/Available pane cards; the adapter owns the whole action row — Add Group,
Add, Remove, Add All, Remove All, then Move To Root and Duplicate once something
is selected, with Clear selection pinned at the end — and the popover carries the
per-language label fields and the entry icon as peer fields in one row.

Only a *stored* entry has anything to edit, so an Available pane selection gets
the actions and no panel. Duplicate can clone a selected stored entry or create a
new empty copy of a selected group. Selecting or clearing an entry is editor state
only; persisting happens when the admin adds, removes, moves, duplicates, renames,
or changes an icon.

The entry icon uses the shared Dlux icon picker rather than a builder-local grid.
Because that picker is a server-rendered component, the template renders it once
into a hidden `data-builder-icon-picker-holder` and the inspector's `custom` field
borrows the node, returning it to the holder on the next render — the same node
throughout, so the picker keeps its bindings.

The Nav Bar builder was the first consumer of the Dlux inspector shell. Its
adapter renders Add Group even with no selected node, then adds Up, Down,
Remove, and Move To Root for a selected node; the shell pins Clear selection at
the row end. Translated node names and the optional URL field render as peer
fields in the shell's responsive grid, so the three share one row when space
allows. Selecting a node only rerenders the builder; adding, moving, removing,
renaming, or changing the URL serializes `navbar_config`. The Hierarchy Tree and
Available Routes panes own matching fixed/capped heights; their internal lists
scroll inside those panes.

The Nav Bar editor is a popover anchored to the selected tree row: the action row
stays inline and the field panel floats just below the row it edits — or just
above it when there is no room below — so editing a node never pushes the panes
down and never covers the node itself. Clicking another row re-anchors the panel;
clicking anywhere else dismisses it. A node with no label in any language reads as
its untitled-group placeholder in both the tree and the header; its generated id
is not a name.

## Inspector Shell

Use the Dlux inspector shell for new builder-style editors that need a selected
object, a contextual action row, and a compact field grid. Include
`dlux/helpers/inspector/css/main.css` and `dlux/helpers/inspector/js/main.js`,
then create it with `window.DluxInspectorShell.create(container, { adapter })`.
The shell is not wired into the current Sidebar, Nav Bar, or Ribbon inspectors
yet; those remain separate until each builder is migrated deliberately.

The adapter owns meaning and persistence. It may provide `getSelection()`,
`getTitle()`, `getSubtitle()`, `getBadge()`, `getActions()`, `getFields()`,
`clearSelection()`, and `commit()`. Actions render in the order returned by the
adapter; the shell adds a pinned Clear selection action by default. Field specs
cover `text`, `url`, `number`, `email`, `textarea`, `select`, `toggle`,
`localized-text`, and `custom`. Use `custom` for controls that already own their
own markup, such as the shared icon picker.

The default presentation is inline. Pass `presentation: 'popover'` when the
field editor should float over the builder instead of reserving form height; the
action row stays inline and the selected editor panel becomes an anchored
popover spanning the host's width.

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
below the modal but none inside it; measuring the viewport put the panel past the
modal's edge, where it was clipped out of sight and lengthened the modal's scroll
area. When the panel fits on neither side it caps its height to the roomier one
and scrolls its own content, so it degrades to cramped rather than invisible.

`dismissOnOutsideClick: true` clears the selection when a click lands outside the
shell. Pass `dismissIgnoreSelector` for the elements that *change* the selection
(the rows themselves): the handler runs in the capture phase, before the host's
own click handler, so an ignored click re-anchors the panel instead of dismissing
it.

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
flow. That separation is required for System Settings exit guards.

Before migrating another existing builder to the shell, write down its selection
shape, editable field specs, contextual actions, commit triggers, render-only
selection changes, and old DOM/function paths that can be removed after the
migration. Migrate one builder at a time; the Nav Bar migration is the reference
case for splitting `renderAll()` from `commitAndRender()` before replacing old
inspector markup.

The Ribbon builder is the third consumer, and the one with no toolbar to hang
actions off: a tab pill belongs to a strip, and a strip belongs to a page, so a
single row of actions at the top of the builder would have nothing to act on.
It passes `actionsPlacement: 'panel'`, which moves the action row inside the
popover above the fields — Restore and Remove for the strip that owns the
selected entry, a `type: 'toggle'` action for whether the tab is shown, and the
pinned Clear selection. Selecting a tab gives labels and an icon; selecting a
custom button gives labels, icon and destination; selecting a strip caption gives
the action row alone, which is how a strip whose split produces no tabs can still
be removed.

An action may be `type: 'toggle'`, rendered as a switch in the action row and
reporting the value it now holds to `onChange`. Use it for per-entry on/off state
that belongs beside the actions rather than among the fields.

Both builders borrow the shared `dlux/helpers/icon_picker.html` in its collapsed
(`inline=False`) form rather than rendering a grid inline. The grid is ~600
buttons; an always-open copy rebuilt all of them on every render of the inspector
and filled the popover instead of dropping over it. The shared field builds them
only while open. It reports a pick by writing to the form field its `field_name`
names, so the borrowing builder must render a hidden input carrying that name —
without one the pick updates the picker and reaches nothing else. Mark that input
`data-dlux-unsaved-ignore`: it holds the *selected* entry's icon, so selecting an
entry rewrites it, and the unsaved-changes guard would otherwise read inspecting
an entry as an edit.

Pass `allow_empty=True` where "no icon" is a real answer — a ribbon tab with no
override keeps the icon its page already supplies. Without it an emptied box and
Reset both write the default back, so an icon cannot be removed at all.

The grid drops below the field, or rises above it when the room below runs out,
measured against the box that actually clips it rather than the viewport — inside
a scrollable modal there is usually screen below the modal and none inside it.

## Tables, filters, and row actions

Prefer `DluxTable` for handwritten tables. It supplies the standard responsive shell, density handling, pagination, empty state, and row-action contract. `Table.Meta` can opt out with `dlux_table = False`, force density with `dlux_density`, set `dlux_per_page`, disable actions with `dlux_actions = False`, or drop the footer toolbar with `dlux_show_footer = False` (which also stops pagination, so every row renders).

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
