# DjangoLux 1.12 stable promotion

Stable 1.12.0 promotes the accepted [1.12.0b3 prerelease](https://github.com/debeski/django-lux/releases/tag/v1.12.0b3). Runtime Python, templates, static assets, dependency metadata and migrations are unchanged; the packaged manifest changes only the version and release URL.

## Beta evidence

- [Release workflow 39050175125](https://github.com/debeski/django-lux/actions/runs/39050175125) passed all eight jobs, including Python 3.11–3.13. The downloaded wheel's 658 package files matched its tag; GitHub published all seven prerelease assets.
- The official testbed updated from b2 to b3 through the normal pinned Composer command, including backup `DVVSiFkz` (40,388 rows). Web and Celery matched all 658 published package files.
- Desktop/mobile history checks verified the translated Changed by column, actor names and unknown-actor fallback with zero browser page errors. Ten domain-table fingerprints and all 396 existing media files remained unchanged.
- Deep checks passed with zero errors, the expected local DEBUG warning and three development/HTTP skips.
- Earlier published-wheel acceptance exercised image upload, rotation, Fit to A4, save and exact history, plus the real ScanLink client against simulated workstation endpoints. Physical scanner hardware was not tested.

Local evidence: `.xclude/validation/1.12.0b3-2026-10-17/` and `.xclude/validation/1.12.0-stable-2026-10-17/`.

## Stable checks

Before tagging, validate stable classification/beta-first policy, the manifest/migration gates, wheel/sdist metadata and package equivalence to published b3. Stable release CI must pass before PyPI/GitHub publication. Verify downloaded stable artifacts after publication.

The additive `0026_file_versions` migration and image floor `>=1.11.0b7` are unchanged. Project file registration and legacy history adoption are explicit integration work, never automatic installation-time conversion. Production deployment and consumer releases are outside this promotion.

Stable evidence is retained in `.xclude/validation/1.12.0-stable-2026-10-18/`.

Local stable checks on 2026-10-18 passed: 110 focused release/channel/document/PDF tests, stable classification with published-beta verification, manifest/migration gates, wheel/sdist and twine. Comparing with the verified published b3 wheel found 657 unchanged package files and only the manifest's version/release URL differing; dependency metadata is identical. A stale local build containing a retired scaffold module was preserved under `stale-build/` before a clean, equivalent rebuild. The full 2,856-test beta suite and 70 JavaScript tests are reused because their runtime inputs are unchanged; the promotion PR runs the full Python-version matrix again.
