# DjangoLux Conceptual Codebase Report

Verified on 2026-06-23 against the unreleased `1.2.4` source tree.

This report explains the codebase as a set of concepts, algorithms, and runtime
systems. It avoids line-by-line implementation commentary and instead focuses on
what the package is trying to coordinate, how decisions flow, what state exists,
and how the major pieces depend on one another.

## 1. One-Sentence Model

DjangoLux is a Django application framework layer that turns an ordinary Django
project into a configurable internal application platform: it owns setup,
branding, language, theme, navigation, permissions, scoped data, user operations,
notifications, audit trails, tables, modal CRUD, reporting, backups, scaffolding,
verified generated-Compose updates, and optional SSO integration.

It is not only a UI skin. Its central idea is that application behavior is
computed from layered configuration, current request state, current user state,
model metadata, URL discovery, and explicit permission helpers.

## 2. The Core Algorithm

Most of the project follows one repeating algorithm:

1. Start with a safe default.
2. Overlay project code settings from `DLUX_CONFIG`.
3. Overlay database settings from the singleton `SystemSettings` row.
4. Normalize the result into bounded choices.
5. Resolve the current user, language, theme, scope, and preferences.
6. Expose that resolved state to templates and JavaScript.
7. Enforce the same decision again in backend views before any data is shown or changed.

This algorithm appears in configuration, theme selection, language selection,
sidebar rendering, navbar crumbs, table density, email delivery, client IP
resolution, public registration, 2FA, report visibility, backup access, scoped
querysets, and dynamic modal CRUD.

The package is therefore best understood as a "resolver framework." It accepts
many optional inputs, then collapses them into deterministic runtime state.

## 3. Primary State Layers

The runtime state comes from five layers.

**Static package defaults:** constants, built-in themes, built-in fonts,
default language catalog, default routes, default settings, and fallback assets.

**Host project settings:** `DLUX_CONFIG`, Django settings, installed apps,
middleware order, template context processors, URL patterns, email backend,
Celery availability, cache backend, storage backend, and optional report/backup
configuration.

**Database state:** `SystemSettings`, scopes, profiles, trusted devices, known
devices, presence sessions, public registrations, notifications, activity logs,
report/full-system backup and restore runs, `DluxUpdateState`, and
`DluxUpdateRun`.

**Request/user state:** current request thread-local, authenticated user,
session keys, signed device cookies, user profile preferences, current path,
current language, current permissions, and URL resolver match.

**Generated deployment state:** the baked Dlux package plus `dlux_runtime`
version directories, atomic active pointer, generation counter, maintenance
marker, and retained updater artifacts. This layer exists only in the recognized
generated Compose architecture; ordinary installations use the baked package.

The package repeatedly asks: "Given all of these layers, what should this
request see or be allowed to do?"

## 4. Naming And Identity

The current package identity is:

- Distribution: `django-lux`
- Import package: `dlux`
- Django app label: `dlux`
- Configuration namespace: `DLUX_CONFIG`
- CLI command: `dlux`
- Backup extension and container magic: `.dlb` / `DLB1`
- Runtime DOM/CSS/event prefix: `dlux`
- Translation dict name: `DLUX_STRINGS`

The codebase still contains intentional compatibility paths for the previous
`django-microsys` identity: the migration command relabels existing databases,
and the translation loader still accepts legacy `MS_TRANSLATIONS` from host apps.

## 5. Settings Bootstrap

The integration helper `dlux_settings(globals())` is the simplest entrypoint.
Conceptually, it patches a Django settings module into a Dlux-ready baseline.

It ensures required apps are present and ordered so Dlux templates and patches
win where needed. It inserts locale middleware and Dlux middleware near Django's
session/auth stack. It appends the Dlux context processor. It sets Crispy Forms
to Bootstrap 5. It sets language/timezone/charset defaults and adds Dlux format
modules.

The helper is additive and idempotent: it reshapes lists instead of requiring
the host project to know the entire desired final settings layout.

## 6. Runtime Configuration

`get_system_config()` is the major configuration reducer.

It starts with hard-coded defaults for identity, assets, home URL, language,
theme, fonts, table density, authentication, email delivery, registration,
public-root behavior, client IP resolution, notifications, login page layout,
sidebar, navbar, titlebar, logging, profile/onboarding behavior, and setup
completion.

It then reads `settings.DLUX_CONFIG`. Finally, it reads `SystemSettings.load()`
when the database is available. Database settings only override defaults when
the system is configured or when a value differs from the model default. This
keeps an unconfigured fresh singleton from accidentally masking project-level
settings.

The final stage normalizes everything:

- Unknown themes are discarded.
- A default theme outside the allowlist falls back to the first allowed theme.
- Unknown table/sidebar density values fall back to balanced.
- Sidebar, navbar, titlebar, login, client IP, email, language, and font config
  are clamped to known shapes.
- Asset paths are normalized for static/media/absolute URL behavior.
- Derived grouped views like `identity`, `localization`, `security`,
  `navigation`, `appearance`, and `personalization` are added for templates.

This means host projects can provide partial or messy JSON-like config, while
runtime consumers receive a predictable structure.

## 7. The SystemSettings Singleton

`SystemSettings` is the database-backed control plane. It keeps identity fields
as columns and mutable subsystem policy in normalized JSON groups. It stores:

- System names per language.
- Logo and favicon.
- Default language and theme.
- Theme allowlist and per-user override flags.
- Font allowlist, default fonts, and per-user font override flag.
- Home URL.
- Setup completion.
- Authentication, email delivery, registration, public-root, and Client IP policy.
- Language catalog.
- Translation overrides.
- Notifications, login, titlebar, sidebar, navbar, logging, profile/onboarding,
  and reserved extra config.

The singleton always saves as primary key `1`. It is cached for performance and
clears sidebar caches when refreshed. Its `delete()` method is intentionally
blocked, while management commands can deliberately delete/reset it through the
queryset path.

The conceptual role of this model is not to be business data. It is the live
runtime policy document for the installed application.

## 8. First-Launch Setup

The first-launch setup wizard is a configuration state machine.

If the system is not configured, middleware prevents ordinary users or anonymous
traffic from bypassing setup. A superuser is sent to `/sys/setup/`; a non-
superuser is logged out and redirected to login.

The setup view loads `SystemSettings`, optionally imports a `config.json` file
from `BASE_DIR`, and renders `SystemSettingsForm` in setup mode. When saved, the
form writes normalized data through the same import/export pathway used by
portable setup JSON.

Fresh systems first choose the setup UI language; that session-only choice does
not set the saved application default language. The wizard then has eleven
stages:

1. Identity: language-keyed system names, logo, favicon, and setup import.
2. Localization: enabled languages, default language, translation matrix.
3. Access and security: public root, registration, email 2FA, client IP,
   single-session behavior, email delivery, and global home URL.
4. Login page: layout, logo visibility/treatment, banner color, hero message.
5. Sidebar: selected routes, groups, toolbar, reordering, icons, density,
   collapse behavior.
6. Navbar: hierarchy/history mode and hierarchy nodes.
7. Titlebar: logo/title/home controls, sizing, alignment, surface, logo
   treatment.
8. Notifications: flash, drawer/badge, message bridge, email, retention, and
   automatic CRUD behavior.
9. Appearance and typography: themes, theme allowlist, fonts, table density.
10. Logging: user/system/audit policy, model/action gates, and retention.
11. Profile page: profile modules, security nudge, landing-page policy, and
    first-login onboarding.

Single-step modal edits reuse the same form but preserve omitted fields from
other steps. That prevents a partial settings modal from clearing unrelated
wizard data.

## 9. Import And Export Of Settings

The setup import/export system uses a portable JSON envelope:

- Format: `django-lux.system-settings`
- Version: `1`
- Package version metadata.
- A normalized `settings` object.

Export redacts SMTP secrets. Import accepts current field names and some runtime
aliases such as `sidebar`, `navbar`, `titlebar`, `login`, and `translations`.

The import algorithm is defensive:

1. Verify the payload is a JSON object.
2. Extract the settings object or treat the whole payload as raw settings.
3. Keep only known fields.
4. Normalize each field to the same bounded representation used by runtime config.
5. Apply to the singleton.
6. Optionally mark the system configured.

This design makes the setup wizard, management command, and auto-load
`config.json` path share one normalization contract.

## 10. Middleware And Request Ownership

`DluxMiddleware` owns several cross-cutting request behaviors.

It stores the current request and user in thread-local storage. Scoped models,
signals, form patches, table patches, and logging can then make request-aware
decisions even when Django APIs do not pass the request directly.

It synchronizes auth redirect settings from the live system config. Login goes
to the configured home URL. Logout goes either to login or to the anonymous
public destination when public root is enabled.

It enforces the first-launch setup guard. Static/media, login/logout, setup,
preference API, and 2FA paths remain reachable; other paths redirect according
to setup state and user role.

It handles root fallback. If a project has no view at `/` and Django returns
404, Dlux redirects the root to setup, login, authenticated home, or anonymous
public target depending on config and user state. If the project has its own
root view, Dlux leaves it alone.

It records session/device presence and attaches a signed device identity cookie.

It detects requests from browsers whose sessions were force-revoked and sends
them to a "session ended" interstitial instead of silently bouncing to login.

It converts `SuspiciousOperation` into JSON for AJAX requests while preserving
normal exception behavior for page requests.

## 11. Context Processor

`dlux_context()` is the template runtime compiler.

It computes:

- `APP_CONFIG` / `config`
- Active language and direction.
- Language catalog and current language metadata.
- `DLUX_STRINGS`
- Theme names and theme options.
- Table density choices.
- Scope status.
- Permission-derived booleans for users, activity log, reports, sections.
- Current user-management tier.
- User preferences after policy filtering.
- Sidebar tree, auto items, groups, toolbar availability, collapse state,
  density, reorder state, and theme/language/font picker availability.
- Navbar enabled state and mode.
- Titlebar config and public-index hide behavior.
- Font-face CSS, active font, allowed fonts, and font picker state.

This context is the bridge between backend policy and the frontend runtime.
The base template exports part of it as JSON script blocks so JavaScript can use
the same resolved state.

## 12. Themes, Fonts, And Visual Runtime

Themes are registry-driven. `dlux/themes.py` defines the canonical ordering,
slug, color, label key, preview style, and CSS path. The runtime only exposes
themes whose CSS file exists, then applies an allowlist from config.

Fonts work similarly. Built-in font metadata and generated `@font-face` CSS are
resolved from the allowed font list. User font preference is honored only if the
system allows user override and the selected font is still allowed.

The visual runtime is external-asset oriented. The base template uses JSON
script blocks for data, external JavaScript for behavior, linked CSS for styling,
and a single nonce-protected dynamic font style block for generated font faces.

Before full page load, `base_head.js` applies theme, font, and accessibility
classes to avoid a flash of the wrong UI state. Later runtime scripts initialize
datepickers, alerts, tables, sidebar, navbar, selectors, setup wizard behavior,
dynamic modals, context menu actions, tutorial overlays, and preference saving.

## 13. Language And Translation

The translation system is key/value based rather than `.po` file based.

The base catalog lives in `DLUX_STRINGS`. Apps can add their own
`translations.py` with a `DLUX_STRINGS` dictionary. Dlux discovers installed app
translation modules and deep-merges them over the core catalog.

Language resolution is:

1. Forced setup preview session language when active.
2. User profile preference, if user language override is allowed.
3. Session language, if allowed.
4. System default language.
5. Django's active language as a last fallback.

`get_strings()` merges base default-language strings, active-language strings,
and runtime database overrides. This lets a host app ship a default catalog and
let superusers override copy later in System Settings.

Dlux also patches Django translation functions and model metadata so model
verbose names, form labels, filter labels, table headers, permission strings,
and log display text can resolve through Dlux strings at render time.

The `MigrationSafeTranslation` wrapper is important conceptually: it behaves as
a runtime-translated string, but serializes into migrations as a stable default
instead of the current active language.

## 14. Scoped Data Model

`ScopedModel` is the base class for data that should be scope-aware and audited.

It adds:

- `scope`
- `created_at` / `updated_at`
- `created_by` / `updated_by`
- `deleted_at` / `deleted_by`
- soft delete behavior
- restore and hard-delete escape hatches
- `objects` as a scoped manager
- `all_objects` as an unfiltered manager

On save, it reads the current thread-local user. New records get `created_by`.
Every save gets `updated_by`. If scope is enabled and the object has no scope,
the user's profile scope is copied onto the record.

On delete, records are soft-deleted by setting `deleted_at` and `deleted_by`.

The scoped manager filters out soft-deleted rows and, when scopes are enabled,
filters records based on the current user:

- Superusers see all.
- Scoped users see their own scope.
- Non-scoped users see only unscoped central data.
- If scopes are disabled, no scope filtering occurs.

This turns scope into a default data boundary rather than something every view
must remember to implement manually.

## 15. Scope Settings

`ScopeSettings` is another singleton. It controls whether scopes are enabled and
whether new users automatically get their own scope.

Scope toggling is treated cautiously in UI and tests because once users have
assigned scopes, disabling the system can change visibility in surprising ways.

Scope behavior flows into:

- Model managers.
- Forms.
- Filters.
- Tables.
- User-management visibility.
- Report visibility.
- API querysets.
- Dynamic modal CRUD querysets.
- Section and subsection operations.
- Activity log scope assignment.

## 16. Runtime Patching

Dlux uses monkey patches at app startup to make ordinary Django patterns behave
like Dlux-aware patterns.

The ModelForm patch injects a scope field for scoped models when needed,
hides/disables it when scopes are disabled or the user is not a superuser, and
refreshes scoped choice querysets under the current user.

The FilterSet patch injects or removes a scope filter for scoped models and
refreshes scoped choice querysets.

The django-tables2 patch adopts the Dlux table template for stock tables,
injects scope columns when appropriate, computes density and page size, applies
the Dlux table classes, adds row context-menu actions, filters those actions by
permission, and configures pagination.

The global translation patch redirects Django gettext-style calls and model
metadata into the Dlux string catalog.

The conceptual benefit is "zero-boilerplate adoption." Host apps can write
ordinary forms, filters, and tables, while Dlux adds the platform behavior at
construction time.

## 17. Authorization Model

Dlux keeps a clear separation between UI visibility and backend authorization.

Core authorization helpers include:

- User directory visibility.
- Activity log visibility.
- User report visibility.
- Report overview visibility.
- Backup download visibility.
- Section view/manage permissions.
- Generic model action permissions.
- Internal sidebar permission tokens.

Superusers bypass most checks. Staff users are categorized into four conceptual
tiers:

- Superuser: full access.
- Global Staff: cross-scope administrative access.
- Central Staff: administrative access to unscoped users/data.
- Scoped Staff: administrative access within one scope.

The package repeatedly checks permissions in views, not only in templates. A
hidden button is never treated as sufficient protection.

## 18. User Management

The user-management list view is a scoped, permission-gated table/filter view.

Its queryset annotates online state from recent presence sessions, selects and
prefetches profile/scope/permission data, excludes soft-deleted profiles, and
then filters by actor tier:

- Non-superusers cannot see superusers.
- Central staff see unscoped non-global-staff users.
- Scoped staff see users in their own scope.
- Global staff see all non-superusers.
- Users without a valid staff tier see none.

User creation, editing, permissions editing, detail modals, reports, reset
password, and delete flows all route through helper checks such as
`can_manage_target_user()` and `user_can_view_user_directory()`.

User deletion is a soft-deactivation path: the user is made inactive, the
profile is soft-deleted, and the username is renamed to free it for reuse.

## 19. Profiles And Preferences

`Profile` stores user-adjacent runtime state:

- phone
- profile picture
- JSON preferences
- scope
- email/phone/TOTP 2FA flags
- encrypted TOTP secret
- hashed backup codes
- email verification timestamp

Profile images are normalized to WebP and resized to 300x300.

Preferences are a JSON object used for theme, language, table density, sidebar
state, sidebar order/tree, navbar mode, font, accessibility, and related UI
state. The preference API validates each incoming key against system policy
before saving. For example, an unavailable theme is discarded, a forbidden
language override is removed, and locked-expanded sidebar mode clears collapsed
state.

Preference reset clears the profile preference object and related session keys.

## 20. Device And Session History

Dlux tracks devices and sessions in three related ways.

`TrustedDevice` represents a 30-day 2FA trust grant. It is keyed by a signed
browser cookie token hash and can be revoked.

`UserKnownDevice` represents a long-lived browser/device identity based on a
separate signed device identity cookie. It aggregates observed IP addresses,
user agents, browsers, operating systems, first seen, and last seen.

`UserPresenceSession` represents a login session by hashed session key. It
tracks request count, estimated active seconds, observed network/device values,
ended/revoked timestamps, and known-device linkage.

Presence updates are throttled so they do not write on every request. When a
session is revoked remotely or by single-session enforcement, Dlux flags the raw
session key hash in cache so the next browser request can show the signed-out
interstitial.

## 21. Authentication And 2FA

Login uses `CustomLoginView`. It authenticates with Django's normal form, then
intercepts successful login when the user profile has 2FA enabled.

If a valid trusted device cookie matches an active `TrustedDevice`, login skips
the challenge, updates device metadata, and optionally enforces single-session
policy.

Otherwise the view stores pre-2FA user, method, next URL, and default redirect
state in the session. If email is the only primary method, it auto-sends an OTP.
The user is redirected to the verification view.

2FA methods:

- Email OTP: six digits, stored hashed in cache, expires after five minutes,
  has resend cooldowns and IP send/verify rate limits.
- TOTP app: `pyotp` secret, QR code generation, issuer from configured system
  name, encrypted secret storage.
- Backup codes: eight 8-digit codes, stored hashed, consumed on use.
- Phone: structural support exists, gated by `SMS_BACKEND`, but email/TOTP are
  the implemented paths.

Disabling 2FA, generating backup codes, trusting the current device, and
revoking sessions require current-password confirmation. Mutating endpoints are
POST-only.

Single active session enforcement is independent of device trust: when enabled,
the newest successful login session wins and all other sessions for that user
are deleted and marked ended/revoked.

## 22. Public Registration

Public registration is disabled by default and gated by email readiness.

The public flow:

1. Anonymous user opens `/accounts/register/`.
2. Honeypot spam field is checked.
3. Email/password form validates.
4. Availability checks ensure registration is enabled and email delivery works.
5. IP and email throttles are applied.
6. Existing email returns the same generic sent page.
7. A local inactive user is created with a generated username.
8. A `PublicRegistration` row stores hashed verification token, status,
   activation mode, IP, user agent, and expiry.
9. Verification email is sent through `send_dlux_mail()`.
10. Verification either activates and logs in the user or moves them to pending
    superuser approval.

Approval and rejection are superuser-only POST routes.

This feature is intentionally separate from optional SSO. It creates local Dlux
accounts, not SSO client-originated accounts.

## 23. Email Delivery

Dlux email config supports two transport concepts:

- Direct SMTP from the web process.
- Relay mode, where generated projects can send to an internal `smtp-relay`
  service.

Secret storage can be:

- Environment/secrets.
- Encrypted database secret.

Export redacts the secret. Setup validation blocks public registration or email
2FA when the resulting email service is not ready, except for accepted local
debug email backends in development.

The email helper resolves effective config, decrypts encrypted secrets when
needed, and sends through Django mail connections.

## 24. Client IP Resolution

Client IP resolution is configurable because logs, registration throttles, 2FA
rate limits, trusted devices, and presence history all depend on it.

Supported modes include:

- `remote_addr`
- `x_forwarded_for`
- `x_real_ip`
- `cloudflare`
- `custom`
- `auto`

The X-Forwarded-For mode understands trusted proxy hops. Custom header names are
normalized into Django `META` keys. If the chosen source is empty, the resolver
falls back through common headers and then `REMOTE_ADDR`.

## 25. Activity Logging

Activity logging is signal-driven plus explicit helper calls.

Login/logout signals create auth entries. Model save/delete signals create CRUD
entries unless the model is excluded, the instance opts out, no authenticated
request user exists, or the update is known noise such as `last_login` only or
profile preference-only updates.

On update, pre-save captures original field values. Post-save compares fields,
masks sensitive names, and stores a diff. User and Profile changes are merged
into a logical "User Profile" entry so user edits do not fragment across two
models.

The log model stores:

- action
- display model name
- stable `model_key`
- object id
- object number/label
- IP address
- user agent
- details JSON
- scope
- inherited actor and timestamps

Duplicate entries inside a short window are suppressed. Operational tracking
models such as trusted devices and presence sessions are excluded to avoid log
flooding.

## 26. Reports

Reports summarize activity logs, not arbitrary database rows.

The report engine:

1. Builds a base activity queryset.
2. Applies scope visibility based on actor tier.
3. Applies a time window: week, month, or all.
4. Filters out Dlux-internal/noise model keys.
5. Groups by user, model, action, and day.
6. Computes totals, deltas, averages, available filters, and recent activity.
7. Optionally caches expensive overview stats by actor scope, filters, language,
   and report config.

The engine prefers stable `model_key` grouping over translated `model_name`
labels. That avoids reports changing identity when the UI language changes.

Reports can export XLSX workbooks with summary and grouped sheets.

## 27. Report Backups

Report backups are scoped, permission-gated ZIP archives for monitoring/export.
They are not full system restore files.

The backup chooses report-eligible models, applies scope and optional time
window filtering, streams serialized JSON fixtures into a ZIP, and streams file
field contents into the same archive. It records a manifest with model counts,
files, and missing files.

Large backups can run in Celery when a worker and broker are actually reachable.
Otherwise views fall back to synchronous generation. Completed backups are
stored through Django default storage and pruned to keep recent history small.

## 28. Full System Backup And Restore

Full system backup is the `.dlb` subsystem. It is separate from reports backup.

A `.dlb` file contains:

- Cleartext `DLB1` magic.
- Cleartext metadata length and metadata JSON.
- Repeated Fernet-encrypted frames of an inner ZIP payload.

The inner ZIP contains:

- `manifest.json`
- serialized model fixtures under `data/<app>/<model>.json`
- file field contents under `files/<app>/<model>/<pk>/<field>/<name>`

Key derivation uses PBKDF2-SHA256 with a random salt. By default the seed is
Django `SECRET_KEY`; an optional passphrase changes the key source and is then
required for restore.

System backup includes every concrete managed model except environment-owned
and bookkeeping models such as sessions, content types, permissions, admin log
entries, and backup/restore run rows. Models are dependency-sorted so referenced
rows load before referrers. Superuser password hashes are omitted from backups.

Restore is full replacement:

1. Decrypt `.dlb` to a temporary ZIP.
2. Read manifest and compare migration state.
3. Fail unless migrations match or the user explicitly ignores mismatch.
4. Suspend Dlux signals.
5. In one transaction with constraints disabled, clear backup bookkeeping,
   implicit M2M rows, and restorable model rows.
6. Deserialize model fixtures in dependency order.
7. Preserve existing superuser password hashes by username or make unmatched
   restored superusers unusable.
8. Save deferred fields.
9. Check constraints.
10. Reset database sequences.
11. Restore files.
12. Clear content type cache, global cache, and sessions.
13. Log the restore summary.

The restore design treats `.dlb` as a whole-system replacement image, not an
incremental import.

## 29. Standalone DLB Viewer

`tools/dlb-viewer/` is a Go program that reads the same `.dlb` container format.
It implements Fernet/PBKDF2 behavior from Go standard-library primitives and
serves a local read-only web UI bound to `127.0.0.1`.

The viewer can browse metadata, model rows, stored files, migration state, and
raw manifest without a running Django instance. It uses a per-run token and
local host checks for basic local-server safety.

## 30. Discovery System

Dlux uses discovery in two main places: model class discovery and sidebar route
discovery.

Model class discovery resolves a model from:

- explicit app label and model name
- `app_label.model_name`
- class name
- verbose name
- fuzzy normalized lookup

Then it resolves related classes by convention:

- `<app>.forms.<Model>Form`
- `<app>.tables.<Model>Table`
- `<app>.filters.<Model>Filter`

Models can also provide class references through known methods or attributes.
When nothing exists, Dlux generates a fallback ModelForm, Table, or FilterSet.

Sidebar discovery walks Django URL patterns, keeps only reversible named routes,
rejects action-like/internal/API/auth/modal/delete routes, infers model/group,
labels, icons, and permissions, and caches a catalog per language/config/URLconf.

This lets host apps become navigable and manageable by following normal Django
conventions instead of registering every surface manually.

## 31. Sidebar Algorithm

The sidebar has three layers:

- Discovered catalog: all valid route candidates.
- System sidebar config: selected entries/groups and behavior.
- User override tree: optional personalized ordering and grouping.

Build algorithm:

1. Load and sanitize configured sidebar.
2. If disabled, return empty navigation.
3. Merge user override tree onto base entries if present.
4. Resolve each configured item against the discovered catalog.
5. Reverse URL names into URLs.
6. Filter every item by strict permission tokens.
7. Drop empty groups.
8. Mark active items based on current request path.
9. Open groups that contain active items or user-open accordions.
10. Return render-ready entries, top-level auto items, and groups.

New base entries missing from a user override are appended so user-specific
ordering does not hide newly added system navigation forever.

System routes use internal permission tokens like `__dlux_user_directory__` so
sidebar visibility mirrors backend helper logic rather than raw `is_staff`.

## 32. Navbar Algorithm

The navbar is optional and can operate in hierarchy mode or history mode.

Hierarchy mode uses configured recursive nodes. A node can be a route or manual
group. Dlux finds the current route by resolver match, searches the hierarchy,
and converts matching ancestors into crumbs with translated labels and resolved
URLs. Runtime-provided crumbs win over configured hierarchy. If no configured
match exists, it falls back to the discovered sidebar catalog and then humanized
route names.

System routes can be wrapped in a "System" crumb. Root-like routes are made
non-clickable unless explicitly configured with a URL.

The setup form can seed a navbar hierarchy from sidebar entries when navbar is
enabled and no hierarchy exists.

## 33. Tables

Dlux takes ownership of stock django-tables2 rendering by default.

Any table with no template or a stock django-tables2 template is switched to
`dlux/tables/table.html` unless it opts out with `dlux_table = False`.

The table platform adds:

- theme-aware shell and classes
- built-in sort links
- empty state
- pagination
- page-size controls
- density controls
- row context actions
- permission-filtered edit/delete actions
- per-table density and page-size overrides

Density resolution priority is:

1. table Meta `dlux_density`
2. user preference
3. system default
4. balanced fallback

Page size resolution priority is:

1. table Meta `dlux_per_page`
2. request query parameter
3. saved user preference
4. explicit RequestConfig default
5. package default
6. first available option

## 34. Forms And Filters

Forms are styled and translated through shared helpers.

`set_field_attrs()` applies labels, placeholders, direction, Bootstrap classes,
and datepicker hooks. `setup_filter_helper()` builds a compact filter row with
search/clear controls while preserving selected query parameters. The advanced
filter helper supports primary fields, collapsible advanced fields, hidden
inputs, and action buttons.

`SystemSettingsForm`, user creation/change/permission forms, profile edit form,
password forms, scope form, and public registration form all build on these
patterns but encode their own domain rules.

Generated forms for discovered models use model fields but add autofill metadata
for foreign keys and hide scope/audit fields where appropriate.

## 35. Dynamic Modal CRUD

Dynamic modal CRUD is the AJAX abstraction for model management.

`DynamicModalManagerView` can receive a model explicitly from the URL, from a
class attribute, or from a query parameter. It resolves form/table/filter classes
through model discovery, then renders a combined modal, detail-only modal, or
form-only modal depending on context.

Access rules are recalculated per request:

- System Settings modals require superuser.
- Profile edit modal is self-only.
- User modals require target-user management rights.
- Generic models require Django add/change/view permissions.
- Querysets are scope-filtered for non-superusers.

On POST, valid forms save through normal model behavior, forcing scope for
non-superusers where applicable. Invalid forms return rendered HTML with errors.

`DynamicModalDeleteView` performs permission checks, scope-filtered lookup, and
related-object detection before deleting. Scoped models soft-delete through
their own `delete()` override.

## 36. Sections And Subsections

Sections are a convention for zero-boilerplate management pages.

A model becomes a section when it declares `is_section = True` or an equivalent
Meta marker. Dlux discovers section models, resolves form/table/filter classes,
and finds subsection models as many-to-many child targets that are not meant to
stand alone.

The section manager lets users tab between discovered section models, filter and
table records, edit inline, add subsection children, and view/delete details.

Security is intentionally allowlist-based: section detail/delete and subsection
operations only accept models discovered as sections or valid subsection
children. Arbitrary `model=` tokens are rejected even if the user has broad
permissions.

## 37. Context Menus And Row Actions

Rows can carry `data-dlux-context` and `data-dlux-actions`. Actions are JSON
objects with labels, icons, event names, payloads, and optional permissions.

Dlux-generated table rows get default view/edit/delete events. Tables can
override or extend actions through `get_dlux_row_actions()`. Actions are cleaned
to remove duplicate/trailing dividers and filtered by permissions before being
serialized.

The frontend context menu reads these actions and dispatches `dlux:` namespaced
events such as record view/edit/delete. Dynamic modal scripts listen for these
events and open the relevant modal or delete confirmation.

## 38. API Helpers

The API module exposes three conceptual groups.

Autofill reads the last visible entry or a specific visible instance and
serializes safe direct fields. It excludes sensitive names, IDs, files, reverse
relations, and deep nested data. It applies model view permission and scope
filters.

Preferences merge validated UI preferences into the user's profile and session.
Every preference key is checked against system policy before it is accepted.

Reset clears profile preferences and related session keys.

## 39. Fetcher And Excel Export

The universal file fetcher accepts a single model instance, list, or queryset.
It introspects file fields, builds clean filenames from model name, identifier,
date, and field name, and returns either one file or a ZIP. It logs download
actions.

The Excel exporter introspects model fields, omits excluded fields, hides file
fields and auto timestamps by default, writes rows with openpyxl, adjusts
columns, and logs export actions.

These helpers are intentionally generic productivity APIs for host apps.

## 40. Options View

The Options view is the authenticated runtime dashboard for personal and system
controls.

All authenticated users can access personal preference cards. Diagnostics are
only shown to superusers and Global Staff. System backup summary is superuser
only.

Diagnostics probe database, cache, API/DRF, Celery, email, OS, Python, Django,
decrypter version, RAM, and disk. Cards are draggable and persisted in the
browser. Visibility of theme, language, font, table density, sidebar density,
navbar mode, and system settings entrypoints comes from resolved context and
permissions.

## 41. Public Templates And Runtime Shell

`dlux/base.html` is the authenticated runtime shell. It provides:

- language/direction attributes
- JSON script bridges
- dynamic font CSS
- Bootstrap LTR/RTL selection
- Dlux CSS and all allowed theme CSS
- titlebar and user hub
- optional sidebar
- optional navbar
- message alerts
- tutorial include
- context menu include
- dynamic modal include
- extension hooks for custom head/scripts

`form_base.html` and `list_base.html` are thin entrypoints that add form/filter
assets around the base shell.

Public auth templates use the configured login layout and language context but
avoid exposing authenticated runtime controls.

## 42. Static Asset Organization

Static assets are organized by surface:

- `main`: base runtime, tables, titlebar, navbar, setup, selectors, options.
- `themes`: one CSS file per theme plus runtime theme switching.
- `language`: language picker and translation runtime helpers.
- `sidebar`: main sidebar, reorder, preload, theme picker.
- `users`: login, profile, permissions, user hub, user report, 2FA UI.
- `helpers`: dynamic modal, context menu, wizard, autofill, tooltips, scan link.
- `forms`: filter form and file field behavior.
- `backup`, `activitylog`, `tutorial`, `accessibility`, `sections`.

The naming convention now uses the single `dlux` prefix across authored CSS,
data attributes, CSS variables, events, and JS globals.

## 43. Security Policy Concepts

The active security standard is DSRP-1. Its practical rules in code are:

- Backend authorization must match UI visibility.
- State-changing security flows are POST-only.
- Sensitive actions require current password where appropriate.
- Public registration is disabled by default and email-verified.
- Activity log/report/user-detail access is explicit.
- Section and modal endpoints reject arbitrary model tokens.
- Sidebar visibility does not imply access by itself.
- Runtime templates avoid executable inline scripts and inline style attributes,
  with narrow exceptions for JSON data and dynamic font CSS.
- Sensitive fields are masked in logs and excluded from autofill.
- Redirects and `next` URLs are checked for safety.
- Backup/restore is superuser-only.

## 44. Scaffolding

The `dlux` CLI creates two kinds of artifacts.

`dlux startproject` creates a Dlux-ready Django project with:

- `config/` settings/urls/asgi/wsgi/celery package
- Dockerfile
- compose files
- nginx config
- generated secrets env
- gunicorn config
- entry/start scripts
- SMTP relay helper
- `dlux-updater` service and `dlux_runtime` volume
- project-owned runtime supervisor and nginx maintenance page
- docs and tests
- requirements pinned to the current `django-lux[updater]` version

`dlux startapp` creates a Dlux-native app skeleton with:

- models
- forms
- filters
- tables
- views
- urls
- translations
- templates
- tests
- app README

With `--register`, it patches `INSTALLED_APPS` and root URLs between Dlux-owned
markers. The scaffold refuses to overwrite existing files or non-empty project
directories.

### Generated Compose runtime and inline updates

Dlux remains an in-process Django app. Generated projects add a deployment
loader around it: the same project image supplies web, Celery, and updater
containers, while the persistent `dlux_runtime` volume can select a verified
versioned package directory ahead of the baked environment on `PYTHONPATH`.

The updater discovers stable non-yanked releases from official PyPI, verifies
the wheel hash and repository/workflow attestation, evaluates the packaged
release manifest, and rejects Python, dependency, platform, updater-schema, or
migration-policy incompatibility as an image-rebuild requirement. A compatible
apply is serialized in the database, staged with `pip --target --no-deps`,
preflighted in a fresh subprocess, backed up, migrated and collected under
maintenance, switched atomically, restarted through the generation counter,
and verified against web/Celery before maintenance clears.

The updater never receives the Docker socket or a published port. Web, Celery,
and nginx mount the runtime volume read-only. Failed work before the pointer
switch leaves the active release unchanged; failed health after switching
restores the previous code/static selection but never automatically restores
the database. See [Verified Inline Updater](inline-updater.md).

## 45. Management Commands

`dlux_setup` appends the recommended settings helper if missing, optionally runs
makemigrations/migrate for Dlux, and runs `dlux_check`.

`dlux_check` validates installed app presence/order, middleware, context
processor, URLs, Crispy settings, and settings helper wiring. It prints concrete
snippets for missing pieces.

`dlux_settings` manages the singleton: status, configure/unconfigure, delete,
reset, export, and import.

`dlux_prune_activity_log` enforces configured user/system/audit retention and
supports a non-mutating `--dry-run`.

`dlux_migrate_from_microsys` migrates a fully migrated `django-microsys` 2.4.1
database by renaming tables, updating content types, rewriting migration
history, and rewriting activity log model keys. It is dry-run by default.

`dlux_update_worker` is the generated-Compose queue/check worker. `migrator`
owns generated-project migration/static/superuser bootstrap, and
`seed_activity_log` is a development data helper.

## 46. Optional SSO Packages

SSO lives under `tools/` as separate packages and is not imported by core Dlux
runtime.

The provider package `django-lux-sso` is an OIDC provider plugin. Its conceptual
authorization decision requires:

- authenticated active user
- active client policy
- exact registered redirect URI
- HTTPS unless localhost is explicitly allowed
- active per-client user role or allow-all-authenticated policy

Claims include standard identity fields plus portable `dlux_sso_role` and
`dlux_sso_client_id`. The role is client-specific and is not a Django permission
dump.

The client package `django-lux-sso-client` is a lightweight Django SDK. It links
accounts by `(issuer, subject)`, optionally creates local users, syncs selected
profile fields, maps portable roles to staff/groups, and never turns provider
`admin` into local `is_superuser`.

## 47. Release And Packaging

The main package version source is the `version` field in
`dlux/release-manifest.json`, read by `dlux.__version__` and consumed by
`pyproject.toml`. (The manifest already ships in the wheel for the updater, so it
doubles as the version source — there is no separate `VERSION` file.)

Releases are tag-driven. The GitHub workflow checks that the pushed tag matches
the manifest version, builds the distribution, publishes to PyPI through Trusted
Publishing, builds `dlb-viewer` binaries, and attaches artifacts to GitHub
Release notes extracted from `CHANGELOG.md`.

Every core wheel packages `dlux/release-manifest.json`. An inline-safe release
must pass the release workflow's manifest/version, migration-operation, wheel,
dependency, and updater compatibility gates before publication; the runtime
updater independently re-verifies the official PyPI artifact and attestation.

Companion SSO packages have their own version files, tag prefixes, and release
workflows.

## 48. Tests And Verification Surface

The test suite is broad and concept-driven. It covers:

- settings helper behavior
- configuration defaults and normalization
- URL/root middleware behavior
- setup wizard rendering and persistence
- import/export of settings
- sidebar and navbar discovery
- table adoption, density, pagination, row actions
- permissions UI and staff tiers
- API scope and preference behavior
- model discovery and generated classes
- activity logging and sensitive-field masking
- security hardening for modal/user/section endpoints
- 2FA, OTP hashing, rate limiting, trusted devices, session revocation
- public registration
- report overview and backups
- full `.dlb` backup/restore
- scaffolding
- updater manifest/discovery/verification/state transitions and bootstrap CLI
- runtime supervisor switching, signal forwarding, and Compose/nginx wiring
- SSO provider/client helpers
- static/template CSP and no-inline regressions

The CI workflow runs the curated package Django suite through
`dlux/tests/test_all.py` with the shared `dlux.tests.settings` harness. That
suite includes `test_defaults_and_urls`, scaffold, backup/report, notifications,
permissions, middleware, and utility coverage.

## 49. Major Invariants

These invariants appear across the codebase:

- Normalize before use.
- Prefer explicit backend permission helpers over template assumptions.
- Treat database settings as runtime policy, not business data.
- Keep scoped data boundaries close to managers/querysets.
- Preserve user preferences only when still allowed by current system policy.
- Keep UI strings translatable through Dlux catalogs.
- Use stable model keys for reports and audit identity.
- Keep operational tracking out of activity logs.
- Keep active Dlux releases immutable and switch only the atomic pointer.
- Treat dependency or unsafe-migration changes as image rebuilds, not inline updates.
- Avoid inline runtime behavior in templates.
- Let host apps follow conventions; fill missing pieces by discovery.
- Keep optional SSO and backup viewer separate from core package imports.

## 50. Current Follow-ups And Operational Risks

The current source and tracker identify these follow-ups:

- External/manual probes such as `test_m2m.py` and `verify_detailed_logs.py`
  remain outside the curated package CI labels until they are converted to the
  shared harness.
- The fallback download/export helper has historically been noted as an area to
  harden around referer handling. In current source `_safe_referer()` uses
  `url_has_allowed_host_and_scheme()`, which is safer than raw referer trust,
  but high-risk deployments should still prefer explicit fallback URLs.
- The large `SystemSettingsForm` and frontend setup wizard are the densest
  coupling point in the codebase. Most runtime config flows converge there, so
  regressions in field preservation or hidden JSON controls can have broad
  effects.
- The inline updater deliberately supports only recognized generated Compose
  layouts and the core `django-lux` package. Companion SSO packages, custom
  indexes, bare-metal installs, dependency-changing releases, and zero-downtime
  rollout remain rebuild/manual deployment concerns.

## 51. Simplest Mental Model For Future Work

When changing DjangoLux, ask these questions in order:

1. Is this a default, project setting, database setting, user preference, or
   request/session state?
2. Where is it normalized?
3. Where is it exposed to templates/JS?
4. What backend helper enforces the same decision?
5. Does it interact with scope, language, theme, table density, sidebar/navbar,
   setup import/export, activity logs, or backups?
6. Does it need tests at the model/helper, view, template, and JavaScript
   contract levels?
7. Does it need docs, changelog, and setup/export compatibility?

Most bugs in this codebase are likely to come from one layer changing without
its paired resolver, template bridge, JavaScript consumer, permission helper,
or test being updated.

## 52. What This Package Ultimately Provides

At the smallest level, DjangoLux provides constants, helpers, templates, CSS,
JavaScript, model mixins, forms, filters, tables, and management commands.

At the largest level, it provides an operating model for internal Django apps:

- a superuser can configure the system after install;
- users can personalize safe parts of the interface;
- staff visibility is derived from scopes and explicit permissions;
- ordinary models can become tables, filters, modal forms, sections, reports,
  and downloads by convention;
- actions are logged and reportable;
- security-sensitive flows require explicit backend checks;
- the full system can be snapshotted and restored;
- projects can be scaffolded into the expected shape;
- generated Compose projects can activate compatible verified Dlux releases
  without rebuilding the project image;
- optional SSO can be added without changing core runtime assumptions.

The main architectural bet is that a Django project becomes easier to operate
when the platform owns repeated cross-cutting decisions centrally, while host
apps remain ordinary Django apps at their edges.
