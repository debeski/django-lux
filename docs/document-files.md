# Document files — design for 1.12.0b2

**Status:** design approved 14 October 2026 (decisions D1–D4 in §6). Branch `feat/document-file-pipeline` from `origin/main` (= `v1.12.0b1`). The owner agreed the direction on 14 October 2026: history moves into DjangoLux, the PDF editor uses ScanLink, file-type checks live in DjangoLux and are extendable, images are supported, and one setup call connects everything. §6 records the decisions.

## 1. What exists today (checked in source)

| Piece | Today | Problem |
|---|---|---|
| File card (`DluxFileInput`, `build_file_field`) | Upload card with a Scan button when ScanLink is on. | Knows nothing about what file types the field accepts beyond an `accept` attribute. |
| ScanLink client (`helpers/scanlink/js/main.js`, `scan_button.js`) | Job-based client: health probe, HTTPS/HTTP fallback, scanner selection, progress, errors. Produces a PDF. | — |
| PDF editor (`dlux.pdf`: `PdfEditorView`, `assemble_pdf`, `editor.js`) | Page reorder/remove/append, modal transport, project adapter (`lookup`, `revision`, `context`, `read_source`, `save`). | Its Scan button `fetch`es `http://localhost:5000/scan` directly (`editor.js:239`), bypassing the ScanLink client: no HTTPS fallback, no scanner choice, no progress, different errors. PDF only. |
| File history | Not in DjangoLux. Archive and Decrees each own a `DocumentFileVersion` model and about ten helpers (`archive_previous_pdf`, `save_active_pdf_bytes`, `finalize_archive_pdf`, `_next_version_number`, `write_pdf_metadata`, …). | The two models are column-identical and the helpers are copies. Every new project would copy them again; the history and download routes are re-written per project. |
| File-type checks | None in DjangoLux for documents. Archive/Decrees validate PDFs in their forms; the asset manager has its own image/font checks (`dlux/assets.py`, Pillow). | Three independent rule sets. |
| Asset manager | Shared library of reusable images/fonts (`ManagedAssetField`). | Separate by design; later it should reuse the same type checks and upload path (§5). |

Pillow is already a core DjangoLux dependency (`pillow>=11.0`) and reads JPEG, PNG, TIFF and WebP; `pypdf` comes with the `pdf` extra. Image support needs no new package.

## 2. Target: one document-file pipeline

**Get pages** (PDF upload, image upload, ScanLink) → **arrange** (editor) → **save one PDF** → **keep the previous file** (history) → **view / download** — all provided by DjangoLux and connected by one call.

### 2.1 File types (`dlux.files`)

A registry of accepted file kinds, each with extensions, MIME types, a content sniff, a size limit, and how it becomes PDF pages:

```python
from dlux.files import register_file_type

register_file_type('pdf', extensions=['.pdf'], sniff=b'%PDF-', to_pages=pdf_pages)          # built in
register_file_type('image', extensions=['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp'], to_pages=image_pages)  # built in
register_file_type('heic', extensions=['.heic'], to_pages=my_heic_pages)                     # a project extension
```

- Checks run server-side on the content (magic bytes / Pillow decode), never the name alone. Renamed or corrupt files are refused with a translated message.
- A document field declares which kinds it accepts (`accept=('pdf', 'image')`, default both). The file card's `accept` attribute, the editor's chooser, and server validation all read the same declaration.
- Limits: the existing PDF tools settings (max pages, max combined MB) still apply to the whole assembly; each kind may add its own per-file limit (images: max pixels to stop decompression bombs).

### 2.2 Images as pages

`assemble_pdf` accepts any registered kind. JPG/JPEG, PNG, TIFF/TIF and WebP become pages — one per image, and one per frame of a multi-page TIFF: EXIF orientation honoured, alpha flattened onto white, converted with Pillow. By default an image page keeps the image's own size and proportions (the image's DPI when it records a sane one, 72–1200, otherwise 150 DPI), so A3 scans, receipts and screenshots stay as they are (§6 D2). The editor previews images as page thumbnails and lets them be rotated, reordered and removed like PDF pages. The manifest gains two optional per-page settings that apply to PDF and image pages alike: `rotate` (0/90/180/270) and `fit` (`"a4"`): **Fit to A4** scales the selected pages onto an A4 sheet, portrait or landscape following the page, keeping proportions and centring them.

### 2.3 ScanLink in the editor

The editor's Scan button uses the shared ScanLink client (scanner selection, progress, HTTPS/HTTP fallback, the same translated errors as the file card). The scanned PDF is added as a new source, exactly like an uploaded file. The direct `fetch('http://localhost:5000/scan')` is removed. (Image output from ScanLink is a later ScanLink-side option; nothing here depends on it.)

### 2.4 History in DjangoLux

- DjangoLux ships a concrete history model, `dlux.FileVersion` (additive migration in `dlux`): generic link (`content_type`, `object_id`), `field_name`, `version_number`, `action_type` (`replace`, `edit`, `normalize`, `clear`), `archived_file`, `active_name_before/after`, `page_count`, `metadata`, scope and audit fields from `ScopedModel`; unique on (content type, object, field, version). Same columns as the Archive/Decrees tables.
- One service does what the copied helpers do today: copy the previous file byte-for-byte into history, write the new file under a new storage name, write PDF metadata, update the field and audit, and roll back cleanly if anything fails (`dlux.files.history.save_new_version`, `archive_previous`, `finalize`).
- Every project uses `dlux.FileVersion` (§6 D1). A project with its own history table moves its rows over once with `manage.py dlux_adopt_file_history <app.Model>`: rows are copied with their document link, field, version numbers, action, archived file name, page count, metadata, scope and audit fields; the archived files themselves stay where they are on disk. The command is idempotent (an adopted row is recognised by document, field and version), refuses conflicting rows, reports counts, and `--verify` compares every copied row and file hash. The project's old table stays untouched until a later project release retires it. Archive and Decrees then delete their copied helpers.
- Soft delete/restore of a document soft-deletes/restores its history rows (the Archive 1.3.0 behaviour, now in DjangoLux).

### 2.5 One setup call

```python
# documents/dlux_options.py (or apps.ready)
from dlux.files import register_document_file

register_document_file(
    Decree, 'pdf_file',
    accept=('pdf', 'image'),
    file_name=decree_pdf_name,                        # optional naming callable
    pdf_metadata=decree_pdf_metadata,                 # optional title/subject/keywords
    can_access=archive_can_access,                    # optional extra rule, e.g. Archive's reviewers
)
```

That one call provides, with no project views or templates:

- Routes under `dlux.urls`: `/sys/files/<app>/<model>/<pk>/<field>/` `source/`, `download/`, `edit/` (editor), `history/`, `history/<version>/download/`.
- Access: `view_<model>` to view/download/history, `change_<model>` to edit, the model's `ScopedManager` scope, soft-deleted rows hidden — plus the optional `can_access(request, document, action)` hook for project rules. Backend checks match what the UI shows (DSRP-1).
- `{% dlux_document_viewer object 'pdf_file' %}` renders the viewer with the right URLs; the file card in forms gets the accepted types and Scan button from the registration; the modal form save path calls the history service when the file changes.
- The PDF tools settings (editing on/off, history on/off, limits) keep working as today.

### 2.6 Compatibility

`PdfEditorView` with a project adapter keeps working in 1.12 (listed in `docs/deprecation-countdown.md` with a removal target), so Archive and Decrees run unchanged on 1.12.0b2 and move to `register_document_file` in their own releases. The downstream grep and `tests/test_downstream_compat.py` cover `dlux/pdf/*` templates and `dlux.pdf` symbols they import.

## 3. Asset manager

Stays a separate feature (a reusable library, deletable when unused; not record history). Once this pipeline is established it reuses the same file-type registry and upload checks, and the file card's Scan/camera input can feed it. Not part of 1.12.0b2.

## 4. Project follow-ups (each in its own release, after 1.12.0b2)

- **Archive:** run `dlux_adopt_file_history documents.DocumentFileVersion` (a few hundred rows), then replace `documents/pdf.py` adapter + history helpers with `register_document_file(...)`; the reviewer PDF route uses `can_access`; 1.3.1 "multiple images" becomes turning on `accept=('pdf', 'image')`.
- **Decrees:** the same: adopt its history rows, then switch.
- **CRMs / others:** opt in only where they hold document files.

Byte-for-byte checks of current and historical downloads on a restored copy are required before either project deploys the switch.

## 5. Implementation order (branch `feat/document-file-pipeline`)

1. `dlux.files` type registry + server-side checks (PDF, JPG/JPEG, PNG, TIFF/TIF, WebP built in); tests incl. renamed/corrupt/oversized files.
2. Image pages in `assemble_pdf` + per-page rotation; editor thumbnails for images.
3. Editor Scan through the ScanLink client.
4. `dlux.FileVersion` + history service + soft-delete cascade + `dlux_adopt_file_history` (copy, idempotency, `--verify`).
5. `register_document_file`: routes, access rules, viewer tag, form/file-card wiring, modal-save hook.
6. Compatibility shims, deprecation entry, downstream compat tests; docs (`FEATURES.md`, `reference.md`, `pdf-toolkit.md`, this file); changelog; `1.12.0b2`.
7. Acceptance on the testbed: Decrees on 1.12.0b2 unchanged; a scratch project using only `register_document_file`; Archive/Decrees history tables plugged in on restored copies with byte-for-byte download checks; desktop/mobile/Arabic browser journeys.

## 6. Decisions for the owner

- **D1 — History storage. Decided 14 October 2026:** one table everywhere. Projects move their history rows into `dlux.FileVersion` (deployed history is a few hundred editor changes); archived files are not moved.
- **D2 — Image page size. Decided 14 October 2026:** pages keep their own size by default (A3 scans, receipts and screenshots are not forced to A4); **Fit to A4** is an editor option for the selected pages, PDF or image.
- **D3 — Keep original images? Decided 14 October 2026:** no. The assembled PDF is the record; earlier PDFs, including pages that came from images, stay in history.
- **D4 — Accepted image types in 1.12.0b2. Decided 14 October 2026:** JPG, JPEG, PNG, TIF, TIFF and WebP become PDF pages. A multi-page TIFF contributes one page per frame; an animated WebP contributes its first frame. Other types (e.g. HEIC) can be added later through the registry.
