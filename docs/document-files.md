# Document files

A *document file* is a model `FileField` that holds a record's PDF. DjangoLux
connects everything around it — the upload card (with Scan), accepted file
types, the PDF viewer, the page editor, downloads and file history — from one
registration. Projects keep their models, permissions and naming; they write no
views, templates or history code.

Since 1.12.0b2. Designed and approved 14 October 2026 (decisions in §8).

Stable 1.12.0 promotes the published, accepted 1.12.0b3 implementation without runtime, dependency or migration changes. The additive `0026_file_versions` migration applies through the normal migration flow; registering project fields and adopting legacy history remain explicit project integration steps. Installation does not automatically register fields, copy history rows or rewrite archived files. The inline image floor remains `>=1.11.0b7`; older images must be rebuilt first. See [1.12 release acceptance](release-1.12-acceptance.md).

## 1. One call

```python
# <app>/apps.py — AppConfig.ready()   (or the app's dlux_options.py)
from dlux.files.registry import register_document_file

register_document_file(
    Decree, 'pdf_file',
    accept=('pdf', 'image'),            # default; kinds from the file-type registry (§2)
    file_name=decree_file_name,         # optional: (document, field_name) -> storage name
    pdf_metadata=decree_pdf_metadata,   # optional: document -> {'/Title': ..., ...}
    can_access=reviewer_access,         # optional: (request, document, action) -> True / False / None
    queryset=archive_queryset,          # optional: (request, model) -> QuerySet to look documents up in
)
```

| Hook | Default |
|---|---|
| `accept` | `('pdf', 'image')` |
| `file_name` | the field's `upload_to` applied to `<model>_<pk>.pdf`; a name containing `/` is used as is. The storage never overwrites; a taken name gets a suffix. |
| `pdf_metadata` | `{'/Title': str(document), '/Subject': <verbose name>}`; existing info keys are kept unless replaced. |
| `can_access` | `None` for every action, i.e. the standard check below. `True` grants, `False` refuses. Actions: `view`, `download`, `history`, `edit`. |
| `queryset` | the dynamic modal's scope- and access-filtered set (`_scope_filtered_modal_queryset`). A project whose central users see `scope IS NULL` rows supplies its own. |

The standard check is `view_<model>` for `view`/`download`/`history` and `change_<model>` for `edit`, on a document found in the lookup set (scope applied, soft-deleted rows hidden). Backend checks match what the UI offers (DSRP-1).

## 2. File types (`dlux.files`)

```python
from dlux.files import register_file_type

register_file_type(
    'heic', extensions=['.heic'], mime_types=['image/heic'],
    sniff=lambda data: data[4:12] in (b'ftypheic', b'ftypheix'),
    to_pdf=heic_to_pdf,                 # bytes -> PDF bytes; omit for kinds that are stored but not paged
    label_key='files_type_heic', label='HEIC', max_bytes=50 * 1024 * 1024,
)
```

- Built in: `pdf` and `image` (JPG/JPEG, PNG, TIF/TIFF, WebP).
- `detect_file_type(data, filename, accept)` decides by **content**: the extension must belong to an accepted kind and the bytes must match it. Renamed, damaged and unaccepted files raise `ValueError` with a translated message (`files_*` strings). `validate_upload(upload, accept, limit)` is the form version (`ValidationError`), `to_pdf_bytes()` returns PDF bytes, `accept_attribute(accept)` the `<input accept>` value, `convertible_types()` the kinds other than PDF that can become pages.
- Images become pages without quality loss: a JPEG is embedded byte-for-byte (its EXIF orientation becomes the page rotation; mirrored orientations are redrawn losslessly), every other image is stored as Flate-compressed pixels. One page per image and one per frame of a multi-page TIFF (an animated WebP gives its first frame); transparency is flattened onto white; a page keeps the image's own size at its recorded DPI (72–1200) or 150 DPI. Frames above 280 megapixels and decompression bombs are refused.
- Every assembled or saved PDF is cleaned up losslessly (`dlux.pdf.assembly.optimize_pdf_writer`): page content streams are Flate-compressed and identical objects are stored once. Nothing is downsampled; lossy shrinking is not offered yet.

## 3. What the registration provides

| Surface | Detail |
|---|---|
| Routes (in `dlux.urls`) | `/sys/files/<app>/<model>/<pk>/<field>/` + `source/` (inline), `download/`, `edit/` (page editor), `history/` (modal list), `history/<version>/download/`. Names `dlux_document_file_source`, `_download`, `_edit`, `_history`, `_version`. Excluded from navigation discovery. |
| Viewer | `{% load dlux_files %}{% dlux_document_viewer object 'pdf_file' %}` renders `dlux/pdf/viewer.html` with these routes; edit and history buttons follow the user's access and the PDF tools settings. `dlux.files.views.document_file_context()` gives the same context to a project template. |
| Page editor | The built-in `DocumentFileAdapter` behind `PdfEditorView` (accept = the registration's kinds). Images join as pages; pages can be selected, rotated and fitted to A4; Scan uses ScanLink (§5). Saving keeps the previous file in history. |
| Forms | Every form the dynamic modal builds gets, for each registered field, the DjangoLux file card with Scan, the `accept` attribute and the server-side type check (`dlux.files.forms.apply_document_file_fields(form)`; a project form can call it too). |
| Modal save | The modal save and the history write share one transaction: a replaced file goes to history (`replace`, or `clear` when emptied), a new PDF gets metadata and its target name, and an accepted image uploaded through the form becomes the PDF (the uploaded image itself is not kept). |
| Soft delete | Deleting a registered document (`instance.delete()` or `queryset.delete()`) soft-deletes its history rows with the same time and actor; `restore()` brings back exactly those rows. |

The PDF tools settings (System Settings → Extra Features: editing, history, maximum pages and size) still apply to every surface.

## 4. File history

- `dlux.FileVersion` (migration `0026_file_versions`, additive and inline-safe): generic document link, `field_name`, `version_number`, `action_type` (`replace`, `edit`, `normalize`, `clear`), `archived_file` (`dlux/file_history/<app>_<model>/<id>/<field>/v<n>_<name>`), `active_name_before`/`after`, `page_count`, `metadata`, scope and audit fields. Unique on document + field + version. History rows take the document's scope, never the actor's.
- `dlux.files.history`: `save_new_version(document, pdf_bytes, field_name, user)` (editor saves), `record_upload(document, previous_name, field_name, user)` (form saves), `archive_previous(...)`, `versions_for(document, field)`, `next_version_number(...)`. The previous file is always copied byte-for-byte before the new one is written under a new storage name; nothing is overwritten. A missing original stops the save.
- Soft-delete wiring uses `dlux.models.soft_delete_signals` (`soft_deleted`, `restored`). `ScopedModel` and `ScopedQuerySet` gather the arguments only when a receiver is connected for that model, so unregistered models pay nothing.
- The history table shows **Changed by** from each version's `created_by`: the person who edited, replaced or cleared the file, alongside the timestamp. It displays their full name, falls back to username, and shows `—` when no actor is recorded. The archived PDF is the file from before that change.

### Moving a project's own history

```bash
python manage.py dlux_adopt_file_history documents.DocumentFileVersion           # dry run: counts only
python manage.py dlux_adopt_file_history documents.DocumentFileVersion --apply --verify
```

Copies every row (soft-deleted ones included) with all values kept: document link, field, version number, action, archived file name, before/after names, page count, metadata, scope, created/updated/deleted times and users. Archived files stay where they are; the copies point at the same storage names. Re-running skips adopted rows; a different row with the same document/field/version is a conflict and stops the run before anything is written. `--verify` checks each copy and that its file can be read. The source table is never modified; a later project release retires it.

## 5. Scan

`scan_button.js` exposes `window.DluxScan.scan({messages, onProgress, metadata})`, which resolves to the scanned PDF. The file card's Scan button and the page editor both call it, so they share the ScanLink health checks (HTTPS/HTTP fallback), scanner selection, progress text and translated errors. File-card Scan buttons inside modals loaded after the page work through event delegation. The attribute set with the wording lives in `dlux/helpers/scanlink/scan_messages.html`. ScanLink stays opt-in (System Settings → Extra Features); without it no scan code reaches the page.

## 6. Existing adapters

`PdfEditorView` with a project adapter is unchanged: `accept` defaults to `('pdf',)`, so existing editors offer PDFs only; setting `accept=('pdf', 'image')` adds images, converted to PDF in the browser round trip (`POST /sys/files/convert/`, `dlux_files_convert`) so the adapter still reads PDF bytes. This path and project-owned history models keep working through v1.x and are scheduled for removal in v2.0 ([Deprecation countdown](deprecation-countdown.md)).

## 7. Moving a project over

1. Upgrade to 1.12.0b2+ (migration `0026` applies).
2. `register_document_file(...)` for each document field, with `queryset`/`can_access` where the project's rules differ from the defaults, and `file_name`/`pdf_metadata` to keep its naming.
3. `dlux_adopt_file_history <app.Model> --apply --verify` on a restored copy, then in production.
4. Replace project PDF routes/templates with the DjangoLux routes and `{% dlux_document_viewer %}`; delete the copied history helpers.
5. Check current and historical downloads byte-for-byte on the restored copy before deploying.

## 8. Decisions (14 October 2026)

- **D1 — History storage:** one table, `dlux.FileVersion`; projects move their rows with `dlux_adopt_file_history` (deployed history is a few hundred editor changes); archived files do not move.
- **D2 — Page size:** pages keep their own size (A3 scans, receipts and screenshots stay as they are); **Fit to A4** is an editor option for selected pages, PDF or image.
- **D3 — Original images:** not kept. The assembled PDF is the record; earlier PDFs, including pages that came from images, stay in history.
- **D4 — Image types:** JPG, JPEG, PNG, TIF, TIFF and WebP; more through `register_file_type()`.
- The asset manager stays a separate feature (a reusable library). It will reuse the file-type registry and upload checks in a later release.
