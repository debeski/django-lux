document.addEventListener('DOMContentLoaded', function () {
    const driverFactory = window.driver && window.driver.js && window.driver.js.driver;
    if (typeof driverFactory !== 'function') {
        return;
    }

    const strings = window.DLUX_STRINGS || {};
    const direction = document.documentElement.getAttribute('dir') === 'rtl' ? 'rtl' : 'ltr';
    const sidebarPopoverSide = direction === 'rtl' ? 'left' : 'right';

    function text(key, fallback) {
        const value = strings[key];
        return typeof value === 'string' && value.trim() ? value : fallback;
    }

    function step(element, titleKey, titleFallback, descriptionKey, descriptionFallback, side = 'bottom', align = 'center') {
        return {
            element,
            popover: {
                title: text(titleKey, titleFallback),
                description: text(descriptionKey, descriptionFallback),
                side,
                align,
            },
        };
    }

    function isRendered(element) {
        if (!element || !element.isConnected || element.hidden || element.getClientRects().length === 0) {
            return false;
        }
        const style = window.getComputedStyle(element);
        return style.display !== 'none' && style.visibility !== 'hidden';
    }

    function resolveTarget(target) {
        if (typeof target !== 'string') {
            return isRendered(target) ? target : null;
        }
        return Array.from(document.querySelectorAll(target)).find(isRendered) || null;
    }

    function resolveSteps(steps) {
        const seen = new Set();
        return steps.reduce((resolved, candidate) => {
            const element = resolveTarget(candidate && candidate.element);
            if (element && !seen.has(element)) {
                seen.add(element);
                resolved.push({ ...candidate, element });
            }
            return resolved;
        }, []);
    }

    function shellSteps() {
        return [
            step('#sidebarToggle', 'tut_sidebar_toggle_title', 'Sidebar control', 'tut_sidebar_toggle_desc', 'Open, close, or collapse the navigation from here.'),
            step('#sidebar', 'tut_sidebar_title', 'Sidebar Navigation', 'tut_sidebar_desc', 'Navigate between system sections.', sidebarPopoverSide, 'start'),
            step('.titlebar', 'tut_titlebar_title', 'Titlebar', 'tut_titlebar_desc', 'The titlebar keeps global tools available on every page.'),
            step('[data-global-search]', 'tut_global_search_title', 'Global search', 'tut_global_search_desc', 'Search pages, actions, settings, and permitted records from anywhere.'),
            step('[data-dlux-notifications-toggle]', 'tut_notifications_title', 'Notifications', 'tut_notifications_desc', 'Review unread work, progress, and system notices.'),
            step('[data-dlux-theme-cycle], #sidebarThemeIndicator', 'tut_theme_switch_title', 'Theme switcher', 'tut_theme_switch_desc', 'Switch between the themes allowed for your account.'),
            step('[data-dlux-lang-cycle]', 'tut_language_switch_title', 'Language switcher', 'tut_language_switch_desc', 'Change the display language; the page and this tutorial follow it.'),
            step('#dlux-user-dropdown-trigger, [data-titlebar-actions]', 'tut_usermenu_title', 'User menu', 'tut_usermenu_desc', 'Open your profile and the tools allowed for your account.'),
        ];
    }

    function genericListSteps() {
        return [
            step('input[name="keyword"], .dlux-filter-form, form[action=""] input[type="search"]', 'tut_search_title', 'Quick Search', 'tut_search_desc', 'Search and narrow the records in this view.', 'right'),
            step('[data-dynamic-modal], .bi-plus-lg', 'tut_add_title', 'Add New', 'tut_add_desc', 'Create a record using the action available in this view.', 'left'),
            step('.dlux-table-shell, .table-responsive-lg, .table-responsive', 'tut_table_title', 'Data Table', 'tut_table_desc', 'Review the records and the actions available to you.', 'top', 'start'),
            step('[data-dlux-table-density-inline]', 'tut_table_controls_title', 'Table controls', 'tut_table_controls_desc', 'Change row density, page size, and move between result pages.'),
        ];
    }

    function pageSteps(path) {
        if (path.includes('/sys/setup/')) {
            return [
                step('.dlux-setup-intro', 'tut_setup_intro_title', 'System setup', 'tut_setup_intro_desc', 'Configure the framework from one guided workspace.'),
                step('[data-dlux-wizard-step-nav]', 'tut_setup_nav_title', 'Setup steps', 'tut_setup_nav_desc', 'Jump between every configuration area; only the active editor is shown.'),
                step('.wizard-step:not(.d-none), .wizard-step[aria-hidden="false"]', 'tut_setup_editor_title', 'Active editor', 'tut_setup_editor_desc', 'Edit this area, preview its result, then continue when ready.'),
                step('[data-dlux-setup-footer]', 'tut_setup_footer_title', 'Setup actions', 'tut_setup_footer_desc', 'Move between steps and save the completed configuration.'),
            ];
        }

        if (path.includes('/sys/options/')) {
            return [
                step('.dlux-options-grid', 'tut_options_overview_title', 'Options workspace', 'tut_options_overview_desc', 'Personal preferences and permitted system controls are collected here.'),
                step('.dlux-admin-panel-heading', 'tut_options_admin_title', 'Admin panel', 'tut_options_admin_desc', 'System health, updates, backups, configuration, and protected commands live together here.'),
                step('[data-admin-command-launcher]', 'tut_options_admin_commands_title', 'Admin commands', 'tut_options_admin_commands_desc', 'Open the command rail for assets, control-panel pairing, password enforcement, and data reset.'),
                step('.dlux-admin-tile--status', 'tut_options_info_title', 'System information', 'tut_options_info_desc', 'Review storage, runtime versions, and service health.'),
                step('[data-dlux-updater]', 'tut_options_updates_title', 'Application updates', 'tut_options_updates_desc', 'Check, review, apply, and roll back verified DjangoLux releases.'),
                step('.dlux-admin-tile--backup', 'tut_options_backups_title', 'Backup and restore', 'tut_options_backups_desc', 'See backup policy and open the full recovery workspace.'),
                step('.dlux-admin-panel-settings', 'tut_options_system_settings_title', 'System settings', 'tut_options_system_settings_desc', 'Open focused editors for branding, security, layout, integrations, and configuration import or export.'),
                step('[data-options-card-handle]', 'tut_options_card_order_title', 'Reorder options', 'tut_options_card_order_desc', 'Drag option cards into the order that works best for you.'),
                step('[data-options-card="accessibility"]', 'tut_options_access_title', 'Accessibility', 'tut_options_access_desc', 'Adjust contrast, colour, text size, and animation.'),
                step('[data-options-card="landing-page"]', 'tut_options_landing_title', 'Landing page', 'tut_options_landing_desc', 'Choose where your account opens after sign-in.'),
                step('.dlux-theme-preview', 'tut_options_theme_title', 'Themes and colours', 'tut_options_theme_desc', 'Choose an allowed theme and apply it immediately.'),
                step('.dlux-language-picker', 'tut_options_lang_title', 'Language settings', 'tut_options_lang_desc', 'Switch the interface and tutorial to another enabled language.'),
                step('[data-options-card="typography"]', 'tut_options_typography_title', 'Typography', 'tut_options_typography_desc', 'Select an allowed interface font.'),
                step('[data-options-card="table-density"]', 'tut_options_table_density_title', 'Table density', 'tut_options_table_density_desc', 'Control the spacing used by data tables.'),
                step('[data-options-card="form-density"]', 'tut_options_form_density_title', 'Form density', 'tut_options_form_density_desc', 'Control the spacing used by form fields.'),
                step('[data-options-card="modal-size"]', 'tut_options_modal_size_title', 'Modal size', 'tut_options_modal_size_desc', 'Choose the working width of pop-up dialogs.'),
                step('[data-options-card="navbar-mode"]', 'tut_options_navbar_title', 'Navigation mode', 'tut_options_navbar_desc', 'Choose hierarchy navigation or recently visited pages.'),
                step('[data-options-card="sidebar-density"]', 'tut_options_sidebar_density_title', 'Sidebar density', 'tut_options_sidebar_density_desc', 'Control spacing in the sidebar navigation.'),
                step('[data-options-card="autofill"]', 'tut_options_assisted_title', 'Assisted entry', 'tut_options_assisted_desc', 'Control related-record autofill and reuse of your last submitted values.'),
                step('[data-options-card="scanlink"]', 'tut_options_scanlink_title', 'ScanLink', 'tut_options_scanlink_desc', 'Check the desktop scanner helper and install an available release.'),
                step('.dlux-options-reset-footer', 'tut_options_reset_title', 'Reset preferences', 'tut_options_reset_desc', 'Restore dismissed prompts or return personal display preferences to their defaults.'),
            ];
        }

        if (path.includes('/sys/backup/')) {
            return [
                step('.dlux-backup-hero', 'tut_backup_create_title', 'Create a backup', 'tut_backup_create_desc', 'Choose full or data-only scope and optionally protect the archive with a passphrase.'),
                step('.dlux-backup-notice.alert-info', 'tut_backup_policy_title', 'Backup policy', 'tut_backup_policy_desc', 'Review scheduling, target, retention, stall detection, and retry policy.'),
                step('#sysbackup-table-body', 'tut_backup_history_title', 'Backup history', 'tut_backup_history_desc', 'Track progress, download completed archives, retry failures, or select a backup to restore.'),
                step('.dlux-backup-upload-form', 'tut_backup_upload_title', 'Import an archive', 'tut_backup_upload_desc', 'Upload an external DLB archive so it can be validated and restored.'),
                step('#sysrestore-table-body', 'tut_backup_restore_history_title', 'Restore history', 'tut_backup_restore_history_desc', 'Review recent recovery attempts and their progress.'),
                step('#sysrestore-panel:not(.d-none)', 'tut_backup_restore_title', 'Restore confirmation', 'tut_backup_restore_desc', 'Confirm the source, credentials, and replacement acknowledgement before recovery starts.'),
            ];
        }

        if (path.includes('/sys/reports/')) {
            return [
                step('.dlux-report-exports', 'tut_reports_exports_title', 'Report exports', 'tut_reports_exports_desc', 'Print the current report, export XLSX, or build a permission-filtered backup ZIP.'),
                step('.dlux-report-period-row', 'tut_reports_period_title', 'Period and search', 'tut_reports_period_desc', 'Choose a reporting window and narrow results by user, model, action, or number.'),
                step('[data-report-choice-panel="models"]', 'tut_reports_models_title', 'Included models', 'tut_reports_models_desc', 'Choose which permitted models contribute totals and exported data.'),
                step('[data-report-choice-panel="operations"]', 'tut_reports_operations_title', 'Included operations', 'tut_reports_operations_desc', 'Choose which activity operations are calculated in every output.'),
                step('.dlux-report-builder-submit', 'tut_reports_apply_title', 'Apply report scope', 'tut_reports_apply_desc', 'Rebuild the overview from the selected filters or reset them.'),
                step('.dlux-report-stats', 'tut_reports_stats_title', 'Summary metrics', 'tut_reports_stats_desc', 'Compare totals, period change, and per-day or per-user averages.'),
                step('.dlux-report-table-grid', 'tut_reports_breakdown_title', 'Report breakdowns', 'tut_reports_breakdown_desc', 'Inspect activity grouped by user, model, operation, and day.'),
                step('.dlux-report-users', 'tut_reports_users_title', 'User drill-down', 'tut_reports_users_desc', 'Open an authorised user report for deeper activity details.'),
            ];
        }

        if (path.includes('/sys/control-panel/')) {
            return [
                step('.dlux-control-hero', 'tut_control_status_title', 'Connection status', 'tut_control_status_desc', 'See whether this deployment is connected, pairing, or offline.'),
                step('.dlux-control-card--form', 'tut_control_pair_title', 'Pair this application', 'tut_control_pair_desc', 'Use the control-panel URL and a one-use enrollment token to connect securely.'),
                step('.dlux-control-card--status', 'tut_control_details_title', 'Connection details', 'tut_control_details_desc', 'Review the agent bridge, transport, identity, and last contact information.'),
            ];
        }

        if (path.includes('/sys/registrations/')) {
            return [
                step('.table-responsive', 'tut_registrations_table_title', 'Pending registrations', 'tut_registrations_table_desc', 'Review verified public sign-ups waiting for an administrator.'),
                step('form[action*="/approve/"] button, form[action*="/reject/"] button', 'tut_registrations_actions_title', 'Approval actions', 'tut_registrations_actions_desc', 'Approve an account or reject and remove the pending registration.'),
            ];
        }

        if (path.includes('/sys/users/')) {
            return [
                ...genericListSteps(),
                step('button[data-dynamic-modal]', 'tut_users_add_btn_title', 'Add user', 'tut_users_add_btn_desc', 'Create an account and configure its access.'),
                step('#btn-manage-scopes', 'tut_users_scopes_title', 'Scope management', 'tut_users_scopes_desc', 'Define which data each department or scope can see.'),
                step('#btn-manage-groups', 'tut_users_groups_title', 'Group management', 'tut_users_groups_desc', 'Build reusable permission groups and manage their members.'),
                step('#autoScopeContainer, #toggleScopes', 'tut_users_scope_toggles_title', 'Scope controls', 'tut_users_scope_toggles_desc', 'Enable scope enforcement and optional automatic scope assignment.'),
                step('.dlux-staff-tier-badge, .badge-role, .badge', 'tut_users_roles_title', 'User roles', 'tut_users_roles_desc', 'Badges distinguish management tiers and delegated access.'),
                step('.dlux-table-body tr, .table tbody tr', 'tut_users_row_title', 'User details and actions', 'tut_users_row_desc', 'Open a row to inspect the user and the actions permitted for your account.'),
            ];
        }

        if (path.includes('/sys/logs/')) {
            return [
                step('.nav-tabs[role="tablist"]', 'tut_logs_tabs_title', 'Log categories', 'tut_logs_tabs_desc', 'Move between user, system, security, and other configured activity categories.'),
                ...genericListSteps(),
                step('.dlux-table-body tr, .table tbody tr', 'tut_logs_row_title', 'Activity details', 'tut_logs_row_desc', 'Open a row to see what changed and the available audit context.'),
            ];
        }

        if (path.includes('/sys/sections/')) {
            return [
                step('#sectionTabs', 'tut_sections_tabs_title', 'Section types', 'tut_sections_tabs_desc', 'Switch between the section models configured by the project.'),
                step('.card form.dlux-form', 'tut_sections_form_title', 'Section editor', 'tut_sections_form_desc', 'Create or update the selected section and its linked subsections.'),
                ...genericListSteps(),
                step('.dlux-table-shell, .table', 'tut_sections_list_title', 'Sections list', 'tut_sections_list_desc', 'Review the entries defined for the selected section type.'),
            ];
        }

        if (path.includes('/accounts/profile/')) {
            return [
                step('.info-value', 'tut_profile_details_title', 'Personal information', 'tut_profile_details_desc', 'Review your account identity, contact details, role, and sign-in history.', 'right'),
                step('.action-btn[data-dynamic-modal]', 'tut_profile_actions_title', 'Profile actions', 'tut_profile_actions_desc', 'Open your user report, edit profile data, or change your password.', 'left'),
                step('.security-method-row', 'tut_profile_2fa_title', 'Security settings', 'tut_profile_2fa_desc', 'Manage available two-factor methods and backup codes.'),
                step('.profile-session-list', 'tut_profile_sessions_title', 'Signed-in devices', 'tut_profile_sessions_desc', 'Review active sessions, trust this device, or sign out another session.'),
                step('.stats-card', 'tut_profile_stats_title', 'Profile statistics', 'tut_profile_stats_desc', 'See quick totals for your activity.'),
                step('.activity-timeline', 'tut_profile_activity_title', 'Recent activity', 'tut_profile_activity_desc', 'Review your recent work and system interactions.'),
            ];
        }

        if (resolveTarget('input[name="keyword"]') && resolveTarget('.table, .dlux-table-shell')) {
            return genericListSteps();
        }

        return [
            step('#mainContent', 'tut_maincontent_title', 'Workspace', 'tut_maincontent_desc', 'This is where the current page and its available actions appear.', 'top'),
        ];
    }

    function getTutorialSteps() {
        const path = window.location.pathname;
        let candidates = [...shellSteps(), ...pageSteps(path)];

        if (typeof window.get_custom_tutorial_steps === 'function') {
            try {
                const customSteps = window.get_custom_tutorial_steps(path);
                if (Array.isArray(customSteps)) {
                    candidates = candidates.concat(customSteps);
                }
            } catch (error) {
                console.error('Error in custom tutorial steps hook:', error);
            }
        }

        return resolveSteps(candidates);
    }

    if (!document.getElementById('driver-rtl-fix')) {
        const style = document.createElement('style');
        style.id = 'driver-rtl-fix';
        style.textContent = `
            .driver-popover {
                direction: ltr !important;
                z-index: 2147483647 !important;
                position: fixed !important;
                right: auto !important;
                bottom: auto !important;
                background-color: #fff !important;
                color: #333 !important;
                border: 1px solid #ddd !important;
                box-shadow: 0 5px 15px rgba(0,0,0,0.3) !important;
                border-radius: 5px !important;
                min-width: 250px !important;
                max-width: 300px !important;
            }
            
            .driver-popover-title, .driver-popover-description {
                direction: ltr !important;
                text-align: left !important;
                font-family: var(--dlux-main-font, var(--dlux-font-fallback, sans-serif)) !important;
                color: #333 !important;
            }

            html[dir="rtl"] .driver-popover-title,
            html[dir="rtl"] .driver-popover-description {
                direction: rtl !important;
                text-align: right !important;
            }
            
            .driver-popover-title {
                font-weight: bold !important;
                font-size: 1.1rem !important;
                margin-bottom: 8px !important;
            }
            
            .driver-popover-arrow {
                content: '' !important;
                display: none !important;
            }

            .driver-popover-footer,
            .driver-popover-progress-text,
            .driver-popover-navigation-btns,
            .driver-popover-prev-btn,
            .driver-popover-next-btn,
            .driver-popover-close-btn {
                display: none !important;
                opacity: 0 !important;
                visibility: hidden !important;
                pointer-events: none !important;
            }

            #tutorial-controls {
                --tut-bar-bg: rgba(255, 255, 255, 0.95);
                --tut-bar-border: #dee2e6;
                --tut-bar-shadow: rgba(0, 0, 0, 0.05);
                --tut-progress-color: #4b5563;
                --tut-next-bg: #3b82f6;
                --tut-next-bg-hover: #2563eb;
                --tut-next-color: #fff;
                --tut-next-shadow: rgba(59, 130, 246, 0.3);
                --tut-prev-bg: #f3f4f6;
                --tut-prev-bg-hover: #e5e7eb;
                --tut-prev-color: #4b5563;
                --tut-prev-border: #e5e7eb;
                --tut-skip-color: #ef4444;
                --tut-skip-border: #fecaca;
                --tut-skip-bg-hover: #fef2f2;

                position: fixed;
                bottom: 0;
                left: 0;
                right: 0;
                width: 100vw;
                background-color: var(--tut-bar-bg);
                border-top: 1px solid var(--tut-bar-border);
                padding: 15px max(12px, env(safe-area-inset-right)) max(15px, env(safe-area-inset-bottom)) max(12px, env(safe-area-inset-left));
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 20px;
                z-index: 2147483647;
                box-shadow: 0 -4px 12px var(--tut-bar-shadow);
                backdrop-filter: blur(5px);
                animation: slideUp 0.3s ease-out;
            }

            .tut-actions {
                display: flex;
                gap: 10px;
            }
            
            @keyframes slideUp {
                from { transform: translateY(100%); }
                to { transform: translateY(0); }
            }

            .tut-btn {
                border: none;
                border-radius: 50px;
                padding: 8px 20px;
                font-family: var(--dlux-main-font, var(--dlux-font-fallback, sans-serif));
                font-size: 0.95rem;
                cursor: pointer;
                transition: all 0.2s;
                font-weight: bold;
            }

            .tut-btn-next {
                background-color: var(--tut-next-bg);
                color: var(--tut-next-color);
                box-shadow: 0 2px 5px var(--tut-next-shadow);
            }
            .tut-btn-next:hover { background-color: var(--tut-next-bg-hover); transform: translateY(-1px); }

            .tut-btn-prev {
                background-color: var(--tut-prev-bg);
                color: var(--tut-prev-color);
                border: 1px solid var(--tut-prev-border);
            }
            .tut-btn-prev:hover { background-color: var(--tut-prev-bg-hover); }
            .tut-btn-prev:disabled { opacity: 0.5; cursor: not-allowed; }

            .tut-btn-skip {
                background-color: transparent;
                color: var(--tut-skip-color);
                border: 1px solid var(--tut-skip-border);
            }
            .tut-btn-skip:hover { background-color: var(--tut-skip-bg-hover); }

            .tut-progress {
                font-family: var(--dlux-main-font, var(--dlux-font-fallback, sans-serif));
                color: var(--tut-progress-color);
                font-weight: bold;
                min-width: 60px;
                text-align: center;
            }

            @media (max-width: 575.98px) {
                #tutorial-controls {
                    justify-content: space-between;
                    gap: 10px;
                }

                .tut-actions {
                    gap: 6px;
                }

                .tut-btn {
                    padding: 8px 12px;
                    font-size: 0.85rem;
                }
            }
        `;

        document.head.appendChild(style);
    }

    const startTourButtons = Array.from(document.querySelectorAll('#start-tour, [data-dlux-start-tour]'));
    startTourButtons.forEach((startTourBtn) => {
        startTourBtn.addEventListener('click', function(e) {
            e.preventDefault();

            // Grouped titlebar actions live in a rail that is closed by default, so
            // their steps would resolve to nothing. Open it for the tour and put it
            // back the way it was on the way out.
            const actionRail = window.__dluxTitlebarRail;
            const reopenRail = !!(actionRail && actionRail.isGrouped() && !actionRail.isOpen());
            if (reopenRail) {
                actionRail.open();
            }
            const releaseRail = () => {
                if (reopenRail && actionRail) {
                    actionRail.close();
                }
            };

            const steps = getTutorialSteps();

            if (steps.length === 0) {
                console.warn('No tutorial steps found for this page.');
                releaseRail();
                return;
            }

            let currentIndex = 0;

            let controls = document.getElementById('tutorial-controls');
            if (!controls) {
                controls = document.createElement('div');
                controls.id = 'tutorial-controls';
                controls.dir = direction;
                controls.lang = document.documentElement.lang || '';

                const progress = document.createElement('span');
                progress.id = 'tut-progress';
                progress.className = 'tut-progress';

                const actions = document.createElement('div');
                actions.className = 'tut-actions';

                const makeButton = (id, className, label) => {
                    const button = document.createElement('button');
                    button.type = 'button';
                    button.id = id;
                    button.className = `tut-btn ${className}`;
                    button.textContent = label;
                    return button;
                };

                actions.append(
                    makeButton('tut-prev', 'tut-btn-prev', text('tut_btn_prev', 'Previous')),
                    makeButton('tut-next', 'tut-btn-next', text('tut_btn_next', 'Next')),
                    makeButton('tut-skip', 'tut-btn-skip', text('tut_btn_skip', 'Skip')),
                );
                controls.append(progress, actions);
                document.body.appendChild(controls);
            }
            controls.style.display = 'flex';

            const driverObj = driverFactory({
                showProgress: false,
                showButtons: [],
                steps: steps,
                onHighlightStarted: () => {
                    currentIndex = driverObj.getActiveIndex() || 0;
                    updateControls();
                },
                onDestroyStarted: () => {
                    controls.style.display = 'none';
                    releaseRail();
                    driverObj.destroy();
                },
                onCloseClick: () => {
                    controls.style.display = 'none';
                    releaseRail();
                    driverObj.destroy();
                }
            });

            document.getElementById('tut-next').onclick = () => {
                if (currentIndex === steps.length - 1) {
                    controls.style.display = 'none';
                    releaseRail();
                    driverObj.destroy();
                } else {
                    driverObj.moveNext();
                }
            };
            document.getElementById('tut-prev').onclick = () => driverObj.movePrevious();
            document.getElementById('tut-skip').onclick = () => {
                controls.style.display = 'none';
                releaseRail();
                driverObj.destroy();
            };

            function updateControls() {
                const total = steps.length;
                const isLast = currentIndex === total - 1;
                const isFirst = currentIndex === 0;

                const ofText = text('tut_of', 'of');
                document.getElementById('tut-progress').innerText = `${currentIndex + 1} ${ofText} ${total}`;
                
                const nextBtn = document.getElementById('tut-next');
                const prevBtn = document.getElementById('tut-prev');

                nextBtn.innerText = isLast ? text('tut_btn_finish', 'Finish') : text('tut_btn_next', 'Next');
                prevBtn.disabled = isFirst;
            }
            
            driverObj.drive();
        });
    });
});
