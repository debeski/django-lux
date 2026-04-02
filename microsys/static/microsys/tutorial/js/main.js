document.addEventListener("DOMContentLoaded", function () {
    // Tutorial Logic
    const driver = window.driver.js.driver;
    
    function getTutorialSteps() {
        const path = window.location.pathname;
        let steps = [];
        const t = window.TUT_STRINGS || {};

        // Base step that applies to most pages
        const sidebarStep = { element: '#sidebar', popover: { title: t.sidebar_title || 'Sidebar', description: t.sidebar_desc || 'Navigate between sections.', side: "right", align: 'start' }};

        // 1. Dashboard / Home (`/sys/`, `/index/`, `/`)
        if (path === '/' || path.includes('/index/') || path === '/sys/' || path === '/sys/dashboard/') {
            steps = [
                sidebarStep,
                { element: '.titlebar', popover: { title: t.titlebar_title || 'Titlebar', description: t.titlebar_desc || 'System name and user menu.', side: "bottom", align: 'center' }},
                { element: '.login-title-btn', popover: { title: t.usermenu_title || 'User Menu', description: t.usermenu_desc || 'Logout or profile.', side: "bottom", align: 'end' }},
                { element: '#sidebarThemeIndicator', popover: { title: t.options_theme_title || 'Theme', description: t.options_theme_desc || 'Change theme.', side: "top", align: 'center' }},
                { element: '#mainContent', popover: { title: t.maincontent_title || 'Workspace', description: t.maincontent_desc || 'Main content area.', side: "top", align: 'center' }}
            ];
        }
        // 2. Sections Management (`/sys/sections/`)
        else if (path.includes('/sys/sections/')) {
            steps = [
                sidebarStep,
                { element: '.bi-plus-lg', popover: { title: t.add_title || 'Add', description: t.add_desc || 'Add new section.', side: "left", align: 'center' }},
                { element: '.table', popover: { title: t.sections_list_title || 'Sections List', description: t.sections_list_desc || 'List of sections.', side: "top", align: 'start' }}
            ];
        }
        // 3. User Management (`/sys/users/`)
        else if (path.includes('/sys/users/')) {
            steps = [
                sidebarStep,
                { element: 'input[name="keyword"]', popover: { title: t.search_title || 'Search', description: t.search_desc || 'Search users.', side: "right", align: 'center' }},
                { element: 'a[href*="create_user"]', popover: { title: t.users_add_btn_title || 'Add User', description: t.users_add_btn_desc || 'Add new user.', side: "bottom", align: 'end' }},
                { element: '#btn-manage-scopes, #toggleScopes', popover: { title: t.users_scopes_title || 'Scopes', description: t.users_scopes_desc || 'Manage scopes.', side: "bottom", align: 'center' }},
                { element: '.badge', popover: { title: t.users_roles_title || 'User Roles', description: t.users_roles_desc || 'Role indicators.', side: "bottom", align: 'center' }},
                { element: '.table tbody tr', popover: { title: t.users_row_title || 'User Details', description: t.users_row_desc || 'Double click row.', side: "bottom", align: 'center' }},
                { element: '.table-responsive', popover: { title: t.table_title || 'Data Table', description: t.table_desc || 'User records.', side: "top", align: 'start' }}
            ];
        }
        // 4. Activity Logs (`/sys/logs/`)
        else if (path.includes('/sys/logs/')) {
             steps = [
                sidebarStep,
                { element: 'input[name="keyword"]', popover: { title: t.search_title || 'Search', description: t.search_desc || 'Search logs.', side: "right", align: 'center' }},
                { element: '.log-row, .table tbody tr', popover: { title: t.logs_row_title || 'Activity Details', description: t.logs_row_desc || 'Double-click to view details.', side: "bottom", align: 'center' }},
                { element: '.table-responsive-lg', popover: { title: t.table_title || 'Data Table', description: t.table_desc || 'Activity records.', side: "top", align: 'start' }}
            ];
        }
        // 5. Options / Settings (`/sys/options/`)
        else if (path.includes('/sys/options/')) {
             steps = [
                sidebarStep,
                { element: '.accessibility-switch', popover: { title: t.options_access_title || 'Accessibility', description: t.options_access_desc || 'Accessibility options.', side: "bottom", align: 'center' }},
                { element: '.table-borderless', popover: { title: t.options_info_title || 'System Info', description: t.options_info_desc || 'Server information.', side: "bottom", align: 'center' }},
                { element: '.theme-preview', popover: { title: t.options_theme_title || 'Themes', description: t.options_theme_desc || 'Change appearance.', side: "top", align: 'center' }},
                { element: '.lang-option, [data-lang]', popover: { title: t.options_lang_title || 'Language', description: t.options_lang_desc || 'Language options.', side: "top", align: 'center' }},
                { element: '#autofillToggle', popover: { title: t.options_autofill_title || 'Autofill', description: t.options_autofill_desc || 'Autofill options.', side: "top", align: 'center' }}
            ];
        }
        // 6. Profile (`/accounts/profile/`)
        else if (path.includes('/accounts/profile/')) {
            steps = [
                sidebarStep,
                { element: '.info-value', popover: { title: t.profile_details_title || 'Profile Details', description: t.profile_details_desc || 'Personal data.', side: "right", align: 'center' }},
                { element: 'a[href*="edit_profile"]', popover: { title: t.profile_edit_title || 'Edit Profile', description: t.profile_edit_desc || 'Update info.', side: "left", align: 'center' }},
                { element: '.bi-shield-lock-fill', popover: { title: t.profile_2fa_title || 'Security Settings', description: t.profile_2fa_desc || 'Enable 2FA.', side: "top", align: 'center' }},
                { element: '.stats-card', popover: { title: t.profile_stats_title || 'Profile Stats', description: t.profile_stats_desc || 'Your statistics.', side: "top", align: 'center' }},
                { element: '.activity-timeline', popover: { title: t.profile_activity_title || 'Activity', description: t.profile_activity_desc || 'Recent actions.', side: "top", align: 'center' }}
            ];
        }
        // Check for generic List Views (Fallback if not matched above but has list elements)
        else if (document.querySelector('input[name="keyword"]') && document.querySelector('.table')) {
            steps = [
                sidebarStep,
                { element: 'input[name="keyword"]', popover: { title: t.search_title || 'Search', description: t.search_desc || 'Search records.', side: "right", align: 'center' }},
                { element: '.bi-plus-lg', popover: { title: t.add_title || 'Add New', description: t.add_desc || 'Add new item.', side: "left", align: 'center' }},
                { element: '.table-responsive-lg, .table-responsive', popover: { title: t.table_title || 'Data Table', description: t.table_desc || 'Records table.', side: "top", align: 'start' }},
            ];
        }
        // Fallback
        else {
            steps = [
                sidebarStep,
                { element: '#mainContent', popover: { title: t.maincontent_title || 'Content', description: t.maincontent_desc || 'Page content.', side: "top", align: 'center' }},
            ];
        }
        
        // Filter out steps where element doesn't exist
        return steps.filter(step => document.querySelector(step.element));
    }

    // Driver instance will be created on click
    // const driverObj = driver({...}); removed to avoid stale config

    // Hack: Force LTR for Driver.js popovers to prevent positioning bugs in RTL layout
    // Check if style already exists to avoid duplication
    if (!document.getElementById('driver-rtl-fix')) {
        const style = document.createElement('style');
        style.id = 'driver-rtl-fix';
        style.innerHTML = `
            .driver-popover {
                /* Reset direction for positioning calculations */
                direction: ltr !important; 
                
                /* Force high z-index and fixed positioning */
                z-index: 2147483647 !important;
                position: fixed !important;
                
                /* CRITICAL: Reset right/bottom defaults in RTL to allow top/left to function */
                right: auto !important;
                bottom: auto !important;
                
                /* Styling */
                background-color: #fff !important;
                color: #333 !important;
                border: 1px solid #ddd !important;
                box-shadow: 0 5px 15px rgba(0,0,0,0.3) !important;
                border-radius: 5px !important;
                min-width: 250px !important;
                max-width: 300px !important;
            }
            
            /* Ensure content inside uses RTL for Arabic text */
            .driver-popover-title, .driver-popover-description {
                direction: rtl !important;
                text-align: right !important;
                font-family: 'Shabwa', sans-serif !important;
                color: #333 !important;
            }
            
            .driver-popover-title {
                font-weight: bold !important;
                font-size: 1.1rem !important;
                margin-bottom: 8px !important;
            }
            
            .driver-popover-arrow {
                content: '' !important;
                display: none !important; /* Hide arrow as it often causes misalignments in hacks */
            }

            /* Hide Default Footer and Buttons Aggressively */
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

            /* Custom Controls Bar */
            #tutorial-controls {
                position: fixed;
                bottom: 0;
                left: 0;
                right: 0;
                width: 100vw;
                background-color: rgba(255, 255, 255, 0.95);
                border-top: 1px solid #dee2e6;
                padding: 15px 0;
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 20px;
                z-index: 2147483648; /* Higher than popover */
                box-shadow: 0 -4px 12px rgba(0,0,0,0.05);
                backdrop-filter: blur(5px);
                direction: ltr;
                animation: slideUp 0.3s ease-out;
            }
            
            @keyframes slideUp {
                from { transform: translateY(100%); }
                to { transform: translateY(0); }
            }

            .tut-btn {
                border: none;
                border-radius: 50px;
                padding: 8px 20px;
                font-family: 'Shabwa', sans-serif;
                font-size: 0.95rem;
                cursor: pointer;
                transition: all 0.2s;
                font-weight: bold;
            }

            .tut-btn-next {
                background-color: #3b82f6;
                color: white;
                box-shadow: 0 2px 5px rgba(59, 130, 246, 0.3);
            }
            .tut-btn-next:hover { background-color: #2563eb; transform: translateY(-1px); }

            .tut-btn-prev {
                background-color: #f3f4f6;
                color: #4b5563;
                border: 1px solid #e5e7eb;
            }
            .tut-btn-prev:hover { background-color: #e5e7eb; }
            .tut-btn-prev:disabled { opacity: 0.5; cursor: not-allowed; }

            .tut-btn-skip {
                background-color: transparent;
                color: #ef4444;
                border: 1px solid #fecaca;
            }
            .tut-btn-skip:hover { background-color: #fef2f2; }

            .tut-progress {
                font-family: 'Shabwa', sans-serif;
                color: #4b5563;
                font-weight: bold;
                min-width: 60px;
                text-align: center;
            }
        `;

        document.head.appendChild(style);
    }

    const startTourBtn = document.getElementById('start-tour');
    if (startTourBtn) {
        startTourBtn.addEventListener('click', function(e) {
            e.preventDefault();
            
            const steps = getTutorialSteps();
            
            if (steps.length === 0) {
                console.warn('No tutorial steps found for this page.');
                return;
            }

            // Instantiate Driver on click to ensure fresh config
            const t = window.TUT_STRINGS || {};
            
            // Helper to get active index since getActiveIndex() availability varies
            let currentIndex = 0;

            // Create Custom UI if not exists
            let controls = document.getElementById('tutorial-controls');
            if (!controls) {
                controls = document.createElement('div');
                controls.id = 'tutorial-controls';
                controls.innerHTML = `
                    <span id="tut-progress" class="tut-progress"></span>
                    <div style="display: flex; gap: 10px;">
                        <button id="tut-prev" class="tut-btn tut-btn-prev">${t.btn_prev || 'Previous'}</button>
                        <button id="tut-next" class="tut-btn tut-btn-next">${t.btn_next || 'Next'}</button>
                        <button id="tut-skip" class="tut-btn tut-btn-skip">${t.btn_skip || 'Cancel'}</button>
                    </div>
                `;
                document.body.appendChild(controls);
            }
            controls.style.display = 'flex';

            const driverObj = driver({
                showProgress: false, // We handle it manually
                showButtons: [], // Hide default buttons if possible via config
                steps: steps,
                onHighlightStarted: (element, step, options) => {
                    // Update UI
                    // Try to find index of current step in steps array
                    // Since steps are objects, simple indexOf might fail if cloned, but let's try direct object ref first or rely on internal tracking
                    // driverObj.getActiveIndex() is best if available.
                    
                    try {
                        currentIndex = driverObj.getActiveIndex();
                    } catch (e) {
                         // Fallback if needed, but it should be there in recent versions
                    }

                    updateControls();
                },
                onDestroyStarted: () => {
                    controls.style.display = 'none';
                    driverObj.destroy();
                },
                onCloseClick: () => {
                     controls.style.display = 'none';
                     driverObj.destroy();
                }
            });

            // Bind Actions
            document.getElementById('tut-next').onclick = () => {
                if (currentIndex === steps.length - 1) {
                    controls.style.display = 'none';
                    driverObj.destroy();
                } else {
                    driverObj.moveNext();
                }
            };
            document.getElementById('tut-prev').onclick = () => driverObj.movePrevious();
            document.getElementById('tut-skip').onclick = () => {
                controls.style.display = 'none';
                driverObj.destroy();
            };

            function updateControls() {
                const total = steps.length;
                const isLast = currentIndex === total - 1;
                const isFirst = currentIndex === 0;

                const ofText = (window.TUT_STRINGS && window.TUT_STRINGS.of) ? window.TUT_STRINGS.of : 'of';
                document.getElementById('tut-progress').innerText = `${currentIndex + 1} ${ofText} ${total}`;
                
                const nextBtn = document.getElementById('tut-next');
                const prevBtn = document.getElementById('tut-prev');

                const nextText = (window.TUT_STRINGS && window.TUT_STRINGS.btn_next) ? window.TUT_STRINGS.btn_next : 'Next';
                const finishText = (window.TUT_STRINGS && window.TUT_STRINGS.btn_finish) ? window.TUT_STRINGS.btn_finish : 'Finish';

                nextBtn.innerText = isLast ? finishText : nextText;
                prevBtn.disabled = isFirst;
            }
            
            driverObj.drive();
        });
    }
});
