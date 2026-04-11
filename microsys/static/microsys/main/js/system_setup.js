(function() {
    'use strict';

    const SETUP_STATE_KEY = `microsys.systemSetupState:${window.location.pathname}`;
    const ICON_SUGGESTIONS = [
        'bi-house',
        'bi-house-fill',
        'bi-house-door',
        'bi-house-door-fill',
        'bi-house-heart',
        'bi-house-heart-fill',
        'bi-house-gear',
        'bi-house-gear-fill',
        'bi-house-lock',
        'bi-houses',
        'bi-speedometer2',
        'bi-speedometer',
        'bi-grid',
        'bi-grid-3x2',
        'bi-grid-3x2-gap',
        'bi-grid-3x3-gap',
        'bi-grid-fill',
        'bi-layout-sidebar',
        'bi-layout-text-sidebar',
        'bi-layout-sidebar-inset',
        'bi-layout-three-columns',
        'bi-box',
        'bi-box-fill',
        'bi-box-seam',
        'bi-box-seam-fill',
        'bi-box2',
        'bi-boxes',
        'bi-inbox',
        'bi-inbox-fill',
        'bi-inboxes',
        'bi-inboxes-fill',
        'bi-archive',
        'bi-archive-fill',
        'bi-collection',
        'bi-collection-fill',
        'bi-folder',
        'bi-folder-fill',
        'bi-folder-plus',
        'bi-folder-check',
        'bi-folder-x',
        'bi-folder2-open',
        'bi-wallet',
        'bi-wallet-fill',
        'bi-wallet2',
        'bi-cash',
        'bi-cash-coin',
        'bi-cash-stack',
        'bi-currency-dollar',
        'bi-currency-euro',
        'bi-currency-exchange',
        'bi-bank',
        'bi-bank2',
        'bi-piggy-bank',
        'bi-credit-card',
        'bi-credit-card-fill',
        'bi-receipt',
        'bi-receipt-cutoff',
        'bi-safe',
        'bi-safe-fill',
        'bi-safe2',
        'bi-shield',
        'bi-shield-check',
        'bi-shield-lock',
        'bi-shield-fill-check',
        'bi-person',
        'bi-person-fill',
        'bi-person-circle',
        'bi-person-badge',
        'bi-person-badge-fill',
        'bi-person-lines-fill',
        'bi-person-vcard',
        'bi-person-gear',
        'bi-people',
        'bi-people-fill',
        'bi-gear',
        'bi-gear-fill',
        'bi-gear-wide',
        'bi-gear-wide-connected',
        'bi-sliders',
        'bi-sliders2',
        'bi-sliders2-vertical',
        'bi-wrench',
        'bi-wrench-adjustable',
        'bi-wrench-adjustable-circle',
        'bi-briefcase',
        'bi-briefcase-fill',
        'bi-building',
        'bi-building-fill',
        'bi-building-gear',
        'bi-buildings',
        'bi-shop',
        'bi-shop-window',
        'bi-file-bar-graph',
        'bi-file-earmark-bar-graph',
        'bi-file-earmark-text',
        'bi-file-earmark-check',
        'bi-file-earmark-code',
        'bi-file-earmark-spreadsheet',
        'bi-file-earmark-person',
        'bi-file-text',
        'bi-clipboard-data',
        'bi-clipboard-data-fill',
        'bi-clipboard-check',
        'bi-clipboard-check-fill',
        'bi-clipboard2-data',
        'bi-clipboard2-check',
        'bi-journal-text',
        'bi-journal-check',
        'bi-journal-richtext',
        'bi-book',
        'bi-book-fill',
        'bi-bookmark',
        'bi-bookmark-star',
        'bi-table',
        'bi-list-ul',
        'bi-list-check',
        'bi-list-task',
        'bi-kanban',
        'bi-kanban-fill',
        'bi-pie-chart',
        'bi-pie-chart-fill',
        'bi-bar-chart',
        'bi-bar-chart-line',
        'bi-bar-chart-steps',
        'bi-graph-up',
        'bi-graph-up-arrow',
        'bi-graph-down',
        'bi-diagram-3',
        'bi-diagram-3-fill',
        'bi-diagram-2',
        'bi-diagram-2-fill',
        'bi-grid-1x2',
        'bi-columns',
        'bi-columns-gap',
        'bi-window',
        'bi-window-sidebar',
        'bi-window-stack',
        'bi-truck',
        'bi-truck-front',
        'bi-truck-flatbed',
        'bi-cart',
        'bi-cart-fill',
        'bi-cart-check',
        'bi-cart3',
        'bi-bag',
        'bi-bag-fill',
        'bi-bag-check',
        'bi-basket',
        'bi-basket-fill',
        'bi-basket3',
        'bi-globe',
        'bi-globe2',
        'bi-globe-europe-africa',
        'bi-chat-square-text',
        'bi-chat-left-text',
        'bi-chat-dots',
        'bi-chat-quote',
        'bi-send',
        'bi-send-check',
        'bi-mailbox',
        'bi-telephone',
        'bi-telephone-fill',
        'bi-telephone-inbound',
        'bi-telephone-outbound',
        'bi-calendar',
        'bi-calendar-event',
        'bi-calendar-check',
        'bi-clock',
        'bi-clock-history',
        'bi-bell',
        'bi-bell-fill',
        'bi-star',
        'bi-star-fill',
        'bi-check-circle',
        'bi-check-square',
        'bi-x-circle',
        'bi-link-45deg',
        'bi-arrow-left-right',
        'bi-arrow-repeat',
        'bi-database',
        'bi-database-fill',
        'bi-database-gear',
        'bi-database-check',
        'bi-calculator',
        'bi-calculator-fill',
    ];

    function t(key, fallback) {
        if (window.__MS_TRANS && typeof window.__MS_TRANS[key] === 'string' && window.__MS_TRANS[key]) {
            return window.__MS_TRANS[key];
        }
        return fallback;
    }

    function parseJson(text, fallback) {
        try {
            return JSON.parse(text || '');
        } catch (err) {
            return fallback;
        }
    }

    function readSetupState() {
        try {
            return parseJson(sessionStorage.getItem(SETUP_STATE_KEY), null);
        } catch (err) {
            return null;
        }
    }

    function persistSetupFormState(form) {
        if (!form || !form.classList.contains('ms-system-setup-form')) {
            return;
        }

        const state = {
            path: window.location.pathname,
            values: {},
            currentStep: 0,
        };

        const steps = Array.from(form.querySelectorAll('.wizard-step'));
        const visibleStepIndex = steps.findIndex((step) => window.getComputedStyle(step).display !== 'none');
        if (visibleStepIndex >= 0) {
            state.currentStep = visibleStepIndex;
        }

        form.querySelectorAll('input[name], select[name], textarea[name]').forEach((field) => {
            if (!field.name || field.name === 'csrfmiddlewaretoken' || field.disabled || field.type === 'file') {
                return;
            }

            if (field.type === 'radio') {
                if (field.checked) {
                    state.values[field.name] = field.value;
                }
                return;
            }

            if (field.type === 'checkbox') {
                state.values[field.name] = Boolean(field.checked);
                return;
            }

            state.values[field.name] = field.value;
        });

        sessionStorage.setItem(SETUP_STATE_KEY, JSON.stringify(state));
    }

    function restoreSetupFormState(root) {
        root.querySelectorAll('form.ms-system-setup-form').forEach((form) => {
            if (form.dataset.setupStateRestored === 'true') {
                return;
            }
            form.dataset.setupStateRestored = 'true';

            const state = readSetupState();
            if (!state || state.path !== window.location.pathname || !state.values || typeof state.values !== 'object') {
                return;
            }

            Object.entries(state.values).forEach(([name, value]) => {
                const safeName = String(name).replace(/"/g, '\\"');
                const fields = Array.from(form.querySelectorAll(`[name="${safeName}"]`));
                if (!fields.length) {
                    return;
                }

                if (fields[0].type === 'radio') {
                    fields.forEach((field) => {
                        field.checked = field.value === value;
                    });
                    return;
                }

                fields.forEach((field) => {
                    if (field.type === 'checkbox') {
                        field.checked = Boolean(value);
                    } else if (field.type !== 'file') {
                        field.value = value;
                    }
                });
            });

            if (Number.isInteger(state.currentStep) && state.currentStep >= 0) {
                form.dataset.msWizardInitialStep = String(state.currentStep);
            }

            sessionStorage.removeItem(SETUP_STATE_KEY);
        });
    }

    window.__msGetWizardInitialStep = function(container) {
        const form = container && (container.matches && container.matches('form') ? container : container.closest && container.closest('form'));
        if (!form || !form.classList.contains('ms-system-setup-form')) {
            return null;
        }
        const state = readSetupState();
        if (!state || state.path !== window.location.pathname) {
            return null;
        }
        return Number.isInteger(state.currentStep) ? state.currentStep : null;
    };

    function humanizeKey(value) {
        return String(value || '')
            .split(':')
            .pop()
            .replace(/[_-]+/g, ' ')
            .replace(/\b\w/g, (char) => char.toUpperCase())
            .trim();
    }

    function availableItemDisplayLabel(item) {
        const label = String(item && item.label ? item.label : '').trim();
        const groupLabel = String(item && item.group_label ? item.group_label : '').trim();
        const urlName = String(item && item.url_name ? item.url_name : item && item.id ? item.id : '').trim();
        const leaf = urlName.split(':').pop();

        if (label && label !== groupLabel) {
            return label;
        }
        if (leaf === 'dashboard' && groupLabel) {
            return `${groupLabel} Dashboard`;
        }
        return humanizeKey(urlName) || groupLabel || t('sidebar_group_label', 'Item');
    }

    function normalizeCatalog(catalog) {
        if (!Array.isArray(catalog)) {
            return [];
        }
        return catalog
            .filter(entry => entry && entry.id && entry.url_name)
            .map(entry => ({
                kind: 'item',
                id: entry.id,
                url_name: entry.url_name,
                label: entry.label || entry.id,
                icon: entry.icon || 'bi-link-45deg',
                permissions: Array.isArray(entry.permissions) ? entry.permissions : [],
                group_key: entry.group_key || 'general',
                group_label: entry.group_label || entry.group_key || 'General',
                group_icon: entry.group_icon || 'bi-folder2-open',
                is_system: Boolean(entry.is_system),
            }));
    }

    function normalizeSidebarConfig(config) {
        if (!config || typeof config !== 'object') {
            return { home_url_name: null, entries: [] };
        }

        const entries = Array.isArray(config.entries) ? config.entries : [];
        return {
            home_url_name: config.home_url_name || null,
            entries: entries.map(normalizeEntry).filter(Boolean),
        };
    }

    function normalizeEntry(entry) {
        if (!entry || typeof entry !== 'object') {
            return null;
        }
        if ((entry.kind || 'item') === 'group') {
            return {
                kind: 'group',
                id: entry.id || `group-${Date.now()}`,
                label: entry.label || t('sidebar_group_label', 'Group'),
                icon: entry.icon || 'bi-folder2-open',
                items: Array.isArray(entry.items) ? entry.items.map(normalizeEntry).filter(Boolean) : [],
            };
        }
        if (!entry.id && !entry.url_name) {
            return null;
        }
        return {
            kind: 'item',
            id: entry.id || entry.url_name,
            url_name: entry.url_name || entry.id,
            label: entry.label || entry.url_name || entry.id,
            icon: entry.icon || 'bi-link-45deg',
            permissions: Array.isArray(entry.permissions) ? entry.permissions : [],
            group_key: entry.group_key || '',
            group_label: entry.group_label || '',
        };
    }

    function cloneEntry(entry) {
        return JSON.parse(JSON.stringify(entry));
    }

    function cloneGroupEntry(group) {
        const items = Array.isArray(group && group.items) ? group.items.map(cloneEntry) : [];
        const label = String(group && group.label ? group.label : '').trim() || t('sidebar_group_label', 'Group');
        return {
            kind: 'group',
            id: makeGroupId(group && (group.id || group.group_key || label || 'group')),
            label,
            icon: group && group.icon ? group.icon : 'bi-folder2-open',
            items,
        };
    }

    function makeGroupId(label) {
        const safeLabel = (label || 'group').toLowerCase().replace(/\s+/g, '-').replace(/[^\w-]+/g, '').replace(/-+/g, '-');
        return `${safeLabel || 'group'}-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    }

    function collectSelectedItemIds(entries, acc) {
        acc = acc || new Set();
        (entries || []).forEach(entry => {
            if (entry.kind === 'group') {
                collectSelectedItemIds(entry.items || [], acc);
                return;
            }
            if (entry.id) {
                acc.add(entry.id);
            }
        });
        return acc;
    }

    function availableItems(state) {
        const selectedIds = collectSelectedItemIds(state.config.entries);
        return state.catalog.filter(item => !selectedIds.has(item.id) && (state.showSystemItems || !item.is_system));
    }

    function groupedAvailableItems(state) {
        const grouped = {};
        availableItems(state)
            .filter(item => {
                if (!state.search) return true;
                const haystack = `${item.label} ${item.group_label} ${item.url_name}`.toLowerCase();
                return haystack.includes(state.search.toLowerCase());
            })
            .forEach(item => {
                const key = item.group_key || item.group_label || 'general';
                if (!grouped[key]) {
                    grouped[key] = {
                        kind: 'group',
                        id: key,
                        label: item.group_label || key,
                        icon: item.group_icon || 'bi-folder2-open',
                        items: [],
                    };
                }
                grouped[key].items.push(item);
            });

        return Object.values(grouped).sort((left, right) => left.label.localeCompare(right.label));
    }

    function findEntryLocation(entries, id, kind) {
        for (let index = 0; index < entries.length; index += 1) {
            const entry = entries[index];
            if (entry.kind === kind && entry.id === id) {
                return { parent: entries, index, entry, container: 'root' };
            }
            if (entry.kind === 'group') {
                if (kind === 'group' && entry.id === id) {
                    return { parent: entries, index, entry, container: 'root' };
                }
                const childIndex = (entry.items || []).findIndex(item => item.id === id && item.kind === kind);
                if (childIndex !== -1) {
                    return { parent: entry.items, index: childIndex, entry: entry.items[childIndex], container: 'group', group: entry };
                }
            }
        }
        return null;
    }

    function topLevelItems(entries) {
        return (entries || []).filter(entry => entry.kind === 'item' && entry.url_name);
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

        const catalogData = builder.querySelector('.ms-sidebar-catalog-data');
        const configData = builder.querySelector('.ms-sidebar-config-data');
        const state = {
            catalog: normalizeCatalog(parseJson(catalogData ? catalogData.value : '[]', [])),
            config: normalizeSidebarConfig(parseJson(hiddenInput.value || (configData ? configData.value : '{}'), {})),
            selected: null,
            selectedTargetGroup: null,
            search: '',
            dragging: null,
            showSystemItems: false,
        };

        const refs = {
            selectedTree: builder.querySelector('[data-builder-selected-tree]'),
            availableList: builder.querySelector('[data-builder-available-list]'),
            search: builder.querySelector('[data-builder-search]'),
            systemToggle: builder.querySelector('[data-builder-system-toggle]'),
            inspector: builder.querySelector('[data-builder-inspector]'),
            inspectorEmpty: builder.querySelector('[data-builder-empty-inspector]'),
            labelInput: builder.querySelector('[data-builder-label-input]'),
            iconInput: builder.querySelector('[data-builder-icon-input]'),
            iconPreview: builder.querySelector('[data-builder-icon-preview]'),
            iconSuggestions: builder.querySelector('[data-builder-icon-suggestions]'),
        };

        function serialize() {
            hiddenInput.value = JSON.stringify(state.config);
        }

        function renderAvailable() {
            refs.availableList.innerHTML = '';

            groupedAvailableItems(state).forEach(group => {
                const section = document.createElement('div');
                section.className = 'ms-builder-available-group';
                const groupButton = document.createElement('button');
                groupButton.type = 'button';
                groupButton.className = 'ms-builder-item available-item fw-semibold';
                groupButton.dataset.pane = 'available';
                groupButton.dataset.entryId = group.id;
                groupButton.dataset.entryKind = 'group';
                if (state.selected && state.selected.pane === 'available' && state.selected.kind === 'group' && state.selected.id === group.id) {
                    groupButton.classList.add('is-active');
                }
                groupButton.innerHTML = `
                    <span class="ms-builder-item-main">
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
                section.appendChild(groupButton);

                const children = document.createElement('div');
                children.className = 'ms-builder-available-items';

                group.items.forEach(item => {
                    const button = document.createElement('button');
                    button.type = 'button';
                    button.className = 'ms-builder-item available-item is-child';
                    button.dataset.pane = 'available';
                    button.dataset.entryId = item.id;
                    button.dataset.entryKind = 'item';
                    if (state.selected && state.selected.pane === 'available' && state.selected.kind === 'item' && state.selected.id === item.id) {
                        button.classList.add('is-active');
                    }
                    button.innerHTML = `
                        <span class="ms-builder-item-main">
                            <i class="bi ${item.icon}"></i>
                            <span class="ms-builder-item-copy">
                                <span class="ms-builder-item-label">${availableItemDisplayLabel(item)}</span>
                                <span class="ms-builder-item-meta">${item.url_name || item.id}</span>
                            </span>
                        </span>
                    `;
                    button.addEventListener('click', () => {
                        state.selected = { pane: 'available', id: item.id, kind: 'item' };
                        state.selectedTargetGroup = null;
                        renderAll();
                    });
                    button.addEventListener('dblclick', () => {
                        addSelectedAvailableItem();
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
            wrapper.className = `ms-builder-node ${entry.kind === 'group' ? 'is-group' : 'is-item'}`;
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

            wrapper.addEventListener('dragstart', () => {
                state.dragging = { id: entry.id, kind: entry.kind };
                wrapper.classList.add('is-dragging');
            });

            wrapper.addEventListener('dragend', () => {
                state.dragging = null;
                builder.querySelectorAll('.ms-builder-drop-target').forEach(el => el.classList.remove('ms-builder-drop-target'));
                builder.querySelectorAll('.ms-builder-drop-before').forEach(el => el.classList.remove('ms-builder-drop-before'));
                builder.querySelectorAll('.ms-builder-drop-after').forEach(el => el.classList.remove('ms-builder-drop-after'));
            });

            wrapper.addEventListener('dragover', (event) => {
                if (!state.dragging) return;
                event.preventDefault();
                const rect = wrapper.getBoundingClientRect();
                const before = event.clientY < rect.top + rect.height / 2;
                wrapper.classList.toggle('ms-builder-drop-before', before);
                wrapper.classList.toggle('ms-builder-drop-after', !before);
            });

            wrapper.addEventListener('dragleave', () => {
                wrapper.classList.remove('ms-builder-drop-before', 'ms-builder-drop-after');
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
                    <div class="ms-builder-group-header">
                        <span class="ms-builder-item-main">
                            <i class="bi ${entry.icon}"></i>
                            <span>${entry.label}</span>
                        </span>
                        <span class="badge text-bg-light">${(entry.items || []).length}</span>
                    </div>
                    <div class="ms-builder-group-items" data-group-dropzone="${entry.id}"></div>
                `;

                const itemsContainer = wrapper.querySelector('[data-group-dropzone]');
                itemsContainer.addEventListener('dragover', (event) => {
                    if (!state.dragging || state.dragging.kind !== 'item') return;
                    event.preventDefault();
                    itemsContainer.classList.add('ms-builder-drop-target');
                });
                itemsContainer.addEventListener('dragleave', () => {
                    itemsContainer.classList.remove('ms-builder-drop-target');
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
                    <span class="ms-builder-item-main">
                        <i class="bi ${entry.icon}"></i>
                        <span>${entry.label}</span>
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

        function renderInspector() {
            if (!state.selected || state.selected.pane !== 'selected') {
                refs.inspector.classList.add('d-none');
                refs.inspectorEmpty.classList.remove('d-none');
                return;
            }

            const location = findEntryLocation(state.config.entries, state.selected.id, state.selected.kind);
            if (!location) {
                refs.inspector.classList.add('d-none');
                refs.inspectorEmpty.classList.remove('d-none');
                return;
            }

            refs.inspector.classList.remove('d-none');
            refs.inspectorEmpty.classList.add('d-none');
            refs.labelInput.value = location.entry.label || '';
            refs.iconInput.value = location.entry.icon || '';
            refs.iconPreview.className = `bi ${location.entry.icon || 'bi-link-45deg'}`;
            refs.iconSuggestions.innerHTML = '';

            ICON_SUGGESTIONS.forEach(icon => {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = `btn btn-sm ms-builder-icon-choice ${location.entry.icon === icon ? 'is-active' : ''}`;
                button.setAttribute('title', icon);
                button.setAttribute('aria-label', icon);
                button.innerHTML = `<i class="bi ${icon}"></i>`;
                button.addEventListener('click', () => {
                    refs.iconInput.value = icon;
                    location.entry.icon = icon;
                    refs.iconPreview.className = `bi ${icon}`;
                    renderAll();
                });
                refs.iconSuggestions.appendChild(button);
            });
        }

        function renderAll() {
            serialize();
            renderSelected();
            renderAvailable();
            renderInspector();
        }

        function addSelectedAvailableItem() {
            if (!state.selected || state.selected.pane !== 'available') return;
            if (state.selected.kind === 'group') {
                const sourceGroup = groupedAvailableItems(state).find(group => group.id === state.selected.id);
                if (!sourceGroup || !sourceGroup.items.length) return;
                const nextGroup = cloneGroupEntry(sourceGroup);
                state.config.entries.push(nextGroup);
                state.selected = { pane: 'selected', id: nextGroup.id, kind: 'group' };
                renderAll();
                return;
            }

            const source = state.catalog.find(item => item.id === state.selected.id);
            if (!source) return;
            const nextItem = cloneEntry(source);
            state.config.entries.push(nextItem);

            state.selected = { pane: 'selected', id: nextItem.id, kind: 'item' };
            renderAll();
        }

        function addAllAvailableItems() {
            const groups = groupedAvailableItems(state).map(cloneGroupEntry).filter(group => group.items.length);
            if (!groups.length) return;
            state.config.entries = state.config.entries.concat(groups);
            state.selected = null;
            state.selectedTargetGroup = null;
            renderAll();
        }

        function removeSelectedEntry() {
            if (!state.selected || state.selected.pane !== 'selected') return;
            const location = findEntryLocation(state.config.entries, state.selected.id, state.selected.kind);
            if (!location) return;
            location.parent.splice(location.index, 1);
            state.selected = null;
            renderAll();
        }

        function removeAllSelectedEntries() {
            state.config.entries = [];
            state.selected = null;
            state.selectedTargetGroup = null;
            renderAll();
        }

        function moveSelectedToRoot() {
            if (!state.selected || state.selected.pane !== 'selected' || state.selected.kind !== 'item') return;
            const location = findEntryLocation(state.config.entries, state.selected.id, 'item');
            if (!location || location.container !== 'group') return;
            const [entry] = location.parent.splice(location.index, 1);
            state.config.entries.push(entry);
            renderAll();
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
            renderAll();
        }

        function duplicateSelectedEntry() {
            if (!state.selected || state.selected.pane !== 'selected' || state.selected.kind !== 'group') return;
            const location = findEntryLocation(state.config.entries, state.selected.id, 'group');
            if (!location) return;
            const duplicate = {
                kind: 'group',
                id: makeGroupId(location.entry.label),
                label: `${location.entry.label} ${t('sidebar_copy_suffix', 'Copy')}`,
                icon: location.entry.icon,
                items: [],
            };
            location.parent.splice(location.index + 1, 0, duplicate);
            state.selected = { pane: 'selected', id: duplicate.id, kind: 'group' };
            renderAll();
        }

        function moveDraggedEntry(target) {
            const dragging = state.dragging;
            if (!dragging) return;

            const source = findEntryLocation(state.config.entries, dragging.id, dragging.kind);
            if (!source) return;
            if (dragging.kind === 'group' && target.type !== 'root-container' && target.type !== 'root-node') {
                return;
            }

            const [entry] = source.parent.splice(source.index, 1);

            if (target.type === 'root-container') {
                state.config.entries.push(entry);
            } else if (target.type === 'group-container') {
                const groupLocation = findEntryLocation(state.config.entries, target.groupId, 'group');
                if (groupLocation && groupLocation.entry.kind === 'group') {
                    groupLocation.entry.items.push(entry);
                } else {
                    state.config.entries.push(entry);
                }
            } else if (target.type === 'root-node') {
                const targetLocation = findEntryLocation(state.config.entries, target.targetId, target.targetKind);
                if (!targetLocation) {
                    state.config.entries.push(entry);
                } else {
                    const insertIndex = target.before ? targetLocation.index : targetLocation.index + 1;
                    state.config.entries.splice(insertIndex, 0, entry);
                }
            } else if (target.type === 'group-node') {
                const groupLocation = findEntryLocation(state.config.entries, target.parentGroupId, 'group');
                if (!groupLocation || groupLocation.entry.kind !== 'group') {
                    state.config.entries.push(entry);
                } else {
                    const targetLocation = findEntryLocation(groupLocation.entry.items, target.targetId, target.targetKind);
                    if (!targetLocation) {
                        groupLocation.entry.items.push(entry);
                    } else {
                        const insertIndex = target.before ? targetLocation.index : targetLocation.index + 1;
                        groupLocation.entry.items.splice(insertIndex, 0, entry);
                    }
                }
            }

            state.selected = { pane: 'selected', id: entry.id, kind: entry.kind };
            state.dragging = null;
            renderAll();
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
                        (state.selected.kind === 'group' && state.selected.id === 'microsys') ||
                        (selectedAvailableItem && selectedAvailableItem.is_system)
                    ) {
                        state.selected = null;
                    }
                }
                renderAvailable();
            });
        }

        refs.labelInput.addEventListener('input', () => {
            if (!state.selected || state.selected.pane !== 'selected') return;
            const location = findEntryLocation(state.config.entries, state.selected.id, state.selected.kind);
            if (!location) return;
            location.entry.label = refs.labelInput.value || '';
            serialize();
            renderSelected();
            renderAvailable();
        });

        refs.iconInput.addEventListener('input', () => {
            if (!state.selected || state.selected.pane !== 'selected') return;
            const location = findEntryLocation(state.config.entries, state.selected.id, state.selected.kind);
            if (!location) return;
            location.entry.icon = refs.iconInput.value || 'bi-link-45deg';
            refs.iconPreview.className = `bi ${location.entry.icon}`;
            serialize();
            renderSelected();
            renderAvailable();
            renderInspector();
        });

        refs.selectedTree.addEventListener('dragover', (event) => {
            if (!state.dragging) return;
            event.preventDefault();
            refs.selectedTree.classList.add('ms-builder-drop-target');
        });
        refs.selectedTree.addEventListener('dragleave', () => {
            refs.selectedTree.classList.remove('ms-builder-drop-target');
        });
        refs.selectedTree.addEventListener('drop', (event) => {
            if (!state.dragging) return;
            event.preventDefault();
            event.stopPropagation();
            moveDraggedEntry({ type: 'root-container' });
        });

        builder.querySelectorAll('[data-builder-action]').forEach(button => {
            button.addEventListener('click', () => {
                const action = button.getAttribute('data-builder-action');
                if (action === 'add-selected') addSelectedAvailableItem();
                if (action === 'add-all') addAllAvailableItems();
                if (action === 'remove-selected') removeSelectedEntry();
                if (action === 'remove-all') removeAllSelectedEntries();
                if (action === 'move-root') moveSelectedToRoot();
                if (action === 'add-group') addGroup();
                if (action === 'duplicate-entry') duplicateSelectedEntry();
                if (action === 'delete-entry') removeSelectedEntry();
            });
        });

        renderAll();
    }

    function initSetupHomeFields(root) {
        root.querySelectorAll('form').forEach((form) => {
            if (form.dataset.setupHomeFieldsBound === 'true') {
                return;
            }

            const routeSelect = form.querySelector('[name="home_url_discovered"]');
            const urlInput = form.querySelector('[name="home_url"]');
            if (!routeSelect || !urlInput) {
                return;
            }

            form.dataset.setupHomeFieldsBound = 'true';

            const selectableValues = new Set(
                Array.from(routeSelect.options || [])
                    .map((option) => option.value)
                    .filter(Boolean)
            );

            function syncSelectFromInput() {
                const currentValue = (urlInput.value || '').trim();
                routeSelect.value = selectableValues.has(currentValue) ? currentValue : '';
            }

            routeSelect.addEventListener('change', () => {
                if (!routeSelect.value) {
                    return;
                }
                urlInput.value = routeSelect.value;
                urlInput.dispatchEvent(new Event('input', { bubbles: true }));
                urlInput.dispatchEvent(new Event('change', { bubbles: true }));
            });

            urlInput.addEventListener('input', syncSelectFromInput);
            urlInput.addEventListener('change', syncSelectFromInput);
            syncSelectFromInput();
        });
    }

    function initSetupLanguagePicker(root) {
        root.querySelectorAll('[data-setup-language-picker]').forEach((picker) => {
            if (picker.dataset.bound === 'true') return;
            picker.dataset.bound = 'true';

            const inputId = picker.getAttribute('data-language-input');
            const input = inputId ? document.getElementById(inputId) : null;
            const form = picker.closest('form');
            if (!input) return;

            const options = Array.from(picker.querySelectorAll('[data-setup-language-choice]'));

            function syncActive() {
                const activeLanguage = input.value || 'en';
                options.forEach((option) => {
                    option.classList.toggle('lang-active', option.getAttribute('data-setup-language-choice') === activeLanguage);
                });
            }

            options.forEach((option) => {
                option.addEventListener('click', () => {
                    const language = option.getAttribute('data-setup-language-choice') || 'en';
                    const currentLanguage = (window.USER_PREFS && window.USER_PREFS._lang) || 'en';
                    input.value = language;
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    syncActive();
                    if (language === currentLanguage) {
                        return;
                    }
                    persistSetupFormState(form);
                    if (window.setLanguage) {
                        window.setLanguage(language);
                    }
                });
            });

            syncActive();
        });
    }

    function initSetupThemePicker(root) {
        root.querySelectorAll('[data-setup-theme-picker]').forEach((picker) => {
            if (picker.dataset.bound === 'true') return;
            picker.dataset.bound = 'true';

            const inputId = picker.getAttribute('data-theme-input');
            const input = inputId ? document.getElementById(inputId) : null;
            if (!input) return;

            const options = Array.from(picker.querySelectorAll('.theme-preview[data-theme]'));

            function syncActive() {
                const activeTheme = input.value || 'light';
                options.forEach((option) => {
                    option.classList.toggle('active', option.getAttribute('data-theme') === activeTheme);
                });
            }

            options.forEach((option) => {
                option.addEventListener('click', () => {
                    const theme = option.getAttribute('data-theme') || 'light';
                    input.value = theme;
                    syncActive();
                    if (window.setTheme) {
                        window.setTheme(theme);
                    }
                });
            });

            syncActive();
        });
    }

    function scan(root) {
        restoreSetupFormState(root);
        initSetupHomeFields(root);
        root.querySelectorAll('.ms-setup-builder').forEach(initBuilder);
        initSetupLanguagePicker(root);
        initSetupThemePicker(root);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => scan(document));
    } else {
        scan(document);
    }

    const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            for (const node of mutation.addedNodes) {
                if (node.nodeType !== 1) continue;
                if (
                    node.matches && (
                        node.matches('.ms-setup-builder') ||
                        node.querySelector('.ms-setup-builder') ||
                        node.querySelector('[data-setup-language-picker]')
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
