# System Configuration

Use this guide when configuring DjangoLux through `/sys/setup/` or `/sys/options/`.
It is for operators; projects that need code-owned defaults should start with
[Project Configuration](project-configuration.md).

## Configuration layers

### Starting with manual setup

Set `DLUX_SKIP_CONFIG_IMPORT=True` in the web and migrator service environments to
bypass automatic `config.json` import. With Composer 1.5.3 or later,
`./start.sh --skip-config` injects it (also with `-d` or `update`).

Both migration bootstrap and setup-page requests honor the option: the file is
neither read nor changed, and the setup wizard remains available. Explicit settings
imports still work, and existing configuration and data are not reset.

Repeat the flag on later deployments until setup is complete, or declare the
environment variable in Compose for a persistent policy. Restarting the same
containers retains the flag; recreating them without it restores normal auto-import
for an unconfigured database.

### Resolution order

DjangoLux resolves configuration in this order:

1. package defaults;
2. project defaults in `settings.DLUX_CONFIG`;
3. live overrides in the `SystemSettings` singleton; and
4. per-user preferences in `Profile.preferences`.

The first three determine system policy. Personal theme, language, sidebar state,
density, and assisted-entry choices remain user-specific and do not rewrite system
defaults.

## First-launch setup

`/sys/setup/` is the initial configuration workflow. It first asks for the setup
language; that choice affects only the wizard UI. The persisted default language is
selected later in **Languages**.

The wizard has nineteen steps, in the order of `SETUP_STEPS`
(`dlux/system/constants.py`):

1. **Branding** — localized names, logo, favicon, footer, and configuration import.
2. **Languages** — language catalog, default language, user overrides, and
   translation overrides.
3. **Email** — delivery path, provider preset, secrets, test send, and failure
   alerts.
4. **Access and Security** — authentication, sessions, registration, consent, and
   client-IP policy.
5. **Themes and Fonts** — theme and font defaults, allowlists, overrides, and edge
   styles.
6. **Titlebar** — home/logo, actions, language switcher, geometry, and surface.
7. **Sidebar** — navigation tree, visibility, toolbar, toggle icon, and personal
   reordering policy.
8. **Navbar** — hierarchy/history mode, navigation root, and user override policy.
9. **Ribbon** — list-page ribbon behavior and tab configuration.
10. **Tables** — density, accent edges, resizing, sticky headers, zebra stripes, row
    actions, audit fields and soft-delete visibility. They are stored in
    `tables_config`, with synchronized mirrors in `layout_config` and the flat keys
    (see [Table columns](table-columns.md)).
11. **Components** — forms, modals and Options-page layout.
12. **Home and Public Pages** — authenticated homepage, per-user override, and
    anonymous public homepage.
13. **Login Page** — layout, logo treatment, color, and localized hero message.
14. **Profile Page** — user modules, onboarding, devices, and activity feed.
15. **Global Search** — titlebar search display and optional record search.
16. **Notifications** — flash, drawer, badge, bridge, email, and CRUD behavior.
17. **Logging** — activity and audit policy plus retention.
18. **System Backup** — schedule, storage, retention, retry policy, and incremental
    chains.
19. **Extra Features** — opt-in integrations such as ScanLink, weather and the entry
    clipboard.

A project that registers app settings tiles with `register_app_settings()` adds a
**Project Settings** step after these: each tile's own form, one section per tile.
It is always last, so no Dlux step changes number, and it appears only while at
least one tile is not registered with `setup=False`. Finishing setup saves each
section with the rest of the wizard (see
[App settings in first-run setup](ui-integration.md#app-settings-in-first-run-setup)).

System Settings modal editors opened from Options use these same categories but show
only the selected category. Setup export/import is intended for reusable development
and staging configuration: it exports settings JSON, not uploaded logo/favicon
binaries or host-specific email verification state.

### Home pages and search

`SystemSettings.homepage_config` and `SystemSettings.search_config` are the canonical
homepage and global-search stores. The older flat, titlebar and public-page keys are
compatibility mirrors scheduled for removal in v2.0 (see
[Deprecation Countdown](deprecation-countdown.md)); new project code uses the
canonical configurations.

**Assigned landing pages.** With the per-user override on, an administrator can also
choose a landing page for a user (Edit User → Landing Page, from the pages that user
can open) or for everyone in a group preset (Groups → Members' Landing Page). The
order is:

1. the user's own Options choice;
2. the user's assignment;
3. the assignment of the user's first active group, by name;
4. the system Home URL.

An assigned page the user can no longer open is skipped at sign-in. Turning the
override off ignores all of these without clearing them.

### Unsaved previews

A preview is a real page rendered by the server with the unsaved form — never a page
patched in the browser. **Preview** (and a section's eye) POSTs the form to
`system_settings_preview_draft` (`/sys/settings/preview/draft/`), which validates it
exactly as a save would (an Options step adds `?step=N`, as its own save does) and
answers with a short-lived token instead of saving.

A frame then loads an ordinary page with `?_dlux_preview=<token>`. For that one
request `SystemSettings.load()` returns the draft (`dlux/system/preview.py`), so
every template, context processor and project view renders what a save would
produce — the project's own pages and branding included.

A preview request:

- renders in the draft's default language (`_dlux_preview_lang` picks another) and
  keeps the viewer's personal theme, table/form density, modal size and font unless
  the draft changes that default, in which case the new default shows;
- is superuser-only and GET-only, and its token only works for the superuser who
  drafted it;
- runs in a transaction that is always rolled back, restores the session it found,
  and skips the auth-redirect sync, device tracking and setup redirects;
- keeps its token through redirects, is sent `Cache-Control: no-store` and
  `X-Frame-Options: SAMEORIGIN`, has page animations disabled, and carries a static
  guard script (`dlux/system/js/preview_guard.js`) that swallows clicks and submits.
  Nothing inline is added, so previews keep the page CSP-compliant.

Only the existing Save action persists anything.

Controls that change no page — ScanLink, the entry clipboard and the PDF tool
options — are listed in `NONVISUAL_PREVIEW_FIELDS` and rendered with
`data-dlux-preview="none"`. Editing one never swaps the page behind the Options modal
for a draft render; the draft still carries its value.

**Behind the Options modal.** On the steps whose subject is page chrome — Branding,
Languages, Themes and Fonts, Titlebar, Sidebar, Navbar and Components — the page
behind the modal follows the form. Once a value differs from how the step opened, a
frame of the current page rendered with the draft replaces it (at the same scroll
position, still dimmed by the modal backdrop), and it re-renders on every change.
Setting a value back returns to the real page.

The step's **Preview** lifts the modal off that page (glass mode); click anywhere,
Escape or Q returns, and the exit click never reaches the page. The modal itself
also takes the draft's default font for the page's language, since fonts are chosen
there.

**The popup.** Steps whose subject is not on the Options page open the popup from
**Preview**:

- Ribbon: a sample list page;
- Home and Public Pages: the configured home page, with a visitor/signed-in switch
  when a public page is enabled;
- Login Page: the login page as a visitor sees it;
- Profile Page: the profile page.

The popup offers the draft's languages and desktop/tablet/mobile widths.

**Section eyes.** Where even that cannot show the subject, the section heading
carries an eye that opens the popup on a sample page built from the standard shells:
*Surfaces & Edges* and *Tables* (a list page with a ribbon, nested tab strips and a
`DluxTable`), *Forms* (a form in the shared form markup) and *Modals* (the real
dynamic modal opened with a form). Sample pages live at
`/sys/settings/preview/sample/<kind>/` and exist only inside a preview.

**The first-run wizard** is a page of its own with nothing behind it, so its Preview
always opens the popup, on the step's page. Email, Access and Security, Global
Search, Notifications, Logging, System Backup and Extra Features have no page
representation; their Preview is disabled with an explanatory tooltip.

## Email delivery

The Email step is grouped as:

- **Delivery Path** — delivery path, secret storage, provider preset;
- **SMTP Connection** — STARTTLS/SSL, host, port, timeout, credentials;
- **Sender & Alerts** — default from address, failure recipients.

Each choice is a Dlux selector rather than a dropdown, so every option and its
consequence is visible before it is picked. When the internal SMTP relay is not
listening, the relay option is locked with the reason attached — unless it is
already the stored delivery path, which is never taken away. The page waits at most
1.5 seconds for that check; when the stack's name resolver does not answer in time,
the relay reads as not listening.

Save the Email step before using **Send test email**. The test intentionally uses
the stored configuration, which is the only way to validate the separate SMTP relay
when that delivery path is selected. A successful send verifies the exact connection
fingerprint; changing transport, secret storage, host, port, TLS/SSL, credentials,
or sender requires another test.

Email 2FA, password reset, public registration, and notification-email controls are
locked until delivery is enabled and verified. They retain their saved values while
locked. Direct environment-managed SMTP and local debug backends are supported too;
see [Deployment Configuration](deployment-configuration.md) for the runtime settings.

## Access and security

The step reads toggles first, then selectors, then the fields each one reveals: the
sign-in and session switches, record visibility, client-IP resolution, public
registration, and privacy links. Client IP source and registration activation mode
are Dlux selectors; the trusted-hops and custom-header fields appear only for the
mode that uses them.

Configure client-IP resolution to match the proxy chain you control:

- **Proxy-aware X-Forwarded-For** is the default; set trusted proxy hops to the
  number of trusted hops at the right of the chain.
- **Direct** uses `REMOTE_ADDR` for a directly exposed web service.
- **X-Real-IP**, **Cloudflare**, and **Custom header** select an explicit source.
- **Auto-detect** is a compatibility fallback, not a substitute for correctly
  configuring a reverse proxy.

All modes retain a guarded fallback rather than returning an empty address. See
[Getting Started](getting-started.md#behind-a-front-proxy--tls-terminator) for the
required front-proxy headers.

The same category controls login lockout, strong-password policy, browser-close and
inactivity sign-out, public registration, email/TOTP 2FA, trusted devices, and
privacy-consent presentation. Security mutations are POST-backed, and
current-password checks protect destructive profile and administrator actions.

## Titlebar

The Titlebar step stores its layout in `titlebar_config`. Three keys decide where the
titlebar's actions sit:

| Key | Values | Default |
| --- | --- | --- |
| `user_hub_style` | `dropdown`, `titlebar_actions` | `dropdown` |
| `actions_layout` | `scattered`, `grouped` | `scattered` |
| `actions_order` | ordered action keys | `search`, `theme`, `language`, `notifications`, `weather`, `home`, `profile`, `help`, `users`, `activity`, `reports`, `settings`, `auth` |

`actions_order` drops unknown and repeated keys; a key it lacks is inserted at its
default position rather than appended. The step lets you reorder actions only under
the Titlebar Actions style.

### User hub styles

- **`dropdown`** keeps the user shortcuts in the `dlux/users/user_hub.html` dropdown
  card. Only the search, theme, language, notification and Home actions sit on the
  bar.
- **`titlebar_actions`** suppresses the dropdown card and renders the available
  shortcuts as `.dlux-titlebar-action` buttons, shaped by the shared
  `titlebar.buttons_shape` setting.

Every available action is rendered, and its `data-titlebar-action-scope` says which
style shows it (`shared` under both styles); CSS hides the rest, so a style change
previews without a round trip. Weather's scope follows its own placement setting.

Users, activity and reports keep their permission gates in either style. A hidden
Home button or a disabled notification drawer omits that action. Authenticated
logout is always a POST form with CSRF.

### Grouped actions

`actions_layout` applies to the Titlebar Actions style; the Dropdown style never
groups by choice, and the setting is locked while it is selected.

- **`scattered`** leaves every action on the bar.
- **`grouped`** moves the optional ones into `#dlux-titlebar-rail` under the
  titlebar, behind the caret in `.titlebar__constants`. Home, that caret and the
  user hub trigger never move.

Either style groups regardless of the setting on viewports under 576px, and when a
scattered row would leave the title less than a readable minimum width.

The rail's buttons keep `dlux-titlebar-btn` styling because the shared rules are
scoped to `:is(.titlebar, .dlux-titlebar-rail)`. The rail mirrors
`data-titlebar-user-hub-style`, `data-titlebar-buttons-shape`,
`data-titlebar-home-shape`, `data-titlebar-show-home` and
`data-titlebar-show-language-switcher` from the titlebar.

Action nodes are moved rather than cloned, so any panel nested inside a toggle keeps
working. A project adding its own titlebar action gets the same treatment without
registering anything.

### Keyboard shortcuts

| Keys | Action |
| --- | --- |
| `Ctrl/Cmd+K` | Focuses the global search box. |
| `Ctrl/Cmd+J` | Opens Options through the rendered Options link. |
| `Ctrl/Cmd+H` | Opens Home through the rendered titlebar Home link. |
| `Ctrl/Cmd+U` | Opens User Management through the rendered Users link. |

The navigation shortcuts follow links the server rendered (for Users,
`[data-dlux-users-link]` in the hub or `[data-titlebar-action-key="users"]` in
Titlebar Actions mode), so a reader without the directory permission has no link and
the key does nothing.

## Navigation and appearance

The sidebar and Navbar are runtime navigation, not setup-only previews. Saved sidebar
visibility is permission-aware; a page does not become available merely because it
appears in the tree. User reordering, if allowed, is a personal layer on top of the
saved system tree.

### Sidebar toggle icon

`toggle_icon` (in `sidebar_config`) is the glyph on the titlebar's sidebar-toggle
button. It is set in step 7 (**Sidebar**) with the same searchable icon picker used
for sidebar entry icons, and defaults to `bi-list`.

The picker is disabled while the sidebar is off, and while `collapse_mode` is
`locked_expanded`: that mode hides the toggle on desktop (it still renders below
1100px).

Any class from the bundled Bootstrap Icons font is accepted. Because the value is
rendered straight into a `class` attribute, the normalizer requires a plain `bi-*`
token (lowercase, no spaces, at most 64 characters) and falls back to the default
for anything else, so a hand-edited or imported `sidebar_config` cannot inject
markup.

Icons listed in `SIDEBAR_TOGGLE_DIRECTIONAL_ICONS` (arrows, chevrons, sidebar
panels) point *toward* the sidebar, so the template tags them
`dlux-icon-directional`: CSS mirrors them under `[dir="rtl"]` and flips them while
the sidebar is collapsed. Symmetric glyphs render as authored.

### Navbar

The Navbar can use a curated hierarchy or a browser-session history. Its Navigation
Root can remain neutral, follow the configured homepage, or use a discovered route
without rewriting the stored hierarchy. Dynamic views can supply
`dlux_navbar_crumbs` when their object-level labels cannot be represented by the
static tree.

### Imported navigation

Imported navigation is validated against the live URLconf. Sidebar entries and
Navbar route nodes naming a route this project does not define are dropped on
import — from a first-launch `config.json`, an Options-page settings import, or
`dlux_settings import` — so the builders only ever show entries that can actually
render.

A stale Navbar node's children are kept and lifted into its place, and a stale
Navigation Root falls back to neutral. Manual Navbar nodes and sidebar entries
carrying a literal `url` are never route-checked.

### Themes and fonts

Themes and fonts use shared registries, so their setup choices, validation, previews,
and runtime stylesheet selection remain aligned. Project-owned entries are
documented in [Project Configuration](project-configuration.md#themes-and-fonts).

## Day-to-day Options

`/sys/options/` is the operational hub after setup. It provides personal display
preferences to ordinary users and superuser-only System Settings, setup export,
backup, Extra Features, and update actions. The System Information card presents
deployment facts and on-demand service diagnostics; the Tasks row reads the
`dlux_worker` heartbeats and queue counts from the database and rereads them on
demand (see [Task Runner](task-runner.md)).

For operational procedures, use [Operations](operations.md). For assets, use
[Managed Assets](managed-assets.md). For deploy/update safety, use
[Verified Inline Updates](inline-updater.md) and [Deployment Doctor](doctor.md).

## Optional weather

Weather is configured under **Extra Features → Weather**: enable it, enter the
OpenWeather API key, search/add locations, choose a default, and select units,
display style, and titlebar/user hub/floating placement (or project embeds only).
Dependent controls remain visible but disabled with tooltips while the feature is
off; saved values are retained. See [Weather](weather.md), including the two-line
dashboard integration and API-key import/export behaviour.

## Entry clipboard

Extra Features offers **Enable entry clipboard**, off by default. It stores
`extra_config.entry_clipboard.enabled` and preserves other Extra Features/project
namespaces. Enabled deployments load the clipboard only for signed-in users. The
popover button shares the assisted-entry row with **Reuse my last entry**; sticky
forms continue to own automatic prefill. See [Entry clipboard](entry-clipboard.md).

## Settings persistence contracts

Focused System Settings editors own only the fields rendered in their section. The
form derives ownership from its layout, disables inactive fields server-side, and
ignores their omitted or stale POST/file values. Ownership is established before
template rendering may trigger validation. Capability locks (such as verified email
requirements) still apply to the active section.

Configuration imports are patches: only supplied keys change; nested objects merge
and explicit lists replace the previous lists. Normalization retains input presence
rather than synthesizing neighboring changes from defaults. The review shows the
effective merged result, while apply retains the original patch. Unspecified app
namespaces and Extra Features remain intact.

`apply_system_settings_import(instance, payload, replace_groups=False)` uses these
patch semantics by default. Complete settings forms and snapshot reverts pass
`replace_groups=True`, so explicitly clearing a mapping or restoring an older
snapshot remains possible. Redacted/omitted SMTP credentials keep the current
encrypted password; choosing non-DB secret storage clears that DB token. The
internal `preserve_email_secret=True` path also accepts a newly encrypted credential
produced by the settings form. Import review/apply/revert share the same semantics
and apply against a locked current settings row.

All settings normalizers use `dlux.system.booleans.parse_boolean`: booleans, numeric
0/1 and the text tokens `true/false`, `yes/no`, `y/n`, `on/off`, and `1/0` are
recognized case-insensitively after trimming. Empty text is false; missing or
invalid input uses the caller's explicit default. Derived credential and
verification markers and mandatory immutable audit logging retain their own
prerequisites.

Single and grouped app-namespace writers merge into a row locked with
`select_for_update()` inside a transaction and write only `extra_config`.

An ordinary section save from the Options modal locks the row the same way. When
another request has written it since the form was built, the submission is re-bound
to the current row under that lock, so the other request's sections are kept and
only the submitting section changes. The first-run setup wizard, which saves every
step at once, keeps whole-form semantics.

Stored settings override the project's `DLUX_CONFIG` per group by its
`db_override_policy` (`configured_or_non_default`): after setup always, before setup
only where the stored group differs from its defaults, and never when the group was
never saved. Extra Features merge per feature key and app namespaces per namespace,
so a stored ScanLink or app value does not hide the project's other features or
namespaces.

Registered catalogue regressions cover ownership, explicit on/off edits, partial
imports, import revert, credentials and concurrent namespace updates.
