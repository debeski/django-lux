# MSRP-1 Security Analysis Report

**Project**: django-microsys  
**Version**: 2.0.3 (2.1.0 pending)  
**Analysis Date**: 2026-05-01  
**Last Updated**: 2026-05-02  
**Standard**: MSRP-1 (Microsys Secure Runtime Policy)

## Executive Summary

This report analyzes the django-microsys framework against the MSRP-1 security standard. The framework implements a multi-tier authorization system with Superuser, Global Staff, Central Staff, and Scoped Staff tiers. Significant security hardening has been applied (MSRP-1 Phase 1 complete), and the three highest-risk open issues from the 2026-05-01 review have now been remediated.

**Overall Risk Level**: MEDIUM  
**Critical Issues**: 0 open  
**High Issues**: 0 open  
**Medium Issues**: 1 open  
**Low/Info**: 3

### 2026-05-02 Remediation Update

The highest-risk items were addressed in code:

- Scaffolded CRUD views now enforce login, model permissions, scope filtering, and create/update/delete audit logging in `microsys/scaffold_templates/app/views.py.tmpl`.
- Generic API detail/autofill lookups now apply scope-aware querysets and skip additional secret-like fields in `microsys/api.py`.
- The stale context-processor `_user_has_sidebar_permission()` helper with staff fallback was removed from `microsys/context_processors.py`.
- `UserListView.get_queryset()` now excludes Global Staff through queryset joins instead of per-request `Permission.objects.get()`, including group-assigned `manage_scopes`.
- `view_activitylog` permission ownership was moved to `UserActivityLog`; migration logic transfers existing Profile-owned assignments.
- Staff users with missing Profile state now fail closed for Central/Global Staff helpers and user-directory access.
- 2FA endpoints now include cache-backed IP rate limits for code verification and OTP sending.
- TOTP secrets are encrypted at rest with Fernet using `MICROSYS_TOTP_SECRET_KEY` / `MICROSYS_SECRET_KEY` / `SECRET_KEY` derived key fallback; legacy plaintext secrets still decrypt/read and are encrypted by migration/save.
- Focused verification passed:
  - Django runner: `microsys.tests.test_views`, `microsys.tests.test_utils` (`113` tests)
  - Django runner: `microsys.tests.test_api`, `microsys.tests.test_scaffold` (`31` tests)
  - Full Django runner: `microsys.tests` (`287` tests)
  - `PYTHONPYCACHEPREFIX=/tmp/microsys-pycache ./.venv/bin/python -m compileall microsys`

---

## Analysis Scope

| Component | Coverage | Status |
|-----------|----------|--------|
| Authentication & 2FA | Full | Hardened |
| Authorization (MSRP-1) | Full | Minor Gaps |
| Public Registration | Full | Secure |
| Optional SSO | Full | Secure |
| Scaffold Templates | Full | Hardened |
| API Endpoints | Full | Hardened |
| Session Management | Full | Hardened |
| Audit Logging | Full | Test Drift |

---

## Part 1: Authentication & Two-Factor Security

### Description
Core authentication layer with optional TOTP, email OTP, and backup codes. Unified login 2FA challenge consolidates all methods into a single input field.

### Findings

| Severity | Issue | Location | Description | Remediation |
|----------|-------|----------|-------------|-------------|
| **LOW** | Session fixation risk on 2FA login | `microsys/views/twofa.py:294` | `login()` called after OTP verification but session ID not rotated | Call `django.contrib.auth.login()` with session rotation or explicitly call `request.session.cycle_key()` before `login()` |
| **RESOLVED 2026-05-02** | TOTP secret stored plaintext | `microsys/models.py` (Profile), `microsys/utils.py` | `totp_secret` field stored authenticator secrets in plaintext. | Field widened and values are encrypted with Fernet using a derived key; migration encrypts existing plaintext secrets and helpers remain backward-compatible with legacy plaintext reads |
| **RESOLVED 2026-05-02** | Rate limiting on TOTP verification relied only on user/cache attempts | `microsys/views/twofa.py` | No per-IP throttling, only per-user OTP attempt counting. | Added cache-backed per-IP throttles for verification attempts and OTP send requests |

### MSRP-1 Compliance

| Requirement | Status | Notes |
|-------------|--------|-------|
| POST-only 2FA mutators | ✅ PASS | `@require_POST` on all state-changing endpoints |
| Backup codes hashed at rest | ✅ PASS | `_hash_backup_code_values()` used |
| Email OTP hashed in cache | ✅ PASS | `code_hash` stored, not plaintext |
| Explicit email OTP trigger | ✅ PASS | User must request email delivery |
| Short OTP TTL | ✅ PASS | Cache TTL enforced |
| Attempt limits | ✅ PASS | Cache-backed attempt counting |
| IP-based throttling | ✅ PASS | Verification and send paths use cache-backed IP counters |
| TOTP encrypted at rest | ✅ PASS | Fernet encrypted with prefixed ciphertext; legacy plaintext read path retained |

---

## Part 2: Authorization & Access Control

### Description
Multi-tier authorization with Superuser → Global Staff → Central Staff → Scoped Staff hierarchy. Permission tokens resolve through `user_matches_permission_token()`.

### Findings

| Severity | Issue | Location | Description | Remediation |
|----------|-------|----------|-------------|-------------|
| **RESOLVED 2026-05-02** | **Stale `_user_has_sidebar_permission()` helper with staff fallback** | `microsys/context_processors.py` | Unused function had dangerous staff fallback logic (`if not permissions: return user.is_staff`). | Removed the stale function entirely; active sidebar permission logic remains in `microsys/discovery.py` and fails closed for empty permissions |
| **RESOLVED 2026-05-02** | **Central Staff queryset filtering fetched permission object on every request** | `microsys/views/users.py` | `Permission.objects.get()` in `get_queryset()` caused avoidable per-request permission-object lookup and could silently skip Global Staff exclusion if permission lookup drifted. | Central Staff filtering now uses queryset joins through direct and group permissions, then `distinct()` |
| **MEDIUM** | `user_has_any_permission_tokens()` default visibility | `microsys/utils.py:663-677` | `default_visible_to_all=False` is secure, but many callers don't explicitly set this. Empty permission lists could theoretically pass in some edge cases. | Audit all callers to ensure `default_visible_to_all=False` is explicit |
| **RESOLVED 2026-05-02** | Scope isolation relied on raw `profile.scope` attribute checks | `microsys/utils.py`, `microsys/views/users.py`, `microsys/views/activitylog.py` | If profile relation didn't exist, helpers could treat staff users as intentionally scopeless. | Added profile-state helpers; Central/Global Staff and user-directory access fail closed when profile state is missing; staff querysets use helper-backed scope checks |
| **LOW** | `is_staff` and `is_superuser` tests are simple attribute checks | `microsys/utils.py:471-476` | No additional verification that user is active (`is_active=True`) | Add `is_active` check to `is_staff()` and `is_superuser()` helpers |

### MSRP-1 Compliance

| Requirement | Status | Notes |
|-------------|--------|-------|
| UI visibility ≠ only control | ✅ PASS | All sidebar items have backend enforcement |
| Direct URL access protected | ✅ PASS | `LoginRequiredMixin`, `UserPassesTestMixin` used |
| Permission tokens preferred | ✅ PASS | `user_matches_permission_token()` centralizes checks |
| State-changing POST-only | ✅ PASS | `@require_POST` on mutators |
| Diagnostics privileged-only | ✅ PASS | Superuser/Global Staff only |

---

## Part 3: Public Registration Playground

### Description
Email-first registration with verification tokens, activation modes (`auto_login_after_verify`, `verified_pending_approval`), and superuser approval workflows. Disabled by default.

### Findings

| Severity | Issue | Location | Description | Remediation |
|----------|-------|----------|-------------|-------------|
| **LOW** | Honeypot field check is simple presence check | `microsys/views/registration.py` | No advanced bot detection beyond hidden field | Consider adding rate limiting per IP and temporal checks |
| **INFO** | Verification token entropy | `microsys/models.py` | Uses `secrets.token_urlsafe(32)` (256 bits) | Adequate; no issue |

### MSRP-1 Compliance

| Requirement | Status | Notes |
|-------------|--------|-------|
| Disabled by default | ✅ PASS | `public_registration_enabled=False` default |
| SMTP-gated | ✅ PASS | Email readiness checked before enabling |
| Email verified before activation | ✅ PASS | Mandatory verification flow |
| Hashed tokens only | ✅ PASS | Tokens hashed in DB |
| Throttled/honeypot protected | ✅ PASS | Cache throttling + honeypot field |
| Generic error responses | ✅ PASS | Duplicate emails get same message as success |
| Approval superuser-only | ✅ PASS | `@user_passes_test(_superuser_required)` |
| POST-only approval | ✅ PASS | `@require_POST` on approve/reject |
| Audit logged | ✅ PASS | `log_user_action()` on approval/rejection |

---

## Part 4: Optional SSO (django-microsys-sso / django-microsys-sso-client)

### Description
OIDC-only SSO provider and client packages living in `optional_packages/`. Fail-closed additive architecture.

### Findings

| Severity | Issue | Location | Description | Remediation |
|----------|-------|----------|-------------|-------------|
| **RESOLVED 2026-05-02** | Provider redirect URI validation not reviewed | `optional_packages/django-microsys-sso/microsys_sso/services.py` | Claims "exact redirect URI" but implementation was not audited in the initial analysis | Verified provider helper uses exact registered redirect URI matching and rejects non-HTTPS callbacks outside allowed localhost development callbacks |
| **LOW** | JWKS key rotation handling | `optional_packages/django-microsys-sso` | Not reviewed in this analysis | Ensure key rotation doesn't cause token validation failures |

### MSRP-1 Compliance

| Requirement | Status | Notes |
|-------------|--------|-------|
| No core runtime imports | ✅ PASS | Packages are separate |
| Fail closed | ✅ PASS | Additive only |
| Exact redirect URIs | ✅ PASS | Verified in provider service helper |
| HTTPS outside localhost | ✅ PASS | Verified in provider service helper |
| Portable roles only | ✅ PASS | `admin`, `staff`, `user` only |
| No Django permission mirroring | ✅ PASS | Flat role claims used |
| No `is_superuser` elevation | ✅ PASS | Provider `admin` ≠ Django `superuser` |

---

## Part 5: Scaffold Template Security

### Description
Templates used by `python -m microsys startapp --register` to generate new application CRUD views.

### Findings

| Severity | Issue | Location | Description | Remediation |
|----------|-------|----------|-------------|-------------|
| **RESOLVED 2026-05-02** | **Generated views lacked authentication or authorization** | `microsys/scaffold_templates/app/views.py.tmpl` | `ListView`, `DetailView`, `CreateView`, `UpdateView`, `DeleteView` had no `LoginRequiredMixin` or `PermissionRequiredMixin`. If `--register` exposed URLs, anonymous users could CRUD. | Added `LoginRequiredMixin`, `PermissionRequiredMixin`, and per-action model permissions |
| **RESOLVED 2026-05-02** | **Queryset did not filter by scope** | `microsys/scaffold_templates/app/views.py.tmpl` | `ExampleRecord.objects.order_by("-created_at")` could return all records regardless of user scope. | Added helper-backed scope filtering that fails closed for non-superusers without scope when scopes are enabled |
| **RESOLVED 2026-05-02** | **No audit logging in generated views** | `microsys/scaffold_templates/app/views.py.tmpl` | No `log_user_action()` calls for create/update/delete. | Added create/update/delete audit logging in generated views |

### MSRP-1 Compliance

| Requirement | Status | Notes |
|-------------|--------|-------|
| Backend permission enforcement | ✅ PASS | Login and model permissions enforced |
| Direct URL access protected | ✅ PASS | Generated views require authenticated users |
| State-changing POST-only | ✅ PASS | Django CBV mutators plus auth/permission checks |
| Audit logging | ✅ PASS | Generated create/update/delete views log actions |

---

## Part 6: API Endpoints

### Description
JSON API endpoints for autofill, model details, and preferences. Located in `microsys/api.py`.

### Findings

| Severity | Issue | Location | Description | Remediation |
|----------|-------|----------|-------------|-------------|
| **RESOLVED 2026-05-02** | `_can_view_model()` didn't check scope | `microsys/api.py` | Only checked Django permission `app.view_model`, not scope isolation. | `get_last_entry()` and `get_model_details()` now use `_visible_queryset()` with scope filtering |
| **LOW** | `get_last_entry()` and `get_model_details()` broad serialization | `microsys/api.py` | `_serialize_instance()` now skips additional secret-like fields, but model-specific field allowlisting is still not implemented | Add explicit model field allowlists for API autofill/detail serialization |
| **LOW** | `update_preferences()` accepts arbitrary keys | `microsys/api.py:164-222` | While values are validated, unknown keys are silently ignored rather than logged | Add logging for rejected/unknown preference keys |

### MSRP-1 Compliance

| Requirement | Status | Notes |
|-------------|--------|-------|
| Login required | ✅ PASS | `@login_required` on all endpoints |
| Permission checks | ✅ PASS | Model view permission plus scope-aware querysets |
| State-changing POST-only | ✅ PASS | `update_preferences()` is POST-only |

---

## Part 7: Session Management

### Description
Django session-based authentication with signed-in device tracking and revocation.

### Findings

| Severity | Issue | Location | Description | Remediation |
|----------|-------|----------|-------------|-------------|
| **MEDIUM** | Session revocation doesn't invalidate Django session | `microsys/views/users.py` (profile view) | Device revocation deletes session from DB but doesn't call `session.flush()` if user is currently using that session from another device | Ensure `session.flush()` is called or use `django.contrib.sessions.backends.cached_db` with delete |
| **LOW** | Session metadata collection stores IP and User-Agent | `microsys/middleware.py` | Privacy concern; may violate GDPR/CCPA without disclosure | Document in privacy policy; add retention limits |

### MSRP-1 Compliance

| Requirement | Status | Notes |
|-------------|--------|-------|
| POST-only revocation | ✅ PASS | Form POST required |
| Own sessions only | ✅ PASS | Filtered by `user=request.user` |
| Current session protected | ✅ PASS | Cannot revoke current session |

---

## Part 8: Audit Logging & Activity Log

### Description
`UserActivityLog` model tracks user actions with metadata. Permission `view_activitylog` controls access.

### Findings

| Severity | Issue | Location | Description | Remediation |
|----------|-------|----------|-------------|-------------|
| **RESOLVED 2026-05-02** | **Permission ownership test drift** | `microsys/models.py`, `microsys/migrations/0002_public_registration.py`, `microsys/tests/test_views.py` | `view_activitylog` permission was defined on `Profile`, while tests and behavior expected it on `UserActivityLog`. | Moved permission to `UserActivityLog`; migration transfers existing user/group assignments from the old Profile-owned permission and removes the old permission |
| **LOW** | Activity log doesn't log failed permission attempts | Various | No logging of 403 responses for security analysis | Add `log_user_action()` calls in permission denied scenarios |

### MSRP-1 Compliance

| Requirement | Status | Notes |
|-------------|--------|-------|
| All actions logged | ⚠️ PARTIAL | Most actions logged; some gaps |
| Permission enforced | ✅ PASS | Permission ownership aligned with `UserActivityLog` |

---

## Part 9: System Settings & Configuration

### Description
`SystemSettings` singleton model controls global configuration including security settings.

### Findings

| Severity | Issue | Location | Description | Remediation |
|----------|-------|----------|-------------|-------------|
| **LOW** | Email config stored in JSONField | `microsys/models.py` | While encrypted in `encrypted_db` mode, the JSON structure allows arbitrary keys not validated by form | Add schema validation for `email_config` JSON structure |
| **INFO** | Export includes non-sensitive config only | `microsys/views/general.py:419-430` | SMTP secrets redacted correctly | Good practice |

### MSRP-1 Compliance

| Requirement | Status | Notes |
|-------------|--------|-------|
| Secrets redacted in export | ✅ PASS | `export_system_settings_payload()` redacts secrets |
| Import requires re-entry | ✅ PASS | Secrets not imported |
| Encrypted DB mode opt-in | ✅ PASS | Explicit `encrypted_db` mode required |

---

## Part 10: Code Quality & Security Anti-Patterns

### Description
General code patterns that may introduce security risks.

### Findings

| Severity | Issue | Location | Description | Remediation |
|----------|-------|----------|-------------|-------------|
| **LOW** | MD5 used for config hashing | `microsys/context_processors.py:28` | `hashlib.md5()` used for cache key, not security, but should be avoided | Use `hashlib.sha256()` or `hashlib.blake2b()` |
| **LOW** | `NoReverseMatch` exceptions caught and silently logged | `microsys/context_processors.py:79-81` | URL resolution failures don't bubble up; could mask configuration errors | Log at ERROR level, not WARNING |
| **INFO** | `get_strings()` may leak translation strings to anonymous users | `microsys/context_processors.py` | `MS_TRANS` always in context even for unauthenticated requests | Acceptable risk; translations are public data |

---

## Recommendations Summary

### Immediate (Before 2.1.0 Release)

No open immediate blockers remain from this report after the 2026-05-02 remediation batch.

### Near-Term (Post-2.1.0)

5. Add explicit model field allowlists for API serialization
6. Add audit logging for permission denied events
7. Fix session revocation behavior for cache-only session backends

### Long-Term

10. Add schema validation for JSON configuration fields
11. Comprehensive penetration testing of SSO provider/client
12. Security audit of JavaScript frontend (sidebar, options, 2FA flows)

---

## MSRP-1 Overall Assessment

| Category | Score | Notes |
|----------|-------|-------|
| Authentication | 9.3/10 | Well-hardened 2FA, minor session fixation risk remains |
| Authorization | 8.5/10 | Good tier system, remaining permission-token/default-visibility audit work |
| Audit | 8/10 | Permission ownership aligned; failed-permission audit logging remains a gap |
| Input Validation | 8/10 | Good form validation, API still needs explicit field allowlists |
| Output Encoding | 9/10 | Templates use Django auto-escaping |
| Configuration | 8/10 | Secure defaults, good secret handling |
| **Overall** | **8.8/10** | **Good with remaining near-term hardening work** |

---

*Report generated for django-microsys security review. MSRP-1 standard applied.*
