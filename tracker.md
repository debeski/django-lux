# DjangoLux PDF workstream tracker
## Current snapshot
- 2026-10-11: Optional, model-agnostic PDF toolkit implemented; no feature migrations.
- Main-line feature branch: codex/shared-pdf-editor (unpublished 1.11.0b7 candidate).
- Maintenance backport: codex/pdf-stable-1103 (unpublished 1.10.3b1 candidate based on published 1.10.2).
- 2026-10-12 review: beta first required; dependency extra requires image rebuild, no schema migration.
- Archive 1.2.0 requires a published stable provider; user authorized beta publication and reference-stack acceptance on 2026-10-12.
## Standards
- Preserve existing data and files; scope/permissions/storage/history belong to project adapters.
- Optional tools use the app-owned dlux.pdf Options namespace; local assets avoid CDN dependence.
- Follow the framework's main AGENTS.md and ecosystem rules; no deletions or feature work on main.
## Active tasks
- [x] Final packaged Archive validation: 49 tests, real browser journeys, schema/static checks PASS; no source overlays.
- [ ] Publish authorized 1.10.3b1; accept published beta on testbed before preparing stable 1.10.3.
- [ ] Archive then rebuilds against published stable; no production deployment authorized.
- [ ] Decrees adoption remains later work.
## Completed recently
- [x] Viewer/editor/history UI, bounded assembly, native file widget, administrator controls, and modal save extensions.
- [x] 2026-10-12 maintenance full suite: 2710 tests OK (2 skips); final release/PDF focused 69 OK; JS 66 OK.
- [x] Added adapter authentication/permission/revision/rollback tests and editor disposal/loading/late-save regression tests.
- [x] Release classification + migration gate, no schema drift, import graph and final wheel/sdist checks PASS.
- [x] 1.10.3 wheel/assets verified; final namespaced PDF translations pass 181 focused tests.
## Validation and docs
- Final logs/artifacts: .xclude/validation/pdf-release-2026-10-12/; prior Archive acceptance: project-archive/main/.xclude/validation/1.2.0/.
- Docs: docs/pdf-toolkit.md, docs/FEATURES.md, docs/reference.md; candidate changelog/version metadata updated.
## Handoff
- Primary code remains unchanged; main tracker records review. Main-line candidate needs these final fixes ported before integration.
- Both projects own DocumentFileVersion; shared UI adoption preserves rows/paths/bytes, with no normalization/backfill.
- Do not promote the beta line to satisfy Archive's stable dependency requirement.
