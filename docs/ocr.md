# OCR text for document files

`dlux.ocr` reads the text of registered document files with [Indra OCR](https://github.com/datalab-to/indra), a CPU-only ONNX engine with Arabic, Latin and 80+ other scripts. Every field registered with `register_document_file()` takes part unless it opts out; nothing else is needed in a project.

The engine runs in the stack's `ocr` service (image `debeski/dlux-ocr`, source `docker/ocr/`). It is reachable only on the internal Compose network, has no published ports and no internet access (its models are baked into the image), and loads its models on the first request, so it idles small while OCR is off. Saves never fail because of OCR: when the service is stopped, missing or busy, rows stay queued and retry.

## For administrators

**System Settings > Extra Features > OCR text extraction** (`SystemSettings.extra_config['ocr']`, exported and imported with the rest of `extra_config`):

| Option | Default | Environment fallback | Meaning |
|---|---|---|---|
| Enable OCR | off | `OCR_ENABLED` | Master switch. Off: nothing is read or queued, Run OCR is refused; text read earlier stays visible and searchable. |
| Read new and replaced files automatically | on | `OCR_AUTO_ON_SAVE` | Read after each save that changes the file. Off: only Run OCR and the backfill read files. |
| Include extracted text in search | on | `OCR_SEARCH` | Global search and `arabic_search_q(..., model=...)` match OCR text. |
| Reading mode | Use the text layer, OCR the rest | `OCR_MODE` (`auto`/`ocr`) | `auto` keeps a sound PDF text layer and OCRs the rest; `ocr` always OCRs. |
| OCR service address | `http://ocr:8080` | `OCR_URL` | http/https only. |
| Time limit per file | 900 s | `OCR_TIMEOUT` | 30–7200; also when a `running` row counts as abandoned. |
| Largest file | 64 MB | `OCR_MAX_FILE_MB` | 1–512; larger files are not sent. |
| CPU threads per file | 2 | `OCR_THREADS` | 1–16, capped by the container's `OCR_MAX_THREADS`. |

Saved values win; an environment string fills an option never saved (or saved invalid); built-in defaults fill the rest. The section shows whether the service answers.

**Starting and stopping the service.** Saving a *change* of Enable OCR asks for the current password (the same check as the Operations panel; superusers only, POST through the settings save) and then queues `service-start` (on) or `service-stop` (off) for the `ocr` service through Composer, audited as `DLUX_OPS_RUN` exactly like a panel action. The section shows the request's progress and result. When Composer is too old, unreachable or busy with another operation, the setting is still saved and the section and a notification say why, pointing to the **Operations panel** (Options > admin rail), which also lists `ocr` with Start, Stop, Restart and Recreate. Saves that do not change the switch never touch the service.

**Reading the text.** The document viewer's toolbar has an **Extracted text (OCR)** button next to History. It opens the text and markdown (escaped, `dir="auto"`), the engine, page count, duration and confidence, and — for users who may edit the document — **Run OCR** / **Run OCR again**, queued ahead of automatic and backfill work. The panel refreshes itself while the file is queued or running.

## For developers

```python
from dlux.files.registry import register_document_file

register_document_file(Decree, 'pdf_file')             # OCR on (default)
register_document_file(Decree, 'attachment', ocr=False)  # this field never read
```

- **Storage**: `dlux.FileText` (migration `0029_file_text`, additive). One row per document, field and file SHA-256 (`dlux_file_text_unique`), so an unchanged file is never read twice; `is_current` marks the row for the file the document holds now, older rows remain. Scope follows the document. Fields: status (`pending`, `running`, `done`, `failed`, `skipped`), source (`auto`, `manual`, `backfill`), requester, engine/engine version/model version, markdown, text, per-page JSON (lines with boxes and confidence, layout blocks, rotation, timings), page count, mean confidence, timings, duration, attempts, error, `file_version` (the `FileVersion` whose save produced this file).
- **Flow**: `post_save` on a registered model schedules after commit (`dlux.ocr.service.schedule`). The Celery task `dlux.tasks.ocr_file` runs at Redis priority 6 (automatic), 0 (Run OCR) or 9 (backfill), and retries a busy or unreachable service after 30 s, 1, 2, 5, 10, 15, 30 and 60 minutes before marking the row `failed`; a `422`-type refusal fails at once; a file changed before the worker ran is `skipped`.
- **Provider seam**: `dlux.ocr.client.call_service(content, mode=None)` is the only call to the engine; replacing Indra means an adapter in `docker/ocr/engines.py` that returns the same JSON (`OCR_ENGINE`), with no DjangoLux change.
- **Search**: `arabic_search_q(term, fields, model=queryset.model)` adds rows whose current OCR text matches (Arabic variants included); without `model` it is unchanged. Global search's data provider adds OCR matches for registered models automatically. `dlux.ocr.service.search_q(model, term)` is the underlying `Q`.
- **Routes**: `GET/POST sys/files/<app>/<model>/<pk>/<field>/text/` (`dlux_document_file_text`): GET needs view access, POST (Run OCR) edit access; both go through `resolve_document`, so the field's `can_access`/`queryset` hooks and scope apply.

### Commands

```bash
python manage.py dlux_ocr_backfill --dry-run
python manage.py dlux_ocr_backfill --batch-size 50 --limit 500
python manage.py dlux_ocr_backfill --files documents.decree.pdf_file --enqueue
python manage.py dlux_ocr_backfill --retry-failed --restart
python manage.py dlux_adopt_ocr_text documents.DocumentOCR            # dry run
python manage.py dlux_adopt_ocr_text documents.DocumentOCR --apply
```

`dlux_ocr_backfill` reads existing files in the command's own process (Celery stays free) and saves its position per file key after every document in `logs/dlux-ocr-backfill.json`; rerun to continue, `--restart` to start over. It stops with "rerun to resume" when the service stays unavailable. `--enqueue` queues on Celery at backfill priority instead.

`dlux_adopt_ocr_text` copies a project's own OCR rows (shaped like Archive's `documents.DocumentOCR`) into `FileText`: dry run by default, idempotent by document/field/SHA-256, conflicts stop the run before anything is written, the source table is untouched. Run it after `dlux_adopt_file_history` so copies re-link to adopted file versions.

## Stack

- Contract (`dlux/contracts/stack.json`): `ocr` is an **optional** service on `internal` only, `restart: safe`, in `invariants.restart.lifecycle` (startable/stoppable) and `invariants.optional_services`. Drift checks skip it when a deployment does not have it.
- Scaffold `compose.yml`: the `ocr` service (`OCR_IMAGE`, default `debeski/dlux-ocr:latest`), read-only root, `tmpfs` `/tmp`, dropped capabilities, `mem_limit` `OCR_MEMORY_LIMIT` (3g), container caps `OCR_WORKERS` (1), `OCR_MAX_THREADS` (4), `OCR_MAX_BYTES` (512 MiB), and `ocr` in `COMPOSER_AGENT_RESTART_SERVICES`. Existing projects add the same block and allow-list entry by hand.
- Image: built from `docker/ocr/` and published by the release workflow as `debeski/dlux-ocr:v<version>` plus `:beta` or `:latest`. Composer's install and in-app image update pull every service's image, so `ocr` follows any image update. Third-party credits: `docker/ocr/NOTICE`.
- Service API (`POST /v1/ocr?mode=&threads=&max_pages=`, `GET /health`) and limits: see `docker/ocr/server.py`.

## Measured (Archive scans, 2026-10-23)

Five real scanned Arabic PDFs (22 pages, no text layer), Apple-silicon Docker: 0.25–0.65 s per page; a 15-page scan in 12.9 s at 2 threads, about 1.7 GB peak at 4 threads. Clean printed body text reads well; errors cluster in kashida-stretched headings, stamps, signatures, handwritten numbers and words split across lines. Treat the text as a search aid, not a transcription.
