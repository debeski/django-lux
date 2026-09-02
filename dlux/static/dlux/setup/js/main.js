(function () {
    'use strict';

    function parseJson(text, fallback) {
        try {
            return JSON.parse(text || '');
        } catch (err) {
            return fallback;
        }
    }

    const TITLEBAR_ACTIONS_DEFAULT_ORDER = [
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

    // Pure builder/config transforms live in setup/js/builder_model.js so they
    // can be unit tested without a DOM. Destructured here so every call site in
    // this file reads exactly as it did when they were local declarations.
    const {
        normalizeLanguageCode,
        normalizeNavbarBuilderNode,
        readNavbarBuilderConfig,
        navbarHierarchyHasNodes,
        sidebarLabelPayload,
        sidebarNodeId,
        sidebarEntryToNavbarNode,
        normalizeCatalog,
        buildCatalogLookup,
        findCatalogEntry,
        cloneEntry,
        makeGroupId,
        collectSelectedItemIds,
        availableItems,
        groupedAvailableItems,
        findEntryLocation,
        insertEntryIntoConfig,
        topLevelItems,
        availableItemDisplayLabel,
        cloneGroupEntry,
        extractImportedSettings,
        frameworkDefaultLabels,
        humanizeKey,
        normalizeEntry,
        normalizeSidebarConfig,
        resolveBuilderGroupLabel,
        resolveBuilderItemLabel
    } = window.DluxSetupModel;

    // Theme and font pickers live in setup/js/appearance.js so they can be
    // exercised in isolation. Destructured here so `scan()` calls them exactly
    // as it did when they were local declarations.
    const {
        initSetupThemePicker,
        initSetupFontPicker,
        unlockEmailDependentFields,
        initEmailApply,
        initEmailSendTest,
        initEmailDeliveryOptions,
        initLogBuilder,
        initProfileBuilder,
        applyBrandingFilePreviews,
        applyFooterPreview,
        applyLayoutBodyPreview,
        applyNotificationPreview,
        applySetupFormStateValues,
        applyTableDensityPreview,
        getSetupStateKey,
        persistSetupFormState,
        readBooleanField,
        readSetupWizardCurrentStep,
        readTrimmedValue,
        rememberSetupWizardStep,
        resolveSetupStateSurface,
        setPreviewVisibility,
        applyTranslationOverridesToMatrix,
        createLanguageRow,
        createSystemNameRow,
        currentSetupLanguageCode,
        ensureTranslationLanguageColumn,
        escapeHtml,
        findSystemNameRow,
        getSetupLanguageCount,
        initLanguageFontsEditor,
        readSystemNames,
        removeTranslationLanguageColumn,
        syncTranslationOverrides,
        firstInvalidControlInStep,
        getSetupAllowedThemeCount,
        initGlobalSearchOptions,
        initSetupHomeFields,
        initSystemSetupEnterBehavior,
        initSystemSetupStepValidation,
        isElementVisible,
        setJsonField,
        setNamedFieldReadonly,
        syncTitlebarActionsBuilderVisibility
    } = window.DluxSetup;

    // Shared field/dependent helpers and the security cluster now live in
    // setup/js/dom.js and setup/js/security.js. Destructured so every call site
    // below reads exactly as it did when these were local declarations.
    const {
        t,
        namedFieldSelector,
        getNamedFieldInputs,
        getNamedFieldValue,
        setNamedFieldDisabled,
        applyDependentTooltip,
        dependentReason,
        setDependentFieldEnabled,
        getSetupStepControls,
        isElementHiddenInsideStep,
        restoreImportedEmailPasswordNotice,
        setBuilderSectionEnabled,
        setCheckboxField,
        setDependentSectionEnabled,
        setImportedEmailPasswordNotice,
        setImportedSetupFinishVisible,
        setNamedFieldValue,
        setupRequiresEmailPassword,
        stepHasRenderedServerError,
        stepHasValidationError,
        syncSetupCustomValidation,
        updateSetupStepValidationState
    } = window.DluxSetupDom;
    const {
        syncPublicPageVisibility,
        initPublicRegistrationOptions,
        initPublicPageOptions,
        initClientIpOptions,
        initAuthSecurityOptions,
        initLoginPageOptions
    } = window.DluxSetup;

    function normalizeTitlebarActionsOrder(value) {
        let rawValue = value;
        if (typeof rawValue === 'string') {
            rawValue = parseJson(rawValue, []);
        }
        if (!Array.isArray(rawValue)) {
            rawValue = [];
        }
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
            if (!seen.has(key)) {
                normalized.push(key);
            }
        });
        return normalized;
    }

    function readTitlebarActionsOrder(form) {
        return normalizeTitlebarActionsOrder(getNamedFieldValue(form, 'titlebar_actions_order'));
    }

    function writeTitlebarActionsOrder(form, order) {
        const field = getNamedFieldInputs(form, 'titlebar_actions_order')[0];
        if (!field) {
            return;
        }
        field.value = JSON.stringify(normalizeTitlebarActionsOrder(order));
        field.dispatchEvent(new Event('change', { bubbles: true }));
    }



    function readSetupState(form) {
        try {
            return parseJson(sessionStorage.getItem(getSetupStateKey(form)), null);
        } catch (err) {
            return null;
        }
    }





    function restoreSetupFormState(root) {
        root.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            if (form.dataset.setupStateRestored === 'true') {
                return;
            }
            form.dataset.setupStateRestored = 'true';

            const state = readSetupState(form);
            const expectedSurface = resolveSetupStateSurface(form);
            if (!state || state.surface !== expectedSurface || !state.values || typeof state.values !== 'object') {
                return;
            }

            applySetupFormStateValues(form, state.values);
            form.__dluxPendingSetupState = state;
            if (Number.isInteger(Number(state.currentStep)) && Number(state.currentStep) >= 0) {
                rememberSetupWizardStep(form, Number(state.currentStep));
                form.dataset.dluxWizardInitialStep = String(Number(state.currentStep));
            }

            rehydrateSetupLanguageEditors(form);
            restoreImportedEmailPasswordNotice(form);
        });
    }

    function finalizeSetupFormStateRestore(root) {
        root.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            const state = form.__dluxPendingSetupState;
            if (!state || form.dataset.setupStateRestoreFinalized === 'true') {
                return;
            }
            form.dataset.setupStateRestoreFinalized = 'true';
            window.requestAnimationFrame(() => {
                if (Number.isInteger(Number(state.currentStep)) && Number(state.currentStep) >= 0) {
                    rememberSetupWizardStep(form, Number(state.currentStep));
                }
                applySetupFormStateValues(form, state.values, { dispatchEvents: true });
                rehydrateSetupLanguageEditors(form);
                restoreImportedEmailPasswordNotice(form);
                syncTranslationOverrides(form);
                applyImmediateSystemSettingsPreview(form);
                sessionStorage.removeItem(getSetupStateKey(form));
                delete form.__dluxPendingSetupState;
            });
        });
    }


    function rehydrateSetupLanguageEditors(form) {
        if (!form || !form.querySelector('[data-language-catalog-editor]')) {
            return;
        }
        const languages = parseJson(getNamedFieldValue(form, 'languages'), null);
        if (!languages || typeof languages !== 'object') {
            return;
        }
        const systemNames = parseJson(getNamedFieldValue(form, 'system_names'), {});
        const defaultLanguage = getNamedFieldValue(form, 'default_language') || 'en';
        rebuildLanguageCatalog(form, languages, systemNames, defaultLanguage);
    }

    window.__dluxGetWizardInitialStep = function (container) {
        const form = (container && container.matches && container.matches('form.dlux-system-setup-form'))
            ? container
            : container && container.querySelector
                ? container.querySelector('form.dlux-system-setup-form')
                : null;
        if (!form) return null;
        const steps = Array.from(form.querySelectorAll('.wizard-step'));
        for (let index = 0; index < steps.length; index += 1) {
            if (stepHasValidationError(steps[index])) {
                return index;
            }
        }
        return null;
    };













    function syncSidebarBehaviorConfig(form) {
        if (!form) {
            return;
        }
        const hiddenInput = form.querySelector('input[name="sidebar_config"]');
        if (!hiddenInput) {
            return;
        }
        const parsed = parseJson(hiddenInput.value || '{}', {});
        const nextConfig = parsed && typeof parsed === 'object' ? parsed : {};
        nextConfig.enabled = readBooleanField(form, '#id_sidebar_enabled', true);
        nextConfig.accent_edge = readBooleanField(form, '#id_sidebar_accent_edge', false);
        nextConfig.enable_reorder = readBooleanField(form, '#id_sidebar_enable_reorder', true);
        nextConfig.show_toolbar = readBooleanField(form, '#id_sidebar_enable_toolbar', true);
        nextConfig.show_sections_manager = readBooleanField(form, '#id_sidebar_show_sections_manager', true);
        nextConfig.show_icons = readBooleanField(form, '#id_sidebar_show_icons', true);
        nextConfig.show_notification_badges = readBooleanField(form, '#id_sidebar_show_notification_badges', true);
        nextConfig.density = getNamedFieldValue(form, 'sidebar_density') || 'balanced';
        nextConfig.allow_user_density = readBooleanField(form, '#id_sidebar_allow_user_density', true);
        nextConfig.collapse_mode = getNamedFieldValue(form, 'sidebar_collapse_mode') || 'icons';
        nextConfig.toggle_icon = getNamedFieldValue(form, 'sidebar_toggle_icon') || 'bi-list';
        if (!Array.isArray(nextConfig.entries)) {
            nextConfig.entries = [];
        }
        if (!Object.prototype.hasOwnProperty.call(nextConfig, 'home_url_name')) {
            nextConfig.home_url_name = null;
        }
        hiddenInput.value = JSON.stringify(nextConfig);
    }

    function syncNavbarBehaviorConfig(form) {
        if (!form) {
            return;
        }
        const hiddenInput = form.querySelector('input[name="navbar_config"]');
        if (!hiddenInput) {
            return;
        }
        const config = readNavbarBuilderConfig(parseJson(hiddenInput.value || '{}', {}));
        config.enabled = readBooleanField(form, '#id_navbar_enabled', false);
        config.default_mode = getNamedFieldValue(form, 'navbar_default_mode') === 'history' ? 'history' : 'hierarchy';
        config.allow_user_mode_override = readBooleanField(form, '#id_navbar_allow_user_mode_override', true);
        hiddenInput.value = JSON.stringify(config);
    }


    function seedNavbarConfigFromSidebar(form) {
        const shell = form ? form.closest('.dlux-system-settings-shell') : null;
        if (!shell || !shell.classList.contains('mode-setup')) {
            return;
        }
        const navbarInput = form.querySelector('input[name="navbar_config"]');
        const sidebarInput = form.querySelector('input[name="sidebar_config"]');
        if (!navbarInput || !sidebarInput) {
            return;
        }
        const navbarConfig = readNavbarBuilderConfig(parseJson(navbarInput.value || '{}', {}));
        if (!navbarConfig.enabled || navbarHierarchyHasNodes(navbarConfig)) {
            return;
        }
        const sidebarConfig = parseJson(sidebarInput.value || '{}', {});
        const langCode = currentSetupLanguageCode(form);
        const nodes = (Array.isArray(sidebarConfig.entries) ? sidebarConfig.entries : [])
            .map((entry, index) => sidebarEntryToNavbarNode(entry, index, langCode))
            .filter(Boolean);
        if (!nodes.length) {
            return;
        }
        navbarConfig.hierarchy = { nodes };
        navbarInput.value = JSON.stringify(readNavbarBuilderConfig(navbarConfig));
        navbarInput.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function initNavbarBuilder(builder) {
        if (!builder || builder.dataset.navbarBuilderBound === 'true') {
            return;
        }
        builder.dataset.navbarBuilderBound = 'true';

        const form = builder.closest('form');
        const hiddenInput = form ? form.querySelector('input[name="navbar_config"]') : null;
        if (!form || !hiddenInput) {
            return;
        }

        const catalog = parseJson(builder.querySelector('.dlux-navbar-catalog-data')?.value || '[]', [])
            .filter((entry) => entry && entry.kind === 'item' && entry.url_name);
        const languages = parseJson(builder.querySelector('.dlux-navbar-languages-data')?.value || '{}', {});
        const currentLang = String((window.USER_PREFS && window.USER_PREFS._lang) || document.documentElement.getAttribute('lang') || 'en').toLowerCase();
        const state = {
            config: readNavbarBuilderConfig(parseJson(hiddenInput.value || builder.querySelector('.dlux-navbar-config-data')?.value || '{}', {})),
            selectedId: '',
            search: '',
            showSystemItems: false,
        };

        const refs = {
            rootSelect: builder.querySelector('[data-navbar-root-select]'),
            tree: builder.querySelector('[data-navbar-tree]'),
            routeList: builder.querySelector('[data-navbar-route-list]'),
            routeSearch: builder.querySelector('[data-navbar-route-search]'),
            inspectorShell: builder.querySelector('[data-navbar-inspector-shell]'),
            systemToggle: builder.querySelector('[data-navbar-system-toggle]'),
        };

        function findNode(nodes, id, parent, index) {
            for (let nodeIndex = 0; nodeIndex < nodes.length; nodeIndex += 1) {
                const node = nodes[nodeIndex];
                if (node.id === id) {
                    return { node, parent: parent || nodes, index: index === undefined ? nodeIndex : index };
                }
                const childLocation = findNode(node.children || [], id);
                if (childLocation) {
                    return childLocation;
                }
            }
            return null;
        }

        function catalogEntry(urlName) {
            return catalog.find((entry) => entry.url_name === urlName);
        }

        function renderRootOptions() {
            if (!refs.rootSelect) {
                return;
            }
            refs.rootSelect.querySelectorAll('optgroup').forEach((group) => group.remove());
            const routeGroup = document.createElement('optgroup');
            routeGroup.label = t('navbar_root_specific_pages', 'Specific page');
            const seen = new Set();
            catalog.forEach((entry) => {
                const urlName = String(entry.url_name || '').trim();
                if (!urlName || seen.has(urlName)) {
                    return;
                }
                // The hierarchy may parent an id-bound route, but the root has to
                // be reachable with no context — it renders on every page.
                if (entry.requires_args || entry.is_form_page) {
                    return;
                }
                seen.add(urlName);
                const option = document.createElement('option');
                option.value = `route:${urlName}`;
                option.textContent = `${String(entry.label || urlName).trim()} (${urlName})`;
                routeGroup.appendChild(option);
            });
            if (routeGroup.children.length) {
                refs.rootSelect.appendChild(routeGroup);
            }

            const configured = state.config.root || { mode: 'neutral', url_name: '' };
            const selectedValue = configured.mode === 'route'
                ? `route:${configured.url_name || ''}`
                : configured.mode;
            const available = Array.from(refs.rootSelect.options).some((option) => option.value === selectedValue);
            if (!available) {
                state.config.root = { mode: 'neutral', url_name: '' };
            }
            refs.rootSelect.value = available ? selectedValue : 'neutral';
        }

        function nodeLabel(node) {
            const labels = node.labels || {};
            // Prefer the override for the current display language so a manual node
            // named in several languages shows the right one in the editor (not just
            // whichever happened to be first in the object).
            const localized = labels[currentLang] || labels[currentLang.split('-')[0]];
            if (localized && String(localized).trim()) {
                return String(localized).trim();
            }
            const route = node.kind === 'route' ? catalogEntry(node.url_name) : null;
            if (route && String(route.label || '').trim()) {
                return String(route.label).trim();
            }
            // No current-language override and no catalog label (manual node named in
            // only other languages): fall back to any configured label. A freshly
            // added group has none, and its generated id is not a name — showing
            // `manual-1788164320169-6798` in the tree and the inspector header is
            // noise, so an unnamed node says so instead.
            const anyLabel = Object.values(labels).find((label) => String(label || '').trim());
            if (anyLabel && String(anyLabel).trim()) {
                return String(anyLabel).trim();
            }
            return t('navbar_untitled_node', 'Untitled group');
        }

        function serialize() {
            state.config.enabled = readBooleanField(form, '#id_navbar_enabled', false);
            state.config.default_mode = getNamedFieldValue(form, 'navbar_default_mode') === 'history' ? 'history' : 'hierarchy';
            state.config.allow_user_mode_override = readBooleanField(form, '#id_navbar_allow_user_mode_override', true);
            hiddenInput.value = JSON.stringify(state.config);
        }

        function selectNode(id) {
            state.selectedId = id || '';
            renderAll();
        }

        function appendNode(node) {
            const selected = findNode(state.config.hierarchy.nodes, state.selectedId);
            const parent = selected ? selected.node.children : state.config.hierarchy.nodes;
            parent.push(node);
            state.selectedId = node.id;
            commitAndRender();
        }

        function createTreeNode(node) {
            const shell = document.createElement('div');
            shell.className = 'dlux-navbar-node';
            const button = document.createElement('button');
            button.type = 'button';
            button.className = `dlux-navbar-node__surface${state.selectedId === node.id ? ' is-active' : ''}`;
            button.innerHTML = `
                <span class="dlux-navbar-node__label">
                    <i class="bi ${node.kind === 'route' ? 'bi-link-45deg' : 'bi-folder2-open'}"></i>
                    <span>${escapeHtml(nodeLabel(node))}</span>
                </span>
                <small>${escapeHtml(node.kind === 'route' ? node.url_name : t('navbar_manual_node', ''))}</small>
            `;
            button.addEventListener('click', () => selectNode(node.id));
            shell.appendChild(button);
            if ((node.children || []).length) {
                const children = document.createElement('div');
                children.className = 'dlux-navbar-node__children';
                node.children.forEach((child) => children.appendChild(createTreeNode(child)));
                shell.appendChild(children);
            }
            return shell;
        }

        function renderTree() {
            refs.tree.innerHTML = '';
            state.config.hierarchy.nodes.forEach((node) => refs.tree.appendChild(createTreeNode(node)));
            if (!refs.tree.children.length) {
                refs.tree.innerHTML = `<p class="text-muted small mb-0">${t('navbar_empty_tree', '')}</p>`;
            }
        }

        function routeMatches(entry) {
            const needle = state.search.toLowerCase();
            if (!needle) {
                return true;
            }
            return [entry.label, entry.url_name, entry.group_label]
                .some((value) => String(value || '').toLowerCase().includes(needle));
        }

        function renderRoutes() {
            refs.routeList.innerHTML = '';
            const groups = {};
            catalog
                .filter((entry) => (state.showSystemItems || !entry.is_system) && routeMatches(entry))
                .forEach((entry) => {
                const key = entry.group_label || entry.group_key || t('navbar_routes', '');
                groups[key] = groups[key] || [];
                groups[key].push(entry);
            });
            Object.entries(groups).forEach(([groupLabel, entries]) => {
                const group = document.createElement('section');
                group.className = 'dlux-navbar-route-group';
                group.innerHTML = `<h6>${escapeHtml(groupLabel)}</h6>`;
                entries.forEach((entry) => {
                    const button = document.createElement('button');
                    button.type = 'button';
                    button.className = 'dlux-navbar-route';
                    // An id-bound route is a valid parent or child, but it has no
                    // context-free URL, so its crumb renders as plain text.
                    const idBound = entry.requires_args
                        ? ` <em>${escapeHtml(t('navbar_route_needs_id', 'needs an id — not clickable'))}</em>`
                        : '';
                    button.innerHTML = `
                        <span>${escapeHtml(entry.label)}</span>
                        <small>${escapeHtml(entry.url_name)}${idBound}</small>
                    `;
                    button.addEventListener('click', () => appendNode({
                        kind: 'route',
                        id: entry.url_name,
                        url_name: entry.url_name,
                        children: [],
                    }));
                    group.appendChild(button);
                });
                refs.routeList.appendChild(group);
            });
            if (!refs.routeList.children.length) {
                refs.routeList.innerHTML = `<p class="text-muted small mb-0">${t('navbar_no_routes', '')}</p>`;
            }
        }

        function languageRows() {
            const languageEntries = Object.entries(languages && typeof languages === 'object' ? languages : {});
            return languageEntries.length ? languageEntries : [['en', { name: 'en' }]];
        }

        function selectedNodeLocation() {
            return findNode(state.config.hierarchy.nodes, state.selectedId);
        }

        function updateNodeLabel(node, code, value) {
            node.labels = node.labels || {};
            const cleaned = String(value || '').trim();
            if (cleaned) {
                node.labels[code] = cleaned;
            } else {
                delete node.labels[code];
            }
            if (!Object.keys(node.labels).length) {
                delete node.labels;
            }
            renderTree();
        }

        function updateNodeUrl(node, value) {
            const cleaned = String(value || '').trim();
            if (cleaned) {
                node.url = cleaned;
            } else {
                delete node.url;
            }
        }

        function renderInspector() {
            if (navbarInspectorShell) {
                navbarInspectorShell.render(selectedNodeLocation());
            }
        }

        function renderAll() {
            renderRootOptions();
            renderTree();
            renderRoutes();
            renderInspector();
        }

        function commitAndRender() {
            serialize();
            renderAll();
        }

        function addManualNode() {
            appendNode({
                kind: 'manual',
                id: `manual-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
                children: [],
            });
        }

        function moveSelected(delta) {
            const selected = findNode(state.config.hierarchy.nodes, state.selectedId);
            if (!selected) {
                return;
            }
            const nextIndex = selected.index + delta;
            if (nextIndex < 0 || nextIndex >= selected.parent.length) {
                return;
            }
            selected.parent.splice(selected.index, 1);
            selected.parent.splice(nextIndex, 0, selected.node);
            commitAndRender();
        }

        const navbarInspectorShell = window.DluxInspectorShell && refs.inspectorShell
            ? window.DluxInspectorShell.create(refs.inspectorShell, {
                adapter: {
                    getActions: ({ selection }) => {
                        const actions = [{
                            id: 'add-group',
                            label: t('navbar_add_manual_node', 'Add Group'),
                            icon: 'bi bi-folder-plus',
                            variant: 'outline-primary',
                            onClick: addManualNode,
                        }];
                        if (!selection) {
                            return actions;
                        }
                        actions.push(
                            {
                                id: 'move-up',
                                label: t('move_up', 'Up'),
                                icon: 'bi bi-arrow-up',
                                disabled: selection.index <= 0,
                                onClick: () => moveSelected(-1),
                            },
                            {
                                id: 'move-down',
                                label: t('move_down', 'Down'),
                                icon: 'bi bi-arrow-down',
                                disabled: selection.index >= selection.parent.length - 1,
                                onClick: () => moveSelected(1),
                            },
                            {
                                id: 'remove',
                                label: t('sidebar_remove_entry', 'Remove'),
                                icon: 'bi bi-trash3',
                                variant: 'outline-danger',
                                onClick: () => {
                                    const current = selectedNodeLocation();
                                    if (!current) return null;
                                    current.parent.splice(current.index, 1);
                                    state.selectedId = '';
                                    commitAndRender();
                                    return null;
                                },
                            },
                            {
                                id: 'move-root',
                                label: t('sidebar_move_root', 'Move To Root'),
                                icon: 'bi bi-distribute-horizontal',
                                disabled: selection.parent === state.config.hierarchy.nodes,
                                onClick: () => {
                                    const current = selectedNodeLocation();
                                    if (!current || current.parent === state.config.hierarchy.nodes) {
                                        return null;
                                    }
                                    current.parent.splice(current.index, 1);
                                    state.config.hierarchy.nodes.push(current.node);
                                    commitAndRender();
                                    return null;
                                },
                            }
                        );
                        return actions;
                    },
                    getFields: ({ selection }) => {
                        if (!selection) return [];
                        const node = selection.node;
                        const labelFields = languageRows().map(([code, payload]) => {
                            const langCode = String(code || '').toLowerCase();
                            return {
                                id: `label-${langCode}`,
                                type: 'text',
                                label: `${(payload && payload.name) || langCode} (${langCode})`,
                                value: (node.labels && node.labels[langCode]) || '',
                                placeholder: node.kind === 'route'
                                    ? t('navbar_route_label_fallback', '')
                                    : t('navbar_manual_label_placeholder', ''),
                                commitOn: 'input',
                                onInput: ({ value }) => {
                                    updateNodeLabel(node, langCode, value);
                                },
                            };
                        });
                        return labelFields.concat([
                            {
                                id: 'url',
                                type: 'url',
                                label: t('navbar_node_url', 'Optional URL'),
                                value: node.url || '',
                                placeholder: '/dashboard/',
                                help: t('navbar_node_url_help', ''),
                                commitOn: 'input',
                                onInput: ({ value }) => {
                                    updateNodeUrl(node, value);
                                },
                            },
                        ]);
                    },
                    getTitle: ({ selection }) => (selection ? nodeLabel(selection.node) : ''),
                    getBadge: ({ selection }) => {
                        if (!selection) return '';
                        return selection.node.kind === 'route'
                            ? selection.node.url_name
                            : t('navbar_manual_node', '');
                    },
                    // The popover hangs off the selected row itself, so the node
                    // being edited is never underneath it.
                    getAnchor: () => refs.tree.querySelector('.dlux-navbar-node__surface.is-active'),
                    clearSelection: () => {
                        state.selectedId = '';
                        renderTree();
                    },
                    commit: serialize,
                },
                strings: {
                    clearSelection: t('navbar_clear_selection', 'Clear selection'),
                    empty: t('navbar_node_inspector_empty', 'Select a node.'),
                },
                presentation: 'popover',
                dismissOnOutsideClick: true,
                // Clicking another node moves the selection; it must not be read as
                // a dismiss, or the popover would close instead of re-anchoring.
                dismissIgnoreSelector: '.dlux-navbar-node__surface',
            })
            : null;

        refs.routeSearch.addEventListener('input', () => {
            state.search = refs.routeSearch.value || '';
            renderRoutes();
        });
        refs.rootSelect?.addEventListener('change', () => {
            const value = String(refs.rootSelect.value || 'neutral');
            state.config.root = value.startsWith('route:')
                ? { mode: 'route', url_name: value.slice(6) }
                : { mode: value === 'home' ? 'home' : 'neutral', url_name: '' };
            serialize();
        });
        if (refs.systemToggle) {
            refs.systemToggle.addEventListener('change', () => {
                state.showSystemItems = Boolean(refs.systemToggle.checked);
                renderRoutes();
            });
        }
        hiddenInput.addEventListener('change', () => {
            state.config = readNavbarBuilderConfig(parseJson(hiddenInput.value || '{}', {}));
            state.selectedId = '';
            renderAll();
        });

        renderAll();
    }

    function applyTitlebarActionOrderPreview(titlebar, order) {
        const normalizedOrder = normalizeTitlebarActionsOrder(order);
        titlebar.querySelectorAll('[data-titlebar-actions]').forEach((container) => {
            const nodesByKey = new Map();
            Array.from(container.children).forEach((node) => {
                const key = node.getAttribute('data-titlebar-action-key') || node.querySelector('[data-titlebar-action-key]')?.getAttribute('data-titlebar-action-key');
                if (key && !nodesByKey.has(key)) {
                    nodesByKey.set(key, node);
                }
            });
            normalizedOrder.forEach((key) => {
                const node = nodesByKey.get(key);
                if (node) {
                    container.appendChild(node);
                }
            });
        });
    }

    function applyTitlebarPreview(form) {
        const titlebar = document.querySelector('.titlebar');
        if (!titlebar) {
            return;
        }

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
        const actionOrder = readTitlebarActionsOrder(form);
        const homeUrl = readTrimmedValue(form, '#id_home_url', titlebar.querySelector('[data-titlebar-home]')?.getAttribute('href') || '/');
        const scopeName = String(titlebar.dataset.titlebarScopeName || '').trim();
        const htmlLang = (document.documentElement.getAttribute('lang') || (window.USER_PREFS && window.USER_PREFS._lang) || 'en').split('-')[0];
        let systemNames = {};
        try {
            systemNames = JSON.parse(getNamedFieldValue(form, 'system_names') || '{}') || {};
        } catch (e) {
            systemNames = {};
        }
        const defaultLanguage = getNamedFieldValue(form, 'default_language') || 'en';
        const resolvedName = systemNames[htmlLang] || systemNames[defaultLanguage] || Object.values(systemNames).find(Boolean) || 'DjangoLux';
        const resolvedTitle = scopeName ? `${resolvedName} - ${scopeName}` : resolvedName;

        titlebar.dataset.titleAlign = titleAlign;
        titlebar.dataset.titleSize = titleSize;
        titlebar.dataset.titlebarHeight = height;
        titlebar.dataset.titlebarSurface = surface;
        titlebar.dataset.titlebarLogoTreatment = logoTreatment;
        titlebar.dataset.titlebarLogoTreatmentShape = logoTreatmentShape;
        titlebar.dataset.titlebarButtonsShape = buttonsShape;
        titlebar.dataset.titlebarHomeShape = buttonsShape;
        titlebar.dataset.titlebarUserHubStyle = userHubStyle === 'titlebar_actions' ? 'titlebar_actions' : 'dropdown';
        titlebar.dataset.titlebarShowTitle = showTitle ? 'true' : 'false';
        titlebar.dataset.titlebarShowLogo = showLogo ? 'true' : 'false';
        titlebar.dataset.titlebarShowHome = showHome ? 'true' : 'false';
        titlebar.dataset.titlebarShowLanguageSwitcher = showLanguageSwitcher ? 'true' : 'false';
        document.body.dataset.dluxTitlebarAccent = accentEdge ? 'on' : 'off';
        applyTitlebarActionOrderPreview(titlebar, actionOrder);

        titlebar.querySelectorAll('[data-titlebar-home]').forEach((homeButton) => {
            if (homeUrl) {
                homeButton.setAttribute('href', homeUrl);
            }
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
        if (titleTarget) {
            titleTarget.textContent = resolvedTitle;
        }
    }



    function applySidebarPreview(form) {
        const sidebar = document.getElementById('sidebar');
        if (!sidebar) {
            return;
        }

        const sidebarEnabled = readBooleanField(form, '#id_sidebar_enabled', true);
        const accentEdge = readBooleanField(form, '#id_sidebar_accent_edge', false);
        const showIcons = readBooleanField(form, '#id_sidebar_show_icons', true);
        const showNotificationBadges = readBooleanField(form, '#id_sidebar_show_notification_badges', true);
        const notificationsEnabled = readBooleanField(form, '#id_notifications_enabled', true);
        const collapseMode = getNamedFieldValue(form, 'sidebar_collapse_mode') || 'icons';
        const density = getNamedFieldValue(form, 'sidebar_density') || 'balanced';
        const allowUserDensity = readBooleanField(form, '#id_sidebar_allow_user_density', true);
        const enableToolbar = readBooleanField(form, '#id_sidebar_enable_toolbar', true);
        const showSectionsManager = readBooleanField(form, '#id_sidebar_show_sections_manager', true);
        const enableReorder = readBooleanField(form, '#id_sidebar_enable_reorder', true);
        const allowThemeOverride = readBooleanField(form, '#id_allow_user_theme_override', true);
        const allowUserLanguage = readBooleanField(form, '#id_allow_user_language_override', true);
        const allowedThemeCount = getSetupAllowedThemeCount(form);
        const languageCount = getSetupLanguageCount(form);
        const themeToolVisible = allowThemeOverride && allowedThemeCount > 1;
        const densityToolVisible = allowUserDensity;
        const reorderToolVisible = enableReorder;

        setPreviewVisibility(sidebar, sidebarEnabled);
        sidebar.dataset.sidebarEnabled = sidebarEnabled ? 'true' : 'false';
        document.body.dataset.dluxSidebarAccent = accentEdge ? 'on' : 'off';
        sidebar.dataset.sidebarShowIcons = showIcons ? 'true' : 'false';
        sidebar.dataset.sidebarCollapseMode = collapseMode;
        sidebar.dataset.sidebarDensity = density;
        sidebar.dataset.sidebarDefaultDensity = density;
        sidebar.dataset.sidebarAllowUserDensity = allowUserDensity ? 'true' : 'false';
        const sidebarNotificationBadgesEnabled = sidebarEnabled && notificationsEnabled && showNotificationBadges;
        const sidebarTree = sidebar.querySelector('#sidebarTreeRoot');
        if (sidebarTree) {
            sidebarTree.dataset.dluxSidebarNotificationBadgesEnabled = sidebarNotificationBadgesEnabled ? 'true' : 'false';
        }
        sidebar.querySelectorAll('[data-dlux-sidebar-notification-badge]').forEach((badge) => {
            const hasCount = String(badge.textContent || '').trim().length > 0;
            badge.classList.toggle('d-none', !sidebarNotificationBadgesEnabled || !hasCount);
        });

        if (collapseMode === 'locked_expanded') {
            sidebar.classList.remove('collapsed');
        }

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
            titlebarToggle.classList.toggle('sidebar-toggle--desktop-disabled', sidebarEnabled && collapseMode === 'locked_expanded');
        }
        setPreviewVisibility(titlebarToggle, sidebarEnabled);

        // The chosen glyph lands on the live toggle as it is picked. Guarded on the
        // picker being rendered: without it the value cannot change, so the class
        // the server already resolved is the correct one to leave alone.
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
            themeToolVisible || densityToolVisible || reorderToolVisible || sectionsManagerVisible
        );

        setPreviewVisibility(themeArrow, sidebarEnabled && themeToolVisible);
        setPreviewVisibility(themeIndicator, sidebarEnabled && themeToolVisible);
        setPreviewVisibility(densityControl, sidebarEnabled && densityToolVisible);
        setPreviewVisibility(reorderToggle, sidebarEnabled && reorderToolVisible);
        setPreviewVisibility(sectionsManagerLink, sidebarEnabled && sectionsManagerVisible);
        setPreviewVisibility(toolbar, toolbarVisible);

        if (!themeToolVisible && themePopup) {
            themePopup.classList.remove('show');
        }

        if (!densityToolVisible) {
            const densityPopup = document.getElementById('sidebarDensityPopup');
            if (densityPopup) {
                densityPopup.classList.remove('show');
            }
        }

        sidebar.querySelectorAll('[data-sidebar-density-choice]').forEach((option) => {
            option.classList.toggle('is-active', option.getAttribute('data-sidebar-density-choice') === density);
        });

        const themeCard = document.querySelector('[data-options-card="theme"]');
        const languageCard = document.querySelector('[data-options-card="language"]');
        const sidebarDensityCard = document.querySelector('[data-options-card="sidebar-density"]');

        setPreviewVisibility(themeCard, themeToolVisible);
        setPreviewVisibility(languageCard, allowUserLanguage && languageCount > 1);
        setPreviewVisibility(sidebarDensityCard, sidebarEnabled && allowUserDensity);
    }




    function applyImmediateSystemSettingsPreview(form) {
        if (!form || !form.classList.contains('dlux-system-setup-form')) {
            return;
        }
        applyTitlebarPreview(form);
        applyNotificationPreview(form);
        applyBrandingFilePreviews(form);
        applySidebarPreview(form);
        applyTableDensityPreview(form);
        applyLayoutBodyPreview(form);
        applyFooterPreview(form);
        window.dispatchEvent(new Event('resize'));
    }

    function initImmediateSystemSettingsPreview(root) {
        root.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            if (form.dataset.immediatePreviewBound === 'true') {
                applyImmediateSystemSettingsPreview(form);
                return;
            }

            form.dataset.immediatePreviewBound = 'true';

            form.querySelectorAll('input[name], select[name], textarea[name]').forEach((field) => {
                const eventName = field.type === 'text' || field.tagName === 'TEXTAREA' ? 'input' : 'change';
                field.addEventListener(eventName, () => {
                    applyImmediateSystemSettingsPreview(form);
                });
                if (eventName !== 'change') {
                    field.addEventListener('change', () => {
                        applyImmediateSystemSettingsPreview(form);
                    });
                }
            });

            applyImmediateSystemSettingsPreview(form);
        });
    }








    function initBuilder(builder) {
        if (!builder || builder.dataset.builderBound === 'true') {
            return;
        }
        builder.dataset.builderBound = 'true';

        const form = builder.closest('form');
        const hiddenInput = form ? form.querySelector('input[name="sidebar_config"]') : null;
        if (!hiddenInput) {
            return;
        }

        const catalogData = builder.querySelector('.dlux-sidebar-catalog-data');
        const fallbackCatalogData = builder.querySelector('.dlux-sidebar-catalog-fallback-data');
        const configData = builder.querySelector('.dlux-sidebar-config-data');
        const languages = parseJson(builder.querySelector('.dlux-sidebar-languages-data')?.value || '{}', {});
        const currentLang = String((window.USER_PREFS && window.USER_PREFS._lang) || document.documentElement.getAttribute('lang') || 'en').toLowerCase();
        const catalog = normalizeCatalog(parseJson(catalogData ? catalogData.value : '[]', []));
        const fallbackCatalog = normalizeCatalog(parseJson(fallbackCatalogData ? fallbackCatalogData.value : '[]', []));
        const catalogLookup = buildCatalogLookup(catalog);
        const fallbackCatalogLookup = buildCatalogLookup(fallbackCatalog);
        const state = {
            catalog,
            config: normalizeSidebarConfig(
                parseJson(hiddenInput.value || (configData ? configData.value : '{}'), {}),
                catalogLookup,
                fallbackCatalogLookup
            ),
            selected: null,
            selectedTargetGroup: null,
            search: '',
            dragging: null,
            showSystemItems: false,
            showFormPages: false,
        };

        const refs = {
            selectedTree: builder.querySelector('[data-builder-selected-tree]'),
            availableList: builder.querySelector('[data-builder-available-list]'),
            search: builder.querySelector('[data-builder-search]'),
            systemToggle: builder.querySelector('[data-builder-system-toggle]'),
            formToggle: builder.querySelector('[data-builder-form-toggle]'),
            inspectorShell: builder.querySelector('[data-builder-inspector-shell]'),
            iconValue: builder.querySelector('[data-builder-icon-value]'),
            iconPicker: builder.querySelector('[data-dlux-icon-picker][data-icon-field="sidebar_builder_entry_icon"]'),
            iconPickerHolder: builder.querySelector('[data-builder-icon-picker-holder]'),
        };
        refs.iconInput = refs.iconPicker ? refs.iconPicker.querySelector('[data-icon-input]') : null;
        refs.iconPreview = refs.iconPicker ? refs.iconPicker.querySelector('[data-icon-preview]') : null;

        function clearDragFeedback() {
            builder.querySelectorAll('.dlux-builder-drop-target').forEach(el => el.classList.remove('dlux-builder-drop-target'));
            builder.querySelectorAll('.dlux-builder-drop-before').forEach(el => el.classList.remove('dlux-builder-drop-before'));
            builder.querySelectorAll('.dlux-builder-drop-after').forEach(el => el.classList.remove('dlux-builder-drop-after'));
            builder.querySelectorAll('.is-dragging').forEach(el => el.classList.remove('is-dragging'));
        }

        function serialize() {
            hiddenInput.value = JSON.stringify(state.config);
        }

        function languageRows() {
            const rows = Object.entries(languages && typeof languages === 'object' ? languages : {});
            return rows.length ? rows : [['en', { name: 'en' }]];
        }

        // Per-language name override resolution for the builder's own tree display.
        // Precedence: explicit per-language override → the current-language catalog
        // label (so the Selected tree matches the Available pane and runtime instead
        // of a label baked in whatever language it was added in) → the stored label
        // (only reached for non-discovered/custom entries and groups).
        function entryLabelForDisplay(entry) {
            const labels = entry && entry.labels;
            if (labels && typeof labels === 'object') {
                const override = labels[currentLang] || labels[currentLang.split('-')[0]];
                if (override && String(override).trim()) {
                    return override;
                }
            }
            const discovered = findCatalogEntry(entry, catalogLookup);
            if (discovered) {
                return availableItemDisplayLabel(discovered);
            }
            return (entry && entry.label) || '';
        }

        function renderAvailable() {
            refs.availableList.innerHTML = '';

            groupedAvailableItems(state).forEach(group => {
                const section = document.createElement('div');
                section.className = 'dlux-builder-available-group';
                const groupButton = document.createElement('button');
                groupButton.type = 'button';
                groupButton.className = 'dlux-builder-item available-item fw-semibold';
                groupButton.dataset.pane = 'available';
                groupButton.dataset.entryId = group.id;
                groupButton.dataset.entryKind = 'group';
                if (state.selected && state.selected.pane === 'available' && state.selected.kind === 'group' && state.selected.id === group.id) {
                    groupButton.classList.add('is-active');
                }
                groupButton.innerHTML = `
                    <span class="dlux-builder-item-main">
                        <i class="bi ${group.icon}"></i>
                        <span>${group.label}</span>
                    </span>
                    <span class="badge text-bg-light">${group.items.length}</span>
                `;
                groupButton.addEventListener('click', () => {
                    state.selected = { pane: 'available', id: group.id, kind: 'group' };
                    state.selectedTargetGroup = null;
                    renderAll();
                });
                groupButton.addEventListener('dblclick', () => {
                    addSelectedAvailableItem();
                });
                groupButton.draggable = true;
                groupButton.addEventListener('dragstart', () => {
                    state.dragging = { pane: 'available', id: group.id, kind: 'group' };
                    groupButton.classList.add('is-dragging');
                });
                groupButton.addEventListener('dragend', () => {
                    state.dragging = null;
                    clearDragFeedback();
                });
                section.appendChild(groupButton);

                const children = document.createElement('div');
                children.className = 'dlux-builder-available-items';

                group.items.forEach(item => {
                    const button = document.createElement('button');
                    button.type = 'button';
                    button.className = 'dlux-builder-item available-item is-child';
                    button.dataset.pane = 'available';
                    button.dataset.entryId = item.id;
                    button.dataset.entryKind = 'item';
                    if (state.selected && state.selected.pane === 'available' && state.selected.kind === 'item' && state.selected.id === item.id) {
                        button.classList.add('is-active');
                    }
                    button.innerHTML = `
                        <span class="dlux-builder-item-main">
                            <i class="bi ${item.icon}"></i>
                            <span>${availableItemDisplayLabel(item)}</span>
                        </span>
                        <span class="badge text-bg-light">${item.url_name || item.id}</span>
                    `;
                    button.addEventListener('click', () => {
                        state.selected = { pane: 'available', id: item.id, kind: 'item' };
                        state.selectedTargetGroup = null;
                        renderAll();
                    });
                    button.addEventListener('dblclick', () => {
                        addSelectedAvailableItem();
                    });
                    button.draggable = true;
                    button.addEventListener('dragstart', () => {
                        state.dragging = { pane: 'available', id: item.id, kind: 'item' };
                        button.classList.add('is-dragging');
                    });
                    button.addEventListener('dragend', () => {
                        state.dragging = null;
                        clearDragFeedback();
                    });
                    children.appendChild(button);
                });

                section.appendChild(children);

                refs.availableList.appendChild(section);
            });

            if (!refs.availableList.children.length) {
                refs.availableList.innerHTML = `<div class="text-muted small">${t('sidebar_no_available', 'No available entries match the current selection.')}</div>`;
            }
        }

        function makeNode(entry, parentGroupId) {
            const wrapper = document.createElement('div');
            wrapper.className = `dlux-builder-node ${entry.kind === 'group' ? 'is-group' : 'is-item'}`;
            wrapper.dataset.entryId = entry.id;
            wrapper.dataset.entryKind = entry.kind;
            wrapper.draggable = true;

            if (state.selected && state.selected.pane === 'selected' && state.selected.id === entry.id && state.selected.kind === entry.kind) {
                wrapper.classList.add('is-active');
            }

            wrapper.addEventListener('click', (event) => {
                event.stopPropagation();
                state.selected = { pane: 'selected', id: entry.id, kind: entry.kind };
                state.selectedTargetGroup = entry.kind === 'group' ? entry.id : (parentGroupId || null);
                renderAll();
            });

            wrapper.addEventListener('dragstart', (event) => {
                event.stopPropagation();
                state.dragging = { pane: 'selected', id: entry.id, kind: entry.kind };
                wrapper.classList.add('is-dragging');
            });

            wrapper.addEventListener('dragend', () => {
                state.dragging = null;
                clearDragFeedback();
            });

            wrapper.addEventListener('dragover', (event) => {
                if (!state.dragging) return;
                event.preventDefault();
                event.stopPropagation();
                const rect = wrapper.getBoundingClientRect();
                const before = event.clientY < rect.top + rect.height / 2;
                wrapper.classList.toggle('dlux-builder-drop-before', before);
                wrapper.classList.toggle('dlux-builder-drop-after', !before);
            });

            wrapper.addEventListener('dragleave', () => {
                wrapper.classList.remove('dlux-builder-drop-before', 'dlux-builder-drop-after');
            });

            wrapper.addEventListener('drop', (event) => {
                if (!state.dragging) return;
                event.preventDefault();
                event.stopPropagation();
                const rect = wrapper.getBoundingClientRect();
                const before = event.clientY < rect.top + rect.height / 2;
                moveDraggedEntry({
                    type: parentGroupId ? 'group-node' : 'root-node',
                    targetId: entry.id,
                    targetKind: entry.kind,
                    before,
                    parentGroupId,
                });
            });

            if (entry.kind === 'group') {
                wrapper.innerHTML = `
                    <div class="dlux-builder-group-header">
                        <span class="dlux-builder-item-main">
                            <i class="bi ${entry.icon}"></i>
                            <span>${entryLabelForDisplay(entry)}</span>
                        </span>
                        <span class="badge text-bg-light">${(entry.items || []).length}</span>
                    </div>
                    <div class="dlux-builder-group-items" data-group-dropzone="${entry.id}"></div>
                `;

                const itemsContainer = wrapper.querySelector('[data-group-dropzone]');
                itemsContainer.addEventListener('dragover', (event) => {
                    if (!state.dragging || state.dragging.kind !== 'item') return;
                    event.preventDefault();
                    itemsContainer.classList.add('dlux-builder-drop-target');
                });
                itemsContainer.addEventListener('dragleave', () => {
                    itemsContainer.classList.remove('dlux-builder-drop-target');
                });
                itemsContainer.addEventListener('drop', (event) => {
                    if (!state.dragging || state.dragging.kind !== 'item') return;
                    event.preventDefault();
                    event.stopPropagation();
                    moveDraggedEntry({ type: 'group-container', groupId: entry.id });
                });

                (entry.items || []).forEach(item => {
                    itemsContainer.appendChild(makeNode(item, entry.id));
                });
            } else {
                wrapper.innerHTML = `
                    <span class="dlux-builder-item-main">
                        <i class="bi ${entry.icon}"></i>
                        <span>${entryLabelForDisplay(entry)}</span>
                    </span>
                    <span class="badge text-bg-light">${entry.url_name}</span>
                `;
            }

            return wrapper;
        }

        function renderSelected() {
            refs.selectedTree.innerHTML = '';

            state.config.entries.forEach(entry => {
                refs.selectedTree.appendChild(makeNode(entry, null));
            });

            if (!refs.selectedTree.children.length) {
                refs.selectedTree.innerHTML = `<div class="text-muted small">${t('sidebar_no_selected', 'No entries selected yet.')}</div>`;
            }
        }

        function setIconPickerValue(icon) {
            const value = String(icon || '').trim() || 'bi-link-45deg';
            if (refs.iconValue) {
                refs.iconValue.value = value;
            }
            if (refs.iconInput) {
                refs.iconInput.value = value;
            }
            if (refs.iconPreview) {
                refs.iconPreview.className = `bi ${value}`;
            }
        }

        function selectedLocation() {
            if (!state.selected || state.selected.pane !== 'selected') {
                return null;
            }
            return findEntryLocation(state.config.entries, state.selected.id, state.selected.kind);
        }

        // The icon picker is server-rendered once (it is a shared Dlux component with
        // its own markup) and parked in a hidden holder. The inspector's custom field
        // borrows the same node, and hands it back on the next render.
        function mountIconPicker(entry) {
            if (!refs.iconPicker) return null;
            setIconPickerValue(entry.icon);
            return {
                node: refs.iconPicker,
                cleanup: () => {
                    if (refs.iconPickerHolder && refs.iconPicker.parentNode !== refs.iconPickerHolder) {
                        refs.iconPickerHolder.appendChild(refs.iconPicker);
                    }
                },
            };
        }

        function updateEntryLabel(code, value) {
            const location = selectedLocation();
            if (!location) return;
            const cleaned = String(value || '').trim();
            location.entry.labels = location.entry.labels || {};
            if (cleaned) {
                location.entry.labels[code] = cleaned;
            } else {
                delete location.entry.labels[code];
            }
            if (!Object.keys(location.entry.labels).length) {
                delete location.entry.labels;
            }
            renderSelected();
            renderAvailable();
        }

        function renderInspector() {
            if (sidebarInspectorShell) {
                sidebarInspectorShell.render(state.selected || null);
            }
        }

        function renderAll() {
            renderSelected();
            renderAvailable();
            renderInspector();
        }

        function commitAndRender() {
            serialize();
            renderAll();
        }

        function addSelectedAvailableItem() {
            if (!state.selected || state.selected.pane !== 'available') return;
            if (state.selected.kind === 'group') {
                const sourceGroup = groupedAvailableItems(state).find(group => group.id === state.selected.id);
                if (!sourceGroup || !sourceGroup.items.length) return;
                const nextGroup = cloneGroupEntry(sourceGroup);
                nextGroup.items = nextGroup.items.map((item) => ({
                    ...item,
                    label: resolveBuilderItemLabel(item, findCatalogEntry(item, catalogLookup), findCatalogEntry(item, fallbackCatalogLookup)),
                }));
                nextGroup.label = resolveBuilderGroupLabel(nextGroup, nextGroup.items, fallbackCatalogLookup);
                state.config.entries.push(nextGroup);
                state.selected = { pane: 'selected', id: nextGroup.id, kind: 'group' };
                commitAndRender();
                return;
            }

            const source = state.catalog.find(item => item.id === state.selected.id);
            if (!source) return;
            const nextItem = cloneEntry(source);
            nextItem.label = resolveBuilderItemLabel(nextItem, source, findCatalogEntry(source, fallbackCatalogLookup));
            state.config.entries.push(nextItem);

            state.selected = { pane: 'selected', id: nextItem.id, kind: 'item' };
            commitAndRender();
        }

        function addAllAvailableItems() {
            const groups = groupedAvailableItems(state)
                .map((group) => {
                    const nextGroup = cloneGroupEntry(group);
                    nextGroup.items = nextGroup.items.map((item) => ({
                        ...item,
                        label: resolveBuilderItemLabel(item, findCatalogEntry(item, catalogLookup), findCatalogEntry(item, fallbackCatalogLookup)),
                    }));
                    nextGroup.label = resolveBuilderGroupLabel(nextGroup, nextGroup.items, fallbackCatalogLookup);
                    return nextGroup;
                })
                .filter(group => group.items.length);
            if (!groups.length) return;
            state.config.entries = state.config.entries.concat(groups);
            state.selected = null;
            state.selectedTargetGroup = null;
            commitAndRender();
        }

        function removeSelectedEntry() {
            if (!state.selected || state.selected.pane !== 'selected') return;
            const location = findEntryLocation(state.config.entries, state.selected.id, state.selected.kind);
            if (!location) return;
            location.parent.splice(location.index, 1);
            state.selected = null;
            commitAndRender();
        }

        function removeAllSelectedEntries() {
            state.config.entries = [];
            state.selected = null;
            state.selectedTargetGroup = null;
            commitAndRender();
        }

        function moveSelectedToRoot() {
            if (!state.selected || state.selected.pane !== 'selected' || state.selected.kind !== 'item') return;
            const location = findEntryLocation(state.config.entries, state.selected.id, 'item');
            if (!location || location.container !== 'group') return;
            const [entry] = location.parent.splice(location.index, 1);
            state.config.entries.push(entry);
            commitAndRender();
        }

        function addGroup() {
            const group = {
                kind: 'group',
                id: makeGroupId('group'),
                label: t('sidebar_new_group', 'New Group'),
                icon: 'bi-folder2-open',
                items: [],
            };
            state.config.entries.push(group);
            state.selected = { pane: 'selected', id: group.id, kind: 'group' };
            commitAndRender();
        }

        function duplicateSelectedEntry() {
            if (!state.selected || state.selected.pane !== 'selected') return;
            const location = findEntryLocation(state.config.entries, state.selected.id, state.selected.kind);
            if (!location) return;
            const copySuffix = t('sidebar_copy_suffix', 'Copy');
            let duplicate;
            if (location.entry.kind === 'group') {
                const groupLabel = location.entry.label || entryLabelForDisplay(location.entry) || t('sidebar_new_group', 'New Group');
                duplicate = {
                    kind: 'group',
                    id: makeGroupId(groupLabel),
                    label: `${groupLabel} ${copySuffix}`,
                    icon: location.entry.icon,
                    items: [],
                };
            } else {
                const duplicateLabel = `${entryLabelForDisplay(location.entry)} ${copySuffix}`;
                duplicate = {
                    ...cloneEntry(location.entry),
                    id: makeGroupId(location.entry.label || location.entry.url_name || location.entry.id || 'item'),
                    label: duplicateLabel,
                    labels: {
                        ...((location.entry.labels && typeof location.entry.labels === 'object') ? location.entry.labels : {}),
                        [currentLang]: duplicateLabel,
                    },
                };
            }
            location.parent.splice(location.index + 1, 0, duplicate);
            state.selected = { pane: 'selected', id: duplicate.id, kind: duplicate.kind };
            commitAndRender();
        }

        function moveDraggedEntry(target) {
            const dragging = state.dragging;
            if (!dragging) return;

            if (dragging.pane === 'available') {
                addDraggedAvailableEntry(target);
                return;
            }

            const source = findEntryLocation(state.config.entries, dragging.id, dragging.kind);
            if (!source) return;
            if (dragging.kind === 'group' && target.type !== 'root-container' && target.type !== 'root-node') {
                return;
            }

            const [entry] = source.parent.splice(source.index, 1);
            insertEntryIntoConfig(state.config.entries, entry, target);

            state.selected = { pane: 'selected', id: entry.id, kind: entry.kind };
            state.dragging = null;
            commitAndRender();
        }

        function addDraggedAvailableEntry(target) {
            const dragging = state.dragging;
            if (!dragging || dragging.pane !== 'available') return;

            if (dragging.kind === 'group') {
                if (target.type !== 'root-container' && target.type !== 'root-node') {
                    return;
                }
                const sourceGroup = groupedAvailableItems(state).find(group => group.id === dragging.id);
                if (!sourceGroup || !sourceGroup.items.length) return;
                const nextGroup = cloneGroupEntry(sourceGroup);
                nextGroup.items = nextGroup.items.map((item) => ({
                    ...item,
                    label: resolveBuilderItemLabel(item, findCatalogEntry(item, catalogLookup), findCatalogEntry(item, fallbackCatalogLookup)),
                }));
                nextGroup.label = resolveBuilderGroupLabel(nextGroup, nextGroup.items, fallbackCatalogLookup);
                insertEntryIntoConfig(state.config.entries, nextGroup, target);
                state.selected = { pane: 'selected', id: nextGroup.id, kind: 'group' };
            } else {
                const source = state.catalog.find(item => item.id === dragging.id);
                if (!source) return;
                const nextItem = cloneEntry(source);
                nextItem.label = resolveBuilderItemLabel(nextItem, source, findCatalogEntry(source, fallbackCatalogLookup));
                insertEntryIntoConfig(state.config.entries, nextItem, target);
                state.selected = { pane: 'selected', id: nextItem.id, kind: 'item' };
            }

            state.dragging = null;
            commitAndRender();
        }

        function removeDraggedSelectedEntry() {
            const dragging = state.dragging;
            if (!dragging || dragging.pane !== 'selected') return;
            const location = findEntryLocation(state.config.entries, dragging.id, dragging.kind);
            if (!location) return;
            location.parent.splice(location.index, 1);
            state.selected = null;
            state.selectedTargetGroup = null;
            state.dragging = null;
            commitAndRender();
        }

        refs.search.addEventListener('input', () => {
            state.search = refs.search.value || '';
            renderAvailable();
        });

        if (refs.systemToggle) {
            refs.systemToggle.addEventListener('change', () => {
                state.showSystemItems = Boolean(refs.systemToggle.checked);
                if (!state.showSystemItems && state.selected && state.selected.pane === 'available') {
                    const selectedAvailableItem = state.catalog.find(item => item.id === state.selected.id);
                    if (
                        (state.selected.kind === 'group' && state.selected.id === 'dlux') ||
                        (selectedAvailableItem && selectedAvailableItem.is_system)
                    ) {
                        state.selected = null;
                    }
                }
                renderAvailable();
                renderInspector();
            });
        }

        if (refs.formToggle) {
            refs.formToggle.addEventListener('change', () => {
                state.showFormPages = Boolean(refs.formToggle.checked);
                if (!state.showFormPages && state.selected && state.selected.pane === 'available') {
                    const selectedAvailableItem = state.catalog.find(item => item.id === state.selected.id);
                    if (selectedAvailableItem && selectedAvailableItem.is_form_page) {
                        state.selected = null;
                    }
                }
                renderAvailable();
                renderInspector();
            });
        }

        // Per-language name overrides (mirrors the navbar builder): one field per
        // configured language, stored on entry.labels[code]. A blank language means
        // "use the auto-translated name" (resolved server-side per viewer language).
        const sidebarInspectorShell = window.DluxInspectorShell && refs.inspectorShell
            ? window.DluxInspectorShell.create(refs.inspectorShell, {
                adapter: {
                    getActions: ({ selection }) => {
                        const location = selectedLocation();
                        const selectedAvailable = Boolean(selection && selection.pane === 'available');
                        const selectedStored = Boolean(location);
                        const inGroup = selectedStored
                            && location.entry.kind === 'item'
                            && location.container === 'group';
                        const actions = [
                            {
                                id: 'add-group',
                                label: t('sidebar_add_group', 'Add Group'),
                                icon: 'bi bi-folder-plus',
                                variant: 'outline-primary',
                                onClick: addGroup,
                            },
                            {
                                id: 'add-selected',
                                label: t('sidebar_add_entry', 'Add'),
                                icon: 'bi bi-arrow-left-square',
                                variant: 'primary',
                                disabled: !selectedAvailable,
                                onClick: addSelectedAvailableItem,
                            },
                            {
                                id: 'remove-selected',
                                label: t('sidebar_remove_entry', 'Remove'),
                                icon: 'bi bi-trash3',
                                variant: 'outline-danger',
                                disabled: !selectedStored,
                                onClick: removeSelectedEntry,
                            },
                            {
                                id: 'add-all',
                                label: t('sidebar_add_all', 'Add All'),
                                icon: 'bi bi-plus-square',
                                variant: 'outline-primary',
                                onClick: addAllAvailableItems,
                            },
                            {
                                id: 'remove-all',
                                label: t('sidebar_remove_all', 'Remove All'),
                                icon: 'bi bi-x-square',
                                variant: 'outline-danger',
                                disabled: !state.config.entries.length,
                                onClick: removeAllSelectedEntries,
                            },
                        ];
                        if (!selection) {
                            return actions;
                        }
                        actions.push(
                            {
                                id: 'move-root',
                                label: t('sidebar_move_root', 'Move To Root'),
                                icon: 'bi bi-distribute-horizontal',
                                disabled: !inGroup,
                                onClick: moveSelectedToRoot,
                            },
                            {
                                id: 'duplicate-entry',
                                label: t('sidebar_duplicate', 'Duplicate'),
                                icon: 'bi bi-copy',
                                disabled: !selectedStored,
                                onClick: duplicateSelectedEntry,
                            }
                        );
                        return actions;
                    },
                    // Only a stored entry has labels and an icon to edit; an Available
                    // pane selection is a source to add, so it gets actions and no panel.
                    getTitle: () => {
                        const location = selectedLocation();
                        return location ? entryLabelForDisplay(location.entry) : '';
                    },
                    getBadge: () => {
                        const location = selectedLocation();
                        if (!location) return '';
                        return location.entry.kind === 'group'
                            ? t('sidebar_group_badge', 'Group')
                            : t('sidebar_item_badge', 'Entry');
                    },
                    getFields: () => {
                        const location = selectedLocation();
                        if (!location) return [];
                        const entry = location.entry;
                        const labelFields = languageRows().map(([code, payload]) => {
                            const langCode = String(code || '').toLowerCase();
                            return {
                                id: `label-${langCode}`,
                                type: 'text',
                                label: `${(payload && payload.name) || langCode} (${langCode})`,
                                value: (entry.labels && entry.labels[langCode]) || '',
                                help: '',
                                commitOn: 'input',
                                onInput: ({ value }) => {
                                    updateEntryLabel(langCode, value);
                                },
                            };
                        });
                        return labelFields.concat([
                            {
                                id: 'icon',
                                type: 'custom',
                                render: () => mountIconPicker(entry),
                            },
                        ]);
                    },
                    getAnchor: () => builder.querySelector(
                        '.dlux-builder-node.is-active, .dlux-builder-item.is-active'
                    ),
                    clearSelection: () => {
                        state.selected = null;
                        state.selectedTargetGroup = null;
                        renderSelected();
                        renderAvailable();
                    },
                    commit: serialize,
                },
                strings: {
                    clearSelection: t('navbar_clear_selection', 'Clear selection'),
                    empty: t('sidebar_editor_empty', 'Select a sidebar entry to edit labels and icon.'),
                },
                presentation: 'popover',
                dismissOnOutsideClick: true,
                dismissIgnoreSelector: '.dlux-builder-node, .dlux-builder-item',
            })
            : null;

        function syncSelectedIconFromPicker() {
            const location = selectedLocation();
            if (!location) return;
            location.entry.icon = String(refs.iconValue && refs.iconValue.value || '').trim() || 'bi-link-45deg';
            serialize();
            // Deliberately not re-rendering the inspector: it owns the picker node,
            // and re-mounting it mid-choice would close the picker's own popover.
            renderSelected();
            renderAvailable();
        }

        if (refs.iconValue) {
            refs.iconValue.addEventListener('input', syncSelectedIconFromPicker);
            refs.iconValue.addEventListener('change', syncSelectedIconFromPicker);
        }

        refs.selectedTree.addEventListener('dragover', (event) => {
            if (!state.dragging) return;
            event.preventDefault();
            refs.selectedTree.classList.add('dlux-builder-drop-target');
        });
        refs.selectedTree.addEventListener('dragleave', () => {
            refs.selectedTree.classList.remove('dlux-builder-drop-target');
        });
        refs.selectedTree.addEventListener('drop', (event) => {
            if (!state.dragging) return;
            event.preventDefault();
            event.stopPropagation();
            moveDraggedEntry({ type: 'root-container' });
        });

        refs.availableList.addEventListener('dragover', (event) => {
            if (!state.dragging || state.dragging.pane !== 'selected') return;
            event.preventDefault();
            refs.availableList.classList.add('dlux-builder-drop-target');
        });
        refs.availableList.addEventListener('dragleave', () => {
            refs.availableList.classList.remove('dlux-builder-drop-target');
        });
        refs.availableList.addEventListener('drop', (event) => {
            if (!state.dragging || state.dragging.pane !== 'selected') return;
            event.preventDefault();
            event.stopPropagation();
            removeDraggedSelectedEntry();
        });

        function loadExternalConfig(rawConfig) {
            state.config = normalizeSidebarConfig(
                rawConfig && typeof rawConfig === 'object' ? rawConfig : parseJson(hiddenInput.value || '{}', {}),
                catalogLookup,
                fallbackCatalogLookup
            );
            state.selected = null;
            state.selectedTargetGroup = null;
            state.dragging = null;
            renderAll();
        }

        hiddenInput.addEventListener('change', () => {
            loadExternalConfig(parseJson(hiddenInput.value || '{}', {}));
        });

        builder.addEventListener('dlux:sidebar-config-imported', (event) => {
            loadExternalConfig(event.detail && event.detail.config);
        });

        renderAll();
    }



    function syncLanguageCatalog(form) {
        if (!form) return;
        const languagesField = form.querySelector('[name="languages"]');
        const namesField = form.querySelector('[name="system_names"]');
        const defaultField = form.querySelector('[name="default_language"]');
        const languages = {};
        let fallbackLanguage = 'en';
        form.querySelectorAll('[data-language-row]').forEach((row, index) => {
            const code = normalizeLanguageCode(row.dataset.languageCode);
            if (!code) return;
            if (index === 0) fallbackLanguage = code;
            const nameInput = row.querySelector('[data-language-name]');
            const dirInput = row.querySelector('[data-language-dir]');
            const flagInput = row.querySelector('[data-language-flag]');
            const defaultInput = row.querySelector('[data-language-default]');
            languages[code] = {
                name: String(nameInput && nameInput.value ? nameInput.value : code).trim() || code,
                dir: dirInput && dirInput.value === 'rtl' ? 'rtl' : 'ltr',
                flag: String(flagInput && flagInput.value ? flagInput.value : '').trim()
            };
            if (defaultInput && defaultInput.checked) {
                fallbackLanguage = code;
            }
        });
        syncSystemNameRows(form, languages);
        const systemNames = readSystemNames(form);
        if (languagesField) languagesField.value = JSON.stringify(languages);
        if (namesField) namesField.value = JSON.stringify(systemNames);
        if (defaultField) {
            defaultField.value = fallbackLanguage;
        }
        syncTranslationOverrides(form);
        applyImmediateSystemSettingsPreview(form);
    }




    function ensureSystemNameRow(form, code, label, value) {
        const list = form && form.querySelector('[data-system-name-list]');
        if (!list || !code) return null;
        let row = findSystemNameRow(form, code);
        if (!row) {
            row = createSystemNameRow(code, label, value);
            list.appendChild(row);
            bindSystemNameRow(form, row);
        }
        const labelTarget = row.querySelector('.dlux-system-name-row__label');
        if (labelTarget) {
            labelTarget.textContent = label || code;
        }
        return row;
    }

    function bindSystemNameRow(form, row) {
        if (!form || !row || row.dataset.bound === 'true') return;
        row.dataset.bound = 'true';
        row.querySelectorAll('[data-system-name-input]').forEach((input) => {
            input.addEventListener('input', () => syncSystemNamesField(form));
            input.addEventListener('change', () => syncSystemNamesField(form));
        });
    }

    function syncSystemNameRows(form, languages) {
        if (!form || !languages) return;
        Object.entries(languages).forEach(([code, payload]) => {
            ensureSystemNameRow(form, code, payload && payload.name ? payload.name : code, '');
        });
        form.querySelectorAll('[data-system-name-row]').forEach((row) => {
            const code = normalizeLanguageCode(row.dataset.languageCode);
            if (code && !languages[code]) {
                row.remove();
            }
        });
    }


    function syncSystemNamesField(form) {
        if (!form) return;
        const namesField = form.querySelector('[name="system_names"]');
        if (namesField) namesField.value = JSON.stringify(readSystemNames(form));
        applyImmediateSystemSettingsPreview(form);
    }

    function initSystemNamesEditor(root) {
        root.querySelectorAll('[data-system-names-editor]').forEach((editor) => {
            if (editor.dataset.bound === 'true') return;
            editor.dataset.bound = 'true';
            const form = editor.closest('form');
            if (!form) return;
            editor.querySelectorAll('[data-system-name-row]').forEach((row) => bindSystemNameRow(form, row));
            form.addEventListener('submit', () => syncSystemNamesField(form));
            syncSystemNamesField(form);
        });
    }




    function bindLanguageCatalogRow(form, row) {
        if (!form || !row || row.dataset.languageBound === 'true') return;
        row.dataset.languageBound = 'true';
        row.querySelectorAll('input, select').forEach((input) => {
            input.addEventListener('input', () => syncLanguageCatalog(form));
            input.addEventListener('change', () => {
                syncLanguageCatalog(form);
                if (input.matches('[data-language-default]') && input.checked) {
                    form.querySelectorAll('[data-language-default]').forEach((defaultInput) => {
                        if (defaultInput !== input) {
                            defaultInput.checked = false;
                        }
                    });
                    syncLanguageCatalog(form);
                }
            });
        });
        const removeButton = row.querySelector('[data-language-remove]');
        if (removeButton) {
            removeButton.addEventListener('click', () => {
                if (removeButton.disabled) return;
                const code = normalizeLanguageCode(row.dataset.languageCode);
                row.remove();
                removeTranslationLanguageColumn(form, code);
                const systemNameRow = findSystemNameRow(form, code);
                if (systemNameRow) systemNameRow.remove();
                const defaultField = form.querySelector('[name="default_language"]');
                if (defaultField && !form.querySelector(`[data-language-row][data-language-code="${defaultField.value}"]`)) {
                    const firstDefault = form.querySelector('[data-language-default]');
                    if (firstDefault) firstDefault.checked = true;
                }
                syncLanguageCatalog(form);
            });
        }
    }

    function addLanguageToCatalog(form, editor, code, name, dir, flag) {
        const list = editor && editor.querySelector('[data-language-list]');
        const normalizedCode = normalizeLanguageCode(code);
        if (!form || !list || !normalizedCode || list.querySelector(`[data-language-code="${normalizedCode}"]`)) {
            return null;
        }
        const label = name || normalizedCode;
        const row = createLanguageRow(normalizedCode, label, dir || 'ltr', flag || '');
        list.appendChild(row);
        bindLanguageCatalogRow(form, row);
        ensureSystemNameRow(form, normalizedCode, label, '');
        ensureTranslationLanguageColumn(form, normalizedCode, label);
        const defaultInput = row.querySelector('[data-language-default]');
        if (defaultInput && !form.querySelector('[data-language-default]:checked')) {
            defaultInput.checked = true;
        }
        syncLanguageCatalog(form);
        return row;
    }

    function rebuildLanguageCatalog(form, languages, systemNames, defaultLanguage) {
        const editor = form && form.querySelector('[data-language-catalog-editor]');
        const list = editor && editor.querySelector('[data-language-list]');
        if (!form || !editor || !list || !languages || typeof languages !== 'object') return;
        list.innerHTML = '';
        Object.entries(languages).forEach(([rawCode, payload]) => {
            const code = normalizeLanguageCode(rawCode);
            if (!code) return;
            const meta = payload && typeof payload === 'object' ? payload : { name: String(payload || code) };
            addLanguageToCatalog(form, editor, code, meta.name || code, meta.dir || 'ltr', meta.flag || '');
        });
        const defaultCode = normalizeLanguageCode(defaultLanguage);
        const defaultInput = defaultCode ? form.querySelector(`[data-language-row][data-language-code="${defaultCode}"] [data-language-default]`) : null;
        if (defaultInput) {
            defaultInput.checked = true;
            // These radios have no shared name, so the single-select behaviour comes from the
            // row's change handler. Fire it so any previously auto-selected default is cleared
            // (otherwise both the first-added language and the imported default appear selected).
            defaultInput.dispatchEvent(new Event('change', { bubbles: true }));
        }
        Object.entries(systemNames || {}).forEach(([rawCode, value]) => {
            const code = normalizeLanguageCode(rawCode);
            const row = ensureSystemNameRow(form, code, languages[code] && languages[code].name ? languages[code].name : code, value);
            const input = row && row.querySelector('[data-system-name-input]');
            if (input) {
                input.value = value || '';
            }
        });
        syncLanguageCatalog(form);
    }


    function initLanguageCatalogEditor(root) {
        root.querySelectorAll('[data-language-catalog-editor]').forEach((editor) => {
            if (editor.dataset.bound === 'true') return;
            editor.dataset.bound = 'true';
            const form = editor.closest('form');
            const list = editor.querySelector('[data-language-list]');
            const codeInput = editor.querySelector('[data-language-code-input]');
            const nameInput = editor.querySelector('[data-language-name-input]');
            const dirInput = editor.querySelector('[data-language-dir-input]');
            const flagInput = editor.querySelector('[data-language-flag-input]');
            const addButton = editor.querySelector('[data-language-add]');
            if (!form || !list) return;

            list.querySelectorAll('[data-language-row]').forEach((row) => bindLanguageCatalogRow(form, row));
            form.querySelectorAll('[data-system-name-row]').forEach((row) => bindSystemNameRow(form, row));
            if (addButton) {
                addButton.addEventListener('click', () => {
                    addLanguageToCatalog(form, editor, codeInput && codeInput.value, nameInput && nameInput.value, dirInput && dirInput.value, flagInput && flagInput.value);
                    if (codeInput) codeInput.value = '';
                    if (nameInput) nameInput.value = '';
                    if (flagInput) flagInput.value = '';
                });
            }
            editor.querySelectorAll('[data-language-suggestion]').forEach((button) => {
                button.addEventListener('click', () => {
                    const code = button.getAttribute('data-language-suggestion');
                    addLanguageToCatalog(form, editor, code, code, 'ltr', '');
                });
            });
            syncLanguageCatalog(form);
        });
    }

    function initTranslationMatrixEditor(root) {
        root.querySelectorAll('[data-translation-matrix]').forEach((matrix) => {
            if (matrix.dataset.bound === 'true') return;
            matrix.dataset.bound = 'true';
            const form = matrix.closest('form');
            const searchInput = matrix.querySelector('[data-translation-search]');
            const statusInput = matrix.querySelector('[data-translation-status]');
            const groupTabs = Array.from(matrix.querySelectorAll('[data-translation-group-tab]'));
            let activeGroup = 'all';

            function applyFilter() {
                const needle = String(searchInput && searchInput.value ? searchInput.value : '').trim().toLowerCase();
                const status = statusInput && statusInput.value ? statusInput.value : 'all';
                matrix.querySelectorAll('[data-translation-row]').forEach((row) => {
                    const text = row.textContent.toLowerCase();
                    const hasStatus = status === 'all' || Boolean(row.querySelector(`[data-source="${status}"]`));
                    const hasGroup = activeGroup === 'all' || row.getAttribute('data-translation-group') === activeGroup;
                    row.classList.toggle('d-none', Boolean(needle && !text.includes(needle)) || !hasStatus || !hasGroup);
                });
            }

            matrix.querySelectorAll('[data-translation-input]').forEach((input) => {
                input.addEventListener('input', () => {
                    syncTranslationOverrides(form);
                    const cell = input.closest('[data-translation-cell]');
                    if (cell) {
                        const value = String(input.value || '').trim();
                        const baseValue = String(input.dataset.baseValue || '').trim();
                        cell.dataset.source = value && value !== baseValue ? 'override' : (value ? cell.dataset.source : 'missing');
                    }
                    applyFilter();
                });
            });
            if (searchInput) searchInput.addEventListener('input', applyFilter);
            if (statusInput) statusInput.addEventListener('change', applyFilter);
            groupTabs.forEach((tab) => {
                tab.addEventListener('click', () => {
                    activeGroup = tab.getAttribute('data-translation-group-tab') || 'all';
                    groupTabs.forEach((candidate) => {
                        candidate.classList.toggle('active', candidate === tab);
                    });
                    applyFilter();
                });
            });
            if (form) {
                form.addEventListener('submit', () => {
                    syncLanguageCatalog(form);
                    syncTranslationOverrides(form);
                });
            }
            syncTranslationOverrides(form);
            applyFilter();
        });
    }

















    function applyImportedFontSettings(form, settings) {
        if (!form || !settings || typeof settings !== 'object') return;

        if (Array.isArray(settings.allowed_fonts)) {
            form.querySelectorAll('[data-setup-font-allowed]').forEach((field) => {
                const slug = field.getAttribute('data-setup-font-allowed') || field.value;
                field.checked = settings.allowed_fonts.includes(slug);
                field.dispatchEvent(new Event('change', { bubbles: true }));
            });
        }

        const defaultFonts = settings.default_fonts && typeof settings.default_fonts === 'object' ? settings.default_fonts : null;
        if (defaultFonts) {
            setJsonField(form, 'default_fonts', defaultFonts);
            form.querySelectorAll('.dlux-lang-font-select').forEach((select) => {
                const lang = normalizeLanguageCode(select.getAttribute('data-lang'));
                if (lang && Object.prototype.hasOwnProperty.call(defaultFonts, lang)) {
                    select.value = defaultFonts[lang] || select.value;
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });
        }
    }

    function applyImportedSidebarSettings(form, sidebar) {
        if (!form || !sidebar || typeof sidebar !== 'object') return;
        const raw = JSON.stringify(sidebar || {});
        const hiddenInput = form.querySelector('input[name="sidebar_config"]');
        if (hiddenInput) {
            hiddenInput.value = raw;
        }
        form.querySelectorAll('.dlux-sidebar-config-data').forEach((node) => {
            node.value = raw;
        });
        form.querySelectorAll('.dlux-setup-builder').forEach((builder) => {
            builder.dispatchEvent(new CustomEvent('dlux:sidebar-config-imported', {
                detail: { config: sidebar }
            }));
        });
        if (hiddenInput) {
            hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    function applyImportedSetupSettings(form, payload) {
        const settings = extractImportedSettings(payload);
        if (!form || !settings) return false;

        const languages = settings.languages && typeof settings.languages === 'object' ? settings.languages : null;
        const systemNames = settings.system_names && typeof settings.system_names === 'object' ? settings.system_names : {};
        if (languages) {
            rebuildLanguageCatalog(form, languages, systemNames, settings.default_language || getNamedFieldValue(form, 'default_language') || 'en');
        } else if (Object.keys(systemNames).length) {
            Object.entries(systemNames).forEach(([rawCode, value]) => {
                const code = normalizeLanguageCode(rawCode);
                const row = ensureSystemNameRow(form, code, code, value);
                const input = row && row.querySelector('[data-system-name-input]');
                if (input) input.value = value || '';
            });
        }

            if (settings.system_names) setJsonField(form, 'system_names', settings.system_names);
            if (settings.languages) setJsonField(form, 'languages', settings.languages);
            const translationOverrides = settings.translations_override || settings.translations;
            if (translationOverrides && typeof translationOverrides === 'object') {
                setJsonField(form, 'translations_override', translationOverrides);
                applyTranslationOverridesToMatrix(form, translationOverrides);
            }

        ['home_url', 'public_root_url', 'default_language', 'default_theme', 'default_table_density', 'default_form_density', 'default_modal_size', 'public_root_theme', 'public_root_title', 'public_root_meta_description'].forEach((name) => {
            if (Object.prototype.hasOwnProperty.call(settings, name)) {
                setNamedFieldValue(form, name, settings[name]);
                getNamedFieldInputs(form, name).forEach((field) => field.dispatchEvent(new Event('change', { bubbles: true })));
            }
        });

        ['allow_user_theme_override', 'allow_user_font_override', 'allow_user_language_override', 'email_2fa', 'prevent_multiple_active_sessions', 'public_root', 'public_root_split_enabled', 'show_titlebar_on_public', 'show_sidebar_on_public', 'public_registration_enabled', 'registration_throttle_enabled', 'honeypot_enabled', 'table_accent_edges', 'sticky_table_headers', 'resizable_table_columns', 'zebra_striping', 'footer_enabled'].forEach((name) => {
            if (Object.prototype.hasOwnProperty.call(settings, name)) {
                setCheckboxField(form, name, settings[name]);
            }
        });

        if (Object.prototype.hasOwnProperty.call(settings, 'registration_activation_mode')) {
            setNamedFieldValue(form, 'registration_activation_mode', settings.registration_activation_mode);
            getNamedFieldInputs(form, 'registration_activation_mode').forEach((field) => field.dispatchEvent(new Event('change', { bubbles: true })));
        }

        const emailConfig = settings.email_config && typeof settings.email_config === 'object' ? settings.email_config : null;
        if (emailConfig) {
            setJsonField(form, 'email_config', emailConfig);
            setNamedFieldValue(form, 'email_config_transport', emailConfig.transport || 'direct');
            setNamedFieldValue(form, 'email_config_secret_storage', emailConfig.secret_storage || 'env');
            getNamedFieldInputs(form, 'email_config_secret_storage').forEach((field) => field.dispatchEvent(new Event('change', { bubbles: true })));
            setNamedFieldValue(form, 'email_config_host', emailConfig.host || '');
            setNamedFieldValue(form, 'email_config_port', emailConfig.port || '587');
            setCheckboxField(form, 'email_config_use_tls', emailConfig.use_tls !== false);
            setCheckboxField(form, 'email_config_use_ssl', emailConfig.use_ssl === true);
            setNamedFieldValue(form, 'email_config_username', emailConfig.username || '');
            setNamedFieldValue(form, 'email_config_default_from_email', emailConfig.default_from_email || '');
            // Only require re-entering the redacted SMTP password when the server actually
            // would (email feature on + encrypted-DB + username) — otherwise a valid config
            // must still offer "Finish setup".
            setImportedEmailPasswordNotice(
                form,
                setupRequiresEmailPassword(form) && !emailConfig.encrypted_password
            );
        } else {
            setImportedEmailPasswordNotice(form, false);
        }

        if (Array.isArray(settings.allowed_themes)) {
            form.querySelectorAll('[data-setup-theme-allowed]').forEach((field) => {
                field.checked = settings.allowed_themes.includes(field.value);
                field.dispatchEvent(new Event('change', { bubbles: true }));
            });
        }

        applyImportedFontSettings(form, settings);

        const sidebarSource = settings.sidebar_config || settings.sidebar;
        const sidebar = sidebarSource && typeof sidebarSource === 'object' ? sidebarSource : null;
        if (sidebar) {
            applyImportedSidebarSettings(form, sidebar);
            setCheckboxField(form, 'sidebar_enabled', sidebar.enabled !== false);
            setCheckboxField(form, 'sidebar_accent_edge', sidebar.accent_edge === true);
            setCheckboxField(form, 'sidebar_enable_reorder', sidebar.enable_reorder !== false);
            setCheckboxField(form, 'sidebar_enable_toolbar', sidebar.show_toolbar !== false);
            setCheckboxField(form, 'sidebar_show_sections_manager', sidebar.show_sections_manager !== false);
            setCheckboxField(form, 'sidebar_show_icons', sidebar.show_icons !== false);
            setCheckboxField(form, 'sidebar_show_notification_badges', sidebar.show_notification_badges !== false);
            setCheckboxField(form, 'sidebar_allow_user_density', sidebar.allow_user_density !== false);
            setNamedFieldValue(form, 'sidebar_density', sidebar.density || 'balanced');
            setNamedFieldValue(form, 'sidebar_collapse_mode', sidebar.collapse_mode || 'icons');
            setNamedFieldValue(form, 'sidebar_toggle_icon', sidebar.toggle_icon || 'bi-list');
        }

        const navbarSource = settings.navbar_config || settings.navbar;
        const navbar = navbarSource && typeof navbarSource === 'object' ? navbarSource : null;
        if (navbar) {
            setJsonField(form, 'navbar_config', navbar);
            setCheckboxField(form, 'navbar_enabled', navbar.enabled === true);
            setCheckboxField(form, 'navbar_allow_user_mode_override', navbar.allow_user_mode_override !== false);
            setNamedFieldValue(form, 'navbar_default_mode', navbar.default_mode === 'history' ? 'history' : 'hierarchy');
            getNamedFieldInputs(form, 'navbar_default_mode').forEach((field) => {
                field.dispatchEvent(new Event('change', { bubbles: true }));
            });
        }

        const titlebarSource = settings.titlebar_config || settings.titlebar;
        const titlebar = titlebarSource && typeof titlebarSource === 'object' ? titlebarSource : null;
        if (titlebar) {
            setCheckboxField(form, 'titlebar_accent_edge', titlebar.accent_edge === true);
            setCheckboxField(form, 'titlebar_show_title', titlebar.show_title !== false);
            setCheckboxField(form, 'titlebar_show_logo', titlebar.show_logo !== false);
            setCheckboxField(form, 'titlebar_show_home_button', titlebar.show_home_button !== false);
            setNamedFieldValue(form, 'titlebar_home_shape', titlebar.buttons_shape || titlebar.home_shape || 'circle');
            setNamedFieldValue(form, 'titlebar_user_hub_style', titlebar.user_hub_style === 'titlebar_actions' ? 'titlebar_actions' : 'dropdown');
            writeTitlebarActionsOrder(form, titlebar.actions_order || TITLEBAR_ACTIONS_DEFAULT_ORDER);
            setNamedFieldValue(form, 'titlebar_title_align', titlebar.title_align || 'start');
            setNamedFieldValue(form, 'titlebar_title_size', titlebar.title_size || 'md');
            setNamedFieldValue(form, 'titlebar_height', titlebar.height || 'balanced');
            setNamedFieldValue(form, 'titlebar_surface', titlebar.surface || 'default');
            setNamedFieldValue(form, 'titlebar_logo_treatment', titlebar.logo_treatment || 'none');
            setNamedFieldValue(form, 'titlebar_logo_treatment_shape', titlebar.logo_treatment_shape || 'soft');
        }

        const loginSource = settings.login_config || settings.login;
        const login = loginSource && typeof loginSource === 'object' ? loginSource : null;
        if (login) {
            setJsonField(form, 'login_config', login);
            setNamedFieldValue(form, 'login_style', login.style || 'split');
            setCheckboxField(form, 'login_show_logo', login.show_logo !== false);
            setNamedFieldValue(form, 'login_banner_color', login.banner_color || '');
            setNamedFieldValue(form, 'login_logo_treatment', login.logo_treatment || 'none');
            setNamedFieldValue(form, 'login_logo_treatment_shape', login.logo_treatment_shape || 'soft');
            const hero = login.hero_message && typeof login.hero_message === 'object' ? login.hero_message : {};
            Object.entries(hero).forEach(([rawCode, message]) => {
                const code = normalizeLanguageCode(rawCode);
                if (code) {
                    setNamedFieldValue(form, `login_hero_message_${code}`, message || '');
                }
            });
        }

        syncLanguageCatalog(form);
        syncTranslationOverrides(form);
        applyImmediateSystemSettingsPreview(form);
        persistSetupFormState(form);
        return true;
    }

    function initSystemSetupImportFile(root) {
        root.querySelectorAll('form.dlux-system-setup-form [data-settings-import-file]').forEach((input) => {
            if (input.dataset.importBound === 'true') return;
            input.dataset.importBound = 'true';
            input.addEventListener('change', () => {
                const form = input.closest('form');
                const file = input.files && input.files[0];
                if (!form || !file) {
                    if (form) setImportedSetupFinishVisible(form, false);
                    return;
                }
                setImportedSetupFinishVisible(form, false);
                const reader = new FileReader();
                reader.onload = () => {
                    try {
                        const payload = JSON.parse(reader.result || '{}');
                        if (!applyImportedSetupSettings(form, payload)) {
                            throw new Error('Invalid setup file');
                        }
                        // Mark import as processed so server doesn't re-apply and override user edits
                        const processedFlag = form.querySelector('input[name="settings_import_processed"]');
                        if (processedFlag) {
                            processedFlag.value = 'true';
                        }
                        const needsEmailPassword = form.dataset.importNeedsEmailPassword === 'true';
                        // Don't offer "finish" yet if the redacted SMTP password must be re-entered.
                        setImportedSetupFinishVisible(form, !needsEmailPassword);
                        persistSetupFormState(form);
                        if (typeof showToast === 'function') {
                            showToast(needsEmailPassword
                                ? t('system_setup_import_needs_email_password', 'The SMTP password is never included in an exported setup file for security. Re-enter it below to finish setup.')
                                : t('system_setup_import_loaded', 'System setup file imported.'));
                        }
                    } catch (error) {
                        setImportedSetupFinishVisible(form, false);
                        if (typeof showToast === 'function') {
                            showToast(t('system_setup_import_invalid', 'Invalid system setup file.'));
                        }
                    }
                };
                reader.readAsText(file);
            });
        });
    }





    // One dependent field (rather than a whole section): same contract as
    // setDependentSectionEnabled — visible but inert, never hidden.


    // `locked_expanded` hides the titlebar toggle on desktop, so its glyph has
    // nothing to style there; the picker follows the collapse mode on top of the
    // sidebar's own enable switch.
    function syncSidebarToggleIconAvailability(form) {
        if (!form) {
            return;
        }
        const sidebarEnabledToggle = form.querySelector('#id_sidebar_enabled');
        const sidebarEnabled = !sidebarEnabledToggle || sidebarEnabledToggle.checked;
        const collapseMode = getNamedFieldValue(form, 'sidebar_collapse_mode') || 'icons';
        const lockedExpanded = collapseMode === 'locked_expanded';
        const available = sidebarEnabled && !lockedExpanded;

        setNamedFieldDisabled(form, 'sidebar_toggle_icon', !available);
        const picker = form.querySelector('[data-dlux-icon-picker][data-icon-field="sidebar_toggle_icon"]');
        if (!picker) {
            return;
        }
        const reason = lockedExpanded && sidebarEnabled
            ? t('sidebar_toggle_icon_locked_reason', 'The sidebar is always expanded, so the toggle is not shown on desktop.')
            : dependentReason(sidebarEnabledToggle);
        setDependentFieldEnabled(picker, available, reason);
    }

    // A step's master toggle dims and disables its dependent settings instead of
    // hiding them, so the admin can see what enabling it will restore. Kept in one
    // place because the field lists were previously duplicated per call site and
    // drifted (a new field disabled in one copy and live in the other).
    const DEPENDENT_FIELDS = {
        sidebar: [
            'sidebar_accent_edge',
            'sidebar_enable_reorder',
            'sidebar_enable_toolbar',
            'sidebar_show_sections_manager',
            'sidebar_show_icons',
            'sidebar_show_notification_badges',
            'sidebar_allow_user_density',
            'sidebar_density',
            'sidebar_collapse_mode',
            'sidebar_toggle_icon',
        ],
        navbar: [
            'navbar_allow_user_mode_override',
            'navbar_default_mode',
        ],
        notifications: [
            'notification_flash_enabled',
            'notification_flash_position',
            'notification_flash_size',
            'notification_flash_text_size',
            'notification_flash_timeout_ms',
            'notification_flash_max_visible',
            'notification_drawer_enabled',
            'notification_badge_enabled',
            'notification_bridge_enabled',
            'notification_email_enabled',
            'notification_email_default',
            'notification_auto_crud_enabled',
            'notification_auto_create',
            'notification_auto_update',
            'notification_auto_delete',
        ],
    };

    // Builder sections (logging, profile) keep their state in the builder's own
    // config object rather than in the posted fields, so disabling their controls
    // is purely presentational — nothing can be lost on save.

    function initSidebarBehaviorOptions(root) {
        root.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            if (form.dataset.sidebarBehaviorBound === 'true') {
                return;
            }

            const toolbarToggle = form.querySelector('#id_sidebar_enable_toolbar');
            const sidebarEnabledToggle = form.querySelector('#id_sidebar_enabled');
            const toolbarNote = form.querySelector('[data-sidebar-toolbar-note]');
            const sidebarDisabledNote = form.querySelector('[data-sidebar-disabled-note]');
            const showIconsToggle = form.querySelector('#id_sidebar_show_icons');
            const notificationBadgesToggle = form.querySelector('#id_sidebar_show_notification_badges');
            const accentEdgeToggle = form.querySelector('#id_sidebar_accent_edge');
            const allowThemeOverrideToggle = form.querySelector('#id_allow_user_theme_override');
            const reorderToggle = form.querySelector('#id_sidebar_enable_reorder');
            const allowUserDensityToggle = form.querySelector('#id_sidebar_allow_user_density');
            const sectionsManagerToggle = form.querySelector('#id_sidebar_show_sections_manager');
            const sectionsToolState = form.querySelector('[data-sidebar-tooling-state]');
            const themeAllowCheckboxes = Array.from(form.querySelectorAll('[data-setup-theme-allowed]'));
            if (!toolbarToggle || !toolbarNote) {
                return;
            }

            form.dataset.sidebarBehaviorBound = 'true';

            function getAllowedThemeCount() {
                return themeAllowCheckboxes.filter((checkbox) => checkbox.checked).length;
            }

            function hasLiveToolbarTool() {
                const themePickerEnabled = Boolean(
                    allowThemeOverrideToggle &&
                    allowThemeOverrideToggle.checked &&
                    getAllowedThemeCount() > 1
                );
                const densityPickerEnabled = Boolean(allowUserDensityToggle && allowUserDensityToggle.checked);
                const reorderEnabled = Boolean(reorderToggle && reorderToggle.checked);
                const sectionsManagerEnabled = Boolean(
                    sectionsToolState &&
                    sectionsToolState.getAttribute('data-sections-manager-available') === 'true' &&
                    (!sectionsManagerToggle || sectionsManagerToggle.checked)
                );
                return themePickerEnabled || densityPickerEnabled || reorderEnabled || sectionsManagerEnabled;
            }

            function syncToolbarAvailability() {
                const sidebarEnabled = !sidebarEnabledToggle || sidebarEnabledToggle.checked;
                if (sidebarDisabledNote) {
                    sidebarDisabledNote.classList.toggle('d-none', sidebarEnabled);
                }
                setDependentSectionEnabled(
                    form,
                    form.querySelector('[data-sidebar-dependent]'),
                    sidebarEnabled,
                    DEPENDENT_FIELDS.sidebar,
                    dependentReason(sidebarEnabledToggle),
                );
                syncSidebarToggleIconAvailability(form);
                const hasToolbarTool = hasLiveToolbarTool();
                const available = sidebarEnabled && hasToolbarTool;
                const sectionsShortcutDisabled = Boolean(
                    sidebarEnabled &&
                    sectionsManagerToggle &&
                    !sectionsManagerToggle.checked &&
                    sectionsToolState &&
                    sectionsToolState.getAttribute('data-sections-manager-available') === 'true'
                );
                toolbarToggle.disabled = !available;
                toolbarNote.classList.toggle(
                    'd-none',
                    !(sectionsShortcutDisabled || (available && !toolbarToggle.checked))
                );
                syncSidebarBehaviorConfig(form);
                applyImmediateSystemSettingsPreview(form);
            }

            function syncCollapseMode() {
                if (!showIconsToggle) {
                    syncSidebarToggleIconAvailability(form);
                    syncSidebarBehaviorConfig(form);
                    applyImmediateSystemSettingsPreview(form);
                    return;
                }
                if (!showIconsToggle.checked && getNamedFieldValue(form, 'sidebar_collapse_mode') === 'icons') {
                    setNamedFieldValue(form, 'sidebar_collapse_mode', 'hidden');
                }
                syncSidebarToggleIconAvailability(form);
                syncSidebarBehaviorConfig(form);
                applyImmediateSystemSettingsPreview(form);
            }

            toolbarToggle.addEventListener('change', syncToolbarAvailability);
            if (sidebarEnabledToggle) {
                sidebarEnabledToggle.addEventListener('change', syncToolbarAvailability);
            }
            if (showIconsToggle) {
                showIconsToggle.addEventListener('change', syncCollapseMode);
            }
            getNamedFieldInputs(form, 'sidebar_collapse_mode').forEach((field) => {
                field.addEventListener('change', syncCollapseMode);
            });
            themeAllowCheckboxes.forEach((checkbox) => {
                checkbox.addEventListener('change', syncToolbarAvailability);
            });
            [
                allowThemeOverrideToggle,
                accentEdgeToggle,
                reorderToggle,
                allowUserDensityToggle,
                sectionsManagerToggle,
                notificationBadgesToggle,
            ].forEach((field) => {
                if (field) {
                    field.addEventListener('change', syncToolbarAvailability);
                }
            });
            if (showIconsToggle) {
                showIconsToggle.addEventListener('change', syncToolbarAvailability);
            }
            getNamedFieldInputs(form, 'sidebar_density').forEach((field) => {
                field.addEventListener('change', () => syncSidebarBehaviorConfig(form));
            });
            syncCollapseMode();
            syncToolbarAvailability();
            syncSidebarBehaviorConfig(form);
        });
    }

    function initNavbarBehaviorOptions(root) {
        root.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            if (form.dataset.navbarBehaviorBound === 'true') {
                return;
            }
            const enabledToggle = form.querySelector('#id_navbar_enabled');
            const dependentSection = form.querySelector('[data-navbar-dependent]');
            const hiddenInput = form.querySelector('input[name="navbar_config"]');
            if (!enabledToggle || !dependentSection || !hiddenInput) {
                return;
            }
            form.dataset.navbarBehaviorBound = 'true';

            function syncNavbarAvailability() {
                setDependentSectionEnabled(form, dependentSection, enabledToggle.checked, DEPENDENT_FIELDS.navbar, dependentReason(enabledToggle));
                syncNavbarBehaviorConfig(form);
                seedNavbarConfigFromSidebar(form);
            }

            enabledToggle.addEventListener('change', syncNavbarAvailability);
            form.querySelector('#id_navbar_allow_user_mode_override')?.addEventListener('change', () => {
                syncNavbarBehaviorConfig(form);
            });
            getNamedFieldInputs(form, 'navbar_default_mode').forEach((field) => {
                field.addEventListener('change', () => syncNavbarBehaviorConfig(form));
            });
            syncNavbarAvailability();
        });
    }

    // The sidebar toolbar can only host the theme picker while it exists. Turning
    // the sidebar or its toolbar off makes that option unchoosable and moves the
    // selection to the titlebar, which is what the server would resolve anyway.
    function syncThemePickerLocationAvailability(form) {
        const holder = form.querySelector('[data-theme-picker-location]');
        if (!holder) {
            return;
        }
        const sidebarEnabledToggle = form.querySelector('#id_sidebar_enabled');
        const toolbarToggle = form.querySelector('#id_sidebar_enable_toolbar');
        const hostable = (!sidebarEnabledToggle || sidebarEnabledToggle.checked)
            && (!toolbarToggle || toolbarToggle.checked);
        holder.setAttribute('data-sidebar-hostable', hostable ? 'true' : 'false');

        const sidebarInput = holder.querySelector('.dlux-choice-option__input[value="sidebar_toolbar"]');
        if (!sidebarInput) {
            return;
        }
        sidebarInput.disabled = !hostable;
        const option = sidebarInput.closest('[data-dlux-selector-option]');
        if (option) {
            option.classList.toggle('is-disabled', !hostable);
        }
        if (!hostable && sidebarInput.checked) {
            const titlebarInput = holder.querySelector('.dlux-choice-option__input[value="titlebar"]');
            if (titlebarInput) {
                titlebarInput.checked = true;
                titlebarInput.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
    }

    function syncSidebarToolbarWarningFallback(form) {
        if (!form || !form.classList || !form.classList.contains('dlux-system-setup-form')) {
            return;
        }

        const toolbarToggle = form.querySelector('#id_sidebar_enable_toolbar');
        const sidebarEnabledToggle = form.querySelector('#id_sidebar_enabled');
        const toolbarNote = form.querySelector('[data-sidebar-toolbar-note]');
        const sidebarDisabledNote = form.querySelector('[data-sidebar-disabled-note]');
        if (!toolbarToggle || !toolbarNote) {
            return;
        }

        const sidebarEnabled = !sidebarEnabledToggle || sidebarEnabledToggle.checked;
        if (sidebarDisabledNote) {
            sidebarDisabledNote.classList.toggle('d-none', sidebarEnabled);
        }
        setDependentSectionEnabled(
            form,
            form.querySelector('[data-sidebar-dependent]'),
            sidebarEnabled,
            DEPENDENT_FIELDS.sidebar,
            dependentReason(sidebarEnabledToggle),
        );
        syncSidebarToggleIconAvailability(form);
        syncThemePickerLocationAvailability(form);

        const allowedThemeCount = Array.from(form.querySelectorAll('[data-setup-theme-allowed]'))
            .filter((checkbox) => checkbox.checked)
            .length;
        const allowThemeOverrideToggle = form.querySelector('#id_allow_user_theme_override');
        const reorderToggle = form.querySelector('#id_sidebar_enable_reorder');
        const allowUserDensityToggle = form.querySelector('#id_sidebar_allow_user_density');
        const sectionsManagerToggle = form.querySelector('#id_sidebar_show_sections_manager');
        const sectionsToolState = form.querySelector('[data-sidebar-tooling-state]');
        const hasToolbarTool = Boolean(
            (
                allowThemeOverrideToggle &&
                allowThemeOverrideToggle.checked &&
                allowedThemeCount > 1
            ) ||
            (allowUserDensityToggle && allowUserDensityToggle.checked) ||
            (reorderToggle && reorderToggle.checked) ||
            (
                sectionsToolState &&
                sectionsToolState.getAttribute('data-sections-manager-available') === 'true' &&
                (!sectionsManagerToggle || sectionsManagerToggle.checked)
            )
        );
        const available = sidebarEnabled && hasToolbarTool;
        const sectionsShortcutDisabled = Boolean(
            sidebarEnabled &&
            sectionsManagerToggle &&
            !sectionsManagerToggle.checked &&
            sectionsToolState &&
            sectionsToolState.getAttribute('data-sections-manager-available') === 'true'
        );

        toolbarToggle.disabled = !available;
        toolbarNote.classList.toggle(
            'd-none',
            !(sectionsShortcutDisabled || (available && !toolbarToggle.checked))
        );
        applyImmediateSystemSettingsPreview(form);
    }



    /* The lock on mail-dependent toggles is rendered server-side, so a test that
       succeeds inside an already-open modal would leave them greyed out until a
       reload — which reads as "the test did nothing". Unlock them in place. */









    function renderTitlebarActionsOrderBuilder(builder, form) {
        const list = builder.querySelector('[data-titlebar-actions-order-list]');
        if (!list) {
            return;
        }
        const items = Array.from(list.querySelectorAll('[data-titlebar-action-order-item]'));
        const order = items.map((item) => item.getAttribute('data-action-key')).filter(Boolean);
        writeTitlebarActionsOrder(form, order);
        items.forEach((item, index) => {
            const upButton = item.querySelector('[data-titlebar-action-move="-1"]');
            const downButton = item.querySelector('[data-titlebar-action-move="1"]');
            if (upButton) {
                upButton.disabled = index === 0;
            }
            if (downButton) {
                downButton.disabled = index === items.length - 1;
            }
        });
    }


    function initTitlebarActionsOrderBuilder(form) {
        const builder = form.querySelector('[data-titlebar-actions-order-builder]');
        if (!builder || builder.dataset.titlebarActionsOrderBound === 'true') {
            return;
        }
        builder.dataset.titlebarActionsOrderBound = 'true';
        const list = builder.querySelector('[data-titlebar-actions-order-list]');
        if (!list) {
            return;
        }

        const hiddenOrder = readTitlebarActionsOrder(form);
        hiddenOrder.forEach((key) => {
            const item = list.querySelector(`[data-titlebar-action-order-item][data-action-key="${key}"]`);
            if (item) {
                list.appendChild(item);
            }
        });

        builder.addEventListener('click', (event) => {
            const button = event.target.closest('[data-titlebar-action-move]');
            if (!button) {
                return;
            }
            const item = button.closest('[data-titlebar-action-order-item]');
            const direction = Number(button.getAttribute('data-titlebar-action-move')) || 0;
            if (!item || !direction) {
                return;
            }
            if (direction < 0 && item.previousElementSibling) {
                list.insertBefore(item, item.previousElementSibling);
            } else if (direction > 0 && item.nextElementSibling) {
                list.insertBefore(item.nextElementSibling, item);
            }
            renderTitlebarActionsOrderBuilder(builder, form);
            applyImmediateSystemSettingsPreview(form);
            persistSetupFormState(form);
        });

        renderTitlebarActionsOrderBuilder(builder, form);
        syncTitlebarActionsBuilderVisibility(form);
    }

    function initTitlebarBehaviorOptions(root) {
        root.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            if (form.dataset.titlebarBehaviorBound === 'true') {
                return;
            }

            const showTitleToggle = form.querySelector('#id_titlebar_show_title');
            const accentEdgeToggle = form.querySelector('#id_titlebar_accent_edge');
            const showLogoToggle = form.querySelector('#id_titlebar_show_logo');
            const showHomeButtonToggle = form.querySelector('#id_titlebar_show_home_button');
            const showLanguageSwitcherToggle = form.querySelector('#id_titlebar_show_language_switcher');
            if (!showTitleToggle || !showLogoToggle || !showHomeButtonToggle) {
                return;
            }

            form.dataset.titlebarBehaviorBound = 'true';
            initTitlebarActionsOrderBuilder(form);

            function syncTitlebarDependencies() {
                const logoTreatment = getNamedFieldValue(form, 'titlebar_logo_treatment') || 'none';
                const showLogo = showLogoToggle.checked;
                const showPlateShape = showLogo && logoTreatment === 'plate';
                const titlebarUserHubStyle = getNamedFieldValue(form, 'titlebar_user_hub_style') || 'dropdown';
                setNamedFieldReadonly(form, 'titlebar_title_align', !showTitleToggle.checked);
                setNamedFieldReadonly(form, 'titlebar_title_size', !showTitleToggle.checked);
                setNamedFieldReadonly(form, 'titlebar_logo_treatment', !showLogo);
                setNamedFieldReadonly(form, 'titlebar_logo_treatment_shape', !showPlateShape);
                const logoReason = dependentReason(showLogoToggle);
                form.querySelectorAll('.dlux-titlebar-logo-dependent').forEach((node) => {
                    setDependentFieldEnabled(node, showLogo, logoReason);
                });
                form.querySelectorAll('.dlux-titlebar-logo-treatment-primary').forEach((node) => {
                    node.classList.toggle('dlux-logo-treatment-primary--wide', showLogo && !showPlateShape);
                });
                form.querySelectorAll('.dlux-titlebar-logo-plate-dependent').forEach((node) => {
                    node.classList.toggle('d-none', !showPlateShape);
                    node.setAttribute('aria-hidden', showPlateShape ? 'false' : 'true');
                });
                setNamedFieldReadonly(form, 'titlebar_home_shape', !showHomeButtonToggle.checked);
                setNamedFieldReadonly(form, 'titlebar_actions_order', titlebarUserHubStyle !== 'titlebar_actions');
                syncTitlebarActionsBuilderVisibility(form);
                applyImmediateSystemSettingsPreview(form);
            }

            showTitleToggle.addEventListener('change', syncTitlebarDependencies);
            if (accentEdgeToggle) {
                accentEdgeToggle.addEventListener('change', syncTitlebarDependencies);
            }
            showLogoToggle.addEventListener('change', syncTitlebarDependencies);
            showHomeButtonToggle.addEventListener('change', syncTitlebarDependencies);
            if (showLanguageSwitcherToggle) {
                showLanguageSwitcherToggle.addEventListener('change', syncTitlebarDependencies);
            }
            form.querySelectorAll('[name="titlebar_logo_treatment"]').forEach((input) => {
                input.addEventListener('change', syncTitlebarDependencies);
            });
            form.querySelectorAll('[name="titlebar_user_hub_style"]').forEach((input) => {
                input.addEventListener('change', syncTitlebarDependencies);
            });
            syncTitlebarDependencies();
        });
    }

    function initNotificationBehaviorOptions(root) {
        root.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            if (form.dataset.notificationBehaviorBound === 'true') {
                return;
            }

            const masterToggle = form.querySelector('#id_notifications_enabled');
            const dependentSection = form.querySelector('[data-notifications-dependent]');
            const flashToggle = form.querySelector('#id_notification_flash_enabled');
            const drawerToggle = form.querySelector('#id_notification_drawer_enabled');
            const autoCrudToggle = form.querySelector('#id_notification_auto_crud_enabled');
            const emailToggle = form.querySelector('#id_notification_email_enabled');
            if (!masterToggle && !flashToggle && !drawerToggle && !autoCrudToggle && !emailToggle) {
                return;
            }

            form.dataset.notificationBehaviorBound = 'true';

            function syncNotificationAvailability() {
                if (!masterToggle || !dependentSection) {
                    return;
                }
                setDependentSectionEnabled(form, dependentSection, masterToggle.checked, DEPENDENT_FIELDS.notifications, dependentReason(masterToggle));
            }

            function syncNotificationDependencies() {
                const flashEnabled = !flashToggle || flashToggle.checked;
                const drawerEnabled = !drawerToggle || drawerToggle.checked;
                const autoCrudEnabled = !autoCrudToggle || autoCrudToggle.checked;
                const emailAvailable = emailToggle && !emailToggle.disabled;
                const emailEnabled = Boolean(emailAvailable && emailToggle.checked);

                [
                    'notification_flash_position',
                    'notification_flash_size',
                    'notification_flash_text_size',
                    'notification_flash_timeout_ms',
                    'notification_flash_max_visible',
                ].forEach((name) => setNamedFieldReadonly(form, name, !flashEnabled));
                setNamedFieldReadonly(form, 'notification_badge_enabled', !drawerEnabled);
                [
                    'notification_auto_create',
                    'notification_auto_update',
                    'notification_auto_delete',
                ].forEach((name) => setNamedFieldReadonly(form, name, !autoCrudEnabled));
                setNamedFieldDisabled(form, 'notification_email_default', !emailEnabled);
                applyImmediateSystemSettingsPreview(form);
            }

            form.addEventListener('change', (event) => {
                const name = event.target && event.target.name;
                if (name === 'notifications_enabled') {
                    syncNotificationAvailability();
                    syncNotificationDependencies();
                } else if (name && name.startsWith('notification_')) {
                    syncNotificationDependencies();
                }
            });
            syncNotificationAvailability();
            syncNotificationDependencies();
        });
    }



    // Full-page setup only: lift the wizard action bar out of the scroll body into
    // the pinned footer row, so the body scrolls between the fixed nav and footer
    // (mirrors how the dynamic modal relocates actions into its sticky footer).
    function initSetupFooterRelocation(root) {
        root.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            const footer = form.querySelector('[data-dlux-setup-footer]');
            if (!footer) {
                return;
            }
            const actions = form.querySelector('.dlux-setup-scroll .dlux-setup-wizard-actions');
            if (actions && actions.parentElement !== footer) {
                footer.appendChild(actions);
            }
        });
    }

    function scan(root) {
        restoreSetupFormState(root);
        initSetupFooterRelocation(root);
        initSetupHomeFields(root);
        if (window.DluxIconPicker) window.DluxIconPicker.init(root);
        initLogBuilder(root);
        initProfileBuilder(root);
        root.querySelectorAll('.dlux-setup-builder').forEach(initBuilder);
        root.querySelectorAll('[data-navbar-builder]').forEach(initNavbarBuilder);
        initSystemNamesEditor(root);
        initLanguageCatalogEditor(root);
        initTranslationMatrixEditor(root);
        initSystemSetupEnterBehavior(root);
        initSystemSetupStepValidation(root);
        initSystemSetupImportFile(root);
        initSetupThemePicker(root);
        initSetupFontPicker(root);
        initLanguageFontsEditor(root);
        initSidebarBehaviorOptions(root);
        initNavbarBehaviorOptions(root);
        root.querySelectorAll('form.dlux-system-setup-form').forEach(syncSidebarToolbarWarningFallback);
        initEmailDeliveryOptions(root);
        initPublicRegistrationOptions(root);
        initPublicPageOptions(root);
        initClientIpOptions(root);
        initAuthSecurityOptions(root);
        initGlobalSearchOptions(root);
        initLoginPageOptions(root);
        initTitlebarBehaviorOptions(root);
        initNotificationBehaviorOptions(root);
        initImmediateSystemSettingsPreview(root);
        finalizeSetupFormStateRestore(root);
    }

    window.__dluxPrepareWizardContainer = function (container) {
        const root = container || document;
        const form = root.matches && root.matches('form.dlux-system-setup-form')
            ? root
            : root.querySelector
                ? root.querySelector('form.dlux-system-setup-form')
                : null;
        if (!form) {
            return;
        }
        scan(document);
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => scan(document));
    } else {
        scan(document);
    }

    document.addEventListener('change', (event) => {
        const target = event.target;
        if (!target || !target.matches) {
            return;
        }
        if (!target.matches(
            '#id_sidebar_enable_toolbar, #id_sidebar_enabled, #id_sidebar_enable_reorder, #id_sidebar_show_sections_manager, #id_sidebar_allow_user_density, #id_allow_user_theme_override, [data-setup-theme-allowed], [data-setup-font-allowed]'
        )) {
            return;
        }
        syncSidebarToolbarWarningFallback(target.closest('form.dlux-system-setup-form'));
    });

    const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            for (const node of mutation.addedNodes) {
                if (node.nodeType !== 1) continue;
                if (
                    node.matches && (
                        node.matches('form.dlux-system-setup-form') ||
                        node.matches('.dlux-setup-builder') ||
                        node.matches('[data-navbar-builder]') ||
                        node.matches('[data-dlux-selector]') ||
                        node.querySelector('.dlux-setup-builder') ||
                        node.querySelector('[data-navbar-builder]') ||
                        node.querySelector('form.dlux-system-setup-form') ||
	                        node.querySelector('[data-dlux-selector]') ||
	                        node.querySelector('[data-language-catalog-editor]') ||
	                        node.querySelector('[data-translation-matrix]') ||
	                        node.querySelector('[data-setup-font-picker]') ||
                        node.querySelector('#dluxLanguageFontsEditor')
                    )
                ) {
                    scan(node);
                    return;
                }
            }
        }
    });

    observer.observe(document.body, { childList: true, subtree: true });
})();
