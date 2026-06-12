# MSRP-1 Security Standard

MSRP-1, the Dlux Secure Runtime Policy, is the active security contract for
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
- Shared modal/runtime helper scripts are shipped as external static assets, and
  the dynamic-modal loader now carries the request CSP nonce so strict
  `script-src` policies do not force a fallback to inline behavior.
- User directory, user detail, reset-password, activity-log, section-management,
  dashboard, user-hub, and sidebar surfaces use helper-backed authorization.
- Built-in system sidebar entries use internal permission tokens:
  `__ms_user_directory__`, `__ms_activity_log__`, `__ms_sections_view__`,
  `__ms_sections_manage__`, and `__ms_authenticated__`.
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
