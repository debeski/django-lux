# System Settings persistence audit — 2026-10-20

## Result

The catalogue has several persistence defects; the language override is one
example of a wider missing-field preservation problem. Six defect groups were
reproduced against the stable **DjangoLux 1.12.0 source**, commit `0b3e4ee`.
The findings below describe the released baseline. Repairs are implemented on
this branch in candidate `1.12.1b1`; production was not modified and the
candidate has not been published.

## Repair status

All six defect groups have corresponding runtime fixes and registered
regressions in `dlux.tests.test_settings_persistence`:

- Ownership is derived from the real layout; inactive POST/file controls are
  protected before validation. A completeness guard fails for unowned fields.
- Import normalization retains presence; review/apply use patches, while full
  form saves and snapshot restores explicitly replace complete groups.
- Redacted/partial imports retain the stored SMTP token, including command/API
  calls using the default secret flag; explicit non-DB storage clears it.
- App namespace writers lock the current row and update only `extra_config`.
- One dependency-free parser owns boolean tokens across the normalizers.
- Notification actor/watch settings survive reconstruction.

All 16 regression tests pass on PostgreSQL, including an actual blocked
second-writer test; the SQLite run skips that one database-specific case.
CI and release builds require the reusable PostgreSQL workflow; its exact
settings module and test command also pass locally against PostgreSQL 17.
The original 72-save matrix now preserves the reported toggles, the 20
credential probes retain their secret, and both stale namespace probes retain
the other namespace. Final package-suite evidence is recorded in `tracker.md`.

The audit is on `audit/settings-persistence-audit`, separate from the existing
`codex/system-settings-standardization` work. That branch's unfinished audit was
read as a lead; the findings below were independently exercised.

## Confirmed findings

### P1 — unrelated single-step saves can reset fourteen editable toggles

For every step, save a valid single-step payload, retaining required hidden
fields but omitting controls owned by other sections. Start with the saved
toggle on. Each of these settings becomes false on all 17 unrelated sections:

| Settings section | Affected settings |
| --- | --- |
| Languages | `allow_user_language_override` |
| Appearance | `allow_user_theme_override`, `allow_user_font_override` |
| Security | `public_registration_enabled`, `registration_throttle_enabled` |
| Titlebar | `titlebar_accent_edge`, `titlebar_show_home_button`, `titlebar_show_language_switcher`, `titlebar_show_logo`, `titlebar_show_title` |
| Sidebar | `sidebar_enabled`, `sidebar_accent_edge` |
| Navbar | `navbar_enabled` |
| Login page | `login_show_logo` |

The form accepts the request and persists the unwanted change. An omitted
checkbox becomes false; these controls lack the complete ownership-aware
preservation used by other settings. Full HTML submissions and stale form
submissions were also tested, separately. A fresh full HTML submission need not
trigger the omission defect: it can still include a checked control from a
hidden section. The failure is not a claim that every save always resets every
listed setting. Disabled, omitted, or stale controls expose the unsafe contract.

**Repair contract:** only the active section may change its owned settings;
unrelated fields must be restored from the authoritative database row even if
a stale hidden value is posted. The active section must retain explicit off
semantics. Test every field against every unrelated section.

### P1 — partial imports reset unspecified neighboring settings

Starting with authentication toggles on, importing only
`{"email_2fa": false}` also disables strong-password enforcement, forgot-password
support, inactivity timeout, multiple-session prevention, and purge-on-exit.
`normalize_system_settings_import_payload()` expands the supplied auth field
into a whole default-filled group before applying it. Both nested and legacy
flat inputs were tested.

Partial nested imports were exercised in all 18 groups with a default boolean
leaf. Multiple groups reset siblings. A partial `extra_config` import containing
only ScanLink removes the saved PDF namespace, an unrelated app namespace,
entry-clipboard configuration, and weather configuration.

This contradicts the settings-import view's documented promise that an absent
key is left alone. Whole-group replacement can be supported, but must be
explicit and distinguishable from a partial patch. Preview/review and apply
must share the same presence-aware semantics.

### P1 — redacted email import erases the stored SMTP secret

Create a real encrypted test password, export the settings, then apply the
export with `preserve_email_secret=True`. Export correctly redacts the secret;
apply replaces the stored email configuration without merging back the existing
encrypted password. The persisted secret is lost. A partial email timeout
import with that same flag also loses it.

All 18 ordinary section saves preserved the same test secret. This finding is
specific to the import boundary, not a blanket email-save failure.

**Repair:** preserve the current encrypted credential when an import omits or
redacts it; make intentional credential clearing an explicit operation. Cover
import, snapshot revert, and partial email patches in regression tests.

### P1 — stale app settings writers overwrite unrelated newer values

Both `write_app_system_config()` and `write_app_system_configs()` read the cached
singleton and save the whole settings row without an authoritative refresh and
row lock. A deterministic stale-instance test writes a new second namespace
to the database, then saves a different namespace through each writer using
the older instance. Both remove the newer second namespace.

**Repair:** merge into a freshly locked row inside a transaction, then write
only the intended storage fields. Test independent namespaces and grouped
writers; refreshing without locking does not close a concurrent-write race.

### P1 — imported string booleans can reverse the intended value

Across 624 probes (`false`, `0`, `off`, `true`, `1`, `on`) on 104 default boolean
leaves, the following 15 groups interpret the literal string `"false"` as true
on at least one leaf:

`auth`, `email`, `registration`, `public_root`, `layout`, `language`, `theme`,
`typography`, `login`, `titlebar`, `search`, `sidebar`, `navbar`, `log`, `profile`.

There were 237 mismatched probe results. This count includes repeated tokens,
derived values and dependency normalization; it is not 237 distinct defects.
The direct examples `email_2fa="false"` and
`public_registration_enabled="false"` become true. Accepted import values
must either be parsed consistently or rejected with an explicit type error.
Ordinary checkbox POST handling is a separate path.

### P2 — no-op saves rewrite supported notification values

Using the full server-rendered form payload, saving any section changes stored
`notification_config.automatic.include_actor=True` to false. With the inverse
fixture, `automatic.watchable=False` becomes true. The group reconstruction in
`SystemSettingsForm.clean()` hard-codes these values even though the normalizer
and import accept other values. Hidden notification fields make an unrelated
section take that reconstruction path as well.

**Repair:** preserve these stored leaves unless explicitly edited. If these
values are intentionally fixed framework policy, enforce that consistently at
normalization/import time rather than changing them on unrelated saves.

## Catalogue coverage

All 18 UI sections were exercised in both enabled and disabled fixtures.
All 183 fields instantiated with optional PDF controls were inventoried.

| Storage group | Schema-declared fields | Audit coverage / result |
| --- | ---: | --- |
| Authentication | 12 | Save matrix, individual edits, partial imports, boolean coercion; import sibling resets. |
| Email | 10 | Save matrix, edits, imports, real encrypted secret; import secret loss. |
| Registration | 8 | Save matrix, edits, imports, coercion; toggle preservation gaps. |
| Public root | 8 | Save matrix, edits, imports, compatibility mirrors, coercion. |
| Homepage | 0 | JSON round trips, partial imports and compatibility mirrors. |
| Client IP | 3 | Save matrix, field edits, registry tests; custom header is correctly ignored unless custom mode is selected. |
| Notifications | 0 | Save matrix, field edits, imports, coercion; unsupported preservation of two stored leaves. |
| Layout | 22 | Save matrix, field edits, imports and coercion. |
| Languages | 3 | Save matrix, toggle edits, imports, custom-language tests; preservation gap. |
| Themes | 3 | Save matrix, picker edits, imports and custom-theme tests; override preservation gap. |
| Typography | 3 | Save matrix, font edits, imports and custom-font tests; override preservation gap. |
| Login page | 0 | Save matrix, hero text edits, JSON round trips and imports; logo toggle gap. |
| Titlebar | 0 | Save matrix, field edits, JSON round trips, imports and coercion; multiple toggle gaps. |
| Search | 0 | Save matrix, field edits, imports, canonical/legacy mirrors and coercion. |
| Ribbon | 0 | Save matrix, choice edits, JSON round trips and step-anchor tests. |
| Sidebar | 0 | Save matrix, field edits, imports, coercion and dependent-control tests; toggle gaps. |
| Navbar | 0 | Save matrix, field edits, imports, coercion and dependent-control tests; enabled toggle gap. |
| Logging | 0 | Save matrix, field edits, nested boolean coercion and imports. |
| Profile | 0 | Save matrix, field edits, imports, coercion and homepage compatibility. |
| Backups | 12 | Save matrix, bounded field edits, partial imports and existing backup-option tests. |
| Extra Features | 0 | ScanLink, weather, entry clipboard, optional PDF controls, namespace preservation and partial import tests. |

Eleven groups declare no individual `SettingField` entries. Branding/assets and
scalar defaults also live outside that schema. Group metadata still uses
`access_security`, `login`, and `advanced`, while the UI has different step
slugs; layout storage also spans several real UI sections. Group-level metadata
alone cannot safely infer field ownership.

## Verified non-defects and exclusions

- Four real managed image selections survived all 18 section saves: logo,
  favicon, login logo and login background (72 asset assertions).
- SMTP encryption survived every ordinary section save; exports did not expose
  the test password or its ciphertext.
- Fresh full-payload edits of the language/theme/font override toggles worked;
  the reported issue is cross-section preservation.
- A sidebar-hosted theme picker correctly moves to the titlebar if its sidebar
  host is disabled. SSL/TLS mutual exclusion, timeout lower bounds, nonpersistent
  email-test recipients/password inputs, disabled weather controls, and invalid
  recipient removal were classified as policies, not new defects.
- One invalid backup target and enabling weather without a key were rejected;
  they were not counted as successful edits or persistence bugs.

## Evidence and limits

Environment: local Python 3.13 / Django 6.1, released 1.12.0 source, in-memory
SQLite and isolated local-memory cache. No live SMTP send, production mutation,
release, or deployment was performed. These are server/form/storage probes,
not a new end-to-end browser acceptance run. Stale-write tests model the lost
update deterministically; they do not measure PostgreSQL scheduling.

- 72 valid step saves: 18 sections × two fixtures × full/step-only payloads.
- 149 individual field mutation attempts: 147 valid, two correctly rejected.
- 18 valid stale-full-form saves; 18 partial nested import probes, three flat/
  Extra Features patch probes, and two export/import round trips.
- 624 boolean normalizer probes across all default boolean leaves.
- 20 SMTP-secret boundary probes; 18 managed-asset probes; two stale app writers.
- Existing focused suites: **308 tests, 306 passed and two skipped**. Existing
  passing tests do not cover the newly reproduced failure contracts.

Scripts, full JSON inventories, per-field outcomes and logs are retained in
`.xclude/validation/settings-catalog-audit-2026-10-20/`. Run `probe.py`, then
`extended.py` and `boundaries.py` with the repository interpreter. Each creates
its own in-memory database. The audit scripts are evidence artifacts rather
than newly registered passing regression tests.

Before a framework release, run the existing beta-channel acceptance against
the published candidate. No tag, push, publication or production deployment is
part of this repair turn.
