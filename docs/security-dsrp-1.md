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

- Pages hand their scripts only `CLIENT_CONFIG_KEYS` (`window.DLUX_CONFIG`: theme,
  fonts, password rules, inactivity timeout). The system configuration, with mail
  transport, lockout thresholds, backup and proxy settings, stays server-side for
  every visitor, signed in or not.
- The generic detail modal escapes stored values. Only markup DjangoLux builds
  itself (download links, boolean icons) is marked safe. A model's
  `extra_detail_fields` row with `is_html` renders unescaped, so its value is built
  with `format_html()`, never from raw input.
- XLSX exports (`fetch_excel()`, Export Entries, user reports) write strings as
  text cells through `append_text_safe_row()`, so a stored value, activity-log
  entry or user agent that starts with `=` never becomes a formula.
- Browser code that builds markup keeps data text. The section manager's View and
  blocked-Delete modals escape record names, field values and related rows;
  row-action labels and dynamic-modal errors are set as text; the login hero's
  markdown escapes quotes, so a link URL cannot leave its `href`. Superuser- and
  staff-editable values are escaped too: sidebar and navbar builder entries,
  language names in the translation matrix, the permissions tier preview (tier,
  scope name, badges, capabilities, warnings), and translated labels placed beside
  an icon or spinner. `dlux/tests/test_js_html_sinks.py` guards these scripts.
- Stored files follow the app's authorization (stack schema 4). The proxy asks `/sys/files/media-access/` before serving any `/media/` file outside the public folders, so a direct link to a registered document file reaches only users who may view the document, and backups, protected assets and file history are never served from `/media/`. Backups are recognised by the backup folder configured now (read per request), by the backup records' own paths and by the `.dlb` suffix, so a custom or changed backup folder stays private; the backup folder can't be a public one, and uploaded restore files get unguessable names. See [Stored files](deployment-configuration.md#stored-files-media).
- The generated proxy applies the Fetch Metadata resource isolation policy
  (`cross_site_request`): what another site's page makes a browser request in the
  background (images, scripts, `fetch()`, form posts, `<object>`/`<embed>`) gets a
  403 before it reaches the app. Links from other sites, same-site requests and
  clients without `Sec-Fetch-*` headers pass, and static files and public media
  stay open to other sites. `composer check` warns (`fetch-metadata`) when a
  stack's proxy lacks it. See
  [Cross-site requests](deployment-configuration.md#cross-site-requests-fetch-metadata).
- The internal SMTP relay verifies its provider before signing in: the
  certificate must chain to a system CA or to one in `SMTP_RELAY_CA_FILE` and name
  the host dialled, over SSL and STARTTLS. A failure stops the delivery before any
  credential is sent and reports step `tls`, reason `certificate`. Turning the
  check off is a deliberate setting (`SMTP_RELAY_TLS_VERIFY=False`, or the Email
  step's switch, which a POST can clear only together with the marker the step
  renders beside it), and the relay logs a warning on every delivery made without
  it. See [Provider certificate](deployment-configuration.md#provider-certificate).
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
- Shared modal/runtime helper scripts are shipped as external static assets.
  Scripts that arrive in modal markup run under the page's nonce only when they
  carry the nonce of the response that delivered them (see
  [Content Security Policy](#content-security-policy)).
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
- User Reports are sensitive audit surfaces. The full report (devices, IP
  addresses, user agents, sessions, e-mail) must remain backend-gated by
  user-directory access, target-management access, and activity-log access.
  A General Reports viewer (`dlux.view_reports`) gets only the *activity* view
  of a user the reports page lists to them (`user_report_access()` →
  `activity`): identity basics and report-eligible actions within their report
  scope; the sensitive sections are never queried for that view.
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

## Content Security Policy

Generated projects send this policy from `config/settings.py` (django-csp):

| Directive | Sources |
| --- | --- |
| `script-src` | `'self'`, the request's nonce (`[SELF, NONCE]`) |
| `style-src` | `'self'`, `'unsafe-inline'` |
| `default-src`, `frame-ancestors`, `form-action`, `base-uri` | `'self'` |
| `object-src` | `'none'` |
| `img-src` | `'self'`, `data:`, `blob:` |
| `font-src` | `'self'`, `data:` |
| `connect-src` | `'self'`, `BASE_URL`, the ScanLink tray origins |

`base-uri 'self'` keeps injected markup from adding a `<base>` element that would
repoint the page's relative script URLs, and `object-src 'none'` refuses plugin
content outright instead of leaving it to `default-src`.

Scripts run only from the site or inline with `nonce="{{ request.csp_nonce }}"`.
There is no `'unsafe-inline'` or `'unsafe-eval'` in `script-src`, so markup injected
into a page cannot run script, and neither can an inline `on…=` handler or a
`javascript:` URL. DjangoLux needs neither source: its templates have no inline
scripts, its JavaScript never calls `eval`, `new Function` or string timers, and
PDF.js runs with `isEvalSupported: false`. Scripts it adds at run time (asset
bundles, the strings script) carry the page's nonce.

The dynamic modal runs the scripts in the markup it fetches. A script that carries
the nonce of the response it came in runs with the page's nonce; any other inline
script keeps its own nonce and is blocked. Markup that a stored value smuggles
into a modal therefore cannot borrow the page's nonce.

A project's own pages follow the same rules: move inline script to a static file or
give it the nonce, replace `onclick=`/`onsubmit=` handlers with listeners in a
script, and pass data through `json_script` or `data-*` attributes. A print window
opened with `window.open('')` inherits the page's policy, so a `<script>` written
into it needs the nonce too.

An existing project keeps the policy its own settings hold; DjangoLux never
rewrites them. While that policy lets scripts run without a nonce, system check
`dlux.W201` warns and names the setting:
`CONTENT_SECURITY_POLICY["DIRECTIVES"]["script-src"]` (or `default-src` when there
is no `script-src`, or django-csp 3.x's `CSP_SCRIPT_SRC`) allows `'unsafe-inline'`
or `'unsafe-eval'`. It becomes an error in v1.20.0
([Deprecation countdown](deprecation-countdown.md#unsafe-inline-and-unsafe-eval-in-a-projects-script-src)). To clear it, fix the project's inline scripts and handlers as
above, then set:

```python
from csp.constants import NONCE, SELF, UNSAFE_INLINE

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        # ...
        "script-src": [SELF, NONCE],
    }
}
```

A project that has to keep an extra script host (a CDN) lists it beside
`SELF, NONCE`. One that still depends on `'unsafe-eval'` can silence the warning
with `SILENCED_SYSTEM_CHECKS = ["dlux.W201"]` and remove that line once the
dependency is gone.

## Inline Updater Boundary

- Inline updates default off outside recognized generated Compose deployments.
- The updater has no Docker socket and publishes no ports. Only its dedicated
  egress bridge can reach PyPI; database/Redis access stays on the internal
  network. Web and nginx mount `dlux_runtime` read-only; `worker` is the only
  DjangoLux service that mounts it read-write.
- Composer's agent discovers and downloads releases, with redirects allowlisted
  to official PyPI hosts, and accepts a wheel only after SHA-256 and PyPI
  attestation verification for `debeski/django-lux` plus
  `.github/workflows/release.yml`; the integrity API's canonical workflow field
  is the basename `release.yml`. `web` and `worker` never fetch a wheel.
- The active pointer is an atomic JSON file; version strings and release paths
  are normalized and constrained below the persistent runtime root.
- The direct web version probe is authenticated with an HMAC derived from the
  deployment `SECRET_KEY`; external requests without the updater probe fail as
  not found.
- Composer stages wheels only into isolated version directories, without their
  dependencies; the baked Python environment is never mutated. Candidate
  subprocesses execute before maintenance and pointer switching.
- Reconcile never downloads or installs a release. A missing or unreadable
  active pointer is rewritten only to the recorded release when it is still
  staged inside `releases/`, is newer than the baked image, and its
  `dlux/release-manifest.json` names its directory's version; anything else
  reverts to the baked image.
- Release summaries render as escaped text. Updater logs are bounded, NUL-free,
  and redact password/secret/token/authorization-shaped values.
- Automatic recovery restores code/static state only. It never automatically
  restores the database; inline-safe migrations must stay backward compatible,
  and the completed pre-operation `.dlb` backup remains a manual recovery tool.

## Rate Limiting & Session Controls

All brute-force and timeout controls are dependency-free (Django cache + session).
Operator-editable System Settings own the normal policy; static deployment
settings provide the controls that are not database-backed and the documented
fallbacks when runtime configuration cannot be resolved.

- **Failed-login lockout.** Repeated failed password attempts are throttled per
  client IP and per attempted username via the cache (`login_throttle.py`). After
  the resolved `login_lockout_threshold` failures (default 5), the identifier is
  locked for `login_lockout_duration_minutes` (default 15); failures count within
  `login_lockout_window_minutes` (default 15). A successful login clears the
  counters. The locked POST is rejected with HTTP 429 before authentication runs,
  and `login_lockout_enabled` gates the policy (default on).
  `DLUX_LOGIN_LOCKOUT_MAX_ATTEMPTS` and `DLUX_LOGIN_LOCKOUT_SECONDS` are legacy
  fallbacks used only when resolved System Settings cannot be read.
- **Public form limits.** Anonymous public forms (reviews, complaints, contact
  forms) limit their POSTs with `dlux.utils.ratelimit`, per client address and in
  total for each form, over fixed windows:
  `@public_form_limit(bucket, per_address=5, total=300, window=3600)` by default.
  A POST counts against its sender first, and only a POST inside its sender's
  limit counts toward the total, so one sender cannot spend the budget every other
  sender shares. The address comes from the centralized client-IP resolution, and
  IPv6 addresses count per /64. Cache keys hold a `SECRET_KEY`-keyed HMAC of the
  address, never the address, and expire a few seconds after their window ends,
  so a request that read the window just before it ended still counts against
  it. Log lines name the form, not the sender. A refused POST gets HTTP 429 with
  `Retry-After` and the
  translated `msg_public_form_rate_limited` message (JSON for script requests), or
  the response of the view's own `on_limited` handler. `DLUX_PUBLIC_FORM_LIMITS`
  overrides a form's limits per deployment. Windows are aligned to the clock, so a
  sender can fit up to twice its limit around a window boundary. Exact counts under
  concurrency need a cache with an atomic `incr` (Redis in generated stacks). A
  cache that cannot be reached lets the POST through and logs the error.
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
- **Password-change session revocation.** While multiple active sessions are
  allowed, the authenticated user's profile password form can retain its newly
  rotated current session and revoke every other recorded session. The control is
  omitted and server-side ignored when `prevent_multiple_active_sessions` is on;
  trusted-device records remain independent of session revocation.

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
