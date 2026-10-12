# DjangoLux PDF workstream tracker
## Current snapshot
- 2026-10-11: Optional, model-agnostic PDF toolkit implemented; no feature migrations.
- Main-line feature branch: codex/shared-pdf-editor (unpublished 1.11.0b7 candidate).
- Maintenance: published/accepted 1.10.3b1 on release/1.10.x; stable 1.10.3 prepared on codex/pdf-stable-1103, unpublished.
- 2026-10-12 review: beta first required; dependency extra requires image rebuild, no schema migration.
- User authorized stable provider first, then pinned Archive/Decrees releases after official shared-editor end-to-end acceptance (2026-10-12); production deployment excluded.
## Standards
- Preserve existing data and files; scope/permissions/storage/history belong to project adapters.
- Optional tools use the app-owned dlux.pdf Options namespace; local assets avoid CDN dependence.
- Follow the framework's main AGENTS.md and ecosystem rules; no deletions or feature work on main.
## Active tasks
- [x] Final packaged Archive validation: 49 tests, real browser journeys, schema/static checks PASS; no source overlays.
- [x] Publish authorized 1.10.3b1 and accept published beta on copied reference stack + isolated Archive consumer.
- [x] Official testbed follow-up: actual published beta web/Celery, 19 PDF tests, deep/browser/backup checks PASS; original rows and 341 files unchanged.
- [x] Official testbed restored healthy to 1.11.0b6 in web/Celery; final original-row/file fingerprints unchanged.
- [ ] Publish authorized stable 1.10.3 after official shared-editor journeys (all three models PASS).
- [ ] Archive then rebuilds against published stable; no production deployment authorized.
- [x] Decrees adapter adoption implemented and committed; Archive integration ready, both require final stable artifact acceptance.
## Completed recently
- [x] Viewer/editor/history UI, bounded assembly, native file widget, administrator controls, and modal save extensions.
- [x] 2026-10-12 maintenance full suite: 2710 tests OK (2 skips); final release/PDF focused 69 OK; JS 66 OK.
- [x] Added adapter authentication/permission/revision/rollback tests and editor disposal/loading/late-save regression tests.
- [x] Release classification + migration gate, no schema drift, import graph and final wheel/sdist checks PASS.
- [x] Published beta: reference stack healthy; 19 Decrees/49 Archive tests; backup + desktop/mobile browsers PASS; original rows/files unchanged.
- [x] Stable wheel implementation/dependencies identical to published beta; stable release gates, build/twine, and final 69 PDF/release tests PASS.
- [x] 1.10.3 wheel/assets verified; final namespaced PDF translations pass 181 focused tests.
## Validation and docs
- Final logs/artifacts: .xclude/validation/pdf-release-2026-10-12/; prior Archive acceptance: project-archive/main/.xclude/validation/1.2.0/.
- Docs: docs/pdf-release-acceptance.md records published artifacts, restored-copy acceptance, and three missing historical fixture files; topic/reference/features current.
## Handoff
- Primary code remains unchanged; main tracker records review. Main-line candidate needs these final fixes ported before integration.
- Both projects own DocumentFileVersion; shared UI adoption preserves rows/paths/bytes, with no normalization/backfill.
- Do not promote the beta line to satisfy Archive's stable dependency requirement.
