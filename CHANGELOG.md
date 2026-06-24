# Changelog

This file owns the release history for `django-lux`.

> `django-lux` is the renamed, actively-maintained successor to
> [`django-microsys`](https://github.com/debeski/django-microsys) (now archived).
> Release history prior to v1.0.0 lives in that archived repository.

## v1.2.8

- **MigrationSafeTranslation Copy/Pickle Fix**: Added `__getnewargs__` to `dlux.translations.MigrationSafeTranslation` returning `(self.key, self.default_val)`. As a `str` subclass it was reconstructed via `str`'s default `__getnewargs__` (only `(str_value,)`), so any `copy.deepcopy`/pickle — notably Django ModelForm field/widget deepcopy of translated labels in Section management (`/sys/sections/`) tabs — called `__new__(cls, value)` and raised `MigrationSafeTranslation.__new__() missing 1 required positional argument: 'default_val'`. Pure-Python fix, no schema change; manifest marked `inline_safe=true`, `migration_policy=backward_compatible`.

## v1.2.7

- **Retrying Celery Health Handshake**: Replaced the updater's single immediate post-restart Celery ping/version checks with bounded retries sharing the 120-second web/Celery health deadline. Candidate activation and automatic pointer rollback now tolerate normal Celery supervisor startup latency instead of falsely failing after web is already healthy, switching back, racing the rollback worker again, and leaving the runtime in degraded maintenance.
- **Rebuild Recovery Clears Maintenance**: Rebuilt-image reconciliation now clears both the durable degraded marker and stale maintenance marker when a newer baked DjangoLux version intentionally supersedes the failed runtime selection. This lets the required v1.2.7 rebuild recover deployments already trapped behind nginx maintenance without manual volume/database surgery.
- **Database-Default Release Gate**: Tightened inline migration validation so a NOT NULL `AddField` must declare `db_default`; a Python-only `default` no longer passes because it is normally removed from the database column after backfilling and cannot protect inserts made by previous-release code during rollback.
- **Bootstrap Repair Release**: Marked v1.2.7 `inline_safe=false` because the faulty health orchestration executes from the already-baked updater while applying a candidate wheel; a candidate cannot repair the process evaluating its own activation. Generated deployments on v1.2.4-v1.2.6 must rebuild/redeploy once with `django-lux[updater]==1.2.7`; later manifest-approved releases can use inline updates again.

## v1.2.6

- **Yanked v1.2.5 (bad migration) — superseded by this release**: v1.2.5 shipped migration `0004` with `SystemBackup.trigger` as NOT NULL but only a Python `default`, which Django drops from the column after backfilling. Once `0004` applied, the updater's pre-update backup — created by the *previous* release's code, which has no `trigger` field (e.g. after a health-check rollback) — hit `null value in column "trigger" of relation "dlux_systembackup" violates not-null constraint`, leaving the inline update unretryable. v1.2.5 has been yanked; install v1.2.6 instead.
- **Backup Trigger Database Default**: `SystemBackup.trigger` now declares `db_default='manual'`, and migration `0004` was corrected to create the column with that persistent database-level default, so any release's code can insert a backup row whether or not it sets `trigger`. (Databases that already applied the broken `0004` from yanked v1.2.5 must run `ALTER TABLE dlux_systembackup ALTER COLUMN trigger SET DEFAULT 'manual';` once, since an already-applied migration is not re-run.)

## v1.2.5

- **Scheduled Backup Policy And Update Safety**: Added migration `0004_system_backup_policy` with defaulted `SystemSettings.backup_config` and `SystemBackup.trigger` fields, a twelfth Backups setup/System Settings surface, Celery-beat due checks, configurable storage-relative `auto_export_target`, age/count retention rotation, and trigger-aware backup history. Inline apply/rollback backups are explicitly tagged, created and verified before maintenance, protected while rotation runs, and described as a blocking safety prerequisite in the review modal; the additive defaulted migration remains inline-safe.
- **Idle Updater Status Reset**: Stopped the Options card from permanently rendering “Update operation completed” for the latest historical check on every page load or manual refresh. The frontend now tracks runs queued by the current page (or discovered while genuinely active), shows successful completion for five seconds, retains actionable failures, and returns an idle up-to-date card to just its installed/latest/check information; `updater.js` is cache-busted as `?v=20260623b`.

## v1.2.4

- **Canonical Wheel Staging Paths**: Fixed every v1.2.2/v1.2.3 inline apply failing before preflight because `RuntimeStore.wheel_path()` saved the verified artifact as `<sha256>-django_lux-X.Y.Z-py3-none-any.whl`; pip parses wheel compatibility from the basename and rejected the digest-prefixed name as an invalid version. Downloads now use `downloads/<sha256>/<canonical-wheel-filename>`, preserving digest isolation without changing the filename pip validates, and bounded/redacted pip diagnostics are persisted on staging failure.
- **Visible Inline-Update Progress**: Kept the review modal open after password confirmation and added a status meter plus durable `DluxUpdateRun.progress_log` output across download, verification, staging, preflight, backup, maintenance, migration, static collection, switching, restart, and health verification. Active apply/rollback runs reopen the progress modal after page reload, terminal errors remain visible instead of silently returning the button to enabled state, and modal dismissal is disabled only while a run is active.
- **Updater Password-Manager Suppression**: Removed the confirmation control from native HTML form submission, queue only the `current_password` field through explicit fetch handling, mark the input as a non-credential storage target, clear it after the queue accepts it, and removed the successful-submit modal dismissal that caused browsers to offer saving the confirmation password as a site login.
- **Repaired-Image State Reconciliation**: Taught updater bootstrap to recognize a newer baked image when the runtime still has no explicit `active.json` and the database records the replaced baked version. Reconciliation now activates the new image and clears stale candidate/rollback metadata instead of attempting to reconstruct the old image as a missing volume release and incorrectly entering degraded mode.
- **Bootstrap Repair Release**: Marked v1.2.4 `inline_safe=false` because the broken staging implementation lives in the already-baked v1.2.2/v1.2.3 updater and cannot repair itself from a candidate wheel. Existing generated deployments must rebuild/redeploy once with `django-lux[updater]==1.2.4`; releases after that repaired bootstrap can resume manifest-approved inline updates.

## v1.2.3

- **Email Provider Presets**: Added a `provider_preset` selector (Gmail, Outlook/Office 365, Amazon SES, Mailgun, internal relay, custom) to `email_config`, surfaced in the Step 3 email-delivery panel. Selecting a preset prefills SMTP host/port/STARTTLS/SSL client-side via `EMAIL_CONFIG_PROVIDER_PRESETS` (mirrored in `system_setup.js`); values remain editable and the choice persists on `SystemSettings.email_config`.
- **Test Email Sender**: Added a superuser-only, POST-only `email_send_test_view` (`sys/settings/email/send-test/`) that validates the recipient, checks `get_email_service_status()`, and sends a one-off message through `send_dlux_mail(..., alert_on_failure=False)`, returning JSON status. Wired into the email panel as a "Send test email" button with a transient recipient field and live result line.
- **Email Failure Alerts**: Added `failure_notification_recipients` to `email_config`. On transactional send failure, `send_dlux_mail` now routes an in-app `notify.error(..., recipients=<users>, email=False)` to the configured operators (never re-entering the broken mail path) and records an `audit`-category `email_delivery_failed` activity-log row. Guarded by the global notification enable flag and best-effort (never masks the original delivery error).
- **Single Version Source**: Retired the `dlux/VERSION` file (moved to `.xpose/`) and made the `version` field in `dlux/release-manifest.json` the sole source of truth. `dlux.__version__`/`get_version()` now read the manifest (which already ships in the wheel for the updater), `pyproject.toml`'s dynamic `attr` and the updater's `get_baked_version()` follow automatically, `validate_local_release_manifest` validates the manifest against its own version, and `release.yml` checks the tag against the manifest version — eliminating the version/manifest drift that previously broke `build-dist`.
- **Release Test Gate**: Added a matrixed `test` job to `release.yml` and made `build-dist` (and therefore `publish-pypi`) depend on it, so a failing suite now blocks PyPI publish — previously the tag pipeline published with no test dependency.
- **Attestation Test Hardening**: Fixed `test_attestation_requires_official_repository_and_workflow` to mock `manifest.importlib.util.find_spec` on its success path so the unit test no longer requires `pypi_attestations` to be pip-installed in CI.

## v1.2.2

- **Interrupted Update Run Recovery**: Added updater-worker startup recovery for durable runs left active by forced container termination or host restart. Pre-switch interruptions now recollect the currently selected static assets before clearing maintenance; post-switch apply interruptions atomically restore the recorded source pointer, swap `DluxUpdateState` active/previous metadata back, recollect source assets, increment `state/generation`, archive staging, and restart on the source interpreter. Recovery failures persist `recovery_failed`, degraded state, and nginx maintenance instead of leaving an ambiguous active run or exposing partially collected assets.
- **Durable Degraded Recovery State**: Stopped startup reconciliation from clearing a failed-recovery degraded marker merely because `active.json` remained syntactically valid. Degraded state now clears automatically only after verified empty-volume reconstruction or intentional activation of a newer rebuilt image, so container restart cannot conceal an unverified code/static recovery failure.
- **Long-Running Update Worker Liveness**: Added a dedicated updater heartbeat thread so full-system backups, migrations, static collection, and health verification can exceed the 45-second health window without making the live worker appear dead. Reconciliation handoffs still invalidate heartbeat before interpreter restart, and a crashed process still ages out normally.
- **Updater Bootstrap Health Handoff**: Invalidated the updater heartbeat before a reconciliation-triggered interpreter restart, instead of briefly reporting healthy with a worker still importing the superseded package. Web and Celery now remain dependency-gated until the updater restarts on the selected release and its migrator bootstrap completes.
- **Image-Rebuild Supersedes Inline Pointer**: Added reconciliation for the required rebuild path after an inline release is active. When the image-baked Dlux version is newer than the persistent volume selection, bootstrap now atomically selects the image, increments generation, clears stale candidate and incompatible pointer-rollback metadata, and restarts the updater so the newer image's migrations run; retained release directories remain untouched.
- **Dirty-Tree Migration Release Gate**: Updated the local inline-safe release checker to compare the full index/worktree against the base tag and include untracked migration files, eliminating false-green pre-commit checks where a new unsafe migration was not yet visible to `base..HEAD`. CI behavior remains equivalent on clean tagged checkouts.
- **Rollback Recovery Degraded-State Guard**: Wrapped manual rollback restoration of the current pointer, static assets, generation, and health in an explicit recovery boundary. Successful recovery now records `pointer_recovered`, returns the failed operation without degrading the restored runtime, and clears maintenance; failed recovery persists `recovery_failed`, marks database/runtime state degraded, keeps nginx maintenance active, and fails updater health after potentially partial static collection.
- **Updater Log Secret Redaction Coverage**: Expanded bounded updater-log sanitization beyond plain `password=value` tokens to cover quoted JSON-style secret keys/values, authorization schemes, CLI secret flags, and environment-style names such as `DJANGO_SECRET_KEY`, preventing bearer credentials or spaced/quoted secret values from surviving command and failure logs.
- **Global Staff Read-Only Update Polling**: Kept Global Staff updater monitoring on the diagnostics-authorized state endpoint instead of repeatedly polling the superuser-only detailed run endpoint during active operations, preserving live read-only status without avoidable 403 retry loops or expanding progress-log access.
- **Persistent Baked-Version Identity**: Made the project-owned supervisor capture the image-installed `django-lux` distribution version in `DLUX_BAKED_VERSION` before prepending any volume release to `PYTHONPATH`. `DluxUpdateState` and reconciliation now preserve that immutable image version separately from the active imported version, so rollback to the baked release remains available after updater, web, or Celery container restart/recreation.
- **Canonical PyPI Publisher Identity Verification**: Corrected the runtime provenance check to match PyPI's integrity API representation of the configured `.github/workflows/release.yml` trusted publisher as workflow basename `release.yml`. The verifier still requires GitHub publisher kind plus repository `debeski/django-lux`, and a live verification against the valid v1.2.1 PyPI wheel now exercises the same publisher contract used by deployed updates.
- **Interpreter-Bound Attestation Verification**: Changed updater provenance verification from a `PATH` lookup for the `pypi-attestations` console script to `sys.executable -m pypi_attestations`, ensuring the verifier installed for the active project interpreter is used in global Python and virtual-environment deployments while preserving fail-closed behavior when the optional module is absent.
- **Release Artifact Hygiene**: Excluded macOS `.DS_Store` metadata from recursive sdist and wheel package data so release artifacts contain only intentional DjangoLux source, templates, static assets, migrations, updater modules, and scaffold files.
- **Documentation Source Synchronization**: Re-audited the package README, documentation hub, getting-started/admin/developer/customization/reference/feature/concept/migration/release manuals, and generated-project README templates against the unreleased code. Corrected the 11-step setup/Nav Bar numbering, current `ActivityLog` naming, six-mode Client IP schema, onboarding keys, table precedence, 12-theme and generated-secret inventories, split `dlux.utils` entry points, management commands, dependency list, broken local links, and stale version metadata; added the generated-Compose updater models, volume/supervisor/security/apply/rollback architecture throughout the deployment and conceptual documentation.
- **Verified Inline DjangoLux Updater**: Added generated-Compose `dlux-updater` infrastructure with the persistent `dlux_runtime` release/state volume, standard-library Gunicorn/Celery generation supervisor, nginx maintenance fallback, official PyPI Simple JSON discovery, SHA-256 plus `debeski/django-lux`/`.github/workflows/release.yml` attestation verification, unchanged-dependency/Python/manifest/migration safety gates, staged `pip --target --no-deps` preflight, full-system backup, atomic activation, web/Celery version health verification, automatic post-switch code/static rollback, and current-password-confirmed manual rollback. Added singleton `DluxUpdateState`, durable bounded-log `DluxUpdateRun`, migration `0003_dlux_update_runtime`, superuser update APIs/System Info controls with Global Staff read-only visibility, and `python -m dlux enable-updater` dry-run/guarded bootstrap with `.xpose` preservation and `docker compose config` validation.
- **Seamless Aether Background Drift**: Changed the Aether theme's `aetherSheen` light-field animation to alternate direction at its eased endpoints instead of resetting from `180%/120%` to `-160%/-20%`, removing the visible lighting jump between iterations while preserving reduced-motion behavior; runtime and setup-preview theme stylesheet cache-busters are now `?v=20260622a`.

## v1.2.1

- **Mirrored System Setup Header**: Flipped the first-launch setup header composition on both the language gate and full wizard so title/description occupy the logical start edge and the logo sits opposite. The markup order and `text-align: start` remain direction-aware, producing text-left/logo-right in LTR and text-right/logo-left in RTL; `system_setup.css` is cache-busted as `?v=20260621a`.
- **English First-Launch Setup Language Selection**: Fixed the setup-language gate appearing to reload without entering the wizard when English was selected. The global `prevent_double_submit.js` helper disabled the form's first submit button during the native `submit` event; because English is the first named button, `setup_language=en` was removed from form serialization, while Arabic continued to work. The helper now uses `event.submitter`, blocks repeat submits with form state, and defers disabling the clicked button until after native serialization; `base.html` cache-busts the helper as `?v=20260621a`, and both English and Arabic setup paths have regression coverage.

## v1.2.0

- **Dlux Permission Descriptions**: Added localized helper text for Dlux-owned assignable permissions that previously rendered without descriptions in the grouped staff/user permission cards: reports, backup downloads, section viewing/management, and activity-log viewing. The grouped permission widget now sources Dlux permission descriptions from a codename-to-translation-key map while keeping permission definitions and migrations unchanged.
- **Titlebar Surface Options Now Apply Across Themes**: Added a post-theme `titlebar_surfaces.css` override layer loaded after every configured theme stylesheet so `titlebar.surface` values are no longer hidden by theme-level `.titlebar { background: ... !important; }` rules. `muted` and `glass` now use theme-aware `color-mix()` backgrounds, explicit border/shadow changes, and glass blur/saturation overrides with enough specificity to win after theme CSS while leaving each theme's `default` titlebar intact; `base.html` loads the asset as `?v=20260620a`.
- **First-Launch Setup Language Gate**: `/sys/setup/` now starts unconfigured systems with a setup-language gate before the wizard renders. The chosen language is stored in `request.session["dlux_initial_setup_language"]` and drives only the first-launch setup UI language/direction; the actual app default language remains the normal editable `default_language` setting in the Localization step and can differ from the setup UI language. Default-language controls inside first-launch setup and later System Settings modals are save-only: `system_setup.js` no longer calls `setLanguage(..., previewOnly)` or posts `__language_preview`, removing the reload path that reset edited theme/font/sidebar/titlebar values and sent the wizard back to step 1. After setup saves, the current session language follows the saved app default language, including newly added catalog languages; `base.html` loads `system_setup.js` as `?v=20260620l`.
- **Initial System Setup App-Shell And Titlebar Preview Stability**: Rebuilt the full-page system setup wizard (`system_setup.html`) as a header/body/footer app-shell with one scroll container (`.dlux-setup-scroll`), sticky `.dlux-setup-step-nav`, and a fixed footer fed by `system_setup.js` (`initSetupFooterRelocation`). Fixed the regression where changing any setup option (titlebar height/surface/icon/logo/user-hub, but also login logo treatment and table density on other steps) shoved the whole shell up behind the titlebar so it looked like it vanished. Root cause was a JS routine that measured `titlebar.getBoundingClientRect().height` into `--dlux-setup-titlebar-offset` on every preview change (the live preview always re-runs `applyTitlebarPreview`); the `position:fixed` viewport's `top` was bound to that var, so a bad/small read collapsed `top` to ~0 and the shell (z-index below the titlebar) jumped up behind it. The measurement is removed (JS no-ops) and `.dlux-setup-viewport` is now a plain flow box (`height: calc(100vh - var(--header-height))`, no `position: fixed`, no `top`, no measured var) — the same scaffold `base.html`'s `#mainContent` uses, so nothing can push it up. The setup card now expands to the full available width (`max-width: none`) and the titlebar sidebar toggle is suppressed only on first-launch setup via `hide_sidebar_toggle=True`, since the setup layout does not render the runtime sidebar. Follow-up: the selector-specific "shoved behind the titlebar" symptom was a **native focus-scroll** — clicking a `DluxChoiceSelectorWidget` card focuses its visually-hidden `.dlux-choice-option__input`; because the input was absolutely positioned without a positioned option ancestor, the browser could scroll the wrong container into view. `selectors.css` now anchors every hidden choice input to its visible `.dlux-choice-option` card (`position: relative`, `inset: 0`, full width/height), and `selectors.js` keeps the pointer-triggered scroll snapshot fallback for already-rendered edge cases while leaving keyboard focus accessible. Cache-busters: `system_setup.css` `?v=20260620k`, `system_setup.js` `?v=20260620l`, `selectors.css` `?v=20260620c`, `selectors.js` `?v=20260620b`.
- **System Settings Registry Source Of Truth**: Added the `dlux.system` package with canonical `constants`, `defaults`, `normalizers`, typed `schema`, and `registry` helpers for `SystemSettings` JSON groups, legacy flat keys, runtime aliases, export/import field coverage, and default runtime config assembly. Internal imports now use `dlux.system.constants`; root `dlux.constants` remains a thin re-export shim for downstream `from dlux.constants import ...`, while the old defaults modules were removed so canonical defaults/normalizers live only under `dlux.system`. Existing published migration callables such as `dlux.models.default_log_config` remain importable as wrappers without changing the stored `SystemSettings` schema.
- **Restored `dlux.constants` public surface + dropped redundant scaffold pagination**: The registry refactor had deleted `dlux/constants.py`, breaking downstream apps with `ModuleNotFoundError: No module named 'dlux.constants'` (e.g. `from dlux.constants import DEFAULT_TABLE_PAGE_SIZE`). Recreated it as a star re-export of `dlux.system.constants` (`__all__`-complete, 66 names). Separately removed the redundant `paginate_by = DEFAULT_TABLE_PAGE_SIZE` and its constant import from the app scaffold template `dlux/scaffold_templates/app/views.py.tmpl` (and the generated `charlie` sample): dlux's `patches.py`/`DluxTable` already own per-page resolution plus the rows-per-page selector, so the static `paginate_by` only re-introduced ListView/django-tables2 double pagination.
- **Schema-Driven Settings Form Slice**: Wired `SystemSettingsForm` low-risk scalar groups (`auth_config`, `registration_config`, `public_root_config`, `layout_config`, and `client_ip_config`) to the `dlux.system` schema for initial-value hydration and cleaned-data packing while leaving email secrets, notifications, login hero copy, titlebar, sidebar, navbar, logging, profile, language, theme, and font builders custom. Completed the flat auth compatibility path for `enforce_strong_passwords` across export/import, setup save, and runtime config merge.

## v1.1.0

- **Single Active Session works with cache-backed sessions**: Added `UserPresenceSession.session_key` folded into the unreleased `0002_system_settings_configs_and_notifications.py` migration so Dlux presence records retain the raw active session key alongside the existing hash. `terminate_other_user_sessions()` now combines DB-backed `django_session` rows with Dlux presence keys and deletes each target through Django's configured `SessionStore`, so `prevent_multiple_active_sessions` evicts Redis/cache-backed sessions as well as DB sessions. The setting is documented as newest authenticated session wins regardless of trusted-device status; older browsers see the session-ended interstitial on their next request.
- **Profile activity feeds capped to five entries each**: `user_profile` now caps both Recent Activity and System Interactions at the latest five entries; `_PROFILE_SYSTEM_INTERACTION_LIMIT` was reduced from 10 to 5 and regression coverage asserts newest-first five-entry output for both feeds.
- **Persisted notifications rerender after language switches**: Added `resolve_translation_key_for_text()` to the translation layer and taught notification flash/drawer/API serialization to infer a `DLUX_STRINGS` key when an older `DluxNotification.message/title` lacks metadata but exactly matches a known core/app/project translation value. Existing built-in rows such as password-change, user-management, section, and file/export notices now display in the active request language after a language switch, while free-form/interpolated messages continue to use stored text. Added missing file/export notice keys and updated fixed file/user/section notification call sites to emit `metadata.message_key` for new rows.
- **Password-change modal keeps validation in place**: Profile password-change failures now stay modal-scoped: invalid `CustomPasswordChangeForm` POSTs no longer enqueue the generic `msg_form_error` notification, `profile.html` marks `#resetPasswordModal` with `data-dlux-open-on-load="true"` when the bound password form has errors, and `profile_2fa.js` reopens the Bootstrap modal and focuses the invalid field after the response render. The password-change success notification now carries `metadata.message_key="msg_password_changed"` for language-aware display.
- **Notification payloads resolve translation keys per request**: `notify(...)` now accepts optional `message_key` and `title_key` arguments and stores them in notification metadata while retaining fallback text in `DluxNotification.message/title`. Flash payloads include those keys, `get_flash_notifications()` localizes queued notices as they drain, and `serialize_notification_state(state, request=...)` localizes titlebar drawer/API items for the active request language. Core profile/security notifications for password changes, session revocation, trusted devices, and current-password confirmation now emit keyed metadata.
- **Password changes now reject unchanged passwords**: Added a shared `DluxPasswordMustChangeMixin` for `CustomPasswordChangeForm` and `ResetPasswordForm` so profile password changes, forced first-login password changes, and staff/admin reset-password submissions reject `new_password2` when it matches the target user's current password hash. The new `password_unchanged` validation path keeps the stored hash untouched, leaves `Profile.preferences["force_password_change"]` active until a genuinely new password is saved, and adds localized `err_password_unchanged` strings.
- **Forced password change now takes precedence over Initial User Setup**: The `DLUX_SHOW_INITIAL_USER_SETUP` context flag now checks `Profile.preferences["force_password_change"]` and suppresses the auto-open `/accounts/welcome/` dynamic modal while the middleware is forcing `/accounts/profile/?force_password_change=1`. This prevents the first-login onboarding modal from AJAX-loading into a 403 on the only allowed page; once the password is changed and the flag is cleared, onboarding can open normally. The profile-page forced-password alert now renders `data-autoclose="false"` so `base_runtime.js` does not remove the required action after the flash timeout.
- **Choice selector cards inherit dark theme surfaces**: `selectors.css` replaced the shared toggle selector's opaque white surface gradients with `--dlux-choice-toggle-surface*` variables backed by `--dlux-choice-surface`, `--dlux-choice-surface-hover`, and `--dlux-choice-surface-active`. System Settings toggle choices such as `titlebar_title_size` now inherit each theme's setup item backgrounds instead of showing light cards in dark-based themes; `base.html` bumps `selectors.css` to `?v=20260619b`.
- **Notification drawer/panel adapts to dark themes**: `notifications.css` replaced the panel's hardcoded light values (white `__panel` background, `#64748b`/`#475569` muted text, faint `rgba(64,94,115,…)` hover/unread tints) with theme variables — `__panel` uses `var(--table-row)`, muted text uses `color-mix(in srgb, var(--title) …)`, and hover/unread tints use `var(--primal-rgb)`. The drawer now reads correctly across all 12 themes (no per-theme overrides; cache-buster bumped to `?v=20260619a`).
- **Titlebar action buttons fixed in dark themes via a shared class**: The notification bell and the generic action buttons kept `titlebar.css`'s hardcoded white background in dark themes because the dark themes only overrode `.dlux-titlebar-home`/`.dlux-login-round` — `.dlux-titlebar-action`/`.dlux-notifications__trigger` were missed, leaving them as gray/white circles. Rather than repeat the four-class list everywhere, all titlebar buttons (home, action, login, notification trigger) now share a single **`dlux-titlebar-btn`** class; `titlebar.css`'s base appearance + hover and the six dark themes' overrides target that one class, so every button gets the correct dark treatment. (Shape variants stay per-class since home-shape applies only to home/trigger/login.) `titlebar.css` + theme CSS cache-busters bumped to `?v=20260619a`.
- **`profile_config` group + first-login Initial User Setup modal**: New `default_profile_config()` JSON group governing the user profile page and onboarding — `show_completion_widget`, `show_session_device_cards`, `show_activity_feed`, `security_nudges` (`off`/`subtle`/`persistent`), `allow_user_home_url`, `onboarding_enabled`, and `onboarding_options` (which prefs the modal offers). The per-user landing page is stored as `Profile.preferences['user_home_url']` (named to match the existing `home_url`/`public_root_url` family) and is honoured at login by `CustomLoginView.get_success_url()` and the 2FA `_resolve_safe_login_redirect()` via `resolve_user_home_url()` — after an explicit `?next`, before the system `home_url`, gated by `allow_user_home_url`. Wired through `normalize_profile_config()`, the config registries/aliases (`profile`), `get_system_config()` DB override, the `SystemSettings.profile_config` JSONField, import/export, and a new **Step 11: Profile Page** wizard step (`profile_builder.html`, dlux toggle styling, `system_setup.js` `initProfileBuilder`, options-card tile, EN/AR strings). Added a per-user `Profile.is_configured` flag (folded into `0002`). The **Initial User Setup** (`initial_user_setup` view at `/accounts/welcome/`) auto-opens once per user via the dlux dynamic modal (context flag `DLUX_SHOW_INITIAL_USER_SETUP` + a `data-dlux-auto-open` trigger and skip handler added to `dynamic_modal/js/main.js`, bumped to `?v=20260618a`); the AJAX GET returns the `{html: ...}` payload the dynamic modal expects. It lets the user pick theme/language/fonts (+ optional home override) into `Profile.preferences` and marks the profile configured. **Superusers are excluded** from the onboarding nudge (they own the system and run the system-setup wizard). The per-user landing page also has a permanent home: a **Landing page** card in the Options view (`/sys/options/`, gated by `allow_user_home_url`), so users can set/change it outside the one-time modal. Both the onboarding modal and the Options card present a **discovered, permission-filtered dropdown** (new `build_user_home_url_options(user)` reuses `discover_sidebar_catalog` + the sidebar permission rules) instead of a free-text field — users only see pages they can actually access — and `update_preferences`/the modal POST validate the submitted value against that allowed set. Simplified the onboarding gate to the single `allow_user_home_url` toggle (dropped the redundant `onboarding_options.user_home_url`). The onboarding save sets `skip_signal_logging` so completing the modal no longer emits a "profile updated" notification or activity-log entry (the signals' preferences-only skip didn't catch the two-field `preferences`+`is_configured` save). The profile page now gates the completion widget, session/device cards, activity feed, and security-health nudge on `profile_config`.
- **Activity log unified as the single source of truth with user/system/audit categories**: Renamed the `UserActivityLog` model to `ActivityLog` (with a backward-compatible `UserActivityLog` module alias and a `RenameModel` folded into the unreleased `0002` migration; `apps.get_model('dlux','ActivityLog')` lookups updated across signals/reports/backup/views/admin/tests). Added a `category` CharField (`user`/`system`/`audit`) with a `dlux_ual_cat_created_idx` composite index and a same-migration `RunPython` backfill that classifies existing rows from `action`/`model_key`/`model_name`. Category is derived at log time by `resolve_log_category()` (precedence: explicit → `dlux_log_category` model attr → `app_label=='dlux'` ⇒ system → default user) and set on `ActivityLog.safe_log(... category=...)`.
- **`log_config` System Settings group drives logging**: New `default_log_config()` JSON group (master `enabled`; `user`/`system` sections with `enabled`, `default_actions`, `retention_days`, and a sparse per-model `models` override map supporting per-action sub-toggles and custom dev action keys; privileged `audit` section with per-event flags, `immutable`, and its own `retention_days`). Wired through `normalize_log_config()`, `_CONFIG_GROUP_NORMALIZERS`, `expand_system_config_groups` (`log`/`logging` aliases), `get_system_config()` DB override, the `SystemSettings.log_config` JSONField + `_SYSTEM_SETTINGS_CONFIG_DEFAULTS`, import/export (`SYSTEM_SETTINGS_EXPORT_FIELDS`), and the setup wizard (new Step 10: Logging) via a `log_builder.html` grid (master/section/audit toggles + searchable per-model/per-action list) hydrated/serialized by `system_setup.js`, with EN/AR strings and `system_setup.css`. High-churn dlux operational models (trusted/known devices, presence, notifications, backups) are seeded excluded by default so they don't flood the log.
- **Config-driven log gating replaces the hardcoded `EXCLUDED_MODELS` list**: `signals.py` now consults `log_config` via `is_model_logging_enabled()` (master/section/model + per-action) with a non-toggleable correctness floor (`LOG_FORCED_EXCLUDED_MODEL_KEYS` — Session and other non-integer-PK/bookkeeping tables). `get_active_log_config()` reads the cached singleton without ever creating it (safe inside save/delete signals).
- **Security events are now captured under the `audit` category**: Added a gated `log_audit_event()` helper and instrumented the previously-unlogged security events — failed logins and lockouts (`login_throttle.register_failed_login` → `LOGIN_FAILED`/`LOCKOUT`), 2FA enable/disable/failure (`views/twofa.py` → `2FA_ENABLE`/`2FA_DISABLE`/`2FA_FAILED`), password change, session/trusted-device revoke (`views/profile.py`), incorrect-password confirmation (`guards.py` → `PERMISSION_DENIED`), and login/logout (`signals.py`). Each is gated by its `log_config['audit']['events']` flag; `resolve_log_category` treats these actions as `audit`.
- **Audit log is append-only and prune-aware**: `ActivityLog.save()`/`delete()` block in-app modification/deletion of `category='audit'` rows. New `dlux_prune_activity_log` management command deletes `user`/`system` rows past their `retention_days` and **skips audit** unless `audit.retention_days > 0` (`--dry-run` supported).
- **Activity-log view category tabs**: `/sys/logs/` now shows user/system/audit tabs (`?category=`) with per-tab counts; the `audit` tab and its rows are restricted to superusers/global staff. Admin gains a `category` column/filter. Tabs use the dlux `nav-tabs` style (themed via `--primal`) to match the rest of the app, and a **Logging** tile (modal `?step=9`) was added to the System Settings options card.
- **Zero-boilerplate `dlux.log_activity` helper**: `from dlux import log_activity; log_activity("APPROVE", obj)` (or `log_activity("EXPORT", pk, model="app.model")`) resolves model/scope/actor/IP from the current request, defaults to the `user` category, honours `log_config` per-model/per-action gating, and returns the created row (custom action strings surface as toggles in Settings once seen).
- **Deterministic User/Profile log unification**: Replaced the fragile same-calendar-second merge (which double-logged when two saves straddled a second boundary) with a rolling-window merge (`_IDENTITY_MERGE_WINDOW_SECONDS`) keyed off `_resolve_identity_user_pk()`.
- **Logging settings grid now matches dlux styling and shows only meaningful models**: The Step 10 grid uses the shared `dlux-settings-toggle-field` switch component instead of raw Bootstrap checkboxes. Added `is_model_loggable()` (`LOG_NEVER_LOGGED_APP_LABELS` incl. health-check `db`, `LOG_NEVER_LOGGED_MODEL_NAMES` incl. `testmodel`, and `LOG_NEVER_LOGGED_MODEL_KEYS`) so Django framework internals, health-check/test models, and dlux operational/identity/self/dummy models (notifications, devices, presence, backups, Profile, ActivityLog, the fieldless `dlux.Section` placeholder) are never logged or offered as toggles. `build_log_model_catalog` puts non-dlux project + section models under **Project** and dlux config models under **System**.
- **Controllable user-identity logging + custom-action toggles**: Added a synthetic `dlux.useridentity` ("User accounts") grid entry under **System** (user accounts are a core dlux component) that gates the unified User+Profile log; identity rows are stored under the `system` category and logging now respects the toggle instead of being force-on. Per-model `actions` now include any `dlux_log_actions = [...]` a model declares, surfacing custom actions (e.g. `download`/`export`) as Step-10 toggles; custom actions remain logged by default and are gated by the same per-model/per-action logic.
- **Removed duplicate native tooltips on titlebar action icons**: Dropped the redundant `title` attribute from the titlebar action elements that already render the custom `data-dlux-tooltip` (logout, help, generic action links, and unauthenticated action links), so hovering no longer shows the browser tooltip stacked on top of the Dlux tooltip. `aria-label` is retained on each for accessibility; the dropdown-layout home/login links (native-tooltip only) are unchanged.

- **Dedicated Notifications settings step with global master gate**: Split the
  notification controls out of the cluttered Titlebar step into their own
  System Settings wizard step (now Step 8: Notifications; Themes & Typography
  moves to Step 9). Added a top-level `notifications.enabled` flag to
  `default_notification_config()`/`normalize_notification_config()` surfaced as a
  `notifications_enabled` master toggle that hides a `data-notifications-dependent`
  block, mirroring the sidebar/navbar enablement pattern. When off,
  `emit_notification_event()`, `get_flash_notifications()`, and
  `get_notification_context()` all short-circuit, suppressing flash notices, the
  titlebar drawer/badge, emails, automatic ScopedModel CRUD notifications, and
  `notify(...)`. Wired the new step into the wizard nav, options.html tiles
  (`?step=7` notifications, `?step=8` appearance), `system_setup.js` master-toggle
  sync + preview gating, EN/AR strings, and the `?step` modal bound (now 0–8).

- **First-login password change enforcement**: Added a create-user-only
  `force_password_change` checkbox (default off) that stores a per-user marker in
  `Profile.preferences`; `DluxMiddleware` redirects marked accounts to
  `/accounts/profile/?force_password_change=1` until the profile password-change
  form succeeds, then clears the marker. The profile page now shows a translated
  password-change prompt, and the flag is not exposed on edit/reset flows.

- **Strong password enforcement (auth_config toggle)**: Added an
  `enforce_strong_passwords` toggle to the consolidated `SystemSettings.auth_config`
  JSON field (default off), surfaced as a System Settings security toggle (split
  from / merged into `auth_config` like the other auth toggles). When enabled,
  new passwords must be >=12 chars with upper- and lower-case letters, a digit,
  and a symbol. Enforcement is a new `dlux.password_validation.DluxStrongPasswordValidator`
  registered in `AUTH_PASSWORD_VALIDATORS` by `dlux_settings()` (a no-op when the
  toggle is off), so every set-password path that runs Django's `validate_password()`
  (registration, user creation, password change/reset) is covered. A live,
  on-focus requirements checklist (`helpers/password_rules/`) appears under
  new-password fields (`autocomplete="new-password"`, incl. dynamic-modal forms),
  ticking each rule green as it is met. The confirm field (`...password2`) instead
  shows a single "matches the password" check against its `...password1` sibling.
  Gated on `window.DLUX_CONFIG.enforce_strong_passwords`, labels via `DLUX_STRINGS`
  (EN/AR), DSRP-1-compliant (external JS/CSS, no inline).

- **No DB access during app init**: `get_strings()` no longer calls
  `get_system_config()`/`get_current_language_code()` (which read the
  `SystemSettings` singleton from the DB) while `apps.ready` is `False`. The dlux
  gettext patch routes lazy translations resolved during `AppConfig.ready()`
  through `get_strings()`, which triggered Django 6.0's "Accessing the database
  during app initialization is discouraged" `RuntimeWarning` on every startup/
  reload — and risked opening a DB connection before migrations run or in a
  pre-forked WSGI worker. During init it now serves the in-memory translation
  catalog with safe defaults; the DB override + active-language layer resumes
  automatically once apps are ready.
- **SystemSettings JSON Config Consolidation**: Reworked `SystemSettings` so only
  identity fields remain standalone (`system_names`, logo/favicon, default
  language/theme, `home_url`, `is_configured`) while mutable settings now live
  in ordered JSON groups: `auth_config`, `email_config`,
  `registration_config`, `public_root_config`, `client_ip_config`,
  `notification_config`, `layout_config`, `language_config`, `theme_config`,
  `typography_config`, `login_config`, `titlebar_config`, `sidebar_config`,
  `navbar_config`, and reserved `extra_config`. Added compatibility
  properties plus legacy `save(update_fields=...)` routing so flat callers keep
  using keys such as `allowed_themes`, `translations_override`,
  `public_root`, and `default_table_density`; `get_system_config()` and setup
  import/export stay flat while accepting nested aliases, and
  `translations_override` remains override-only data. Replaced the uncommitted
  `0002_auth_config.py` and `0003_notifications.py` with unified
  `0002_system_settings_configs_and_notifications.py`, folding old columns into
  grouped JSON and adding the notification models/config in one migration.
- **Consolidated Package CI Test Harness**: Added shared
  `dlux.tests.settings`/`dlux.tests.harness` Django test configuration and
  switched `.github/workflows/ci.yml` to the curated `dlux/tests/test_all.py`
  runner; restored `test_defaults_and_urls.py` to the CI label set, moved report
  overview backup polling into versioned static JS, refreshed stale scaffold/
  cache-buster/root-redirect assertions, and made `get_system_config()` quiet
  expected missing-table/test-DB fallback paths while preserving warnings for
  unexpected config failures.
- **Read-Only Notification Clear**: Changed the titlebar notification drawer
  `bi-x-lg` bulk clear action and `clear_all_notifications()` helper to dismiss
  only already-read visible states, preserving unread items so they remain visible
  until the user explicitly reads them; the drawer now refreshes after the POST instead
  of blanking the list client-side.
- **Titlebar User Hub Layout Styles**: Added `titlebar.user_hub_style`
  (`dropdown` default, `titlebar_actions`) and normalized
  `titlebar.actions_order` inside the existing `SystemSettings.titlebar_config`
  JSON field; added a System Settings style selector plus compact action-order
  builder with live titlebar preview; style 2 renders profile/help/users/
  activity/reports/settings/auth as permission-gated `.dlux-titlebar-action`
  buttons in a horizontal titlebar rail, keeps notification/home omission tied
  to existing drawer/home toggles, and uses POST + CSRF for logout.
- **Style 2 notification drawer fix**: In `titlebar_actions` mode the notification
  bell opened a panel that never appeared — the horizontal action rail
  (`.titlebar__actions--titlebar`, `overflow-x:auto`/`overflow-y:hidden`) clipped
  the `position:absolute` dropdown. Pinned the panel with `position:fixed`
  (anchored to the titlebar top-end corner) for `≥576px` in style 2, leaving the
  existing mobile full-width fixed rule and style 1 dropdown untouched; also gave
  the bell a `data-dlux-tooltip` so it matches its sibling titlebar actions.
- **Options switch-row mobile layout**: Stopped the Options page simple toggle
  rows (`.dlux-options-switch-row`, e.g. High Contrast) from stacking the label
  and switch onto separate lines on mobile — they now keep their `space-between`
  row since there is ample width; the more complex toggle/reset shells still
  stack as before.
- **Notification CRUD Toggle Layout**: Changed the System Settings notification
  automatic-CRUD toggle row from four-column `col-xl-3` sizing to three equal
  `col-lg-4` columns so the master/create/delete toggles fill the full row.
- **Notification Drawer Bulk Controls**: Replaced the titlebar notification drawer
  “Mark all read” text link with a Bootstrap `bi-envelope-open` icon action,
  added a `bi-x-lg` clear-all action backed by `/sys/api/notifications/clear-all/`
  and `clear_all_notifications()` to dismiss read current-user drawer states, localized
  the JS empty-drawer text, and renamed/clarified notification email delivery as
  a master-gated email channel over rule/API-triggered mail.
- **Stale singleton cache fix ("settings reset, then return")**: `SingletonModel.load()`
  now discards a *readable-but-stale* cached pickle — one written by an older model
  revision (a dev hot-reload, or a deploy/migration that added fields such as
  `auth_config`/`notification_config`). Such a pickle unpickles without error (so the
  existing poisoned-key guard never fired) but lacks the new field attributes, so
  `get_system_config()`'s `hasattr()` guards silently served their defaults — system
  settings appeared to reset, then "returned" once the cache was rebuilt. `load()` now
  verifies the cached instance carries every current concrete field (`_meta.concrete_fields`)
  and rebuilds from the DB (self-healing on next read) if any are missing.
- **Resilient SystemSettings Cache (setup-wizard lockout fix)**: Hardened
  `SingletonModel.load()` so an unreadable or incompatible cached singleton — e.g.
  a pickled `SystemSettings` written by a prior code revision and left in Redis
  after a dev hot-reload or a model-changing deploy — no longer raises out of
  `load()`; the poisoned key is logged, `cache.delete()`d, and transparently
  rebuilt from the database, and the existing-row check plus `cache.set`/
  `refresh_cache()` writes are now exception-guarded. Added a cache-free safety
  net in `get_system_config()` that, when the merge block fails, consults
  `SystemSettings.objects.filter(pk=1, is_configured=True)` directly so a cache
  read error can no longer collapse to the default `is_configured=False`. This
  was making `DluxMiddleware._setup_redirect_response` treat a fully configured
  system as unconfigured — force-logging-out non-superusers and routing
  superusers to `system_setup` — i.e. the recurring "signed out then dropped into
  initial system setup despite an intact, configured database" reports.
- **Notification Settings Polish**: Clarified System Settings notification
  controls with translated help text for automatic CRUD master/create/update/
  delete behavior, renamed the update selector to “Automatic update mode,”
  disabled and server-coerced notification email delivery/default-email toggles
  unless Dlux email delivery is configured, grouped email toggles into their own
  row, added live unsaved preview for notification drawer/badge and flash
  presentation settings, and promoted `titlebar.buttons_shape` as the canonical
  titlebar action-button shape setting while preserving legacy `home_shape`.
- **Cursor-Safe Backup Streaming**: Reworked shared report ZIP and full-system
  `.dlb` backup export streaming to use primary-key page iteration plus a
  backup-local JSON serializer for many-to-many fields, avoiding Django
  `QuerySet.iterator()` server-side named cursors that can fail in PostgreSQL
  transaction-pooling deployments with errors such as missing `_django_curs_*`
  cursors; added a focused system-backup regression test that patches
  `QuerySet.iterator()` to prove the export path no longer depends on it.
- **Zero-Boilerplate Dlux Notifications**: Added a durable notification pipeline
  with `DluxNotification`, `DluxNotificationState`, `DluxNotificationRule`, and
  `DluxNotificationWatch` models; added
  `SystemSettings.notification_config` for flash position/size/text-size/timeout,
  drawer/badge bridge/email/retention, and automatic CRUD defaults; exposed
  `dlux.notifications.notify(...)` with `.success/.warning/.error` helpers,
  inferred request/user/scope metadata, session-backed redirect flash queue,
  rule routing, model-level watches, optional email delivery, and a disabled-by-default
  Django messages compatibility bridge; wired `ScopedModel` create/update/
  delete auto-events through the activity-log signal diff/masking path with
  generic modal/context-menu route metadata; added titlebar notification drawer UI,
  unread badge, detail/dismiss/mark-all-read API endpoints, and converted Dlux
  setup, 2FA, backup, profile, user, section, registration, guard, and fetcher
  call sites from Django message storage to `notify(...)`.
- **Debug Notification Trigger**: Added DEBUG-only, superuser/global-staff guarded
  `/sys/debug/notifications/` for exercising Dlux notification flash, drawer, and
  inbox behavior with `level`, `flash`, `persist`, `email`, and `next` query
  controls.
- **Non-Blocking Django Message Toasts**: Replaced full-width absolute Django
  message banners with shared `dlux/includes/messages.html` flash markup,
  compact `.dlux-flash-container` / `.dlux-page-alert-container` positioning,
  icon + close-button alert content, and a `base_runtime.js`
  `.dlux-alert--closing` removal path that disables pointer events immediately
  instead of leaving invisible titlebar-blocking hitboxes during fade-out.
- **Microsys Migration Missing Table Repair**: Updated
  `dlux_migrate_from_microsys` to create concrete Dlux `0001_initial` tables that
  are absent from older Microsys source schemas, and added
  `--repair-missing-tables` for already-relabelled databases missing tables such
  as `dlux_systembackup`, `dlux_reportbackup`, and `dlux_systemrestore`.
- **Utils Re-Export Completion**: Restored `default_auth_config` and
  `normalize_auth_config` from `dlux.utils`, fixing host-project startup when
  `dlux.forms` imports consolidated auth-config helpers after the utils package
  split.
- **Microsys Migration Guide Accuracy**: Updated the in-place migration guide to
  note that `python manage.py migrate` may apply post-rebrand `dlux` migrations,
  including the unified SystemSettings/notifications migration, after
  `dlux_migrate_from_microsys --yes`.
- **The Lux Signature (hidden attribution)**: A layered, on-brand ("Lux = light")
  credit woven into the universal `base.html` and shared assets so every page
  carries attribution to DjangoLux by default — invisible in normal use,
  discoverable by the curious, **purely client-side (no network calls/telemetry),
  and removable**. Seven layers: (1) a single quiet `%c`-styled console line on load
  via new `dlux/static/dlux/main/js/signature.js`; (2) a `window.lux`/`window.dlux`
  console getter (`enumerable:false`, so it only fires when typed — never on
  `window` expansion) that prints an expanded credit card; (3) typing `dlux` on a
  page outside form fields reveals a compact non-interactive visual credit using
  `.dlux-signature-pop`; (4) `<meta name="generator" content="DjangoLux X.Y.Z">`;
  (5) a `data-dlux` attribute on
  `<html>` that doubles as the DSRP-1 data bridge the signature script reads
  (no inline JS); (6) a `--dlux-credit` CSS custom property + `/*! … */` banner in
  `main.css`; (7) a Dublin-Core `<metadata>` self-signature in `base_logo.svg` and
  `login_logo.svg`. Version is exposed via `DLUX_VERSION` (context processor);
  dynamic surfaces show the live version, static assets carry a timeless credit
  (no version) to avoid release-time drift. DSRP-1-compliant (external assets +
  `data-*` bridge, CSP nonce); `signature.js` and `template_cleanup.css`
  cache-busters bumped to `20260615a`, `main.css` keeps the credit banner.
- **Auth Hardening — login lockout, 2FA window, session timeouts** (dependency-free,
  cache/session only):
  - **Failed-login lockout**: new `dlux/login_throttle.py` throttles failed
    password attempts per IP + username via the cache; after
    `DLUX_LOGIN_LOCKOUT_MAX_ATTEMPTS` (default 5) the identifier is locked for
    `DLUX_LOGIN_LOCKOUT_SECONDS` (default 900s). Wired into `CustomLoginView`
    (`post` rejects locked attempts with HTTP 429, `form_invalid` counts,
    `form_valid` clears). Gated by the `login_lockout_enabled` toggle (default on)
    surfaced in the Access & Security settings group.
  - **Consolidated `auth_config` JSON field**: replaced the standalone
    `email_2fa` and `prevent_multiple_active_sessions` boolean columns (and the
    proposed `login_lockout_enabled` column) with a single `auth_config`
    `JSONField` on `SystemSettings`, treated like the other JSON configs —
    split into individual UI toggles on the form and merged on save. The
    `auth_config` data migration is folded into the unified
    `0002_system_settings_configs_and_notifications.py`, which migrates
    existing boolean values into grouped JSON and drops the old columns.
    `get_system_config()` flattens `auth_config` back
    to top-level keys so every existing read site (`config.get('email_2fa')`,
    etc.) and the settings export/import format are unchanged.
  - **2FA completion window**: the pre-2FA challenge now carries a server
    timestamp (`PRE_2FA_STARTED_AT_SESSION_KEY`) and is abandoned after
    `DLUX_2FA_CHALLENGE_WINDOW_SECONDS` (default 300s) in `verify_otp_view`,
    closing the gap where a half-finished challenge lived for the whole session.
  - **Idle + absolute session timeouts**: `DluxMiddleware` enforces optional
    `DLUX_SESSION_IDLE_TIMEOUT_SECONDS` and `DLUX_SESSION_ABSOLUTE_TIMEOUT_SECONDS`
    windows (both default 0/off, opt-in) beyond Django's `SESSION_COOKIE_AGE`,
    logging out and routing to the session-ended page with an
    `idle_timeout`/`session_timeout` reason. Documented in `DSRP-1`.
- **Conceptual Codebase Report**: Added `docs/conceptual-codebase-report.md`, a concept-first architecture and algorithm map covering layered runtime configuration, setup/import/export, middleware/context resolution, scoped data, authorization, 2FA/session trust, public registration, audit logging, reports, `.dlb` backup/restore, discovery, sidebar/navbar, tables, dynamic modal CRUD, scaffolding, optional SSO, and release/test surfaces.
- **Logo Mark Polish**: Refined the crimson `L` in `base_logo.svg` and
  `login_logo.svg` — removed the white center-seam highlight, added a graphite
  (`#10191f`) outline so it seats into the shield like the `D`, slimmed the
  stroke to match the `D`'s weight, and replaced the seam with a subtle
  upper-stem edge sheen. Reworked the top bevel reflection from a flat opaque
  chevron into a fading `sheen` gradient glint.

## v1.0.3

- **Utils Package Modular Split**: Reorganized the 4,286-line monolithic
  `dlux/utils.py` (140 public symbols) into a `dlux/utils/` package — 13 feature
  modules (`config`, `crud`, `discovery`, `mail`, `navigation`, `twofactor`,
  `authorization`, `users`, `sections`, `activity_log`, `settings`,
  `localization`, `import_export`) plus `common.py` for the cross-feature leaf
  helpers (role/profile/scope/permission accessors, `_normalize_asset_url`,
  `_coerce_import_bool`). The inter-module import graph is an acyclic DAG;
  `__init__.py` re-exports all 140 names so every `from dlux.utils import X` and
  `dlux.utils.X` call site is unchanged. Code was extracted verbatim
  (AST-faithful), with dlux-level relative imports rewritten `.x` → `..x`. The
  original `dlux/utils.py` is kept intact on disk (inert; shadowed by the
  package) as a reference/rollback.
- **Constants Import Cleanup**: Removed stale imports of the deleted legacy
  home-url constant from the split `dlux/utils/` modules and localized the old
  `/sys/` compatibility sentinel in the remaining unconfigured-settings
  fallback checks and regression test.
- **Titlebar Text Clipping Fix**: Relaxed the titlebar title line-height and
  added a small vertical text buffer so Arabic lower dots and Latin descenders
  (`g`, `j`, etc.) are not clipped by the title row's overflow/truncation box;
  bumped the `titlebar.css` cache-buster.
- **Options Sidebar Density Visibility**: Hid the Options-page Sidebar Density
  card when the sidebar runtime surface is disabled, matching the existing
  context processor and setup-preview behavior that already suppress runtime
  sidebar density controls unless `sidebar.enabled` is true.

## v1.0.2

- **Rebrand Wizard Navigation Regression Fix**: Fixed the first-launch System
  Setup wizard step navigation, which silently broke during the
  `microsys`→`dlux` rebrand. The `data-ms-*` → `data-dl-*` kebab-case attribute
  rename was applied to templates and `querySelector` selectors but missed the
  matching camelCase `element.dataset.msX` reads (which a `data-ms-` find/replace
  cannot catch). `dataset.msWizardStepTarget` was reading the now-nonexistent
  `data-ms-wizard-step-target`, yielding `NaN`, so the step-nav bullets never
  highlighted (`is-active`/`is-complete`) and clicks never navigated. Renamed
  every stale read to its correct `dataset` form (shipped as `dataset.dluxX`
  after the prefix streamline below) across `helpers/wizard/js/main.js`,
  `main/js/system_setup.js`, `themes/js/main.js`, `users/js/user_report.js`,
  and `forms/js/filter_form.js`.
- **Related dataset-binding fixes (same root cause)**: `dluxWizardInitialStep`
  (wizard now returns to the correct step after a language-preview reload),
  `dluxPreviewThemeCss` (theme-preview `<link>` de-dupe guard now matches the
  attribute it writes, preventing duplicate stylesheet injection), and the User
  Report export base / window / page-size bindings (`dluxUserReport*`).
- **Full `microsys`/`ms` naming residue sweep**: Eliminated all remaining
  pre-rebrand identifiers so no `ms`/`micro` naming survives in runtime code.
  - **Translation system unified to `DLUX_STRINGS`**: the template/JS context
    variable (`MS_TRANS`/`__MS_TRANS`), the per-app catalog dict
    (`MS_TRANSLATIONS`), and the JS injection (`window.DLUX_STRINGS` via the
    `dlux-strings-data` `json_script`) now share one token. The discovery loader
    reads `DLUX_STRINGS` with an **inert fallback to legacy `MS_TRANSLATIONS`**,
    so apps not yet migrated keep loading; `dlux startapp` scaffolds emit
    `DLUX_STRINGS`. JS helper `window.ms_trans()` → `window.dluxString()`.
  - **`micro:` event bus → `dlux:`**: every custom event (`micro:record:*`,
    `micro:dynamic_modal:open`, `micro:subsection:*`, `micro:reset-password`,
    `micro:soft-delete`, `micro:view-*`, and `ms:wizard-step-change`) renamed to
    the `dlux:` namespace across Python producers and JS listeners; row-action
    attributes `data-micro-actions`/`data-micro-context` → `data-dlux-*`; element
    id `microContextMenu` and template `micro_context_menu.html` →
    `dluxContextMenu`/`dlux_context_menu.html`; `__micro*Initialized` guards →
    `__dlux*`. **Fixed a latent bug**: the context menu read an unset
    `window.MS_TRANS`, so its labels never localized — now reads `DLUX_STRINGS`.
  - **Template tags**: `ms_timesince`→`dlux_timesince`,
    `ms_querystring`/`ms_querystring_multi`→`dlux_querystring`/`dlux_querystring_multi`.
  - **Internal tokens/ids**: permission sentinels `__ms_*__`→`__dlux_*__`,
    session key `ms_force_language_preview`→`dlux_force_language_preview`, CSS
    class `ms-2fa-badge`→`dlux-2fa-badge`, ids `msOptionsGrid`/`msLanguageFontsEditor`/`msFontPreviews`→`dlux*`,
    internal dataset flags and JS globals → `dlux*`.
  - **DB index names**: `ms_ual_*` → `dlux_ual_*` in `models.py` and the initial
    migration (fresh installs only; in-place-migrated DBs keep the harmless
    physical `ms_ual_*` names — documented in the migration guide).
  - **Security standard `MSRP-1` → `DSRP-1`**: the acronym now matches its words
    (Dlux Secure Runtime Policy); `docs/security-msrp-1.md` →
    `docs/security-dsrp-1.md`, all docs/code references updated.
- **Prefix streamline — single `dlux` token across all surfaces**: Unified the
  pre-existing two-tier `dl-`/`dlux` convention onto one brand token. Renamed the
  entire markup/DOM vocabulary — **267 `.dlux-*` CSS classes**, **36
  `data-dlux-*` attributes** (+ their camelCase `dataset.dluxX` reads), **124
  `--dlux-*` CSS custom properties**, button classes (`dlux-btn-*`), component
  classes, and element ids — across every authored CSS, template, and JS file.
  Producer↔consumer pairs (CSS↔HTML↔JS selectors, Python-emitted attributes↔JS
  `dataset` reads) were renamed in lockstep and verified consistent; vendored
  Bootstrap/Chart.js/datepicker assets (`bs-*`) were left untouched.
- **Static cache-buster bump**: Bumped `?v=` to `20260612c` for every changed
  JS/CSS asset so browsers load the corrected scripts (`login.css`/`login.js`
  keep their always-fresh `{% now 'U' %}` busters).

## v1.0.1

- **SSO Companion Release Builds**: Fixed `release-sso.yml` and
  `release-sso-client.yml` to call each companion's `build.py` helper instead
  of `python -m build` from inside a directory containing a local `build.py`,
  preventing recursive self-invocation that caused GitHub Actions exit 143
  during `django-lux-sso` and `django-lux-sso-client` distribution builds. Each
  companion now owns a package-local `VERSION` file used by `__version__`,
  dynamic pyproject metadata, and the workflow tag guard.
- **DjangoLux Brand Logo**: Activated the SVG-first DjangoLux brand system with
  graphite shield/monogram source assets (`base_logo.svg`, `login_logo.svg`) by
  switching default `logo`, `login_logo`, and favicon URLs to the SVG assets,
  centering the separated `Django`/`Lux` login wordmark under the shield,
  refreshing the README hero image, and updating login/titlebar fallbacks plus
  the mobile login mask to avoid stale `django-microsys` WebP branding.

## v1.0.0

- **Rebrand from django-microsys**: First release under the `django-lux` name
  (import package `dlux`). Feature-equivalent to `django-microsys` 2.4.1 — the
  full system/runtime framework (first-launch setup wizard, user & security
  operations, four-tier staff authorization, multiple 2FA flows, scopes, audit
  logging, dynamic modal CRUD, reports/overview, and the encrypted full-system
  backup) carries over with identical behavior. The package imports as `dlux`,
  the Django app label and database tables use the `dlux_*` prefix, project
  configuration lives under `DLUX_CONFIG` (`from dlux.utils import
  dlux_settings`), the scaffolding CLI is `dlux` (`python -m dlux startproject`),
  and the system backup format is `.dlb` (`DLB1`, kind `dlux-system-backup`)
  with the standalone `tools/dlb-viewer` reader. The 545 internal `ms-` CSS
  classes were renamed to `dl-`; the optional SSO companions are
  `django-lux-sso` / `django-lux-sso-client` with OIDC claims `dlux_sso_role`
  and `dlux_sso_client_id`. Migrations are squashed to a fresh `0001_initial`.
- **In-place migration from django-microsys**: Added the
  `dlux_migrate_from_microsys` management command that converts an existing,
  fully-migrated `django-microsys` 2.4.1 database to `django-lux` without data
  loss — renames every `microsys_*` table to `dlux_*`, repoints
  `django_content_type` (so permissions follow automatically), collapses the
  recorded migration history to dlux's `0001_initial`, and rewrites
  app-label-qualified `UserActivityLog.model_key` values (`microsys.*` →
  `dlux.*`). Dry-run by default; pass `--yes` to apply. See
  [docs/migrating-from-microsys.md](docs/migrating-from-microsys.md).
