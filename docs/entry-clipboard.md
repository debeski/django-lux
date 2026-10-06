# Entry clipboard

Enable **Entry clipboard** in **System Settings → Extra Features**. The
system-wide switch is off by default and stored in
`extra_config.entry_clipboard.enabled`; no migration is needed. When enabled,
eligible text fields are available by default, with explicit opt-out below.
Assets are loaded only for signed-in users while the feature is enabled.
The switch takes effect on the next page load. Disabling it hides the clipboard
without erasing snippets already saved in the tab.
Changing the switch does not refresh the live settings-preview background or
change the sidebar's expansion state.

The canonical default and normalizer live in `dlux.system.defaults` and
`dlux.system.normalizers`. Imported boolean strings such as `"on"` and
`"false"` become booleans; malformed sections become disabled. The extra group
itself remains empty by default so it does not override a project's configuration.
Clipboard initialization reads the refreshed settings instance, and its field
is disabled outside the Extra Features step to preserve unrelated saves.

The flag survives settings export/import and uploaded setup files, through the
canonical `extra_config` group and its `extra`/`custom` aliases. Importing an
Extra Features section without the flag resets it to off; an import that does
not include that group leaves the clipboard control unchanged.

The icon-only Bootstrap `bi-clipboard` button has a translated tooltip and
accessible label. It sits in the same assisted-entry header row as **Reuse my
last entry** on supported forms. Other eligible forms receive a compact header
button. The popover has two compact rows: the target-field dropdown beside a
copy icon, and snippet search beside an X icon that clears saved snippets.
Icons have translated tooltips and accessible labels. No close button is needed.
Copy preserves the selection from the active field. Saved snippets appear as
compact table-like rows: **+** inserts at the saved cursor without deleting
existing text, and the rewind arrow replaces the entire field. Number/date
controls receive the whole value. Clicking entry text opens its full content;
a back arrow returns to the filtered list. Focusing a field updates the selector.
**Alt+Shift+C** opens the popover; **Escape** or clicking outside dismisses it.
No form values are captured automatically.
Custom full-page forms without sticky model markers still receive the translated
Assisted entry legend and clipboard icon. Sticky reuse is a separate feature;
this clipboard release does not add sticky integration to custom forms.

## Explicit opt-out

Exclude a field in its form initializer:

```python
self.fields['reference'].widget.attrs['data-dlux-entry-clipboard'] = 'false'
```

The same attribute on a form, fieldset, or enclosing container excludes its
fields. Password, hidden, file, disabled and readonly controls are always
excluded, as are fields with password/token/secret/CSRF names and password,
payment-card or one-time-code autocomplete hints. Supported controls are
textareas and text, search, telephone, URL, email, number and date inputs.
Selects and toggles are not snippet targets. Backend validation and permissions
continue to apply normally.
Dlux ribbons (`.dlux-ribbon` or `[data-dlux-ribbon-autosubmit]`) and forms nested
inside them are always excluded: filters receive no clipboard button or targets.
Dlux reports pages, report builders and user-report surfaces are also excluded.

## Existing assisted entry

The clipboard provides manual snippet insertion only. Automatic next-record
prefill remains the responsibility of **sticky forms**, including its existing
Save & Add More handoff. See [Assisted entry](reference.md#assisted-entry).
The clipboard adds no carry-forward switches or separate prefill mechanism.

## Storage and integration

Snippets are scoped by authenticated user ID in `sessionStorage`, for the
current origin and browser tab: at most 20 snippets of 2,000 characters each.
The base page removes other users' snippet keys when accounts switch and removes
all snippet keys on an anonymous page, including the login page after logout.
A browser-history restore with a different recorded user clears stale clipboard
controls and reloads the page. A missing user ID prevents clipboard initialization.
They render as text and are not sent to a server or read from the operating
system clipboard. **Clear clipboard** removes saved snippets. A browser may
copy session storage when duplicating a tab or preserve it on session restore.
If storage is unavailable, snippets work in memory until page reload.

Full-page forms using the Dlux base and dynamically loaded modal forms initialize
automatically. Custom clients can call `window.DluxEntryClipboard.init(root)`
after inserting forms. Forms with no eligible fields show no clipboard button.
Saved presets, pinning, search and multi-field bundles are future extensions.

## Local CRM acceptance mount

On 2026-10-03 the sales CRM dev stack (`sales_edition/currency-switch`, port 84)
mounted this checkout's `dlux` directory read-only at `/app/dlux` in web and
Celery via `compose.dev.yml`. `./start.sh update -d -nm web celery` recreated
both services and collected static without running migrations. Both import
the local framework source; the source manifest reports 1.10.2b1, but these
unreleased clipboard changes are not part of that published tag.

To return to the image package, remove the two local source-mount entries from
the dev override and rerun the same command. Hard-refresh the browser after
changing static assets because the dev Caddy serves them with immutable caching.

## Local testbed acceptance mount

On 2026-10-03 `testbed-dlux` (port 8088) mounted the same source read-only in web
and Celery at `/app/dlux` and the selected inline release's
`/opt/dlux-runtime/releases/1.10.1b1/dlux` path. The second mount covers supervised
runtime imports. This is a local uncommitted candidate, not the published version
named by the runtime state. Clipboard was off in the testbed settings at mounting.

`./start.sh -nm` applies these mounts without migrations and collects static;
the normal start path reuses the local-only app image, whereas `update` tries
to pull it from a registry. The testbed README documents the four mount lines
and how to restore packaged release testing. Hard-refresh after changing static.
