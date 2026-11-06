# Entry clipboard

The entry clipboard lets a user keep short text snippets in the browser tab and
insert them into form fields by hand.

Enable **Entry clipboard** in **System Settings → Extra Features**. The
system-wide switch is off by default and stored in
`extra_config.entry_clipboard.enabled`; no migration is needed. When it is on,
eligible text fields support snippets by default, with an
[explicit opt-out](#explicit-opt-out). Assets load only for signed-in users while
the feature is enabled.

The switch takes effect on the next page load. Disabling it hides the clipboard
without erasing snippets already saved in the tab. Changing the switch does not
refresh the live settings-preview background or change the sidebar's expansion
state.

## Settings storage

The canonical default and normalizer live in `dlux.system.defaults` and
`dlux.system.normalizers`. Imported boolean strings such as `"on"` and `"false"`
become booleans; malformed sections become disabled. The extra group itself stays
empty by default so it does not override a project's configuration. Clipboard
initialization reads the refreshed settings instance, and its field is disabled
outside the Extra Features step so unrelated saves keep it.

The flag survives settings export/import and uploaded setup files, through the
canonical `extra_config` group and its `extra`/`custom` aliases. Importing an
Extra Features section without the flag resets it to off; an import that does not
include that group leaves the clipboard control unchanged.

## Button and popover

The icon-only Bootstrap `bi-clipboard` button has a translated tooltip and
accessible label. It sits in the same assisted-entry header row as **Reuse my
last entry** on forms that support sticky reuse; other eligible forms receive a
compact header row with the translated **Assisted entry** legend and the button.

The popover has two compact rows, and needs no close button:

- the target-field dropdown beside a **Copy** icon;
- snippet search beside a **Clear clipboard** (X) icon that removes saved
  snippets.

Every icon has a translated tooltip and accessible label.

- **Copy** keeps the selection from the active field. Focusing a field updates
  the target selector.
- Saved snippets appear as compact table-like rows. **Add** (+) inserts at the
  saved cursor without deleting existing text; **Replace** (the rewind arrow)
  replaces the entire field. Number and date controls receive the whole value.
- Clicking entry text opens a detail view with its full content; **Back** (a back
  arrow) returns to the filtered list.

**Alt+Shift+C** opens the focused form's popover; **Escape** or clicking outside
dismisses it. No form values are captured automatically.

## Explicit opt-out

Exclude a field in its form initializer:

```python
self.fields['reference'].widget.attrs['data-dlux-entry-clipboard'] = 'false'
```

The same attribute on a form, fieldset, or enclosing container excludes its
fields.

| Controls | Clipboard |
| --- | --- |
| Textareas; text, search, telephone, URL, email, number and date inputs | Snippet targets |
| Selects and toggles | Never targets |
| Password, hidden, file, disabled and readonly controls | Always excluded |
| Fields named like password/token/secret/CSRF, or with password, payment-card or one-time-code autocomplete hints | Always excluded |

Dlux ribbons (`.dlux-ribbon` or `[data-dlux-ribbon-autosubmit]`) and forms nested
inside them are always excluded: filters receive no clipboard button or targets.
Dlux reports pages, report builders and user-report surfaces are also excluded.
Backend validation and permissions apply normally.

## Existing assisted entry

The clipboard provides manual snippet insertion only. Automatic next-record
prefill belongs to **sticky forms**, including their Save & Add More handoff; see
[Assisted entry](template-customization.md#assisted-entry). The clipboard adds no
carry-forward switches or separate prefill mechanism.

Sticky reuse needs explicit model capability metadata (`data-model-name` and
`data-app-label`), which the dynamic modal emits on create forms only. A custom
form without those markers still gets the Assisted entry legend and clipboard
button, but no sticky-reuse switch.

## Storage and integration

Snippets live in `sessionStorage`, scoped by authenticated user ID, for the
current origin and browser tab: at most 20 snippets of 2,000 characters each.
They render as text and are never sent to a server or read from the operating
system clipboard. **Clear clipboard** removes saved snippets. If storage is
unavailable, snippets work in memory until the page reloads.

- The base page removes other users' snippet keys when accounts switch, and
  removes all snippet keys on an anonymous page, including the login page after
  logout.
- A browser-history restore with a different recorded user clears the stale
  clipboard controls and reloads the page.
- A missing user ID prevents clipboard initialization.
- A browser may copy session storage when duplicating a tab, or preserve it on
  session restore.

Full-page forms using the Dlux base and dynamically loaded modal forms initialize
automatically. Custom clients call `window.DluxEntryClipboard.init(root)` after
inserting forms. Forms with no eligible fields show no clipboard button.
