# Optional PDF toolkit

`dlux.pdf` supplies model-agnostic PDF viewing and modal page editing. Projects
retain ownership of document models, authorization, scoping, revision
identities, storage, and history. The toolkit adds no migrations and does not
discover or rewrite project media. For new work, prefer
[`register_document_file()`](document-files.md), which builds on this toolkit
and supplies the adapter, routes and history.

Install `django-lux[pdf]` for server-side assembly. Adding this extra changes the
wheel's dependency metadata, so it requires a project image rebuild; the inline
updater cannot install it. `pypdf` is imported only when assembly runs, so other
DjangoLux users do not acquire that dependency.

Viewer and editor assets, PDF.js (the legacy build), its worker, its image
decoders and its license are packaged locally under
`dlux/static/dlux/pdf/vendor/` (`vendor/README.md` records the version, source
and integrity). The legacy build runs on Firefox ESR, Chrome and Edge 125+, and
Safari 18+, the browsers DjangoLux supports. PDF.js is an ES module, imported on
demand rather than loaded as a classic script.

Every PDF.js load disables evaluation (`isEvalSupported: false`) and runs with no
WebAssembly (`useWasm: false`): the strict `script-src 'self' 'nonce-…'` policy
allows neither `'unsafe-eval'` nor `'wasm-unsafe-eval'`. JPEG 2000, JBIG2 and
CCITT-fax images decode through the JavaScript image decoders shipped under
`vendor/wasm/<version>/`. The worker is same-origin.

## Integration

Include assets once in the project base-page extension:

```django
{% load dlux_tags %}
{% include_once 'dlux/pdf/assets.html' %}
```

The include carries the viewer, the page editor and their stylesheet. PDF.js
itself loads only when a viewer or editor opens a file, imported through the
`pdf` bundle ([On-demand assets](ui-integration.md#on-demand-assets)). Project
code that calls PDF.js itself waits for it first:

```js
const pdfjsLib = await window.DluxPdfJs.load();
const pdf = await pdfjsLib.getDocument({ data: bytes }).promise;
```

`DluxPdfJs.load()` resolves with the library, having set its worker to the
same-origin worker and pointed it at the shipped image decoders. Its
`getDocument()` applies `isEvalSupported: false` and `useWasm: false`, so callers
need not; it also accepts a bare URL or byte array. Pass a loaded document, or
its loading task, to its own `destroy()` to release the worker.

Before PDF.js has loaded, `window.pdfjsLib` is a stand-in whose
`getDocument(...).promise` loads it first; see
[Deprecation Countdown](deprecation-countdown.md#pdfjslib-before-pdfjs-loads).

Turn on the administrator controls from the consuming app's `dlux_options.py`;
they appear in **System Settings → Extra Features** under **PDF tools**, beside
the Entry clipboard:

```python
from dlux.pdf import register_pdf_options
register_pdf_options()
```

The controls are page editing, file history, maximum pages and maximum combined
size; a project that never calls `register_pdf_options()` sees none of them.

| Setting | Default | Range |
|---|---|---|
| Page editing | on | — |
| File history viewing | on | — |
| Maximum selected pages | 500 | 1–5,000 |
| Maximum combined source size | 100 MiB | 1–500 MiB |

They are stored in the app-owned `extra_config['app']['dlux.pdf']` namespace,
which `get_pdf_features()` reads; only an Extra Features save writes them. The
limits include existing PDF sources, independently of proxy/request size limits.
Disabling tools preserves project data; projects must continue their own
required file preservation.

## Editor adapter

Mount `PdfEditorView.as_view(adapter=YourAdapter())` on a project route. It
returns a modal fragment on GET and assembles/saves on POST inside a
transaction. The adapter contract is:

| Hook | Contract |
|---|---|
| `lookup(request, route_kwargs, lock=False)` | Resolve an authorized document in the correct scope. Require change permission. When `lock=True`, lock the row in the surrounding transaction. Raise 403/404 for refused access. |
| `revision(document)` | Return a string that changes when the document's editable state changes. |
| `context(request, document, route_kwargs)` | Supply `source_url`, `edit_url`, `history_url`, and `download_url`. An empty source URL represents no current PDF. |
| `read_source(request, document, source)` | Return bounded PDF bytes for `current` or a referenced multipart upload. Resolve only allowed sources; never treat the source key as a filesystem path or arbitrary URL. |
| `save(request, document, pdf_bytes)` | Preserve the original, stage output safely, and update project pointers/audit/history. Database rollback does not roll back filesystem writes. |

Requests carry a `revision` and a JSON `manifest`, for example:

```json
[{"source":"current","page":2},{"source":"upload_0","page":1}]
```

- Pages are one-based integers.
- An item may also carry `rotate` (0/90/180/270, clockwise) and `fit: "a4"`: the
  page scaled onto an A4 sheet, portrait or landscape following the page,
  keeping its proportions.
- The assembler rejects empty/malformed selections, out-of-range pages, invalid
  page options, encrypted sources, and configured size/page excesses. Each
  source is read once.
- `assemble_pdf(..., accept=...)` turns any accepted `dlux.files` kind into pages
  first, so images (JPG/JPEG, PNG, TIF/TIFF, WebP) are sources too, embedded
  without quality loss.
- The result is cleaned up losslessly (`optimize_pdf_writer`: Flate content
  streams, identical objects stored once).

`PdfEditorView.accept` (default `('pdf',)`) chooses which kinds the editor's
chooser offers. Images are converted to PDF pages in the browser's round trip
through `POST /sys/files/convert/` (`dlux_files_convert`) before upload, so a
project adapter's `read_source` still receives PDF bytes.

Editing-disabled requests receive 403 before adapter lookup. Authentication and
ordinary project CSRF middleware remain required. Authorization and
source/history routes are deliberately project responsibilities.

A project's source view should answer with
`dlux.files.serving.serve_file(request, field_file, content_type='application/pdf')`
after its own access check. It serves byte ranges, so pdf.js can start before a
large scan finishes downloading, and `ETag`/`Last-Modified` with `304`, so
reopening a record does not download the file again. See
[Serving stored files](document-files.md#serving-stored-files).

## Viewer and history

Render `dlux/pdf/viewer.html` with `source_url`, `file_name`, `download_url`,
`edit_url`, `history_url`, `can_edit`, and `pdf_features`. No model field name is
assumed. The viewer initializes on dynamically inserted content and releases its
PDF worker when removed/closed.

- The page opens fitted to the viewer's width. **Zoom in / Zoom out** step by
  25% between 50% and 300% of that fit, and the page is drawn at the screen's
  pixel density so it stays sharp. The fit follows the viewer's size (modal,
  window, fullscreen).
- **Fullscreen** toggles: the button switches to an exit icon and label
  (`pdf_exit_fullscreen_label`) and follows the document, so leaving with Esc
  resets it too.
- The canvas is always `direction: ltr`, since pdf.js positions text itself.
- When pdf.js cannot draw the file, the browser's own viewer shows it in an
  iframe; page and zoom buttons are disabled there, print and fullscreen still
  work. The iframe is loaded only for that fallback, so a normal view downloads
  the file once.

In the dynamic modal, the viewer's history, extracted text and edit buttons open
on top of the entry, and their Back returns to it
([Sections and dynamic modals](ui-integration.md#sections-and-dynamic-modals)).

The editor uses a DjangoLux file widget, supports reorder/remove/append, page
selection, Rotate and Fit to A4, guards unsaved page edits (on close, Back, and
links to another view in the modal), releases thumbnail workers, and avoids
submitting an untouched current PDF. Its Scan button uses
the shared ScanLink client (`window.DluxScan.scan()` from `scan_button.js`), the
same routine as the file card: health check, scanner selection, progress and
translated errors.

Saving is disabled while source pages are loading. Closing or replacing the
editor cancels active PDF loads; a late save reply cannot navigate away from a
newer modal surface.

`dlux/pdf/history.html` consumes a display `document`, `versions`,
`is_modal=True`, and an optional `history_return_url`. Each version provides
`version_number`, `action_type`, `page_count`, `file_name`, `download_url`, and
`created_at`.

- Optional `created_by` supplies the **Changed by** column (full name, falling
  back to username; `—` without an actor): who performed the change that
  archived the file. Load it with `select_related()` for queryset-backed rows.
- Supply permission-checked download URLs, not public file paths.
- Enforce `history_enabled` in project history/download handlers.

Archive's `documents/pdf.py` is a worked example of a project adapter.

A project that adopts the toolkit with its own history model (such as a
`DocumentFileVersion`) keeps its existing history rows, content-type/object
references, version numbers, and `archived_file` paths. Adoption requires no
file-history conversion or automatic PDF normalization/backfill. Validate
existing current and historical downloads byte-for-byte on a restored copy
before deployment, and preserve project-specific secondary attachment behavior.
To move those rows into `dlux.FileVersion` later, see
[Moving a project's own history](document-files.md#moving-a-projects-own-history).

## Modal save extensions

Existing response semantics remain unchanged unless the caller opts in:

- `close_modal: true` with `refresh_parent: true` closes/refreshes even when
  saving a form reached through a deeper modal surface.
- `add_more_url` with `add_more: true` persists the exact next-form URL before
  refreshing. Projects must authorize any prefill target themselves.
- A submission reply received after another modal navigation does not replace
  the newer surface.

## Tests

The assembly, editor and document-file tests need `pypdf`, so install the `pdf`
extra (`pip install -e '.[pdf]'`) before running the suite; CI and the release
workflow do the same.
