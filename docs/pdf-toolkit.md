# Optional PDF toolkit

`dlux.pdf` supplies model-agnostic PDF viewing and modal page editing. Projects retain ownership of document models, authorization, scoping, revision identities, storage, and history. The feature introduces no migrations and does not discover or rewrite project media.

Install `django-lux[pdf]` for server-side assembly. Adding this extra changes wheel dependency metadata, so the maintenance release requires a project image rebuild; it cannot be installed by the existing inline updater. `pypdf` is imported when assembly runs, so other DjangoLux users do not acquire that dependency. Viewer/editor assets, PDF.js 3.11.174, its worker, and its license are packaged locally. Every PDF.js load disables evaluation.

## Integration

Include assets once in the project base-page extension:

```django
{% load dlux_tags %}
{% include_once 'dlux/pdf/assets.html' %}
```

Turn on the administrator controls from the consuming app's `dlux_options.py`; they appear in **System Settings → Extra Features** under **PDF tools**, beside the Entry clipboard (since 1.11.1; earlier releases drew a separate Options tile):

```python
from dlux.pdf import register_pdf_options
register_pdf_options()
```

The controls are page editing, file history, maximum pages and maximum combined size; a project that never calls `register_pdf_options()` sees none of them. They are stored where they always were, `extra_config['app']['dlux.pdf']`, so upgrading keeps existing values, and only an Extra Features save writes them. `get_pdf_features()` reads that namespace. Editing and history viewing default on; selected pages default to 500 and combined source bytes to 100 MiB. Administrators may configure 1–5,000 pages and 1–500 MiB. The limits include existing PDF sources, independently of proxy/request size limits. Disabling tools preserves project data; projects must continue their own required file preservation.

## Editor adapter

Mount `PdfEditorView.as_view(adapter=YourAdapter())` on a project route. It returns a modal fragment on GET and assembles/saves on POST inside a transaction. The adapter contract is:

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

Pages are one-based integers. An item may also carry `rotate` (0/90/180/270, clockwise) and `fit: "a4"` (the page scaled onto an A4 sheet, portrait or landscape following the page, keeping its proportions). The assembler rejects empty/malformed selections, out-of-range pages, invalid page options, encrypted sources, and configured size/page excesses; each source is read once. `assemble_pdf(..., accept=...)` turns any accepted `dlux.files` kind into pages first, so images (JPG/JPEG, PNG, TIF/TIFF, WebP) are sources too, embedded without quality loss. The result is cleaned up losslessly (`optimize_pdf_writer`: Flate content streams, identical objects stored once).

`PdfEditorView.accept` (default `('pdf',)`) chooses which kinds the editor's chooser offers. Images are converted to PDF pages in the browser's round trip through `POST /sys/files/convert/` (`dlux_files_convert`) before upload, so a project adapter's `read_source` still receives PDF bytes. For new work prefer [`register_document_file()`](document-files.md), which supplies the adapter, routes and history.

Editing-disabled requests receive 403 before adapter lookup. Authentication and ordinary project CSRF middleware remain required. Authorization and source/history routes are deliberately project responsibilities.

## Viewer and history

Render `dlux/pdf/viewer.html` with `source_url`, `file_name`, `download_url`, `edit_url`, `history_url`, `can_edit`, and `pdf_features`. No model field name is assumed. The viewer initializes on dynamically inserted content and releases its PDF worker when removed/closed.

The editor uses a DjangoLux file widget, supports reorder/remove/append, page selection, Rotate and Fit to A4, guards unsaved page edits, releases thumbnail workers, and avoids submitting an untouched current PDF. Its Scan button uses the shared ScanLink client (`window.DluxScan.scan()` from `scan_button.js`), the same routine as the file card: health check, scanner selection, progress and translated errors.

Saving is disabled while source pages are loading. Closing or replacing the editor cancels active PDF loads; a late save reply cannot navigate away from a newer modal surface.

`dlux/pdf/history.html` consumes a display `document`, `versions`, `is_modal=True`, and an optional `history_return_url`. Each version provides `version_number`, `action_type`, `page_count`, `file_name`, `download_url`, and `created_at`. Optional `created_by` supplies the **Changed by** column (full name, falling back to username; `—` without an actor). This identifies who performed the change that archived the file. Load `created_by` with `select_related()` for queryset-backed rows. Supply permission-checked download URLs, not public file paths. Enforce `history_enabled` in project history/download handlers.

The Archive adapter is a worked example in `documents/pdf.py`. Decrees can adopt the same toolkit later through its own adapter; its models and storage do not need to move into DjangoLux.

Both projects already have a project-owned `DocumentFileVersion` model. Adoption must reuse existing history rows, content-type/object references, version numbers, and `archived_file` paths. It requires no file-history conversion or automatic PDF normalization/backfill. Validate existing current and historical downloads byte-for-byte on a restored copy before deployment; preserve project-specific secondary attachment behavior.

## Modal save extensions

Existing response semantics remain unchanged unless the caller opts in:

- `close_modal: true` with `refresh_parent: true` closes/refreshes even when saving a form reached through a deeper modal surface.
- `add_more_url` with `add_more: true` persists the exact next-form URL before refreshing. Projects must authorize any prefill target themselves.
- A submission reply received after another modal navigation does not replace the newer surface.

## Acceptance

Run the registered PDF tests, translation/template/widget policy tests, import-cycle checks, and the framework suite. Verify the consuming app on its stable baseline and again on the final packaged provider. A local source overlay establishes compatibility, not publication or stable release acceptance.

Archive must use a published stable provider before its 1.2.0 release. The feature branch's 1.11.0b7 metadata is an unpublished development candidate; it is not an approved Archive dependency or an instruction to publish/promote the framework's beta line.

The maintenance beta `1.10.3b1`, based on published `1.10.2`, was published and accepted on 2026-10-12. Stable `1.10.3` is prepared with the same implementation; the beta alone does not satisfy Archive's release requirement. CI installs the optional PDF extra so assembly tests execute. See [published beta acceptance](pdf-release-acceptance.md) for evidence and limits.

## Main-line reconciliation

The 1.11.0b7 candidate uses the exact PDF Python module, templates, assets, and regression tests published in stable 1.10.3. Main-line Entry Clipboard initialization and submitter capture remain in the shared modal transport. The optional dependency metadata requires a rebuilt project image; the candidate forbids inline installation and declares `requires.baked_image >=1.11.0b7`, including when its own tag enters baseline history. This toolkit adds no migrations; the existing 1.11 backup migrations remain additive. CI and release test jobs install the PDF extra. Publication is separate from branch integration.

Reconciliation validation (2026-10-12): all 2,775 main-line Python tests pass (five expected database/inline-policy skips), all 66 JavaScript tests pass, wheel/sdist and release classification/manifest gates pass, and all 644 wheel package files match source. PDF implementation/assets/tests match stable 1.10.3 byte-for-byte. Evidence: `.xclude/validation/mainline-pdf-reconciliation-2026-10-12/`.

[PR #3](https://github.com/debeski/django-lux/pull/3) merged into `main` after [CI 38285965692](https://github.com/debeski/django-lux/actions/runs/38285965692) passed Python 3.11–3.13. An isolated Decrees reference-stack container baked with the candidate wheel additionally verified all 644 installed package files, then passed all three models’ real preview/edit/history Back/page removal/save/exact prior-file download journeys, bookmarks, Options, desktop/mobile layout and zero browser page errors. Only synthetic fixture rows/files were added to the copied stack; the acceptance container is stopped and retained. The candidate remains untagged/unpublished; stable consumer pins remain on 1.10.3.
