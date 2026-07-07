# Project Tracker (django-lux)

## Part 1: Project Related
### Current Verified Snapshot:
- v1.3.0–v1.3.5 ALL TAGGED + RELEASED (v1.3.0 groups/presets+folded 1.2.15; v1.3.1–1.3.5 = user-built image-level update orchestration: `DluxImageUpdate`+migration `0008`, composer-updater hand-off, registry-driven availability, proxy-served deploy progress, manifest `highlights`, reworked Updates card). Working tree = UNRELEASED v1.3.6 (auth-security config, see Completed). Manifest = v1.3.6, INLINE_SAFE (no new migration).
- `dlux/release-manifest.json` is the version source (v1.3.6, inline_safe:TRUE; optional `highlights` array since 1.3.1). Migration baseline `0008` (v1.3.1 `DluxImageUpdate`; prior `0007` v1.3.0 GroupProfile/GroupMembership — `manage_groups` perm rides in GroupProfile CreateModel.options to stay inline-safe). Groups built on native `auth.Group` (has_perm unions group perms → non-breaking).
- v1.2.7 remains the mandatory rebuilt baseline before later manifest-approved inline releases.
- DjangoLux supplies settings/setup, scoped models, auth/security, navigation, reports, backup, scaffolding, SSO hooks, and the Compose updater.
- Updater state uses `DluxUpdateState`/`DluxUpdateRun` plus `dlux_runtime` releases, atomic pointer, generation, maintenance, heartbeat, and degraded markers.
- `switch_pos` is rolled back to active/baked v1.2.4 but degraded with maintenance retained after candidate and rollback Celery probes raced normal startup. v1.2.13 reconcile now SELF-HEALS this class: once back on baked it clears the stuck degraded flag (needs one reconcile post-upgrade, or a one-time flag clear / `down -v` since the current row predates the fix).

### Current Project Adopted Standards:
- Integrate settings with `from dlux.utils import dlux_settings`; call `dlux_settings(globals())`; mount `dlux.urls` at root.
- `dlux.system` owns settings defaults/schema/normalizers/registry; migration-history wrappers remain in `dlux.models`.
- DSRP-1 requires backend authorization to match UI visibility and security mutations to be POST-only.
- Authored runtime CSS/data/events/JS use the `dlux` prefix and external assets; user copy uses `DLUX_STRINGS`.
- Releases are tag-driven; package/version/release validation all read `dlux/release-manifest.json`.

### Adopted Standards' rules and policies:
- Maintain this tracker as verified project state, <=100 lines total; Part 1 <=55 lines.
- Root changelog sections are newest-first `## vX.Y.Z` with flat bold-title bullets; tagged sections are immutable.
- Never delete repository files; relocate obsolete/replaced material under `.xpose/` with relative-path preservation.
- Preserve unrelated user changes and use `apply_patch` for source/doc edits.
- NEVER put raw HTML tags in i18n strings or form label/help_text (en+ar+fallbacks): crispy renders help_text UNescaped, and an injected tag (e.g. `<title>`) silently truncates innerHTML-loaded dynamic-modal forms — swallowing every node after it with NO Python/JS error. Use plain words or HTML entities.
- ALWAYS reuse dlux-provided components, never roll your own: settings-form choice fields MUST bind `DluxChoiceSelectorWidget` via `_bind_choice_selector_widget` (variant `toggle` for few options, `card`+searchable for many) — never plain `forms.Select`; toggles use `build_settings_toggle_field`; modals use the dynamic modal; spinners use `DluxLoadingButton`; strings via `DLUX_STRINGS`/`s.get`. New settings keys follow the existing field's full pattern (decl→schema→normalizer→default→form widget→initial→clean preservation→payload→APP_CONFIG→export/import→en+ar). All of this is DSRP-1 (CSP-safe data-*/external-asset controls) + form-consistency; match an existing field end-to-end before adding one.
- Feature/config/schema/API/security/deployment changes require same-turn technical documentation.

### Cross-Cutting Audits if any:
- 2026-06-23: Updater audit covered artifacts, attestation, dependency/migration gates, supervisor/runtime state, recovery, UI/API, scaffold, nginx, and Compose.
- 2026-06-24: ScanLink no PDF byte/page cap; gen-project nginx effective `5M` upload ceiling. Reports audit covered activity-window/Celery-backup/download-handoff/media/nginx.
- 2026-07-04: Scaffold-vs-`../project-decrees` audit — core dlux files IDENTICAL (entrypoint/gunicorn/nginx/smtp_relay/start.sh/gitattributes); scaffold is AHEAD (Dockerfile apt deps, supervisor `baked_version()`); decrees was gen'd on dlux 1.0.4/pinned 1.2.10 so most diffs = project-specific or project-lagging. Fixed: stray committed `.pyc` in scaffold_templates→`.xpose`. OPEN (need user call): back-port compose `post_start migrator` + smtp-relay `depends_on db/redis` from decrees? (healthcheck→`manage.py check` and web `build:.` look project-specific, NOT recommended).

### Current Project's Unsolved Known Bugs:
- Fallback file/download redirects remain a high-risk-deployment review point; `_safe_referer()` currently enforces allowed hosts.
- Mounted test Compose uses Redis sessions; never use live `cache.clear()` probes because they delete browser sessions.

### Incomplete Tasks:
- **Priority 1:**
  - [ ] Browser-validate setup Step 10 logging grid hydrate/serialize, audit tab, and prune after collectstatic.
  - [ ] Browser-validate v1.2.13: anon public root with show_sidebar_on_public on — confirm `sidebar_items.html` degrades gracefully (public/empty entries) for AnonymousUser.
- **Priority 2:**
  - [ ] Optional request-scoped `transaction.on_commit` activity aggregator; deferred due TestCase/order fragility.
- **Completed Recently:**
  - [x] v1.3.6 PRIVACY NOTICE + REGISTRATION CONSENT (CHANGELOG; 683 tests green incl. `test_registration.RegistrationConsentAndPrivacyTests` ×5; no migration, inline-safe). 4 `registration_config` keys — `privacy_policy_url`/`terms_url`/`privacy_notice_text` (str) + `registration_require_consent` (bool) — full settings pattern (schema/defaults/normalizer/registry/EXPORT_FIELDS/models.configure/utils.config db-blocks+APP_CONFIG.security/import_export + form fields `_clean_preserved_text`/`_clean_preserved_toggle`+initial+`_schema_group_from_cleaned` compose + en+ar). Shared partial `dlux/includes/auth_privacy_notice.html` (reads APP_CONFIG.security; NOTE Django templates forbid `_`-prefixed vars → use `sec` not `_sec`) included on login.html + register.html. Consent = required checkbox on `PublicRegistrationForm(require_consent=…)`→`clean_consent`; register_view passes it. login.css `.dlux-auth-privacy`/`.dlux-auth-consent` (checkbox reset + self-supplied checkmark, same generic-`input`-bleed class as trust switch). NEW docs `docs/data-privacy.md` (personal-data inventory, retention, transparency-vs-consent = security→legitimate-interest-not-consent, operator controls) linked from docs index. Framework ships NO legal text. Not browser-verified.
  - [x] v1.3.6 2FA VERIFY PAGE RESTYLE (CHANGELOG; template+view+CSS only, inline-safe): `2fa/verify.html` now wraps in the login-style system (`dlux-login--{style}` via `login_config`/`login_hero_message` from new `_login_style_context`; APP_CONFIG.login fallback) so it follows split/centered/minimal/fullpage. `.dlux-twofa-verify`(+`--methods`) modifier bumps the fixed split-card height (was sized for the short login form → Verify btn + back link overflowed the card), mirroring the register `--register` pattern. Trust-device = SELF-CONTAINED switch (::before knob, logical inset-inline-start for RTL, !important over generic input background/focus). form-switch caused doubled/misplaced knob b/c login `input`/`input:focus` `background` shorthands wipe the switch bg-image; dropped form-switch class. Back/cancel/resend = in-card `.login-2fa-back` pill buttons. Method buttons = icon-only circular `.login-2fa-method-btn` + `data-dlux-tooltip` (labels kept `visually-hidden` so twofa_verify.js unchanged; resend countdown still shows via status line). login.css buster→20260706b. Verified both intents render (enable 200, login shows 4 icon btns+4 tooltips+switch+--methods). NOT browser-verified visually.
  - [x] v1.3.6 AUTH-SECURITY CONFIG (CHANGELOG; 678 tests green incl. new `test_auth_security.py` ×11 registered in test_all.py; no migration, inline-safe): 4 new `auth_config` keys — `login_lockout_threshold` (1–50 def 5) / `login_lockout_window_minutes` / `login_lockout_duration_minutes` (1–1440 def 15) / `strong_password_min_length` (8–64 def 12) — full settings pattern (schema int `legacy_flat` → defaults → normalizers → registry → EXPORT_FIELDS → load() seed → import/export → form `_auth_int_clean` preservation → en+ar). `login_throttle.py` now config-driven and splits window (counter TTL) vs duration (lock TTL, `max(window,duration)` when locked); legacy `DLUX_LOGIN_LOCKOUT_*` settings = fallback only. `password_validation.py` reads min length; `{count}`-templated `password_rules_help`/`password_rule_min_length`. Settings UI: number fields REVEALED under their parent toggles (`data-auth-lockout-fields`/`data-auth-strong-fields` + `initAuthSecurityOptions` in system_setup.js, mirrors client-ip hops idiom). PASSWORD CARD: `password_rules/js` now binds ALWAYS (was strong-only) — strong mode = configured min len (from flat `DLUX_CONFIG.strong_password_min_length`) + 4 char classes; normal mode = 8+ chars + not-entirely-numeric (`password_rule_not_numeric`); replaced the raw-HTML `help_password_common` bullets (3 form sites help_text='', i18n value rewritten plain-text, `mark_safe` dropped). KEY INSIGHT: `_schema_group_from_cleaned`/`_apply_schema_group_initials` are schema-driven → adding schema fields auto-wires compose+initials. `utils/config.normalize_auth_config` now DELEGATES to the system normalizer (was a drift-prone duplicate). Busters: system_setup.js+password_rules/js→20260706a (1 test assert updated). NOT browser-verified.
  - [x] v1.3.0 RELEASED — Permission Groups/Presets on native `auth.Group` + `GroupProfile`/`GroupMembership` (migration 0007), `manage_groups` perm, Manage Groups modal, preset selector + inherited-perm badge UX, column-first permission cards, dark-theme contrast root-fix (shared theme tokens in permissions.css), activity-log badge fix. Full detail in CHANGELOG.
  - [x] v1.2.13–v1.2.15 RELEASED (folded into v1.3.0 for 1.2.15) — appearance/config toggles, Options restructure/polish, System Info Redis/Celery/Composer diagnostics, sticky headers, updater recovery hardening. All in CHANGELOG.

### One-line info about last verified Tests:
- 2026-07-07: v1.3.6 full suite GREEN in throwaway venv: 683 tests (=678 auth-security batch + 5 `test_registration.RegistrationConsentAndPrivacyTests`; auth batch = +11 `test_auth_security.py` normalizer/clamps/throttle/min-length/seed/roundtrip). `makemigrations --check` clean (all keys JSONField-resident). REMINDER: new test modules MUST be added to `test_all.py` TEST_LABELS (CI uses the explicit list, not autodiscovery). NOT browser-run.
- 2026-07-04: v1.3.0 baseline 667 green; inline-safe guard `ManifestTests.test_local_migrations_honor_manifest_inline_safe_claim` runs real migrations through the validator whenever manifest.inline_safe=true.
- 2026-06-24→27: earlier baselines — v1.2.13 652 green (browser-verified Options; fixed test_supervisor baked-version pin + test_user_profile_stats model-name collision); v1.2.11 631 OK; CI fixes (footer_enabled override clobber, .env line count, test_updater setRootStatus).

### One-line info about last time edited Docs:
- 2026-07-07: v1.3.6 docs — NEW `docs/data-privacy.md` (personal-data inventory + transparency-vs-consent + operator controls), linked from docs index; reference.md +4 privacy flat-keys; admin-guide.md Privacy & Consent bullet. (Prior 2026-07-06: reference +6 auth keys; admin-guide lockout/password bullets; FEATURES "Sign-in Protection & Password Policy" + 2FA restyle.)

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Prefer `rg`/`rg --files` for discovery; inspect durable updater runs through the database, not web access logs alone.

### Global Rulesets:
- Keep tracker/changelog/docs synchronized with verified code and executed checks.
- Static cache-busting: v1.3.6 replaced ALL manual `?v=DATE` busters with `{% dlux_static 'path' %}` (dlux_tags) → appends `?v=dlux.__version__` (read from PACKAGE, not context, so it works in widget/`render_to_string`-without-request templates like grouped_permissions/profile_image — `{{ DLUX_VERSION }}` context var would be EMPTY there and reintroduce staleness). So every release auto-busts everything; use `{% dlux_static %}` (not `{% static %}`) for any versioned dlux asset + `{% load dlux_tags %}` before first use. PLAN v1.3.7: adopt ManifestStaticFilesStorage in scaffold settings (content-hashed) and drop dlux_static/`?v=` — audit confirmed static tree is Manifest-ready (no dangling url()/sourceMappingURL; only note: login.css `url(/static/img/login_logo.svg)` is absolute→unhashed, project-supplied). Root cause of the v1.3.5 admin-panel-unstyled report: options.css/updater.js reworked without bumping their `?v=`.

### Agent Handoff Rules:
- Read `tracker.md` every turn; preserve user work; use tag state plus release manifest before changelog/version edits.

### References and Links:
- Security: `docs/security-dsrp-1.md`; updater: `docs/inline-updater.md`; release: `docs/RELEASING.md`.
