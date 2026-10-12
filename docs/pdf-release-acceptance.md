# PDF maintenance release acceptance

## Published beta: 1.10.3b1 (2026-10-12)

- Based on stable `v1.10.2`, integrated into `release/1.10.x`; no unrelated 1.11 beta work.
- [Release workflow](https://github.com/debeski/django-lux/actions/runs/38223152551) passed all jobs, including the framework suite with the PDF extra on Python 3.11, 3.12, and 3.13.
- [GitHub prerelease](https://github.com/debeski/django-lux/releases/tag/v1.10.3b1): seven assets. PyPI wheel payload verified byte-for-byte against the tag, with its recorded SHA256 `f41410d4da65fbffd5c9be365b6db59b06e16d7a1d51ab133b1403467a24a7fd`.
- Local final implementation: 2,710 framework tests OK (two skips), 69 final PDF/release tests OK, all 66 JavaScript tests OK, no migration drift or module-scope import cycles, build/twine/installed-wheel smoke checks passed.
- The optional extra changes dependency metadata. Both beta and prepared stable require an image rebuild; migration effect is `none`.

## Reference stack

The existing `testbed-dlux` remains on 1.11.0b6. A separate copy at `testbed-dlux/.xclude/pdf-maintenance-1103b1` runs the published beta on port 8090, with a restored database and copied media. Email is disabled in the copy.

- All nine document-table counts and row-content fingerprints match the original, including 20,100 decrees. All 339 original media files match their original SHA256 values.
- Generated-stack startup, all service health checks, Django checks, and migration-drift checks passed. Composer's deep in-container doctor passed with zero errors; debug/mail warnings reflect the local test configuration.
- Nineteen Decrees PDF/upload/config tests passed. Source-only configuration assertions needed Dockerfile, release workflow, and compose fixtures copied into the test container; application Python and framework code were not overlaid.
- `dlux_backup` completed: 40,304 rows, no error. Options displayed 1.10.3b1 and the collected PDF editor asset was served; desktop/mobile browser checks passed without page errors.
- The highest beta-channel update remains 1.11.0b6. This acceptance deliberately uses the exact maintenance beta wheel, rather than an unpinned update.

## Archive consumer

An isolated copy of the existing Archive validation database/media runs an application image with the published beta wheel on port 8124. This is beta compatibility acceptance, not an Archive release artifact.

- All 49 document tests passed, including permission/scope, revision conflicts, malformed/encrypted/oversized files, and file/database failure recovery.
- Installing/migrating/collecting static preserved all original document rows, four history rows, and all 16 existing current/history files. No schema drift or new migration; no normalization or backfill.
- Browser journeys passed: existing preview/history, real entry/upload/save, filter retention, PDF page removal/save, byte-identical preservation of the new document's prior PDF, and unchanged original downloads. Desktop/mobile screenshots were inspected after modal transitions settled; no horizontal overflow or page errors.
- Fixture limitation: three pre-existing history rows reference files already absent in the source validation container. Their 404 behavior is unchanged; the available historical PDF remains byte-identical. No claim is made about inaccessible production media.
- Original row-content fingerprints and all original file hashes remained unchanged after browser edits to a newly created test record.

## Stable preparation and remaining work

Stable 1.10.3 carries the beta implementation unchanged. Its wheel implementation/assets/dependency metadata match the published beta byte-for-byte; only version and release URL differ. Stable classification, manifest/migration gates, wheel/sdist checks, and 69 final PDF/release tests pass. Publication requires authorization. After publication, Archive must rebuild against the stable PyPI artifact and verify equivalence before its 1.2.0 release. Production deployment remains outside this acceptance. Physical scanner testing and production backup/restored-copy rehearsal remain operator work. Decrees shared-toolkit adoption is a separate adapter task and retains its current history/storage contract.

Machine-local logs, downloaded artifacts, hashes, browser scripts, and screenshots: `pkg-django-lux/pdf-stable-1103/.xclude/validation/pdf-release-2026-10-12/`; reference-stack logs/snapshots: `testbed-dlux/.xclude/pdf-maintenance-1103b1/`.
