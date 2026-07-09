# DSRP-1 Security Standard

DSRP-1, the Dlux Secure Runtime Policy, is the active security contract for
runtime-exposed Dlux surfaces. It exists so visual affordances, direct URL
access, AJAX endpoints, and state-changing flows all agree on the same backend
authorization decision.

## Core Rules

- UI visibility is never the only control. Every protected route or action must
  enforce the matching backend authorization rule.
- Direct URL access, sidebar discovery/rendering, dashboard shortcuts, user-hub
  shortcuts, modal CRUD, context actions, diagnostics, setup/security flows, and
  2FA mutators must use the same permission intent.
- Prefer shared helpers and internal permission tokens resolved by
  `user_matches_permission_token()` over ad hoc `is_staff` checks.
- State-changing security flows must be POST-only unless the endpoint is
  explicitly read-only.
- Runtime HTML must not rely on inline CSS, inline `style=` attributes, or
  executable inline JavaScript unless there is a documented unavoidable need.
  Prefer dedicated static assets plus `json_script` or `data-*` bridges so CSP
  can stay strict and consistent across Dlux surfaces.
- Diagnostics and system-wide configuration surfaces are privileged-only, while
  authenticated users may retain their own personal preference controls.
- Sensitive stored security material must be hashed or externally protected
  where practical; Dlux backup codes are hashed at rest.
- All user-facing UI strings must be resolved through the Dlux translation framework. Hardcoded English or Arabic literals are prohibited in Python, templates, and JavaScript to ensure consistent localization and prevent information leakage via untranslated internal labels.

## Applied Dlux Measures

- Dynamic modal manager/delete views enforce backend authorization for model,
  user, and profile surfaces.
- Table row context-menu actions are permission-filtered server-side
  (`filter_context_actions`): each action declares its required permission and is
  omitted from the emitted `data-dlux-actions` JSON when the user lacks it, so the
  **Delete** entry only appears for holders of `delete_<model>` (matching the
  delete view's own 403 gate). The `manage_sections` override applies only to
  actions explicitly flagged `section_action` and never bypasses per-model
  delete/change permissions on generic data grids. `delete_<model>` permissions
  are assignable from the grouped permission UI so deletion can be delegated;
  sensitive `auth`/internal-`dlux` deletes stay non-assignable.
- Shared modal/runtime helper scripts are shipped as external static assets, and
  the dynamic-modal loader now carries the request CSP nonce so strict
  `script-src` policies do not force a fallback to inline behavior.
- User directory, user detail, reset-password, activity-log, section-management,
  dashboard, user-hub, and sidebar surfaces use helper-backed authorization.
- Built-in system sidebar entries use internal permission tokens:
  `__dlux_user_directory__`, `__dlux_activity_log__`, `__dlux_sections_view__`,
  `__dlux_sections_manage__`, and `__dlux_authenticated__`.
- Staff management follows the documented Superuser, Global Staff, Central Staff,
  and Scoped Staff tiers.
- 2FA enable/setup/disable/resend/backup-code mutators are POST-only and backup
  codes are hashed. Email OTPs are generated with `secrets` and stored hashed in
  cache with short TTL and attempt limits. Email OTPs can be automatically
  delivered on login to reduce challenge friction.
- Profile session revocation is POST-only and restricted to sessions belonging
  to the current authenticated user. "Trusted" status can be applied to a session
  for 30 days to bypass 2FA challenges on the same browser, and untrusted
  sessions cannot revoke trusted sessions. When configured, a newly trusted
  session can revoke every other active session for that user.
- User Reports are sensitive audit surfaces. They must remain backend-gated by
  user-directory access, target-management access, and activity-log access.
  Durable non-auth device grouping uses a signed first-party cookie stored only
  as a hash and must not be treated as authentication or trusted-device proof.
- Client IP resolution is centralized and configurable (direct, header, or
  proxy-aware) to ensure security logs and throttles remain accurate across
  varied deployment environments.
- Public registration is disabled by default, SMTP-gated, email-verified before
  activation, protected by cache throttles plus a honeypot, and uses hashed
  verification tokens only.
- Public registration approval/rejection is superuser-only and POST-only.
- Options diagnostics are restricted to superusers and Global Staff; ordinary
  authenticated users keep personal preference controls and receive no
  diagnostic context values.
- All new security surfaces (2FA, Trusted Devices, IP resolution) strictly
  follow the translation-first policy, utilizing the Dlux translation
  framework for all user-facing copy and challenge messages.
- Inline updater state is readable only to superusers/Global Staff; check/apply/
  rollback mutations are superuser-only CSRF-protected POSTs, and apply/rollback
  also require the existing current-password guard and emit audit events.

## Inline Updater Boundary

- Inline updates default off outside recognized generated Compose deployments.
- The updater has no Docker socket and publishes no ports. Only its dedicated
  egress bridge can reach PyPI; database/Redis access stays on the internal
  network. Web, Celery, and nginx mount `dlux_runtime` read-only.
- Discovery and redirects are allowlisted to official PyPI hosts. A wheel is
  accepted only after SHA-256 and PyPI attestation verification for
  `debeski/django-lux` plus `.github/workflows/release.yml`; the integrity API's
  canonical workflow field is the basename `release.yml`.
- The active pointer is an atomic JSON file; version strings and release paths
  are normalized and constrained below the persistent runtime root.
- The direct web version probe is authenticated with an HMAC derived from the
  deployment `SECRET_KEY`; external requests without the updater probe fail as
  not found.
- Wheels install only into isolated version directories using `--no-deps`; the
  baked Python environment is never mutated. Candidate subprocesses execute
  before maintenance and pointer switching.
- Release summaries render as escaped text. Updater logs are bounded, NUL-free,
  and redact password/secret/token/authorization-shaped values.
- Automatic recovery restores code/static state only. It never automatically
  restores the database; inline-safe migrations must stay backward compatible,
  and the completed pre-operation `.dlb` backup remains a manual recovery tool.

## Rate Limiting & Session Controls

All brute-force and timeout controls are dependency-free (Django cache + session)
and resolve their thresholds from settings, defaulting to secure values.

- **Failed-login lockout.** Repeated failed password attempts are throttled per
  client IP and per attempted username via the cache (`login_throttle.py`). After
  `DLUX_LOGIN_LOCKOUT_MAX_ATTEMPTS` failures (default 5) the identifier is locked
  for `DLUX_LOGIN_LOCKOUT_SECONDS` (default 900s); a successful login clears the
  counters. The locked POST is rejected with HTTP 429 before authentication runs.
  Gated by the `login_lockout_enabled` SystemSettings toggle (default on).
- **2FA completion window.** The pre-2FA challenge carries a server timestamp and
  is abandoned after `DLUX_2FA_CHALLENGE_WINDOW_SECONDS` (default 300s), so a
  half-finished challenge cannot persist for the whole session lifetime. This is
  in addition to the existing 5-minute email-code expiry, 3-attempt per-code
  lockout, per-IP 2FA send/verify limits, and resend cooldowns.
- **Idle + absolute session timeouts.** `DluxMiddleware` enforces optional
  sliding-idle (`DLUX_SESSION_IDLE_TIMEOUT_SECONDS`) and hard absolute
  (`DLUX_SESSION_ABSOLUTE_TIMEOUT_SECONDS`) windows beyond Django's
  `SESSION_COOKIE_AGE`; both default to `0` (disabled — opt-in per deployment
  policy). On expiry the user is logged out and routed to the session-ended
  interstitial with an `idle_timeout` / `session_timeout` reason. Timestamps are
  middleware-managed on the session; the idle clock write is throttled to ~30s.

## Public Registration Boundary

Public registration creates local Dlux users only. It does not add
client-originated SSO registration APIs and does not alter optional SSO provider
or client packages.

The first v1 policy is intentionally narrow:

- The deployer must explicitly enable `public_registration_enabled`.
- Email delivery must be ready through the selected delivery path (`direct` or
  generated Docker `relay`) and selected secret storage (`env` or
  `encrypted_db`). Export/import redacts secrets and requires re-entry after
  import.
- Public signup creates an inactive user first.
- Email verification is mandatory before activation or approval.
- `auto_login_after_verify` activates and signs in the verified local user.
- `verified_pending_approval` keeps the user inactive until a superuser POSTs an
  approval.
- Duplicate, throttled, and honeypot submissions use generic responses and must
  not disclose account existence.
- Bulk password-change enforcement is an admin-panel command, not a setting. The
  `/sys/admin/force-password-change-all/` POST endpoint is superuser-only,
  requires the acting user's current password, skips all superusers, and reuses
  the existing `Profile.preferences["force_password_change"]` marker enforced by
  `DluxMiddleware`.
- Default public-registration scope/group assignment is owned by the Scopes and
  Groups managers, not by System Settings. Scope default changes are superuser
  POSTs; Group preset default changes require `dlux.manage_groups` plus the
  normal preset-management scope gate. Activation applies live `auth.Group`
  memberships after verification/approval and never uses the admin-created-user
  first-login password-change checkbox.

## Optional SSO Extensions

SSO is optional and must remain additive. The provider plugin and client SDK do
not change core `dlux` runtime imports, URLs, middleware, or login behavior
unless the host project explicitly installs and mounts them.

Cross-platform OIDC compatibility is a first-priority SSO requirement. The
provider contract must be usable by non-Django clients through standard OIDC
discovery, Authorization Code flow, JWKS validation, standard identity claims,
and portable role claims.

Provider packages must:

- fail closed when a client policy, redirect URI, user membership, or role is
  missing or inactive;
- issue portable per-client roles only: `admin`, `staff`, or `user`;
- avoid exporting project-generated Django permissions to connected clients;
- use exact redirect URI registration and HTTPS outside explicitly allowed local
  development callbacks;
- keep token/session revocation and audit trails backend-enforced.

Client packages must:

- link local users by stable `(issuer, subject)` identity, not mutable email;
- auto-create users only when the provider grants an allowed role;
- never map provider `admin` to Django `is_superuser`;
- set `is_staff` only when the host project explicitly maps roles to staff
  access.
