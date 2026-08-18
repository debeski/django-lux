# Deprecation Countdown

Every compatibility workaround DjangoLux still ships, why it exists, and when it
goes away. A shim only earns a place here if removing it today would break a
downstream project; anything else should just be deleted.

**Rules**

- Add an entry in the same turn you add the shim. An undocumented shim becomes
  permanent by accident.
- Give every entry a concrete removal target (a version, not "later").
- Removal is a **major**-version action unless the entry says otherwise.
- When you remove one, move it to *Removed* with the version that dropped it —
  keep the history so the reason survives.

## Active

### Homepage settings compatibility mirrors

- **Introduced:** v1.8.0 (`homepage_config` consolidation)
- **Remove in:** v2.0.0 (next major)
- **Canonical contract:** `SystemSettings.homepage_config` and runtime
  `homepage_config`/`homepage`. The JSON contains `default_url`,
  `allow_user_override`, and a nested `public` object with `enabled`,
  `separate_url`, `url`, `theme`, `title`, `meta_description`,
  `show_titlebar`, and `show_sidebar`.
- **Compatibility kept:** model saves synchronize `home_url`,
  `public_root_config`, and `profile_config['allow_user_home_url']` in both
  directions. Runtime config and setup imports still accept those legacy keys
  and emit their flat aliases. Migration `0016` adds the canonical JSON with a
  database default; the runtime promotes pre-upgrade values immediately and the
  first normal model save persists them canonically.
- **Migration:** move host configuration and direct consumers to
  `homepage_config`; `homepage` and `public_homepage` remain accepted grouped
  aliases during the compatibility window.
- **Safe to remove when:** active projects no longer read/write `home_url`,
  `public_root_config`, or the profile-owned landing-page permission.

### Global-search titlebar compatibility mirrors

- **Introduced:** v1.8.0 (`search_config` extraction)
- **Remove in:** v2.0.0 (next major)
- **Canonical contract:** `SystemSettings.search_config` and runtime
  `search_config`/`search`, containing `enabled`, `display_mode` (`icon` or
  `always`), and `include_data`.
- **Compatibility kept:** model saves synchronize
  `titlebar_config.global_search_mode` and
  `titlebar_config.global_search_include_data` in both directions. Runtime
  config and setup imports accept the old titlebar keys. Migration `0016` adds
  `search_config` with a database default; the runtime promotes pre-upgrade
  titlebar values immediately and the first normal model save persists them.
- **Migration:** move host configuration and direct consumers to
  `search_config`; `search` and `global_search` remain accepted grouped aliases
  during the compatibility window.
- **Safe to remove when:** no active project stores or reads global-search
  options from `titlebar_config`.

### Static path shims: `dlux/main/css/{main,buttons,index_cards}.css`

- **Introduced:** v1.8.0 (static tree reorganisation)
- **Remove in:** next major
- **What it is:** the `main/` static folder became `base/`. These three files
  remain as one-line `@import`s of their `base/` counterparts.
- **Why these three:** a survey of the six active projects (2026-08-09) found
  exactly these paths still linked from project templates:
  | Path | References | Projects |
  | --- | --- | --- |
  | `dlux/main/css/buttons.css` | 8 | project-archive (6), project-sales-crm (2) |
  | `dlux/main/css/main.css` | 2 | project-sales-crm |
  | `dlux/main/css/index_cards.css` | 1 | project-archive |
  A renamed path 404s silently — a missing stylesheet raises nothing, the page
  just renders unstyled — so the breakage would surface as a cosmetic bug report
  rather than an error.
- **Migration:** point project templates at `dlux/base/css/<file>.css`.
- **Safe to remove when:** no project template references `dlux/main/css/`.
- **Related, not shimmed:** project-archive also links
  `dlux/main/css/{navtabs,doc_detail,gen_report}.css` (13 references). Those
  files do **not** exist in DjangoLux and never did at that path — the project's
  own copies live in `documents/static/documents/css/`. Those references are
  already dead and need fixing in project-archive, not here.

### Template path shim: `dlux/includes/messages.html`

- **Introduced:** v1.8.0 (template tree aligned with static)
- **Remove in:** next major
- **What it is:** the flash/alert partial moved to
  `dlux/notifications/messages.html` (it belongs to the notifications feature —
  `dlux.notifications` owns both the drawer and the flash queue). The old path is
  a one-line `{% include %}` of the new one.
- **Why it exists:** `project-sales-crm` includes it directly from
  `public_catalog/templates/public_catalog/public_base.html` in both editions
  (`switch_pos` and `gov_edition`). Unlike a missing stylesheet, a missing
  `{% include %}` raises `TemplateDoesNotExist` — those two public pages would
  have returned 500.
- **Migration:** `{% include 'dlux/notifications/messages.html' %}`.
- **Safe to remove when:** no project includes `dlux/includes/messages.html`.

### `dlux.reports` re-exports of relocated archive primitives

- **Introduced:** v1.8.0 (archive serialization moved out of reports)
- **Remove in:** next major
- **What it is:** `_CursorlessJSONSerializer`, `_model_natural_key_fields`,
  `_safe_archive_segment` and `stream_model_into_zip` now live in
  `dlux/utils/archive.py`, and `_iter_queryset_by_pk` in `dlux/utils/common.py`.
  `dlux.reports` (and `dlux.reports.queries`) re-export them so the historical
  import surface is unchanged.
- **Also here:** `backup_record_folder()` and `build_relation_schema()` in
  `dlux/reports/archive.py` are thin wrappers that re-apply the reports
  config-driven label resolver, because the `utils` versions take an explicit
  `label_field_resolver` and default to no resolver. Removing the wrappers
  silently changes record-folder naming — do not "simplify" them away.
- **Migration:** import from `dlux.utils.archive` / `dlux.utils.common`, and pass
  `label_field_resolver=` when you want the reports naming.

### Package facades (`forms`, `models`, `reports`, `discovery`, `backup`, `translations`)

- **Introduced:** v1.8.0 (Phase 1 package splits)
- **Remove in:** never — this is the public API, not a temporary shim
- **What it is:** each package `__init__.py` re-exports every symbol the old
  single module exposed (51/59/93/67/53/17 names respectively).
- **Why it is listed here:** the re-exports look like dead code to a linter, and
  a "tidy up the unused imports" pass would break every downstream project.
  `dlux/tests/test_package_facades.py` imports the committed split modules,
  verifies declared facade exports, and confirms `dlux/models/__init__.py` keeps
  Django's app registry populated. It never reads `.xpose/` archives.

### Legacy modal chrome normalisation

- **Introduced:** pre-v1.6
- **Remove in:** next major — survey done 2026-08-09, no live fragment depends on it
- **What it is:** dynamic-modal fragments that still return Bootstrap
  `.modal-header` / `.modal-body` / `.modal-footer` chrome are normalised at
  runtime: the embedded title is promoted to the shell, remaining header content
  moves into the body, and footer actions are pinned.
- **Why it exists:** the modal shell owns its own header/footer; older project
  fragments predate that contract.
- **Migration:** return body content only and mark custom button rows with
  `data-dlux-modal-footer`. See `docs/developer-guide.md`.
- **Survey (2026-08-09, six active projects):** every live template carrying
  `.modal-header`/`.modal-body`/`.modal-footer` is a **self-owned** Bootstrap
  modal with its own `.modal` shell, which the normaliser never touches. The
  only chrome-only fragments found sit inside archived
  `.xpose/venv-site-packages/dlux-1.2.2/` copies, i.e. not live code.
  project-dlux-panel's fleet partials already use the modern
  `data-dlux-modal-footer` contract, and project-decrees emits it from
  `documents/forms.py`. No project blocks removal.

### `view.sidebar_exclude = True`

- **Introduced:** superseded by `dlux_exclude` / `dlux_include`
- **Remove in:** next major
- **What it is:** the released per-view flag that hides a view from every sidebar
  feature; still honoured alongside the newer profile-aware attributes.
- **Migration:** `dlux_exclude = True` (or a profile name / iterable of names).

### Cookie-based assisted-entry prefill (`enable_prefill`)

- **Introduced:** ≤ v1.5.10, retired in v1.8.0
- **Remove in:** n/a — shim already gone; kept here as a migration note
- **What it is:** assisted entry used to gate on an `enable_prefill` cookie
  defaulting to `'true'`. It is now two `Profile.preferences` keys,
  `autofill_from_related` and `sticky_forms`, read server-side through
  `dlux.utils.sticky_forms_enabled()` / `sticky_form_initial()`.
- **Outstanding:** `project-decrees` still reads the cookie and needs converting
  the way `project-archive` was.

## Watch list

Not shims, but known compatibility exposure to keep in view.

- **Static path reorganisation (v1.8.0).** The whole `dlux/static/dlux/` tree was
  regrouped by feature. Any project template that links a DjangoLux stylesheet or
  script by path is affected, not just `index_cards.css`. Only that one file has
  a shim, because it is the only asset DjangoLux does not load itself. Publish the
  full old → new path table in the release notes.
- **Collected static.** Renamed assets keep serving from a project's existing
  `collectstatic` output until the next collect. A deploy that skips
  `collectstatic` will serve the old tree with new templates.
- **Template tree reorganisation (v1.8.0).** `dlux/templates/dlux/includes/` was
  dispersed into feature folders. Audited against the six active projects: they
  reference `dlux/base.html`, `dlux/form_base.html`, `dlux/list_base.html`,
  `dlux/forms/assets_head.html`, `dlux/forms/assets_scripts.html` and
  `dlux/helpers/dynamic_modal_form.html` — all still valid — plus
  `dlux/includes/messages.html`, which is now shimmed. `dlux/includes/` remains
  the project extension namespace (`custom_head.html`, `custom_scripts.html`,
  `custom_footer.html`); those three paths are unchanged and are not deprecated.
- **`UserDetailModalView` response format (v1.8.0).** `/sys/users/<pk>/modal/`
  now returns the dynamic-modal contract `{"html": …}` instead of a raw HTML
  body, so the row action can use the shared `dlux:dynamic_modal:open` event. A
  project fetching that URL and injecting `response.text` directly must read
  `response.json().html`. No shim: the endpoint is internal to the user table,
  and no active project calls it.

## Planned removals (not yet shims)

### The in-container inline-update executor

- **Deprecated in:** v1.8.0 — **removed in v1.9.0**
- **Plan:** `docs/updater-consolidation.md`
- **Composer is a hard requirement from v1.8.0.** Inline updates need a Composer
  service in the deployment (latest stable image), in addition to Composer being
  the deployer. This is the intended direction — DjangoLux is being stripped of
  outbound responsibilities and Composer handles them from outside. A stack
  without one has no update path; `composer check --fix` installs the services.
- **What goes in v1.9.0:** PyPI polling, wheel download and attestation, release
  staging, `dlux enable-updater`, the `DLUX_UPDATE_EXECUTOR="inline"` escape
  hatch and the inline branches it selects, and the `updater` optional
  dependency (`pypi-attestations`). Composer executes the update; DjangoLux
  states intent, as it already does for image updates.
- **NOT removed — corrected 2026-08-11:** the `dlux-updater` Compose service and
  the `dlux_update_worker` / `dlux_reconcile` commands. An earlier draft listed
  them. Verified against `compose.yml.tmpl`: the service also runs
  `dlux_reconcile` and `migrator`, `web` declares
  `depends_on: dlux-updater: condition: service_healthy`, and
  `dlux_update_worker` is the only caller of `UpdateService.process_next()` —
  the queue drainer that writes the hand-off. Removing them would delete the
  migration gate and the intent producer, not just the executor.
- **What stays permanently:** the supervisor (bootstrap — it must live in the
  baked image), the state models, the admin UI, and the runtime volume itself.
  Inline updates remain inline; `inline_safe` in the release manifest still
  decides whether a release may be applied without an image rebuild.
- **Why a release of overlap:** in 1.8.0 the DjangoLux side keeps working exactly
  as before, so a deployment can upgrade into 1.8.0, migrate its stack to the
  Composer-side updater at its own pace, verify it, and only then move to 1.9.0.
  Nothing is forced within a single release.
- **Why it must not be removed in 1.8.0:** a deployed `compose.yml` is
  project-owned and names `dlux_update_worker`, `dlux_reconcile` and the
  supervisor in the `dlux-updater` service, which is `restart: always` and
  labelled `org.dlux.restart: "protected"`. Deleting any of them in the release a
  box upgrades *into* turns that service into a protected crash loop — the exact
  failure project-archive is already in.
- **Migration:** `composer check --fix` retires the `dlux-updater` service once
  the deployed runtime is 1.8.0 or newer, preserving named volumes. The
  Composer-side updater is expected to be the more stable path: it stages and
  verifies a release *before* activating it, and health-gates the restart from
  outside the container being swapped, which an in-container updater cannot do.
- **Safe to remove when:** every active deployment reports a 1.8.0+ runtime and
  no stack still defines `dlux-updater`.

## Removed

### `dlux.constants` — removed in v1.8.0

- **Shipped:** ~v1.2.0 to v1.7.x, when the constants moved to
  `dlux.system.constants` and this re-export was left behind.
- **Removed early on purpose.** It was never listed here, which is the failure
  this document exists to prevent, and it had no consumer: none in the six
  active projects, none in Composer, and inside dlux the `from .constants
  import` sites all resolve to `dlux.system.constants`.
- **The migrations claim, tested and false.** It was believed to be required by
  migrations. Migrations do serialize dlux dotted paths — but
  `dlux.models.default_*_config`, never `dlux.constants`, and those wrappers
  import `..system.constants` directly. Verified by removing the module and
  running `makemigrations --check` (no changes detected) plus the full suite
  (1596 passing). The likely source of the belief is `docs/reference.md`, where
  the sentence about the re-export sat immediately before the real migration
  invariant; that paragraph has been rewritten to separate them.
- **Use instead:** `from dlux.system.constants import ...`.

### Module aliases that never shipped — added and dropped within v1.8.0

`dlux/password_validation.py`, `dlux/stack_contract.py` and
`dlux/runtime_contract.py` were written as re-exports when their modules moved
into `dlux/auth/` and `dlux/contracts/`, then removed before the release.

Recorded here because the *reasoning* is worth keeping, not the shims: each was
added defensively, and a search for consumers found none — not in any of the six
active projects, not in Composer, and inside dlux only in tests that were
trivially repointed. For `password_validation` the alias was redundant by
construction as well, because `dlux_settings()` rewrites a hand-pinned legacy
validator path to the new one at settings-import time, so the old module is
never resolved.

The lesson for the next move: check for consumers *before* writing the shim. A
shim with no consumer still costs a second canonical path, an entry in this
file, and a removal to remember.
