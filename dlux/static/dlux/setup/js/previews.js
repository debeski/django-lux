/* System Settings live previews.
 *
 * This module owns mutations of rendered page chrome made from unsaved System
 * Settings values. Every handler is safe when its target is absent because the
 * setup wizard and the Options modal expose different page surfaces.
 */
(function (root) {
    'use strict';

    const { getNamedFieldValue } = root.DluxSetupDom;
    const { getSetupAllowedThemeCount, getSetupLanguageCount } = root.DluxSetup;

    // Mirrors TITLEBAR_ACTIONS_ORDER in dlux/system/constants.py. Keep this
    // complete: normalization also feeds the titlebar order builder.
    const TITLEBAR_ACTIONS_DEFAULT_ORDER = [
        'search',
        'theme',
        'language',
        'notifications',
        'home',
        'profile',
        'help',
        'users',
        'activity',
        'reports',
        'settings',
        'auth',
    ];
    const TITLEBAR_ACTIONS_KNOWN = new Set(TITLEBAR_ACTIONS_DEFAULT_ORDER);
    const SYSTEM_SETTINGS_STEPS = [
        'branding',
        'languages',
        'email',
        'security',
        'appearance',
        'titlebar',
        'sidebar',
        'navbar',
        'ribbon',
        'layout',
        'homepage',
        'login_page',
        'profile',
        'search',
        'notifications',
        'logging',
        'backups',
        'extras',
    ];
    const PREVIEW_CAPABILITIES = {
        branding: 'surface',
        languages: 'surface',
        appearance: 'surface',
        titlebar: 'surface',
        sidebar: 'surface',
        navbar: 'surface',
        ribbon: 'surface',
        layout: 'surface',
        homepage: 'popup',
        login_page: 'popup',
    };

    function parseJson(text, fallback) {
        try {
            return JSON.parse(text || '');
        } catch (error) {
            return fallback;
        }
    }

    function readBooleanField(form, selector, fallback) {
        const field = form.querySelector(selector);
        return field ? Boolean(field.checked) : Boolean(fallback);
    }

    function readTrimmedValue(form, selector, fallback) {
        const field = form.querySelector(selector);
        return field ? String(field.value || fallback || '').trim() : fallback || '';
    }

    function setPreviewVisibility(element, isVisible) {
        if (!element) return;
        element.classList.toggle('d-none', !isVisible);
        element.style.display = isVisible ? '' : 'none';
    }

    function normalizeTitlebarActionsOrder(value) {
        let rawValue = value;
        if (typeof rawValue === 'string') rawValue = parseJson(rawValue, []);
        if (!Array.isArray(rawValue)) rawValue = [];
        const seen = new Set();
        const normalized = [];
        rawValue.forEach((item) => {
            const key = String(item || '').trim();
            if (TITLEBAR_ACTIONS_KNOWN.has(key) && !seen.has(key)) {
                normalized.push(key);
                seen.add(key);
            }
        });
        TITLEBAR_ACTIONS_DEFAULT_ORDER.forEach((key) => {
            if (!seen.has(key)) normalized.push(key);
        });
        return normalized;
    }

    function readTitlebarActionsOrder(form) {
        return normalizeTitlebarActionsOrder(getNamedFieldValue(form, 'titlebar_actions_order'));
    }

    function applyTitlebarActionOrderPreview(titlebar, order) {
        const normalizedOrder = normalizeTitlebarActionsOrder(order);
        titlebar.querySelectorAll('[data-titlebar-actions]').forEach((container) => {
            const nodesByKey = new Map();
            Array.from(container.children).forEach((node) => {
                const key = node.getAttribute('data-titlebar-action-key')
                    || node.querySelector('[data-titlebar-action-key]')?.getAttribute('data-titlebar-action-key');
                if (key && !nodesByKey.has(key)) nodesByKey.set(key, node);
            });
            normalizedOrder.forEach((key) => {
                const node = nodesByKey.get(key);
                if (node) container.appendChild(node);
            });
        });
    }

    function applyTitlebarPreview(form) {
        const titlebar = document.querySelector('.titlebar');
        if (!titlebar) return;

        const showTitle = readBooleanField(form, '#id_titlebar_show_title', true);
        const accentEdge = readBooleanField(form, '#id_titlebar_accent_edge', false);
        const showLogo = readBooleanField(form, '#id_titlebar_show_logo', true);
        const showHome = readBooleanField(form, '#id_titlebar_show_home_button', true);
        const showLanguageSwitcher = readBooleanField(form, '#id_titlebar_show_language_switcher', false);
        const titleAlign = getNamedFieldValue(form, 'titlebar_title_align') || 'start';
        const titleSize = getNamedFieldValue(form, 'titlebar_title_size') || 'md';
        const height = getNamedFieldValue(form, 'titlebar_height') || 'balanced';
        const surface = getNamedFieldValue(form, 'titlebar_surface') || 'default';
        const logoTreatment = getNamedFieldValue(form, 'titlebar_logo_treatment') || 'none';
        const logoTreatmentShape = getNamedFieldValue(form, 'titlebar_logo_treatment_shape') || 'soft';
        const buttonsShape = getNamedFieldValue(form, 'titlebar_home_shape') || 'circle';
        const userHubStyle = getNamedFieldValue(form, 'titlebar_user_hub_style') || 'dropdown';
        const actionsLayout = getNamedFieldValue(form, 'titlebar_actions_layout') === 'grouped' ? 'grouped' : 'scattered';
        const homeUrl = readTrimmedValue(
            form,
            '#id_home_url',
            titlebar.querySelector('[data-titlebar-home]')?.getAttribute('href') || '/',
        );
        const scopeName = String(titlebar.dataset.titlebarScopeName || '').trim();
        const htmlLang = (
            document.documentElement.getAttribute('lang')
            || (root.USER_PREFS && root.USER_PREFS._lang)
            || 'en'
        ).split('-')[0];
        let systemNames = {};
        try {
            systemNames = JSON.parse(getNamedFieldValue(form, 'system_names') || '{}') || {};
        } catch (error) {
            systemNames = {};
        }
        const defaultLanguage = getNamedFieldValue(form, 'default_language') || 'en';
        const resolvedName = systemNames[htmlLang]
            || systemNames[defaultLanguage]
            || Object.values(systemNames).find(Boolean)
            || 'DjangoLux';

        titlebar.dataset.titleAlign = titleAlign;
        titlebar.dataset.titleSize = titleSize;
        titlebar.dataset.titlebarHeight = height;
        titlebar.dataset.titlebarSurface = surface;
        titlebar.dataset.titlebarLogoTreatment = logoTreatment;
        titlebar.dataset.titlebarLogoTreatmentShape = logoTreatmentShape;
        titlebar.dataset.titlebarButtonsShape = buttonsShape;
        titlebar.dataset.titlebarHomeShape = buttonsShape;
        titlebar.dataset.titlebarUserHubStyle = userHubStyle === 'titlebar_actions' ? 'titlebar_actions' : 'dropdown';
        titlebar.dataset.titlebarActionsLayout = actionsLayout;
        titlebar.dataset.titlebarShowTitle = showTitle ? 'true' : 'false';
        titlebar.dataset.titlebarShowLogo = showLogo ? 'true' : 'false';
        titlebar.dataset.titlebarShowHome = showHome ? 'true' : 'false';
        titlebar.dataset.titlebarShowLanguageSwitcher = showLanguageSwitcher ? 'true' : 'false';
        document.body.dataset.dluxTitlebarAccent = accentEdge ? 'on' : 'off';
        applyTitlebarActionOrderPreview(titlebar, readTitlebarActionsOrder(form));

        titlebar.querySelectorAll('[data-titlebar-home]').forEach((homeButton) => {
            if (homeUrl) homeButton.setAttribute('href', homeUrl);
        });
        document.querySelectorAll('#dlux-user-dropdown-card').forEach((card) => {
            const hideDropdown = userHubStyle === 'titlebar_actions';
            card.classList.toggle('d-none', hideDropdown);
            card.setAttribute('aria-hidden', hideDropdown ? 'true' : 'false');
        });

        const dropdownHelp = document.querySelector('#dlux-user-dropdown-card [data-dlux-start-tour]');
        const titlebarHelp = titlebar.querySelector('.titlebar__actions--titlebar [data-dlux-start-tour]');
        if (dropdownHelp && titlebarHelp) {
            if (userHubStyle === 'titlebar_actions') {
                dropdownHelp.removeAttribute('id');
                titlebarHelp.setAttribute('id', 'start-tour');
            } else {
                titlebarHelp.removeAttribute('id');
                dropdownHelp.setAttribute('id', 'start-tour');
            }
        }
        const titleTarget = titlebar.querySelector('[data-titlebar-title-text]');
        if (titleTarget) titleTarget.textContent = scopeName ? `${resolvedName} - ${scopeName}` : resolvedName;
    }

    function applySidebarPreview(form) {
        const sidebar = document.getElementById('sidebar');
        if (!sidebar) return;

        const sidebarEnabled = readBooleanField(form, '#id_sidebar_enabled', true);
        const accentEdge = readBooleanField(form, '#id_sidebar_accent_edge', false);
        const showIcons = readBooleanField(form, '#id_sidebar_show_icons', true);
        const showNotificationBadges = readBooleanField(form, '#id_sidebar_show_notification_badges', true);
        const collapseMode = getNamedFieldValue(form, 'sidebar_collapse_mode') || 'icons';
        const density = getNamedFieldValue(form, 'sidebar_density') || 'balanced';
        const allowUserDensity = readBooleanField(form, '#id_sidebar_allow_user_density', true);
        const enableToolbar = readBooleanField(form, '#id_sidebar_enable_toolbar', true);
        const showSectionsManager = readBooleanField(form, '#id_sidebar_show_sections_manager', true);
        const enableReorder = readBooleanField(form, '#id_sidebar_enable_reorder', true);
        const allowThemeOverride = readBooleanField(form, '#id_allow_user_theme_override', true);
        const allowUserLanguage = readBooleanField(form, '#id_allow_user_language_override', true);
        const themeToolVisible = allowThemeOverride && getSetupAllowedThemeCount(form) > 1;
        const densityToolVisible = allowUserDensity;

        setPreviewVisibility(sidebar, sidebarEnabled);
        sidebar.dataset.sidebarEnabled = sidebarEnabled ? 'true' : 'false';
        document.body.dataset.dluxSidebarAccent = accentEdge ? 'on' : 'off';
        sidebar.dataset.sidebarShowIcons = showIcons ? 'true' : 'false';
        sidebar.dataset.sidebarCollapseMode = collapseMode;
        sidebar.dataset.sidebarDensity = density;
        sidebar.dataset.sidebarDefaultDensity = density;
        sidebar.dataset.sidebarAllowUserDensity = allowUserDensity ? 'true' : 'false';

        const badgesEnabled = sidebarEnabled && showNotificationBadges;
        const sidebarTree = sidebar.querySelector('#sidebarTreeRoot');
        if (sidebarTree) sidebarTree.dataset.dluxSidebarNotificationBadgesEnabled = badgesEnabled ? 'true' : 'false';
        sidebar.querySelectorAll('[data-dlux-sidebar-notification-badge]').forEach((badge) => {
            badge.classList.toggle('d-none', !badgesEnabled || !String(badge.textContent || '').trim());
        });

        if (collapseMode === 'locked_expanded') sidebar.classList.remove('collapsed');
        const titlebar = document.querySelector('.titlebar');
        if (titlebar) {
            titlebar.dataset.sidebarCollapseMode = collapseMode;
            const startSide = titlebar.querySelector('.titlebar__side--start');
            if (startSide) {
                startSide.classList.toggle('titlebar__side--empty', !sidebarEnabled);
                startSide.classList.toggle('titlebar__side--has-toggle', sidebarEnabled && collapseMode !== 'locked_expanded');
                startSide.classList.toggle('titlebar__side--mobile-toggle', sidebarEnabled && collapseMode === 'locked_expanded');
            }
        }
        const titlebarToggle = document.getElementById('sidebarToggle');
        if (titlebarToggle) {
            titlebarToggle.classList.toggle(
                'sidebar-toggle--desktop-disabled',
                sidebarEnabled && collapseMode === 'locked_expanded',
            );
        }
        setPreviewVisibility(titlebarToggle, sidebarEnabled);

        const toggleIconPicker = form.querySelector('[data-dlux-icon-picker][data-icon-field="sidebar_toggle_icon"]');
        const toggleGlyph = titlebarToggle ? titlebarToggle.querySelector('i') : null;
        if (toggleIconPicker && toggleGlyph) {
            const icon = getNamedFieldValue(form, 'sidebar_toggle_icon') || 'bi-list';
            const directional = String(toggleIconPicker.getAttribute('data-icon-directional') || '')
                .split(/\s+/)
                .filter(Boolean);
            toggleGlyph.className = `bi ${icon}${directional.includes(icon) ? ' dlux-icon-directional' : ''}`;
        }

        const toolbar = sidebar.querySelector('.sidebar-toolbar');
        const themeArrow = document.getElementById('sidebarThemeArrow');
        const themeIndicator = document.getElementById('sidebarThemeIndicator');
        const themePopup = document.getElementById('sidebarThemePopup');
        const densityControl = sidebar.querySelector('.sidebar-density-control');
        const reorderToggle = document.getElementById('sidebarReorderToggle') || sidebar.querySelector('.reorder-toggle');
        const sectionsManagerLink = sidebar.querySelector('.sidebar-toolbar-link');
        const sectionsManagerVisible = showSectionsManager && Boolean(sectionsManagerLink);
        const toolbarVisible = sidebarEnabled && enableToolbar && Boolean(
            themeToolVisible || densityToolVisible || enableReorder || sectionsManagerVisible
        );

        setPreviewVisibility(themeArrow, sidebarEnabled && themeToolVisible);
        setPreviewVisibility(themeIndicator, sidebarEnabled && themeToolVisible);
        setPreviewVisibility(densityControl, sidebarEnabled && densityToolVisible);
        setPreviewVisibility(reorderToggle, sidebarEnabled && enableReorder);
        setPreviewVisibility(sectionsManagerLink, sidebarEnabled && sectionsManagerVisible);
        setPreviewVisibility(toolbar, toolbarVisible);
        if (!themeToolVisible && themePopup) themePopup.classList.remove('show');
        if (!densityToolVisible) document.getElementById('sidebarDensityPopup')?.classList.remove('show');
        sidebar.querySelectorAll('[data-sidebar-density-choice]').forEach((option) => {
            option.classList.toggle('is-active', option.getAttribute('data-sidebar-density-choice') === density);
        });

        setPreviewVisibility(document.querySelector('[data-options-card="theme"]'), themeToolVisible);
        setPreviewVisibility(
            document.querySelector('[data-options-card="language"]'),
            allowUserLanguage && getSetupLanguageCount(form) > 1,
        );
        setPreviewVisibility(
            document.querySelector('[data-options-card="sidebar-density"]'),
            sidebarEnabled && allowUserDensity,
        );
    }

    function applyBrandingPreview(form) {
        function previewAsset(fieldSelector, targets, attribute) {
            const valueInput = form.querySelector(fieldSelector);
            const picker = valueInput?.closest('[data-asset-picker]');
            const uploadInput = picker?.querySelector('[data-asset-picker-upload]');
            const selectedUrl = String(picker?.dataset.initialUrl || '').trim();
            const applyUrl = (url) => {
                if (!url) return;
                document.querySelectorAll(targets).forEach((element) => element.setAttribute(attribute, url));
            };
            if (uploadInput?.files?.[0]) {
                const reader = new FileReader();
                reader.onload = () => applyUrl(reader.result);
                reader.readAsDataURL(uploadInput.files[0]);
                return;
            }
            applyUrl(selectedUrl);
        }

        previewAsset('#id_logo', '.titlebar__logo, .dlux-setup-page-logo', 'src');
        previewAsset('#id_favicon', 'link[rel="icon"]', 'href');
    }

    function applyFooterPreview(form) {
        if (!form.querySelector('[name="footer_enabled"]')) return;
        const footer = document.querySelector('footer.dlux-footer');
        if (!footer) return;
        footer.style.display = readBooleanField(form, '#id_footer_enabled', true) ? '' : 'none';
        const text = getNamedFieldValue(form, 'footer_text');
        const textElement = footer.querySelector('.dlux-footer__text');
        if (textElement && text) textElement.textContent = text;
        const linkElement = footer.querySelector('.dlux-footer__link');
        if (linkElement) {
            const linkText = getNamedFieldValue(form, 'footer_link_text');
            const linkUrl = getNamedFieldValue(form, 'footer_link_url');
            if (linkUrl) linkElement.setAttribute('href', linkUrl);
            if (linkText || linkUrl) linkElement.textContent = linkText || linkUrl;
            setPreviewVisibility(linkElement, Boolean(linkUrl));
        }
    }

    function applyLayoutPreview(form) {
        const mappings = [
            ['sticky_table_headers', '#id_sticky_table_headers', 'dluxStickyHeader', true],
            ['resizable_table_columns', '#id_resizable_table_columns', 'dluxTableResize', true],
            ['zebra_striping', '#id_zebra_striping', 'dluxZebra', true],
            ['table_accent_edges', '#id_table_accent_edges', 'dluxTableAccent', false],
        ];
        mappings.forEach(([name, selector, dataKey, fallback]) => {
            if (form.querySelector(`[name="${name}"]`)) {
                document.body.dataset[dataKey] = readBooleanField(form, selector, fallback) ? 'on' : 'off';
            }
        });
        const tableEdges = getNamedFieldValue(form, 'table_edges');
        const cardEdges = getNamedFieldValue(form, 'card_edges');
        if (tableEdges) document.body.dataset.dluxTableEdges = tableEdges;
        if (cardEdges) document.body.dataset.dluxCardEdges = cardEdges;
    }

    function applyTableDensityPreview(form) {
        const density = getNamedFieldValue(form, 'default_table_density') || 'balanced';
        if (typeof root.applyDluxTableDensityPreview === 'function') {
            root.applyDluxTableDensityPreview(density);
        }
    }

    function applyThemePreview(theme, cssUrl) {
        if (typeof root.setTheme !== 'function') return;
        root.setTheme(theme, { preview: true, cssUrl: cssUrl || '' });
    }

    function applyFontPreview(form) {
        let storedFont = '';
        try {
            storedFont = localStorage.getItem('appFont') || '';
        } catch (error) {
            storedFont = '';
        }
        const personalFont = String(root.USER_PREFS?.font || storedFont).trim();
        if (personalFont) return;
        const language = String(document.documentElement.lang || root.USER_PREFS?._lang || 'en').split('-')[0];
        const defaults = parseJson(getNamedFieldValue(form, 'default_fonts'), {});
        const fontSlug = defaults && typeof defaults === 'object' ? defaults[language] : '';
        const family = fontSlug && root.DLUX_FONT_FAMILIES ? root.DLUX_FONT_FAMILIES[fontSlug] : '';
        if (family) document.documentElement.style.setProperty('--dlux-main-font', `'${family}', sans-serif`);
    }

    function applyNavbarPreview(form) {
        const navbar = document.querySelector('[data-dlux-navbar]');
        if (!navbar || !form.querySelector('[name="navbar_enabled"]')) return;
        const enabled = readBooleanField(form, '#id_navbar_enabled', false);
        const mode = getNamedFieldValue(form, 'navbar_default_mode') === 'history' ? 'history' : 'hierarchy';
        setPreviewVisibility(navbar, enabled);
        navbar.dataset.navbarMode = mode;
        if (enabled && typeof navbar.__dluxRenderMode === 'function') navbar.__dluxRenderMode(mode);
    }

    function applyRibbonPreview(form) {
        const ribbon = document.querySelector('.dlux-ribbon-header');
        if (!ribbon || !form.querySelector('[name="ribbon_layout"]')) return;
        const layout = getNamedFieldValue(form, 'ribbon_layout') || 'default';
        const style = getNamedFieldValue(form, 'ribbon_style') || 'accent';
        const showTitle = readBooleanField(form, '#id_ribbon_title', true) && layout !== 'compact';
        ['default', 'stacked', 'compact'].forEach((value) => {
            ribbon.classList.toggle(`dlux-ribbon-layout-${value}`, layout === value);
        });
        ['accent', 'panel', 'flat'].forEach((value) => {
            ribbon.classList.toggle(`dlux-ribbon-skin-${value}`, style === value);
        });
        setPreviewVisibility(ribbon.querySelector('.dlux-ribbon-heading'), showTitle);
    }

    function currentPreviewStep(form) {
        const steps = Array.from(form.querySelectorAll('.wizard-step'));
        const activeIndex = steps.findIndex((step) => !step.classList.contains('d-none') && step.style.display !== 'none');
        if (activeIndex >= 0) return SYSTEM_SETTINGS_STEPS[activeIndex] || '';
        const initialIndex = Number(form.dataset.dluxWizardInitialStep);
        return Number.isInteger(initialIndex) ? SYSTEM_SETTINGS_STEPS[initialIndex] || '' : '';
    }

    function visiblePreviewTarget(step) {
        const selectors = {
            branding: '.titlebar, footer.dlux-footer',
            languages: '.titlebar',
            titlebar: '.titlebar',
            sidebar: '#sidebar',
            navbar: '[data-dlux-navbar]',
            ribbon: '.dlux-ribbon-header',
        };
        if (step === 'appearance' || step === 'layout') return true;
        return Boolean(selectors[step] && document.querySelector(selectors[step]));
    }

    function resolvePreviewMode(form) {
        const step = currentPreviewStep(form);
        const capability = PREVIEW_CAPABILITIES[step] || '';
        if (!capability) return { mode: '', step };
        if (capability === 'popup') return { mode: 'popup', step };
        const modal = form.closest('#universalDynamicModal');
        return { mode: modal && visiblePreviewTarget(step) ? 'glass' : 'popup', step };
    }

    function previewButtonsFor(form) {
        const buttons = Array.from(form.querySelectorAll('[data-dlux-system-settings-preview]'));
        if (form.id) {
            const escapedId = root.CSS && typeof root.CSS.escape === 'function'
                ? root.CSS.escape(form.id)
                : form.id.replace(/["\\]/g, '\\$&');
            document.querySelectorAll(`[data-dlux-system-settings-preview][form="${escapedId}"]`).forEach((button) => {
                if (!buttons.includes(button)) buttons.push(button);
            });
        }
        return buttons;
    }

    function syncPreviewButtons(form) {
        const { mode, step } = resolvePreviewMode(form);
        previewButtonsFor(form).forEach((button) => {
            const unavailable = button.dataset.previewUnavailableLabel || 'Preview is not available for this step.';
            button.disabled = !mode;
            button.dataset.previewMode = mode;
            button.dataset.previewStep = step;
            button.setAttribute('aria-disabled', mode ? 'false' : 'true');
            if (mode) button.removeAttribute('title');
            else button.setAttribute('title', unavailable);
        });
    }

    let glassPreviewState = null;

    function exitGlassPreview() {
        if (!glassPreviewState) return;
        const { modal, button, clickHandler, keyHandler, hideHandler } = glassPreviewState;
        modal.classList.remove('dlux-system-preview-glass');
        delete modal.dataset.dluxPreviewHint;
        const content = modal.querySelector('.modal-content');
        if (content) delete content.dataset.dluxPreviewHint;
        document.body.classList.remove('dlux-system-preview-active');
        modal.removeEventListener('click', clickHandler, true);
        document.removeEventListener('keydown', keyHandler, true);
        modal.removeEventListener('hide.bs.modal', hideHandler);
        glassPreviewState = null;
        if (button?.isConnected) button.focus({ preventScroll: true });
    }

    function enterGlassPreview(form, button) {
        const modal = form.closest('#universalDynamicModal');
        if (!modal) return;
        exitGlassPreview();
        applySystemSettingsPreview(form);
        modal.dataset.dluxPreviewHint = root.DLUX_STRINGS?.preview_close_hint
            || 'Click anywhere, press Escape, or press Q to return.';
        const content = modal.querySelector('.modal-content');
        if (content) content.dataset.dluxPreviewHint = modal.dataset.dluxPreviewHint;
        modal.classList.add('dlux-system-preview-glass');
        document.body.classList.add('dlux-system-preview-active');

        const clickHandler = (event) => {
            event.preventDefault();
            event.stopImmediatePropagation();
            exitGlassPreview();
        };
        const keyHandler = (event) => {
            if (event.key !== 'Escape' && String(event.key || '').toLowerCase() !== 'q') return;
            event.preventDefault();
            event.stopImmediatePropagation();
            exitGlassPreview();
        };
        const hideHandler = () => exitGlassPreview();
        glassPreviewState = { modal, button, clickHandler, keyHandler, hideHandler };
        root.setTimeout(() => {
            if (!glassPreviewState || glassPreviewState.modal !== modal) return;
            modal.addEventListener('click', clickHandler, true);
            document.addEventListener('keydown', keyHandler, true);
            modal.addEventListener('hide.bs.modal', hideHandler);
        }, 0);
    }

    function previewElement(tag, className, text) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined && text !== null) element.textContent = String(text);
        return element;
    }

    function selectedAssetUrl(form, selector) {
        const input = form.querySelector(selector);
        return String(input?.closest('[data-asset-picker]')?.dataset.initialUrl || '').trim();
    }

    function previewSystemName(form) {
        const language = String(document.documentElement.lang || 'en').split('-')[0];
        const names = parseJson(getNamedFieldValue(form, 'system_names'), {});
        return names[language] || Object.values(names).find(Boolean) || 'DjangoLux';
    }

    function buildPopupShell(form, step) {
        const shell = previewElement('div', 'dlux-system-preview-shell');
        const theme = getNamedFieldValue(form, 'default_theme') || 'light';
        shell.dataset.previewTheme = theme;
        shell.dataset.previewStep = step;
        shell.dataset.cardEdges = getNamedFieldValue(form, 'card_edges') || 'curved';
        shell.dataset.tableEdges = getNamedFieldValue(form, 'table_edges') || 'curved';

        const titlebar = previewElement('header', 'dlux-system-preview-shell__titlebar');
        const logoUrl = selectedAssetUrl(form, '#id_logo');
        if (logoUrl) {
            const logo = previewElement('img', 'dlux-system-preview-shell__logo');
            logo.src = logoUrl;
            logo.alt = '';
            titlebar.appendChild(logo);
        }
        titlebar.appendChild(previewElement('strong', '', previewSystemName(form)));
        titlebar.appendChild(previewElement('span', 'dlux-system-preview-shell__actions', '⌕  ◐  ●'));
        shell.appendChild(titlebar);

        if (step === 'login_page') {
            const login = previewElement('main', 'dlux-system-preview-login');
            const hero = previewElement('section', 'dlux-system-preview-login__hero');
            const language = String(document.documentElement.lang || 'en').split('-')[0];
            hero.appendChild(previewElement(
                'h2',
                '',
                getNamedFieldValue(form, `login_hero_message_${language}`) || 'Welcome back',
            ));
            hero.appendChild(previewElement('p', '', 'Secure access to your workspace.'));
            const card = previewElement('section', 'dlux-system-preview-login__card');
            card.appendChild(previewElement('h3', '', 'Sign in'));
            card.appendChild(previewElement('div', 'dlux-system-preview-shell__input', 'Email'));
            card.appendChild(previewElement('div', 'dlux-system-preview-shell__input', 'Password'));
            card.appendChild(previewElement('div', 'dlux-system-preview-shell__button', 'Continue'));
            login.append(hero, card);
            shell.appendChild(login);
            return shell;
        }

        const navbarEnabled = readBooleanField(form, '#id_navbar_enabled', false);
        if (navbarEnabled || step === 'navbar') {
            const navbar = previewElement('nav', 'dlux-system-preview-shell__navbar');
            navbar.append(
                previewElement('span', '', 'Home'),
                previewElement('span', '', '›'),
                previewElement('span', '', getNamedFieldValue(form, 'navbar_default_mode') === 'history' ? 'Recent page' : 'Current section'),
            );
            shell.appendChild(navbar);
        }

        const workspace = previewElement('div', 'dlux-system-preview-shell__workspace');
        const sidebarEnabled = readBooleanField(form, '#id_sidebar_enabled', true);
        if (sidebarEnabled || step === 'sidebar') {
            const sidebar = previewElement('aside', 'dlux-system-preview-shell__sidebar');
            ['Dashboard', 'Records', 'Reports', 'Settings'].forEach((label) => {
                sidebar.appendChild(previewElement('div', '', label));
            });
            workspace.appendChild(sidebar);
        }

        const content = previewElement('main', 'dlux-system-preview-shell__content');
        if (step === 'homepage') {
            content.appendChild(previewElement('h1', '', getNamedFieldValue(form, 'public_root_title') || 'Welcome'));
            content.appendChild(previewElement(
                'p',
                'dlux-system-preview-shell__lead',
                getNamedFieldValue(form, 'public_root_meta_description') || 'Your public homepage preview.',
            ));
        } else {
            const ribbon = previewElement('section', 'dlux-system-preview-shell__ribbon');
            ribbon.dataset.layout = getNamedFieldValue(form, 'ribbon_layout') || 'default';
            ribbon.dataset.style = getNamedFieldValue(form, 'ribbon_style') || 'accent';
            if (readBooleanField(form, '#id_ribbon_title', true)) {
                ribbon.appendChild(previewElement('h2', '', 'Records'));
            }
            const tabs = previewElement('div', 'dlux-system-preview-shell__tabs');
            ['All', 'Active', 'Archived'].forEach((label, index) => {
                const tab = previewElement('span', index === 0 ? 'is-active' : '', label);
                tabs.appendChild(tab);
            });
            ribbon.appendChild(tabs);
            content.appendChild(ribbon);

            const cards = previewElement('div', 'dlux-system-preview-shell__cards');
            ['Overview', 'Recent activity', 'Quick actions'].forEach((label) => {
                const card = previewElement('article', 'dlux-system-preview-shell__card');
                card.appendChild(previewElement('strong', '', label));
                card.appendChild(previewElement('p', '', 'Preview content uses unsaved settings without writing them.'));
                cards.appendChild(card);
            });
            content.appendChild(cards);
        }
        workspace.appendChild(content);
        shell.appendChild(workspace);

        if (readBooleanField(form, '#id_footer_enabled', true)) {
            shell.appendChild(previewElement(
                'footer',
                'dlux-system-preview-shell__footer',
                getNamedFieldValue(form, 'footer_text') || `© ${previewSystemName(form)}`,
            ));
        }
        return shell;
    }

    function openPopupPreview(form, step, button) {
        document.querySelector('[data-dlux-system-preview-popup]')?.remove();
        const overlay = previewElement('div', 'dlux-system-preview-popup');
        overlay.dataset.dluxSystemPreviewPopup = '';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        const dialog = previewElement('div', 'dlux-system-preview-popup__dialog');
        const heading = previewElement('div', 'dlux-system-preview-popup__heading');
        const title = previewElement('strong', '', `Preview · ${step.replace(/_/g, ' ')}`);
        const close = previewElement('button', 'btn-close');
        close.type = 'button';
        close.setAttribute('aria-label', root.DLUX_STRINGS?.btn_close || 'Close');
        heading.append(title, close);
        dialog.append(heading, buildPopupShell(form, step));
        overlay.appendChild(dialog);
        document.body.appendChild(overlay);
        document.body.classList.add('dlux-system-preview-popup-active');

        const closePopup = () => {
            document.removeEventListener('keydown', keyHandler, true);
            overlay.remove();
            document.body.classList.remove('dlux-system-preview-popup-active');
            if (button?.isConnected) button.focus({ preventScroll: true });
        };
        const keyHandler = (event) => {
            if (event.key !== 'Escape' && String(event.key || '').toLowerCase() !== 'q') return;
            event.preventDefault();
            event.stopImmediatePropagation();
            closePopup();
        };
        close.addEventListener('click', closePopup);
        overlay.addEventListener('click', (event) => {
            if (event.target === overlay) {
                event.preventDefault();
                closePopup();
            }
        });
        document.addEventListener('keydown', keyHandler, true);
        close.focus({ preventScroll: true });
    }

    function initPreviewControls(form) {
        const buttons = previewButtonsFor(form);
        buttons.forEach((button) => {
            if (button.dataset.dluxSystemPreviewBound === 'true') return;
            button.dataset.dluxSystemPreviewBound = 'true';
            button.addEventListener('click', () => {
                const { mode, step } = resolvePreviewMode(form);
                if (!mode) return;
                applySystemSettingsPreview(form);
                if (mode === 'glass') enterGlassPreview(form, button);
                else openPopupPreview(form, step, button);
            });
        });
        if (form.dataset.dluxPreviewStepBound !== 'true') {
            form.dataset.dluxPreviewStepBound = 'true';
            form.addEventListener('dlux:wizard-step-change', () => syncPreviewButtons(form));
        }
        syncPreviewButtons(form);
    }

    function applySystemSettingsPreview(form) {
        if (!form || !form.classList.contains('dlux-system-setup-form')) return;
        applyTitlebarPreview(form);
        applyBrandingPreview(form);
        applySidebarPreview(form);
        applyNavbarPreview(form);
        applyRibbonPreview(form);
        applyTableDensityPreview(form);
        applyLayoutPreview(form);
        applyFontPreview(form);
        applyFooterPreview(form);
        root.dispatchEvent(new Event('resize'));
    }

    function initSystemSettingsPreview(scope) {
        scope.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            if (form.dataset.systemSettingsPreviewBound === 'true') {
                applySystemSettingsPreview(form);
                initPreviewControls(form);
                return;
            }
            form.dataset.systemSettingsPreviewBound = 'true';
            form.querySelectorAll('input[name], select[name], textarea[name]').forEach((field) => {
                const eventName = field.type === 'text' || field.tagName === 'TEXTAREA' ? 'input' : 'change';
                field.addEventListener(eventName, () => applySystemSettingsPreview(form));
                if (eventName !== 'change') {
                    field.addEventListener('change', () => applySystemSettingsPreview(form));
                }
            });
            applySystemSettingsPreview(form);
            initPreviewControls(form);
        });
    }

    const previewApi = {
        TITLEBAR_ACTIONS_DEFAULT_ORDER,
        applyBrandingPreview,
        applyFontPreview,
        applyFooterPreview,
        applyLayoutPreview,
        applyNavbarPreview,
        applyRibbonPreview,
        applySidebarPreview,
        applySystemSettingsPreview,
        applyTableDensityPreview,
        applyThemePreview,
        applyTitlebarPreview,
        initSystemSettingsPreview,
        normalizeTitlebarActionsOrder,
        readBooleanField,
        readTitlebarActionsOrder,
        readTrimmedValue,
        setPreviewVisibility,
    };
    root.DluxSetupPreview = Object.assign(root.DluxSetupPreview || {}, previewApi);
    root.DluxSetup = Object.assign(root.DluxSetup || {}, previewApi, {
        applyBrandingFilePreviews: applyBrandingPreview,
        applyImmediateSystemSettingsPreview: applySystemSettingsPreview,
        applyLayoutBodyPreview: applyLayoutPreview,
        initImmediateSystemSettingsPreview: initSystemSettingsPreview,
    });
})(typeof window !== 'undefined' ? window : globalThis);
