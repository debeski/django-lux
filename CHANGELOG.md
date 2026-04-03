# Changelog

This file now owns the release history for `django-microsys`.

Older README version-history entries were migrated here and normalized into newest-first headings with bullet lists so future updates stay easier to scan and maintain.

## v1.18.12

- **Broader Curated Icon Set**: Expanded the setup inspector's icon suggestions to a much more diverse, verified set covering navigation, storage, finance, admin, communication, scheduling, and data-oriented icons.

## v1.18.11

- **Inspector Two-Column Layout**: Reworked the setup sidebar inspector into a cleaner two-column layout, with label/icon fields on one side and the icon chooser on the other.
- **Expanded Scrollable Icon Picker**: Greatly increased the available Bootstrap icon suggestions and moved them into a capped inline-scroll picker so the inspector stays compact while offering many more choices.

## v1.18.10

- **Global Home URL Setting**: Moved Home selection out of the sidebar builder and into general System Settings, so developers can choose any discovered page as the project-wide Home destination or type a custom URL directly.
- **Sidebar/Home Decoupling**: Stopped letting sidebar configuration implicitly override `home_url`, and reset the builder's old Home selector so sidebar structure no longer dictates the titlebar Home button.

## v1.18.9

- **Unified Runtime Sidebar Tree**: Replaced the live sidebar's split auto-items/accordion-groups render path with the same single tree model used by the first-launch setup builder, so saved Microsys sidebar structure now renders directly at runtime.
- **Tree-Based Personal Reordering**: Reworked live sidebar reordering to save a user-specific tree override instead of juggling separate root/group/localStorage order buckets, while still merging in newly added base sidebar items from system setup.

## v1.18.8

- **Optional Titlebar Home Target**: Stopped forcing the titlebar Home button to follow a top-level sidebar item, so setup can leave Home on its normal system destination without adding an Index entry to the sidebar.
- **Builder Home Selector Cleanup**: The sidebar builder now offers a default "use the titlebar Home button link" option instead of auto-selecting the first sidebar item or disabling the control when no top-level entries exist.

## v1.18.7

- **Setup Form Initial Sync Fix**: Corrected the first-launch System Settings form so cleaned singleton defaults are pushed into `self.initial` after form construction, preventing stale legacy values like `ادارة النظام` from rendering in the Arabic name field.

## v1.18.6

- **Immediate Setup Language Switching**: Removed the extra Apply action from first-launch setup so language cards now switch the UI immediately, matching the instant-feedback feel of the theme picker.
- **State-Safe Language Reloads**: The immediate setup language switch still preserves the current wizard step and unsaved onboarding values before reloading the page.

## v1.18.5

- **Shared Language Picker UI**: Replaced the setup default-language dropdown with the same language-card toggle UI used in Options, so language and theme selection now feel consistent during first launch.
- **Setup State Preservation**: Applying a setup language change now preserves the wizard step and unsaved text/JSON/sidebar values across the reload instead of resetting the onboarding form.

## v1.18.4

- **Pre-Setup Branding Cleanup**: Removed the legacy Arabic system-name default so fresh and unconfigured installs no longer surface `ادارة النظام` before setup is completed.
- **Blank Arabic Setup Field**: The Arabic system-name field now starts empty during first launch, while runtime branding continues to fall back to `microSYS` until the developer saves real names.

## v1.18.3

- **System Default Theme**: Added `SystemSettings.default_theme` and `MICROSYS_CONFIG['default_theme']` fallback support so new users inherit a configurable default look until they save their own theme preference.
- **Setup Theme Picker**: Added the same circular theme chooser from Options to first-launch setup beside default language, with live preview while editing the system default.

## v1.18.2

- **Theme Fallback Fix**: Added a guaranteed default `light` theme path so titlebar and other theme-scoped surfaces no longer render transparent when no theme preference is saved.
- **Sidebar Toggle Polish**: Refined the titlebar sidebar toggle with a proper default surface and matching dark-theme treatment.

## v1.18.1

- **Theme-Aware Setup Builder**: Refactored the first-launch sidebar builder to derive its surfaces, text, active states, and tree accents from shared Microsys theme tokens instead of hardcoded colors.
- **Shared Control Styling**: Wired setup search, home destination, and inspector inputs onto existing `glass-input` styling for consistent appearance across themes.

## v1.18.0

- **First-Launch Setup Wizard**: Added `/sys/setup/` onboarding for branding, languages, translations, and global sidebar configuration, while keeping System Settings editable later from Options.
- **Resolver-Driven Sidebar Builder**: Replaced suffix-based discovery with reversible URL discovery and a two-pane builder with group selection, add-all/remove-all controls, and persistent home destination handling.
- **Navigation Cleanup**: Excluded Microsys, Django admin, and health-check routes from discovered application navigation.

## v1.17.7

- **Modern Tooltips**: Replaced native browser tooltips in the User Hub with custom, high-fidelity glass-morphism tooltips for a more premium toolbar experience.

## v1.17.6

- **User Hub UX Optimization**: Prevented automatic collapse of the user hub dropdown when interacting with tutorial controls or the sidebar theme picker.

## v1.17.5

- **Avatar Fix**: Enforced circular shape and fixed dimensions for titlebar user avatars to prevent layout issues with square images.

## v1.17.4

- **User Hub Dark Mode**: Complete dark theme overrides for the user trigger and dropdown hub, featuring enhanced glass-morphism and high-contrast toolbars.

## v1.17.3

- **UI Cleanup**: Removed decorative pseudo-element from hero section background to ensure a clean, glitch-free visual across all themes.

## v1.17.2

- **Dark Mode Refinement**: Fixed dashboard hero section gradient in dark mode for a more premium, high-contrast appearance.

## v1.17.1

- **UI Optimization**: Reduced user button height and padding in the titlebar for a more compact and refined navigation experience.

## v1.17.0

- **Modern UX & Branding Overhaul**: Systematic enhancement of the titlebar and sidebar.
- **User Intelligence Center**: Replaced legacy titlebar buttons (Home, Help, Logout) with a modern, circular user trigger.
- **Advanced User Dropdown**: Implemented a professional, rectangular glass-morphism dropdown activated by the user icon. Features real-time info text on the left and a high-fidelity image preview on the right.
- **Fixed Dropdown Toolbar**: Integrated specialized toolbar at the bottom of the user dropdown containing Profile, Manage Users (for staff), Activity Log, and System Options links.
- **Sidebar Streamlining**: Deprecated and removed the `system_group` accordion and its associated dashboard elements to simplify navigation.
- **Circular Login Interface**: Introduced a sleek, circular login icon for unauthenticated users.

## v1.16.0

- **Interactive User Wizard**: Transformed user creation and editing into an interactive 2-step wizard (Account Details & Permissions) within the dynamic modal system.
- **Dynamic Permission Translation**: Implemented a system-wide patch to dynamically translate permission prefixes and labels based on the active language.
- **Permission Widget Polishing**: Fixed "Select All" functionality at both App and Model levels in the permission widget using event delegation for reliable AJAX support.
- **Modal Flow Optimization**: Updated the dynamic modal success handler to trigger a parent page reload specifically for the user management flow, ensuring the list view is always synchronized with changes.

## v1.15.9

- **Leftover `_get_default_strings` Fix**: Replaced two remaining references to the removed `_get_default_strings()` function in `utils.py` (`_build_generic_detail_context` and `_build_generic_table_class`) with `get_strings()`. These stale references caused `NameError` -> 500 Internal Server Error when the Dynamic Modal Manager auto-generated tables/detail views for models like `SystemSettings`.

## v1.15.8

- **Filter Layout Suffix Fix**: Fixed hardcoded fallback strings `'from'` and `'to'` in `set_field_attrs` to properly consult the mapped translation dictionary keys `'filter_from'` and `'filter_to'` when computing translated placeholders for range filters (`__gte` and `__lte`).

## v1.15.7

- **Context Menu Smart View Duplicate Data Fix**: Fixed a bug in `collect_related_objects` where M2M relations were processed twice (via both `auto_created` reverse accessors and `many_to_many` forward accessors), causing duplicate cards in the Smart View modal. Added tracking to ensure relations are only added once.
- **Modal CSS Fix**: Replaced hardcoded `text-white-50` class with theme-adaptive `text-muted` in `section_manager.js` to ensure related records list items are visible in both light and dark themes.

## v1.15.6

- **M2M Serialization Fix**: Wrapped lazy translation proxies (`verbose_name`, `verbose_name_plural`) with `str()` in `utils.py` and `views/sections.py` to prevent `TypeError: Object of type Promise is not JSON serializable` resulting in 500 errors when viewing section details with M2M relations via Context Menu.

## v1.15.5

- **Translation Signature Fix**: Fixed `get_strings` function call and replaced removed `_get_request_lang` usages in `utils.py` and `models.py` with Django's native language detection to prevent `AttributeError` during form generation.

## v1.15.4

- **Translation System Streamlining**: Completely overhauled the translation system to make `get_strings()` the single, smart source of truth. Removed all redundant wrappers from `utils.py` (`_get_default_strings`, `_get_request_lang`, `_get_request_translations`), `forms.py` (`_get_form_strings`), and `filters.py` (`_get_filter_strings`). All views, templates, tables, forms, and filters now route directly through `translations.get_strings()` which automatically handles request/session/profile context language resolution internally.

## v1.15.3

- **Universal Context Menu Translation**: Augmented the `Table.__init__` patch in `AppConfig.ready()` to automatically and globally translate `label` properties inside `row_attrs['data-micro-actions']` dynamically based on the current user linguistic preferences.

## v1.15.2

- **Micro Context Menu Dark Mode Enhancement**: Updated hover background color for context menu items in dark mode to improve contrast and reduce visual harshness.

## v1.15.1

- **Translation Language Resolution Fix**: Rewrote `get_strings()` to use the same robust language fallback as `microsys_context`: user profile prefs -> session -> `MICROSYS_CONFIG['default_language']` -> `get_language()` -> `'ar'`. Previously the function skipped profile prefs and `default_language`, causing Django's default `en-us` to override the intended Arabic default.
- **Table Patch Kwargs Fix**: Fixed `TypeError` in `_patched_init` where microsys-specific kwargs (`translations`, `request`, `model_name`) were forwarded to django-tables2's `Table.__init__()`.

## v1.15.0

- **Universal Auto-Translation**: Augmented `AppConfig.ready()` patches to automatically translate Table headers, Filter labels, and ModelForm field labels by looking up `verbose_name` or `label` in the project's translation dictionary. Supports `tbl_` and `label_` prefixes with zero developer effort.

## v1.14.0

- **Scope Auto-Injection**: Monkey-patches `ModelForm`, `FilterSet`, and `Table` in `AppConfig.ready()` to auto-inject and manage scope for any `ScopedModel`-based component - zero developer effort.
- Auto Scope on Save: `ScopedModel.save()` now auto-sets scope from user's profile (like `created_by`).
- ScopeForeignKey Fix: `formfield()` no longer returns `None` when scopes are disabled.

## v1.13.0

- **User Modal CRUD**: Migrated User add/edit from separate pages into `DynamicModalManagerView`.
- **Smart Form Kwargs**: Auto-introspects form `__init__` signatures and passes `user`/`request` if accepted.
- **`form_class` / `template_name` Overrides**: URL-level customization of form class and template.
- **`show_table` / `show_form` Flags**: Render form-only, table-only, or combined.
- **`handles_save` Flag**: Forms managing their own save cycle (password hashing, M2M).
- **`get_modal_context()` Convention**: Models can define this method to auto-inject extra context into modals.
- **`UserModalForm`**: Smart proxy delegating to creation/change forms based on instance.

## v1.12.7

- **Reusable Global List Template**: Added `microsys/helpers/global_list.html` to standardize form/filter/table list views project-wide.
- **Event Rename**: Renamed `micro:section:*` -> `micro:record:*` for semantic accuracy across AutoTable, `section_manager.js`, and all consumer templates.

## v1.12.6

- **Global Context Menus**: Refactored AutoTable generic context menus to dispatch decoupled `micro:record:edit` events, empowering standard views to handle routing and custom views to pipe explicitly into Dynamic Modals without boilerplate code.

## v1.12.5

- **HR Validation Overhaul**: Shipped powerful `ProfileCompletionMiddleware` and `EmployeeSetupForm` that globally trap unverified dummy users upon login, forcing them to complete their profiles before gaining system access.

## v1.12.4

- **Dynamic Connected Profiles Failsafe**: Universal `post_save` signal that introspects one-to-one user profiles globally and auto-creates them with type-safe dummy values, bypassing database requirements for flawless system-agnostic onboarding.

## v1.12.3

- **Migrator Component Integration**: Integrated `migrator.py` into the `microsys/management/commands` package to centralize and reuse initial deployment logic across projects. Added `-mm` (make-migrations) flag to `migrator.py` to safely force makemigrations.

## v1.12.2

- **`get_model_classes` Performance Enhancement**: Upgraded `get_model_classes` utility to use dictionary caching and `LazyModelClasses` for lazy evaluation, reducing module import overhead during the request loop.
- **`get_model_classes` Overrides**: Added support for explicit convention overrides via the `overrides` argument or the model-level `model_classes_overrides` attribute.

## v1.12.1

- **Universal Filter Standardization**: Migrated `Users`, `Sections`, and `Activity Log` views to the unified `setup_filter_helper` utility. All core lists now benefit from conditional clear buttons, `Hidden` GET parameter preservation, and consistent responsive layouts.

## v1.12.0

- **Smart Filter Controls**: Enhanced `setup_filter_helper` to conditionally render the reset (cancel) button. It now only appears when active filters with non-empty values are present, reducing UI clutter.
- **Alignment Refinement**: Standardized global filter alignment to `start` for improved visual hierarchy.

## v1.11.5

- **Dynamic Sidebar Width**: Converted sidebar layout to `col-auto` with `fit-content` min-width on large screens, allowing it to adapt to the longest item or accordion parent.
- **Flexible Content Layout**: Updated the main content area to utilize fluid grid sizing, ensuring it seamlessly fills the workspace adjacent to the dynamic sidebar.

## v1.11.4

- **Sidebar RTL Precision**: Synchronized direction context with sidebar templatetags to ensure correct chevron mirroring in RTL layouts.
- **Padding Optimization**: Refined RTL padding for sidebar items and accordion buttons to pull navigation elements flush with the sidebar borders, eliminating "phantom" side gaps.

## v1.11.3

- **Separate Accordion URL Button**: Modified sidebar accordion headers to display a separate, non-intrusive URL button (`>`/`<`) for groups with dashboard links, preserving default accordion toggle behavior without JS routing conflicts.

## v1.11.2

- **Premium Dark Theme Legibility**: Comprehensive overhaul of contrast, outlines, and visibility for all UI components in dark mode.
- **Improved Text Contrast**: Enforced high-contrast labels and text utility classes for maximum readability on dark backgrounds.
- **Preserved Utility Borders**: Protected Bootstrap `border-*` classes from global theme overrides.

## v1.11.1

- **Sidebar Parent Reordering**: Enabled reordering for entire accordion groups with dedicated persistence and FOUC prevention.

## v1.11.0

- **Sidebar Accordion Refinement**: Added dashboard navigation behavior to the built-in "System" group header, matching the split-accordion behavior of other functional groups.

## v1.10.3

- **Removed all `hasattr` guards** in views (fields always exist now).
- Simplified `ScopedManager` (no conditional `deleted_at` check).

## v1.10.2

- **UserActivityLog Refactor**: Removed redundant `user`/`timestamp` fields in favor of inherited `created_by`/`created_at` with backward-compat properties.
- **Centralized Logging**: Enhanced `log_user_action()` utility and replaced all manual `UserActivityLog.objects.create()` calls across signals, fetcher, and views.

## v1.10.1

- **Global Soft-Delete**: `delete()` overridden to perform soft-delete; added `soft_delete()`, `restore()`, and `hard_delete()` methods.

## v1.10.0

- **ScopedModel Audit Trail**: Added six built-in fields (`created_at`, `updated_at`, `created_by`, `updated_by`, `deleted_at`, `deleted_by`) with `editable=False` to `ScopedModel`.
- **Auto-Populated Actors**: `save()` override auto-populates `created_by` and `updated_by` from thread-local middleware.

## v1.9.2

- **Comprehensive README Overhaul**: Added extensive developer how-to documentation for Dynamic Modal Manager, 2FA, Template Tags, Double-Submit Prevention, and Preferences API.
- Expanded `ScopedModel` docs (dual managers, `ScopeForeignKey`, soft-delete), Section Mode (class resolution order, customization hooks), Context Menu (permission filtering, event actions, action schema), Autofill (API endpoints), and Activity Logging (safe_log, diffs, masking).
- Updated file structure to reflect the `views/` package refactor.

## v1.9.1

- **Views Modularization**: Refactored monolithic `views.py` into a `views/` package with dedicated modules: `general.py`, `users.py`, `twofa.py`, `sections.py`, `scopes.py`, `activitylog.py`, `profile.py`, and `sidebar.py`.
- Added role-distinguishing top comments to all functions and classes.

## v1.9.0

- **Dynamic Modal Reconstruction**: Successfully restored the deleted `DynamicModalManagerView` and `DynamicModalDeleteView` functionality.
- Standardized dynamic modals with a unified AJAX-driven combined view (List + Form) for auxiliary models.
- Integrated related-record protection in deletion views with localized error messaging.

## v1.8.1

- **Auto Profile Creation**: Added a `post_save` signal to automatically create a `Profile` instance whenever a new user is created to prevent profile-missing errors.
- **Sidebar Accordions State**: Updated sidebar accordions to decouple from the active URL and each other, strictly persisting each accordion's open or close state independently based purely on user interaction.

## v1.8.0

- **Dynamic Multi-Language Tutorial**: Completely refactored the guided tutorial system. The tutorial is now fully dynamic based on the current URL path (`/sys/`, `/sys/sections/`, `/sys/users/`, etc.), supports full English and Arabic translations, and intelligently targets elements even if they change positions.

## v1.7.12

- **Offline Twemoji Flags**: Added local hosting for the Twemoji Country Flags web-font polyfill to ensure flag emojis render correctly on Windows without external CDN dependencies.

## v1.7.11

- **Theme Fixes**: Resolved issue where language picker options appeared white in dark theme by adding proper CSS variable overrides in `dark.css`.

## v1.7.10

- **Responsive 2FA UI**: Fixed two-factor authentication method rows to stay side-by-side on small screens, preventing the enable buttons and labels from stacking.

## v1.7.9

- **Premium Navigation Stability**: Finalized logout button with a `warning` theme, fixed icon wobble transitions, and tightened spacing for a high-end, glitch-free feel.

## v1.7.8

- **UI Refinement**: Moved the user's name outside the sign-out button in the titlebar for better separation.

## v1.7.7

- **Navigation Refactor**: Moved Profile to Sidebar and simplified Titlebar to a unified `Username | Logout` button.

## v1.7.6

- **Intuitive Double-Click Feedback (2026-02-17)**: Automatic pointer cursor for double-click targets.

## v1.7.5

- **Unified User Detail Modal (2026-02-17)**: AJAX-driven modal for user details, integrating the activity timeline and migrating context-menu events for users.

## v1.7.3

- **Dashboard Activity Chart**: Added a built-in activity chart powered by Plotly.js, visualizing system activity for the last 24 hours.
- **Responsive Chart**: Chart automatically resizes with the window and sidebar toggles using `ResizeObserver`.

## v1.7.2

- **Premium Modal UI**: Overhauled all section and activity modals with the glass-card/info-label design from the Profile view.
- **Dark Mode Accessibility**: Increased glass-card opacity to `0.92` and refined shadows to ensure data visibility in dark themes.
- **Double Modal Fix**: Resolved redundant script inclusion causing duplicate modal triggers.
- **Log Refinement**: Standardized activity log details with profile-consistent typography and theme-aware badges.

## v1.7.1

- **Enhanced Activity Logging**: Added JSON-based detail tracking for all updates (diffs), including masked password changes and file-download specifics.
- **Log Deduplication**: Implemented smart merging of concurrent User and Profile updates into single log entries.
- **Double Submit Prevention**: Added global JavaScript protection to disable submit buttons immediately after click.
- **Profile UI**: Updated the profile view to display detailed log history with formatted diffs.

## v1.7.0

- **Universal Fetcher**: Added a global, smart single-file and multi-file downloader.
- Added a data-driven Excel exporter for querysets with auto-hidden fields and an optional exclude-fields list.

## v1.6.3

- **Login Enhancements**: Added language switcher, session-based language persistence, and fixed RTL alignment bug.
- **Smart Redirects**: Login now automatically redirects authenticated users and supports `home_url` config fallback.
- **Unified Translations**: Refactored the internal translation helper to support anonymous sessions.

## v1.6.2

- **Custom Password Form**: Refactored the password-change form with dynamic translations and helpful descriptions.
- **RTL/LTR Fixes**: Fixed login screen text direction in English mode.
- **Profile Translations**: Fully translated profile view and edit pages.

## v1.6.1

- **Translation Upgrade**: Improved translation system and coverage.
- Various bug fixes and stability improvements.

## v1.6.0

- **Context Menu**: Added global, data-driven context-menu support for interactive elements.

## v1.5.2

- Completely restructured the README for a clearer understanding of the system and its setup.

## v1.5.1

- Autofill fixes: Resolved `500` and `404` errors during clearing, refined toggle behavior, and standardized console logging.

## v1.5.0

- **Global Dynamic Autofill Feature**: Automatically fill forms from related foreign keys (for example, user-profile data) with smart clearing and toggle controls.

## v1.4.1

- Translation-related fixes and UI enhancements.

## v1.4.0

- **Comprehensive Translation Framework**: Table headers, filter labels and placeholders, and template strings now resolve from `translations.py` per user language.
- Tables, filters, and templates (`manage_users`, `user_activity_log`, `manage_sections`) are fully translated.
- Reset Defaults now purges sidebar reordering from the database and local storage.
- Reset UI redesigned to match other options with inline Confirm and Cancel animation.
- Fixed activity-log actions always showing in Arabic regardless of language due to duplicate `get_table_kwargs`.

## v1.3.6

- Fixed theme-picker popup positioning in LTR mode (CSS logical properties).

## v1.3.5

- Switched to database JSON attached to the user profile for consistent preferences across devices.

## v1.3.4

- Added global head and scripts injection.

## v1.3.3

- Optimized form and filter auto-generation and layout.

## v1.3.2

- Fixed the README and added detailed instructions.

## v1.3.1

- Auto-generated section filters now include date-range pickers (from and to) with Flatpickr integration.
- Added clarifying inline comments to complex view logic.
- Fixed login Enter-key submission.
- PyPI release.

## v1.3.0

- **Section table context menu**: Right-click on table rows for Edit and Delete actions.
- **View Subsections modal**: Sections with many-to-many subsections show linked items in a modal.
- AJAX-based section deletion with related-record protection.
- Auto-generated tables now include row data attributes for JavaScript binding.

## v1.2.1

- Fixed subsection display so subsections show correctly regardless of user scope.
- Fixed `SessionInterrupted` errors by reducing session writes in section management.
- Scope toggle now accepts an explicit target state to prevent race conditions.
- Improved error messaging in Arabic for scope operations.

## v1.2.0

- **Dynamic Section Management**: New powerful zero-boilerplate section-management mode.
- Name changed to `django-microsys`.
- Scope fields now hide automatically when scopes are disabled.
- System sidebar group ships by default and remains configurable.
- `is_staff` moved into the permissions UI.

## v1.1.0

- **Application Complete Restructure** with modular files, templates, static assets, and related cleanup.
- URL restructure: auth at `/accounts/`, system at `/sys/`.
- Added `microsys_setup` and `microsys_check` management commands.
- Runtime configuration validation.

## v1.0.0

- Initial release as a pip package.
