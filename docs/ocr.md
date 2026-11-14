# OCR text for document files

`dlux.ocr` reads the text of registered document files with
[Indra OCR](https://github.com/datalab-to/indra), a CPU-only ONNX engine with
Arabic, Latin and 80+ other scripts. Every field registered with
`register_document_file()` takes part unless it passes `ocr=False`; nothing else
is needed in a project.

The engine runs in the stack's optional `ocr` service, using the project image
and `python -m dlux.ocr.serve`, like the SMTP relay. Install the optional
`django-lux[ocr]` extra and bake its models into that image. The service:

- is reachable only on the internal Compose network, with no published ports and
  no internet access (its models are baked into the image);
- loads its models on the first request, so it idles small while OCR is off.

Saves never fail because of OCR: when the service is stopped, missing or busy,
rows stay queued and retry.

## For administrators

**System Settings > Extra Features > OCR text extraction**
(`SystemSettings.extra_config['ocr']`, exported and imported with the rest of
`extra_config`):

| Option | Default | Environment fallback | Meaning |
|---|---|---|---|
| Enable OCR | off | `OCR_ENABLED` | Master switch. Off: no new reads are queued, existing queued jobs wait, Run OCR is refused; text read earlier stays visible and searchable. |
| Read new and replaced files automatically | on | `OCR_AUTO_ON_SAVE` | Read after each save that changes the file. Off: only Run OCR and the backfill read files. |
| Include extracted text in search | on | `OCR_SEARCH` | Global search and `arabic_search_q(..., model=...)` match OCR text. |
| Reading mode | Use the text layer, OCR the rest | `OCR_MODE` (`auto`/`ocr`) | `auto` keeps a sound PDF text layer and OCRs the rest; `ocr` always OCRs. |
| OCR service address | `http://ocr:8080` | `OCR_URL` | Internal service name or private LAN address only; http/https, no redirects. |
| Time limit per file | 900 s | `OCR_TIMEOUT` | 30–7200; also when a `running` row counts as abandoned. |
| Largest file | 64 MB | `OCR_MAX_FILE_MB` | 1–512; larger files are not sent. |
| CPU threads per file | 2 | `OCR_THREADS` | 1–16, capped by the container's `OCR_MAX_THREADS`. |

Saved values win; an environment string fills an option never saved (or saved
invalid); built-in defaults fill the rest. The section shows whether the service
answers.

Replacing or clearing a file invalidates its previous current text even when
automatic reads are off or the replacement exceeds the size limit; historical
text remains stored.

The section also holds background catch-up and the models included in automatic
OCR; see [Background catch-up and model selection](#background-catch-up-and-model-selection).

**Starting and stopping the service.** Saving a *change* of Enable OCR opens the
shared DjangoLux password-confirmation dialog: the same check as the Operations
panel, superusers only, POST through the settings save. It then queues
`service-start` (on) or `service-stop` (off) for the `ocr` service through
Composer, audited as `DLUX_OPS_RUN` exactly like a panel action.

- Enabling first checks fresh service health: an already healthy service needs
  no redundant Start operation.
- The section shows the request's progress and result.
- When Composer is too old, unreachable or busy with another operation, the
  setting is still saved, and the section and a notification say why. They point
  to the **Operations panel** (Options > admin rail), which also lists `ocr` with
  Start, Stop, Restart and Recreate.
- Saves that do not change the switch never touch the service.

Starting, stopping and restarting `ocr` through Composer requires Composer 1.9.0
or later, which allow-lists the service.

**Reading the text.** The document viewer's toolbar has an **Extracted text
(OCR)** button next to History. It opens the text and markdown (escaped,
`dir="auto"`), the engine, page count, duration and confidence. For users who
may edit the document it adds **Run OCR** / **Run OCR again**, queued ahead of
automatic and backfill work. The panel refreshes itself while the file is queued
or running.

## For developers

```python
from dlux.files.registry import register_document_file

register_document_file(Decree, 'pdf_file')             # OCR on (default)
register_document_file(Decree, 'attachment', ocr=False)  # this field never read
```

- **Storage**: `dlux.FileText` (migration `0029_file_text`, additive). One row per
  document, field and file SHA-256 (`dlux_file_text_unique`), so an unchanged
  file is never read twice. `is_current` marks the row for the file the document
  holds now; older rows remain. Scope follows the document.
- **Fields**: status (`pending`, `running`, `done`, `failed`, `skipped`), source
  (`auto`, `manual`, `backfill`), requester, engine/engine version/model version,
  markdown, text, per-page JSON (lines with boxes and confidence, layout blocks,
  rotation, timings), page count, mean confidence, timings, duration, attempts,
  error, and `file_version` (the `FileVersion` whose save produced this file).
- **Flow**: `post_save` on a registered model schedules after commit
  (`dlux.ocr.service.schedule`). The task `dlux.tasks.ocr_file` (defined in
  `dlux.jobs`) runs on the [Task Runner](task-runner.md) at priority 0 (Run OCR),
  -6 (automatic) or -9 (backfill) in `django.tasks` terms, higher first. It is
  `requeue_lost`, so a run lost with a dead worker goes back to the queue. A busy
  engine (`503` with `Retry-After`, or `429`) is reading another file: the run
  waits one to two `Retry-After` intervals and asks again, without using any of
  its retries, so a backlog larger than the engine never fails files. An
  unreachable or failing service is retried after 30 s, 1, 2, 5, 10, 15, 30 and 60
  minutes before the row is marked `failed`; a `422`-type refusal fails at once; a
  file changed before the worker ran is `skipped`.
- **Provider seam**: `dlux.ocr.client.call_service(content, mode=None)` is the
  only call to the engine. Replacing Indra means an adapter in
  `dlux/ocr/engine.py` that returns the same JSON, selected with `OCR_ENGINE`.
- **Search**: `arabic_search_q(term, fields, model=queryset.model)` adds rows
  whose current OCR text matches (Arabic variants included); without `model` it
  is unchanged. Global search's data provider adds OCR matches for registered
  models automatically. `dlux.ocr.service.search_q(model, term)` is the
  underlying `Q`.
- **Routes**: `GET/POST sys/files/<app>/<model>/<pk>/<field>/text/`
  (`dlux_document_file_text`). GET needs view access, POST (Run OCR) edit
  access; both go through `resolve_document`, so the field's
  `can_access`/`queryset` hooks and scope apply.

### Background catch-up and model selection

Importing the core/PDF package and reading saved text need no task worker.
Viewer-triggered, automatic and background OCR need
`python manage.py dlux_worker` (the `worker` service in a generated stack; see
[Task Runner](task-runner.md)). Synchronous CLI backfill runs without it.

**Read older files in the background** (off by default) finds registered files
with no finished result while OCR is enabled, including entries created before
OCR was installed:

- Defaults: up to **5 files every 300 seconds**, pausing catch-up when **10
  pending/running files** already exist. These three controls set background
  intensity; CPU/RAM thresholds are not used.
- Manual requests keep priority over automatic and background work.
- The settings section shows the last scan's checked/queued counts and pause
  reason.

**Models included in automatic OCR** governs save-triggered reads and
background/CLI backfill. An empty selection disables all automatic reads.

- Manual **Run OCR** from the entry viewer stays available for excluded models,
  subject to normal edit permission. Developer `ocr=False` still disables OCR for
  that field entirely.
- Excluding a model also stops its already-queued automatic jobs from starting;
  a job already extracting may finish.
- Existing text stays readable and searchable, and replacing an excluded file
  still invalidates stale current text.

The scanner is `dlux.tasks.ocr_background`, which runs once per minute (the
`dlux-ocr-background` entry of `DLUX_TASK_SCHEDULE`), gated by the configured
interval. It:

- rotates across registered fields, using a shared-cache lock and checkpoints,
  limits scan work, and sends `backfill` tasks at the lowest priority (-9);
- does not re-read completed, failed or skipped results; failed files can be
  retried manually or with `dlux_ocr_backfill --retry-failed` for included
  models;
- recovers stale lost queue messages without overriding normal retry delays;
- restarts its metadata scan safely when the cache is cleared; persisted
  `FileText` results prevent re-extraction.

Pausing background catch-up stops new scans; already-queued jobs may finish. OCR
off pauses extraction and retries; a missing service and queue pressure pause
catch-up.

Settings in `extra_config['ocr']`:

| Key | Range | Default |
|---|---|---|
| `background_enabled` | boolean | `false` |
| `background_interval` | 60–86400 seconds | `300` |
| `background_batch_size` | 1–100 | `5` |
| `background_queue_limit` | 1–1000 | `10` |
| `automatic_models` | registered model labels, e.g. `documents.decree` | unset: all registered models |

Saving an explicit `automatic_models` selection fixes that set, so newly
registered models need selecting too.

### Commands

```bash
python manage.py dlux_ocr_backfill --dry-run
python manage.py dlux_ocr_backfill --batch-size 50 --limit 500
python manage.py dlux_ocr_backfill --files documents.decree.pdf_file --enqueue
python manage.py dlux_ocr_backfill --retry-failed --restart
python manage.py dlux_adopt_ocr_text documents.DocumentOCR            # dry run
python manage.py dlux_adopt_ocr_text documents.DocumentOCR --apply
```

`dlux_ocr_backfill` reads existing files in the command's own process (the task
worker stays free). It saves its position per file key after every document in
`logs/dlux-ocr-backfill.json` (`--state-file` to change it); rerun to continue,
`--restart` to start over. When the service stays unavailable (`--wait`, default
60 seconds, up to `--max-waits`, default 10, per file), it stops with "rerun to
resume". `--enqueue` queues on the task worker at backfill priority instead.

`dlux_adopt_ocr_text` copies a project's own OCR rows (shaped like Archive's
`documents.DocumentOCR`) into `FileText`. It is a dry run by default, idempotent
by document/field/SHA-256; conflicts stop the run before anything is written,
and the source table is untouched. Run it after `dlux_adopt_file_history` so
copies re-link to adopted file versions.

## Stack

- **Contract** (`dlux/contracts/stack.json`): `ocr` is an **optional** service on
  `internal` only, `restart: safe`, in `invariants.restart.lifecycle`
  (startable/stoppable) and `invariants.optional_services`. Drift checks skip it
  when a deployment does not have it.
- **Scaffold `compose.yml`**: `ocr` uses the same `WEB_IMAGE` as `web` and
  `worker`, with `entrypoint: []` and
  `command: ["python", "-m", "dlux.ocr.serve"]`. Its
  read-only root, temporary `/tmp`, dropped capabilities, internal-only network
  and memory/CPU limits isolate engine execution. `ocr` is included in
  `COMPOSER_AGENT_RESTART_SERVICES`. Existing projects add the same service and
  allow-list entry; `check --fix` does not add it automatically.
- **Image dependencies**: install `django-lux[ocr]` (or
  `django-lux[updater,ocr]`). The scaffold includes the extra by default;
  projects without OCR can omit it. Set `INDRA_OCR_MODEL_DIR=/opt/indra/models`
  and run `python -m dlux.ocr.fetch_models --if-installed` during the image
  build. Runtime sets `HF_HUB_OFFLINE=1`; models are never downloaded by `web` or
  `worker`. Only the OCR process loads the engine. Credits and model-license
  location: `dlux/ocr/NOTICE`.
- **Upgrades**: adding or changing the OCR extra requires a project image
  rebuild; inline package installation cannot supply engine dependencies or
  model files. After that rebuild, compatible DjangoLux changes can be installed
  inline for `web`/`worker`. The OCR service keeps running its baked version until
  the project image is updated or the container is recreated, so keep its HTTP
  contract compatible.
- **Releases**: no separate OCR image, Docker Hub secrets or OCR release
  workflow is required. Composer updates the project image for the service along
  with the other application containers.
- **Service API**: `POST /v1/ocr?mode=&threads=&max_pages=` and `GET /health`;
  see `dlux/ocr/serve.py`. Public service URLs, embedded credentials, URL paths,
  loopback/link-local addresses and redirects are rejected.

## Resource planning

| Variable | Default | Bounds |
|---|---|---|
| `OCR_WORKERS` | `1` | Concurrent extraction and upload buffering. |
| `OCR_QUEUE_SIZE` | `2` (minimum `1`) | Waiting HTTP-handler slots beyond the workers. |
| `OCR_QUEUE_WAIT` | `20` seconds | The wait for an engine slot. |
| `OCR_READ_TIMEOUT` | `30` seconds | Socket inactivity for headers and uploads. |
| `OCR_MAX_BYTES` | 64 MiB (512 MiB in the generated Compose service) | One request's upload. |
| `OCR_MAX_PAGES` | `500` | Pages per request. |
| `OCR_MAX_THREADS` | CPU count (`4` in the generated Compose service) | Threads per request; caps the *CPU threads per file* option. |

Connections beyond the queue, and requests that wait longer than `OCR_QUEUE_WAIT`
for a slot, receive `503` with `Retry-After: 30` ("The OCR engine is busy."),
which DjangoLux waits out without counting it against the file. They may be
closed before upload: a client still uploading can observe a broken pipe or reset
instead of reading that response, which DjangoLux retries as an unavailable
service. Waiting requests do not buffer their files.

Uploads need a single `Content-Length` header, without `Transfer-Encoding`;
truncated, stalled and oversized uploads are refused.

The generated Compose service exposes the queue and inactivity settings above.
The application's default per-file limit (*Largest file*) stays 64 MB; both
limits apply. Change container environment limits through the deployment
configuration and recreate the OCR service.

If a file is replaced while its OCR request is running, the completed text
remains historical and cannot become current again: finishing a historical job
never changes the current-file selection.

The OCR extra adds ONNX Runtime, image-processing dependencies and model files to
the project image. Model loading is lazy and confined to the OCR process. Choose
`OCR_MEMORY_LIMIT` (generated default `3g`) and `OCR_MAX_THREADS` for the
deployment. Extraction quality varies for handwriting, stamps and damaged scans;
treat extracted text as a search aid and retain the original document.
