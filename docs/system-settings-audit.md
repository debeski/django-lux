# System settings integration audit and standard

Audited 2026-10-03 against main `02f0eb4` (v1.10.2b1), plus the separate,
uncommitted `codex/entry-clipboard` implementation. This report distinguishes
existing behavior from the proposed integration contract. It does not claim
that the runtime has already been standardized.

## Status (2026-10-21)

This report is the 2026-10-03 baseline. A second, test-driven catalogue audit
(`system-settings-catalog-audit.md`) repeated its high-priority findings, and the
repairs shipped in 1.12.1 and 1.12.2b1:

| Finding | Status |
| --- | --- |
| String booleans read as true | Fixed in 1.12.1 — one parser, `dlux.system.booleans.parse_boolean` |
| Patch, replacement and reset not explicit | Fixed in 1.12.1 — imports patch supplied keys; complete forms and snapshot reverts replace explicitly |
| Refresh is not concurrency protection | Fixed — app writers and import apply/revert locked in 1.12.1; ordinary section saves locked and re-based in 1.12.2b1 |
| Inactive-step fields overwritten (ownership) | Fixed in 1.12.1 — ownership derived from the rendered layout |
| Precedence differs between groups | Fixed in 1.12.2b1 — every group gate uses `db_override_policy` through `db_group_applies()`; Extra Features and app namespaces merge per entry |
| ScanLink reloads the live preview | Fixed in 1.12.2b1 — `NONVISUAL_PREVIEW_FIELDS` marks nonvisual controls server-side |
| Obsolete `setup_step`/`admin_section` metadata | Open — nothing reads it |
| Import review groups Ribbon under Layout | Open — hand-written `GROUPS` table in `settings_diff.py` |
| Simplifications (dead normalizer copies in `utils/config.py`, duplicate default builder, hand-written import alias table) | Open |

## Decision

Keep `dlux.system` as the canonical configuration layer and make its registry
drive integration. Combine the schema-backed form helpers with Weather's
step-scoped configure/clean/apply lifecycle, app settings' declarative controls,
and the live import review's explicit selection policy. No existing group is a
complete reference implementation.

Do not introduce a second settings framework, flatten every nested builder, or
make every form field a legacy model property. Complex navigation builders,
secret handling and compatibility adapters need explicit hooks; ordinary
booleans, choices and numbers should not need bespoke routing in five places.

## Coverage

The registry covers all 21 model JSON fields ending in `_config`; its existing
test verifies that coverage. It is not a complete inventory of editable fields:
branding, managed assets and some scalar selections live outside those groups.
Eleven groups declare no individual `SettingField` entries. That is acceptable
for opaque builders, but ordinary controls in those groups lose the benefits of
shared initial-value and save routing.

The table records verified integration weaknesses, not a claim that every
operation in a group is broken. “String boolean” means a direct normalizer probe
with a boolean leaf set to `"false"` returned `True`.

| Integration | Useful existing pattern | Gap or unnecessary complexity |
| --- | --- | --- |
| Branding and managed assets | Native asset fields and per-step identity cleaners | Outside group schema; needs explicit inventory rather than the docs' claim that every setting is grouped JSON. |
| Authentication | Schema-backed initials/save; bounded numeric normalization | String boolean; obsolete `access_security` step metadata. |
| Email | Normalization, portable secret redaction, explicit verification fingerprint | Schema omits newer enabled/verification/provider/timeout/recipient fields; obsolete step metadata; `password_configured` accepts string truthiness. Secret and verification hooks are justified. |
| Registration | Schema-backed fields and validation | String boolean; obsolete step metadata. |
| Public-root compatibility | Explicit mirrors to canonical homepage | String boolean; two representations are intentional temporary compatibility, not a model for new settings. |
| Homepage | Canonical nested config, compatibility synchronization and runtime promotion | No field declarations; compatibility branches require retirement, not further copies. |
| Client IP | Small typed schema with bounded proxy hops | Obsolete step metadata; runtime assembly still routes it manually. |
| Notifications | Default-aware boolean coercion and nested normalization | No field declarations; bespoke runtime nested merge policy must be explicit. |
| Layout | Most complete schema-backed ordinary control integration | String boolean; group spans Layout, Branding, Security and Ribbon, so a single group step cannot own every field. |
| Languages | Registry fields and translation-layer merging | String boolean; scalar default language remains separately routed. |
| Themes | Registry fields and allowed-theme normalization | String boolean; default theme and scope behavior remain bespoke. |
| Typography | Registry fields and font registry validation | String boolean; default font and per-language matrices require explicit adapters. |
| Login page | Dedicated cleaner and native layout | String boolean; no fields declared; `login` metadata differs from actual `login_page` slug. |
| Titlebar | Native builder and canonical search compatibility bridge | String boolean; no fields declared; carries old search storage as well as its own controls. |
| Search | Own canonical group and legacy promotion | `enabled` uses default-aware parsing but `include_data` uses truthiness; no fields declared. |
| Ribbon | Opaque structural normalizer and native builder | No fields declared; default factory is empty, so leaf-default probes do not cover all builder values; import review currently places ribbon under Layout. |
| Sidebar | Route sanitization and discovery integration | String boolean; no fields declared; runtime entries are combined with project entries instead of using ordinary group replacement. |
| Navbar | Route sanitization and native builder | String boolean; no fields declared; nonempty DB defaults override project values even before setup is configured. |
| Logging | Nested defaults and event/action filtering | String boolean including nested event toggles; no fields declared. |
| Profile/onboarding | Nested normalization and canonical homepage bridge | String boolean; no fields declared; compatibility home override is duplicated. |
| Backups | Typed schema, default-aware booleans and bounded numbers | Better coercion baseline; hand-written initial/import/save integration persists despite schema. Operational scheduling hooks are justified. |
| Extra Features container | Empty package default preserves project namespaces | `advanced` metadata differs from actual `extras`; opaque namespaces and framework features lack one registration contract. |
| ScanLink | Simple namespaced toggle | No namespace normalizer; initial read precedes authoritative row refresh; no inactive-step field disabling; setup upload does not map the toggle; step-wide live preview treats it as visual. |
| Weather | Configure after refresh, disable fields outside its step, independent clean/apply hooks, portable key policy | Boolean aliases differ from other groups; frontend/backend import mapping is duplicated. It is the best form lifecycle reference, not the best complete integration. |
| Entry clipboard, separate feature branch | Canonical default/normalizer, after-refresh initial, independent apply guard, both setup import paths, authenticated asset gate | Nonvisual preview exclusion is a field-specific JS list; ScanLink still needs the same contract. Keep automatic reuse in sticky forms/save-add-more. |
| Project-owned app settings | Declarative registration, generated native fields, namespace-preserving writes, grouped save, size cap, audit event | Writers read cached singleton and save whole row without locking; concurrent namespace edits can overwrite each other. `json.dumps(default=str)` undermines the stated rejection of non-JSON values. |

## Verified behavioral findings

### High priority: boolean interpretation changes meaning

`normalizers.py` has three competing conventions: Python `bool`,
`_coerce_import_bool`, and default-aware `_to_bool`. Weather has another accepted
value set. These are observable differences, not styling issues.

- `normalize_auth_config({'email_2fa': 'false'})['email_2fa']` is `True`.
- `normalize_system_settings_import_payload({'auth_config': {'email_2fa': 'false'}})`
  exports that interpretation as `email_2fa=True`.
- `normalize_search_config({'include_data': 'false'})['include_data']` is `True`,
  while its `enabled` control correctly parses false.
- Imported `extra_config.scanlink.enabled='false'` remains a string; ScanLink's
  form initializer then applies `bool(...)` to it.

Default-leaf probes found the same problem in registration, public root, layout,
language, theme, typography, login, titlebar, sidebar, navbar, logging and profile.
Backups, homepage and notifications passed those false-string probes. Email's
derived credential marker needs a separate policy from an editable toggle.

**Required contract:** one typed boolean parser with documented accepted strings
and a supplied fallback for missing/invalid values. A normalizer must return
booleans. Apply it at the input boundary, not repeatedly in consumers. Do not
change security defaults silently while consolidating parsing.

### High priority: patch, replacement and reset are not explicit

The live import review says absent keys remain unchanged. However, expansion of
`{'auth_config': {'email_2fa': False}}` synthesizes the other auth defaults as
flat import keys. A partial flat auth payload also creates a full normalized
group. Thus file presence and default expansion cannot be treated as equivalent.
Whole-group replacement can be valid, but must be explicit to the operator and
must not masquerade as an absent-key-preserving patch.

**Required contract:** retain raw presence information separately from normalized
values; patch changes only supplied paths; replacement is explicitly selected;
reset applies canonical defaults explicitly. Preserve meaningful false, zero,
empty-string and empty-list values. Setup bootstrap and live import may use
different operations, but must call the same normalization and routing layer.

### High priority: refresh is not concurrency protection

The core form refreshes a bound modal instance before building initials, which
addresses an existing stale-cache bug. ScanLink reads its initial before that
refresh. App namespace writers still call cached `SystemSettings.load()`.
Neither refreshing once nor grouping writes protects a later whole-row save
against an intervening write by another request.

**Required contract:** authorize, validate, then apply the requested paths to a
fresh database row inside a transaction. Use row locking or a revision check;
save owned storage fields and invalidate caches after successful persistence.
Compatibility mirrors must be included in that transaction. Keep preview drafts
outside this writer; they must never persist settings or operational effects.

### Medium priority: precedence differs between groups

`_build_system_config()` uses configured-or-non-default logic for auth, homepage,
search, notifications, logs, profile and backups. Sidebar, navbar, email and login
instead admit any nonempty database dictionary. A default-valued singleton can
therefore override project configuration differently by group before setup.
Extra config is admitted when nonempty and replaced as a whole in ordinary layer
assembly; a saved framework namespace can displace unrelated project namespaces.
Sidebar entries have a separate DB-plus-project deduplication rule; translations
merge by language; notifications merge nested sections.

`SettingGroup.db_override_policy` is declared but not consumed. It currently
describes a policy that several runtime branches do not enforce.

**Required contract:** one resolver with explicit, tested per-group precedence and
merge policy. Preserve intentional navigation/translation behavior as named
adapters. Establish empty-value and namespace-deletion semantics before changing
merges; a blanket recursive merge would make intentional clearing unreliable.

### Medium priority: UI ownership and preview eligibility are duplicated

Six groups refer to obsolete slugs: auth, email, registration and client IP use
`access_security`; login uses `login`; extra uses `advanced`. Layout says
`appearance` despite owning controls in multiple actual steps. No runtime consumer
currently uses this metadata to choose the active form step, so it is misleading
metadata rather than the direct cause of current step-save behavior.

Import review has another handwritten grouping table: Ribbon lives under Layout,
and Extras is `extra`. Preview uses a step-wide `GLASS_STEPS` set. Consequently a
nonvisual ScanLink change in Extras can launch a background-page replacement.
Clipboard already demonstrated this class of sidebar disturbance and added a
local exclusion on its feature branch.

**Required contract:** field-level UI step and preview effect (`none`, `page`, or
explicit target), separate from storage ownership. Derive navigation, import
review grouping and preview change detection from that ownership. Draft submission
must still contain nonvisual values even when they do not trigger preview.

## What to simplify, and what to retain

Simplify duplicated default construction in `build_default_system_config`, manual
import aliases, repeated backend/frontend upload field maps, repeated ordinary
initial/save mappings, and handwritten export group normalization dispatch. Several
old normalizer bodies in `utils/config.py` are overwritten by aliases to the
canonical functions later in the module; these are misleading maintenance copies.
Public aliases and migration-history wrappers must remain importable.

An absent alias in `get_import_aliases()` is **not by itself an import failure**:
`expand_system_config_groups()` resolves registry aliases first. `public_root`
and `languages` intentionally collide with established flat inputs. Replace the
manual table only with collision-aware derivation and behavioral compatibility
tests, not a blind `get_config_aliases()` substitution.

Retain leaf-module boundaries, lazy imports that prevent cycles, managed assets,
native field widgets, route sanitization, encryption/redaction, email verification,
bounded draft storage, explicit import selection/snapshots, and temporary
homepage/search compatibility synchronization. These solve real requirements.
Do not replace server-rendered previews with a second client-side settings engine.

## Standard integration contract

1. **Register once:** declare storage path, default, normalizer/type, form name,
   UI step, export/import policy, legacy aliases, and preview effect. Keep group
   declarations for defaults/merge policy; add field declarations for ordinary
   controls. Treat branding and managed assets as explicit scalar registrations.
2. **Normalize once at boundaries:** factories return fresh containers;
   normalizers tolerate malformed input, clamp numbers and validate choices,
   return stable shapes, and are idempotent. Missing is distinct from false/empty.
   Opaque project namespaces survive normalization.
3. **Use one form lifecycle:** determine step and refresh before initials; disable
   fields outside their owning step; validate active controls; build a patch from
   actually submitted/owned paths. Preserve dependent values while toggles are off.
4. **Use one transactional writer:** patch the fresh row, synchronize documented
   mirrors, save once, invalidate caches and record the actual change. A preview
   uses the same validation/application logic against a copied draft, without the
   persistence, logging or scheduler side effects.
5. **Use one portable import/export path:** schema-derived routing plus explicit
   hooks for assets, route sanitization and secrets. Keep selection/presence
   metadata. The browser applies canonical server mappings rather than maintaining
   an independent interpretation of the uploaded config.
6. **Use one runtime resolver:** defaults → project → permitted DB overrides with
   declared merge semantics. Runtime consumers read resolved canonical paths;
   flat mirrors exist only for shipped compatibility.
7. **Verify behavior, not source spelling:** defaults/project/DB precedence,
   false strings and malformed values, round-trip portability, partial edits,
   inactive-step preservation, two-writer concurrency, secret preservation,
   preview non-persistence, nonvisual preview isolation, authorization, and both
   setup upload modes. Add browser checks for native controls/RTL where relevant.

`legacy_flat=True` is for compatibility with an already shipped flat model/runtime
API. A top-level form control alone does not justify a new flat model property;
`form_name` already maps a control to nested storage.

## Implementation order

**Saved for later:** per user instruction on 2026-10-03, defer implementation
until the clipboard work is finished. Resume this plan on
`codex/system-settings-standardization`; keep the clipboard workstream separate.

1. Characterize current precedence, clearing, import presence and concurrent
   writes with behavioral tests. Fix boolean parsing and ScanLink's lifecycle,
   normalization and import parity first; apply the nonvisual preview contract to
   both ScanLink and clipboard.
2. Introduce the shared patch/writer contract, then adopt core steps and app
   namespaces. Preserve compatibility synchronization and operational hooks.
3. Correct and complete field ownership metadata; derive ordinary form routing,
   review grouping and preview eligibility. Keep builder-specific hooks small.
4. Adopt declared runtime merge policies and schema-driven portable routing;
   retire duplicate implementation bodies while retaining public shims. Any public
   path relocation requires downstream checks and deprecation records.

These are separate behavioral changes, not a release-wide cosmetic rewrite. Do
not silently integrate or deploy this work over the unfinished clipboard branch.

## Validation and limits

176 existing tests passed across registry, settings diff, app registry/groups,
project setup, email and weather on the isolated audit checkout. Direct probes
covered boolean leaves in every registered default dictionary, import expansion,
and step-slug consistency. Empty/default-less builders need their own behavioral
cases; passing existing tests does not prove the identified gaps are absent.

This audit did not change production behavior or the mounted CRM source. Concurrent
write loss and whole-extra replacement are identified from verified writer/merge
code; a live two-request reproduction remains part of phase 1. Clipboard's previous
package/browser verification belongs to its separate feature branch.
