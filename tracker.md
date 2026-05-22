# Project Tracker (django-microsys)

## Part 1: Project Related
### Current Verified Snapshot:
- Verified through `2026-05-22`: local package version markers are on `v2.2.3` and current edits remain focused on runtime bug-fix batches.
- System setup/System Settings uses a six-step wizard. Step 2 owns language catalog, system names, default language, language override policy, and the translation matrix. Step 6 owns themes, fonts, and table density.
- Dynamic Font Management is active:
  - font registry lives in `microsys/fonts.py`,
  - `SystemSettings` stores `allowed_fonts`, language-keyed `default_fonts`, and `allow_user_font_override`,
  - Options uses the shared selector markup and `--ms-main-font`.
- Runtime theme allowlisting remains enforced by context and the preferences API. `2026-05-22` setup preview work adds a setup-only path that can load a disabled theme stylesheet for preview without widening runtime preference acceptance.
- Explicit `setTheme(...)` changes now run through a short veil fade around the class swap; reduced-motion and Microsys `no-animations` skip the fade, and sidebar item/icon transitions pause under that veil so they resolve with the same swap.
- Neon theme no longer applies its generic `.option-section` overlay/stacking treatment to Options cards; `.ms-options-panel` stays on the dedicated Options styling path instead of inheriting the redundant glow overlay layer.
- Options System Info now renders backend server time from a dedicated preformatted display key, avoiding generic `current_time` collisions and preserving explicit seconds.
- Collapsed Icons Only sidebar now removes redundant folder-button/label `flex-grow-1` classes, zeroes hidden label flex space, and applies a dedicated collapsed folder-row centering path so parent/folder accordion icons remain centered and labels vanish immediately.
- Shared enabled `.form-switch` controls now expose a pointer cursor; Options reorder handles use enabled-handle cursor selectors specific enough to keep both button surface and grip icon on grab/grabbing over Bootstrap's enabled-button pointer rule.
- Profile confirm-password modals submit the same confirmation path from Enter, keep password-protected Profile actions open through their JSON password check, and render current-password errors inline while the input is corrected.
- Profile activity grouping treats virtual session-revoke logs as System Interactions.
- System Settings single-step modal POSTs preserve omitted Step 6 values server-side. Step resolver accepts modal wizard steps `0..5`.
- Current translation contract from code, docs, and `dhub` runtime inspection:
  - app-local sources are installed app `translations.py` modules exposing `MS_TRANSLATIONS`,
  - Step 2 matrix is meant to group Microsys, installed app, project-config, and settings-only override keys,
  - `dhub-web-1` still has `/app/req.txt` pinned to `django-microsys==2.2.2`, but the live web container inspected on `2026-05-22` bind-mounts this workspace's `microsys/` package into `/app/microsys`.

### Current Project Adopted Standards:
- Preferred settings integration:
  - `from microsys.utils import microsys_settings`
  - `microsys_settings(globals())`
- Preferred scaffolding:
  - `python -m microsys startproject <project_name> [destination]`
  - `python -m microsys startapp <app_name> [--register]`
- Preferred page entrypoints:
  - `microsys/form_base.html`
  - `microsys/list_base.html`
- Preferred helper APIs:
  - `require_current_password(request)`
  - `build_archive_file_field('<field_name>')`
  - `build_settings_toggle_field(form, '<field_name>', css_class='...')`
  - `set_profile_totp_state(profile, raw_secret=..., enabled=...)`
- Active standards:
  - MSRP-1 is the runtime authorization standard; source is `docs/security-msrp-1.md`.
  - Optional SSO is additive-only under `optional_packages/`.
  - Public registration is core, additive, and email-gated.

### Adopted Standards' rules and policies:
- Backend authorization must match protected UI visibility; hidden controls are not authorization.
- Keep Microsys defaults framework-neutral unless behavior is an explicit framework contract.
- Prefer additive helpers, templates, and extension points over project-rewriting behavior.
- Do not use `settings.configure()` as a host-project installation path.
- Do not rely on app-order template shadowing for critical behavior when an explicit helper or template path exists.
- For setup/System Settings:
  - use `build_archive_file_field(...)` for Microsys archive/file widgets,
  - use `build_settings_toggle_field(...)` for shared toggle-card booleans,
  - mirror UI gating in backend validation/normalization.
- Do not add inline CSS or executable inline JS to templates unless unavoidable; prefer static assets, `json_script`, and `data-*`.
- All new or revised user-facing copy must use Microsys translations, not local English/Arabic literals or new template `|default:"..."` fallbacks.
- Generated/scaffolded URL entrypoints must enforce login and the relevant permission on the backend.
- Published distributions should exclude `microsys.tests`, Python caches, and compiled Python artifacts unless a release explicitly needs them.

### Cross-Cutting Audits if any:
- Prior verified audits cover CSP-oriented template cleanup, setup toggle consistency, permissions UI filtering, modal JSON error tolerance, staff-tier surface restoration, and packaged-distribution exclusions.
- Browser/manual audit coverage is still incomplete for mounted-app setup flows, Options selector behavior, sidebar/titlebar runtime behavior, and POST-only 2FA flows.

### Current Project's Unsolved Known Bugs:
- Live confirmation is pending after the `2026-05-22` Step 2 matrix source fix. The `dhub` container reproduced a Microsys-only matrix with discovered `portfolio` and `documents` sources under installed Microsys `2.2.2`; local merge isolation now keeps app keys out of the core source claim path.
- Live confirmation is pending after the `2026-05-22` Options font asset cache-bust. Local `options.js` already marks a clicked `[data-font]` selector `is-active` immediately; the reported missing highlight is production-only.
- Live confirmation is pending after the `2026-05-22` setup-only disabled-theme preview path for Step 6.
- Live confirmation is pending for the `2026-05-22` sidebar-item theme-switch follow-up; the veil fade was accepted, but sidebar item transitions still looked choppy until they were paused under the veil.
- User confirmed on `2026-05-22` that the neon Options reorder fix is working after removing redundant neon `.option-section` overlay/stacking selectors from `.ms-options-panel`.
- Verified in restarted `dhub-web-1` on `2026-05-22`: Options System Info rendered backend server time with seconds (`2026-05-22 17:58:56`) after the web worker reloaded the bind-mounted dedicated display-key change. Date-only HTML seen immediately before restart came from the older running worker state.
- Live confirmation is still pending after the refined `2026-05-22` Step 4 Icons Only sidebar fix; CSS label collapse alone was not sufficient, so folder accordion templates now also drop redundant Bootstrap `flex-grow-1` classes and collapsed folder rows force instant label suppression plus centered icon/header alignment.
- First-launch System Setup has a runtime mismatch between the sidebar-toolbar removal warning and Options modal behavior.
- Live Options -> System Settings Step 3 modal save has returned HTTP 400 in the user's mounted app while local full modal POST reproductions return 200; use AJAX JSON error/class or live server logs next.
- Browser/runtime confirmation remains pending in the mounted app after the Step 2 relay/env readiness fix.
- `microsys/fetcher.py` fallback download/export redirects still trust raw `HTTP_REFERER`.
- User confirmed on `2026-05-22` that the shared toggle pointer cursor and Profile confirm-password Enter submit fixes work.
- Live confirmation is pending for the `2026-05-22` Options reorder handle cursor follow-up after the grip icon changed but Bootstrap's enabled-button pointer cursor still won on the surrounding button surface.
- After `dhub-web-1` restarted at `2026-05-22T18:13:02Z`, a profile-context check on its current admin activity grouped the newest `DELETE session` row under System Interactions; the user's immediately prior browser test hit Gunicorn workers started before that Python classifier change was loaded.
- Live confirmation is pending after the Profile confirm-password inline-validation follow-up: disable-2FA, backup-code generation, and session revoke now keep wrong-password JSON errors inside the modal instead of relying on page messages.
- User-reported runtime backlog not handled in the current batch:
  - re-enabling a previously disabled sidebar drops child toggle state and can force Hide Completely collapse mode.

### Incomplete Tasks:
- Tasks:
  - Priority 1:
    - [ ] Re-check Step 2 app source tabs after the fixed local code/package reaches `dhub`.
    - [ ] Browser-check the `2026-05-22` Options font highlight and Step 6 disabled-theme preview fixes in production/mounted app.
    - [ ] Browser-check sidebar item repaint after pausing sidebar transitions under the accepted theme-switch fade.
    - [ ] Browser-check reduced-motion/no-animation bypass for the theme switch fade.
    - [ ] Browser-check Step 4 Icons Only collapsed sidebar after zeroing hidden folder-label flex space for centered parent/folder icons.
    - [ ] Browser-check the Options reorder handle button surface after the enabled-handle cursor specificity fix.
    - [ ] Browser re-check Profile User Activity after the `dhub-web-1` restart so the virtual `session` entry stays under System Interactions.
    - [ ] Browser-check inline wrong-password feedback in Profile confirm-password modals for disable-2FA, backup codes, and session revoke.
    - [ ] Harden `microsys/fetcher.py` fallback redirects for missing, local, and forged external referers.
    - [ ] Capture the live Step 3 System Settings modal HTTP 400 JSON/log details if it still reproduces.
  - Priority 1 browser validation:
    - [ ] Setup/System Settings wizard navigation, language catalog, translation matrix, allowed themes/fonts, sidebar, titlebar, and email readiness.
    - [ ] Options card order persistence, System Info placement, autofill/reset, selector widgets, and theme persistence.
    - [ ] Pre-setup mounted-project guard for anonymous, superuser, and non-superuser requests.
    - [ ] POST-only 2FA setup, verify, resend, disable, backup-code, and trusted-device/session UX.
    - [ ] Staff-tier create/edit/profile/detail/manage-table surfaces and user-hub mobile toolbar wrap.
  - Priority 2:
    - [ ] Run generated-project validation for `python -m microsys startproject`.
    - [ ] Run generated-app validation for `python -m microsys startapp --register`.
    - [ ] Validate generated Docker/Celery/health-check baseline in a live boot.
    - [ ] Validate optional provider/client OIDC after installing their dependencies.
    - [ ] Keep unrelated nested settings/import-export/password/force-2FA refactor as a separate planned batch.
  - Completed Recently:
    - [x] Added setup-only preview support for a Step 6 theme that was disabled when the page loaded.
    - [x] Smoothed explicit theme changes with a short switch veil fade instead of broad element transitions.
    - [x] Paused sidebar item/icon transition repaint while the theme-switch veil is active after the user isolated remaining choppiness to sidebar items.
    - [x] Removed redundant neon `.option-section` overlay/stacking selectors from Options cards by excluding `.ms-options-panel`.
    - [x] User confirmed the neon-theme Options card reorder issue is fixed.
    - [x] Switched Options System Info backend server time to a dedicated preformatted display key so project/global `current_time` collisions cannot collapse it back to a date-only value.
    - [x] Restarted `dhub-web-1` and verified its Django Options render now emits backend server time with seconds.
    - [x] Zeroed collapsed folder-label flex space so Step 4 Icons Only parent/folder accordion icons stay centered.
    - [x] Removed redundant folder-button/label `flex-grow-1` classes from sidebar accordion templates after the user confirmed the parent item was still pushed sideways when collapsed.
    - [x] Added a dedicated collapsed folder-row centering path so parent labels do not linger and the folder icon does not hug the wall during sidebar collapse.
    - [x] Added shared enabled switch pointer cursor behavior and raised Options reorder handle cursor specificity above Bootstrap's enabled-button pointer rule.
    - [x] Routed Enter in the Profile confirm-password input through the existing confirm modal action without stacking key handlers.
    - [x] Kept Profile confirm-password modals open through JSON password checks so wrong passwords render inline and clear while corrected.
    - [x] Added AJAX session-revoke success/error responses for the modal path while preserving non-AJAX message fallback.
    - [x] Classified virtual Profile session-revoke activity logs as System Interactions while leaving mounted-app logs under Recent Activity.
    - [x] Bumped the production `options.js` asset key for the existing immediate Options font `is-active` update path.
    - [x] Reproduced the Step 2 matrix source collapse in `dhub` and isolated app translation merges from `MICROSYS_STRINGS` so app source tabs remain claimable.
    - [x] Fixed Step 2 relay/env email readiness detection for scaffolded `SMTP_RELAY_*` plus `DEFAULT_FROM_EMAIL`.
    - [x] Preserved omitted Step 6 values on single-step System Settings modal saves and fixed modal step `5` resolution.

### One-line info about last verified Tests:
- `2026-05-22`: focused `DiscoverRunner` checks passed for Profile confirm-password inline JSON hook coverage, AJAX session-revoke password error/redirect responses, shared switch/Options cursor assets, and virtual session activity grouping; focused compileall and `git diff --check` passed. Restarted `dhub-web-1` after the latest Profile view change.

### One-line info about last time edited Docs:
- `2026-05-16`: main README/docs batch covered Trusted Devices, Client IP Resolution, advanced 2FA UX, Dynamic Font Management, and the Step 5/6 wizard split; no docs changed on `2026-05-22`.

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- Reusable helper APIs:
  - `require_current_password(request)`
  - `build_archive_file_field('<field_name>')`
  - `build_settings_toggle_field(form, '<field_name>', css_class='...')`
  - `set_profile_totp_state(profile, raw_secret=..., enabled=...)`
- Common validation commands:
  - Focused defaults/render suite: `./.venv/bin/python -c "import microsys.tests.test_defaults_and_urls; import django; from django.test.runner import DiscoverRunner; django.setup(); raise SystemExit(bool(DiscoverRunner(verbosity=1).run_tests(['microsys.tests.test_defaults_and_urls'])))"`
  - Focused modal/view suites: import target test modules before `django.setup()`, then run targeted labels through `DiscoverRunner`.
  - Full compile check without repo pycache churn: `PYTHONPYCACHEPREFIX=/tmp/microsys-pycache ./.venv/bin/python -m compileall microsys`
  - Packaging check: build wheel/sdist, then inspect for `microsys/tests`, `__pycache__`, `.pyc`, and `.pyo`.
- Known environment note: `node` is not available locally, so `node --check` is not a current JS validation path.

### Global Rulesets:
- Prefer explicit reusable helpers over template shadowing or duplicated inline HTML.
- When a UI issue differs between modal/runtime/setup surfaces, verify the actual load/bind/runtime path before adding sync code.
- Keep tracker entries grounded in verified code, verified runtime behavior, or explicit user instruction.
- Do not convert user complaints into fixed tracker notes until the real runtime path is verified.
- Leave unrelated worktree changes untouched.
- For translation bugs, check the app-local `translations.py` contract and translation discovery layer before adding hardcoded copy.
- When implementing a big change, identify three real-life break scenarios and provide fixes/workarounds.

### Agent Handoff Rules:
- Re-read this tracker at the start of every turn and update it after meaningful state, task, bug, test, docs, or handoff changes.
- User correction: their target app mounts this repo, so do not assume they are running only the packaged PyPI release when local checkout is active.
- `dhub-web-1` inspected on `2026-05-22` still has `/app/req.txt` pinned to `django-microsys==2.2.2`, but it currently bind-mounts this workspace's `microsys/` directory into `/app/microsys`; restart the web worker after local Python/template changes before judging the live render.
- User correction for current runtime bug batch: stay on the bug-fix path, keep impact minimal, and ask or research when evidence is insufficient.
- User correction for Options reorder cursor: the first cursor patch reached the grip icon only; Bootstrap still kept pointer on the surrounding enabled handle button until the handle selector specificity was raised.
- User correction for Profile activity grouping: the `2026-05-22` browser retest after session revoke still showed the row under Recent Activity before `dhub-web-1` reloaded the bind-mounted Python view.
- User correction for Profile confirm-password modals: wrong-password feedback should stay in the live modal flow instead of falling back to stale page-level Django messages.
- User correction for theme animation: the veil fade is desired; remaining theme-switch choppiness was observed only in sidebar items.
- User correction for the current Options bug batch: the Server Time issue is specifically date-only output with no hour/minutes; neon-theme Options reorder is confirmed fixed.
- User correction on `2026-05-22`: even after the first local `current_time|date:"Y-m-d H:i:s"` patch, runtime still rendered only `2026-05-22`; avoid assuming the generic `current_time` key is safe in mounted projects.
- If setup default-language preview refreshes direction but not server-rendered text, inspect `microsys/static/microsys/main/js/system_setup.js` and `microsys/static/microsys/language/js/main.js`; reload preview must persist form state without restoring stale wizard step.
- If first-launch later steps look empty, inspect shared wizard `d-none` handling before changing form markup.
- If shared setup toggle layout regresses, inspect `build_settings_toggle_field(...)` plus `system_setup.css` before replacing the renderer.
- Keep Step 3 email TLS/SSL on the dedicated email-toggle path unless intentionally retired and browser-verified.
- If permission group noise returns, inspect `get_assignable_permissions_queryset()` and `GroupedPermissionWidget.get_context()` before changing templates.
- Preserve explicit user corrections in future tracker updates.

### References and Links:
- Key project files:
  - `microsys/forms.py`
  - `microsys/translations.py`
  - `microsys/utils.py`
  - `microsys/context_processors.py`
  - `microsys/static/microsys/main/js/system_setup.js`
  - `microsys/static/microsys/themes/js/main.js`
  - `microsys/templates/microsys/base.html`
  - `microsys/tests/test_defaults_and_urls.py`
- Translation docs currently state the app-source matrix contract:
  - `docs/admin-guide.md`
  - `docs/customization-guide.md`
- Optional SSO references:
  - `optional_packages/django-microsys-sso/microsys_sso`
  - `optional_packages/django-microsys-sso-client/microsys_sso_client`
