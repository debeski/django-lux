/* Pure data model behind the setup wizard's sidebar and navbar builders.
 *
 * Split out of setup/js/main.js, which had grown to 5,047 lines in a single
 * closure with no tests. These functions were chosen because they are
 * transitively free of the DOM: they take plain config objects and return plain
 * config objects, which makes them the only part of the wizard that can be unit
 * tested without a browser. Everything DOM-bound stayed behind.
 *
 * Exposed the same way helpers/icon_picker/js/main.js exposes DluxIconPicker —
 * a namespace on window, loaded before setup/js/main.js, which destructures it.
 * The `globalThis` fallback lets `node --test` require this file directly; see
 * tests-js/ — which must require setup/js/dom.js first, since `t` comes from
 * there.
 */
(function (root) {
    'use strict';

    // `t` is the string lookup from setup/js/dom.js, which must load first.
    // Three label resolvers fall back to a translated default when an entry
    // carries none, so this module is no longer strictly standalone.
    const { t } = root.DluxSetupDom;

    function normalizeLanguageCode(value) {
        return String(value || '').trim().toLowerCase().replace(/_/g, '-').replace(/[^a-z0-9-]/g, '');
    }

    function normalizeNavbarBuilderNode(rawNode) {
        if (!rawNode || typeof rawNode !== 'object') {
            return null;
        }
        const id = String(rawNode.id || '').trim();
        if (!id) {
            return null;
        }
        const kind = rawNode.kind === 'route' ? 'route' : 'manual';
        const labels = {};
        Object.entries(rawNode.labels || {}).forEach(([rawCode, rawLabel]) => {
            const code = normalizeLanguageCode(rawCode);
            const label = String(rawLabel || '').trim();
            if (code && label) {
                labels[code] = label;
            }
        });
        const node = {
            kind,
            id,
            children: (Array.isArray(rawNode.children) ? rawNode.children : [])
                .map(normalizeNavbarBuilderNode)
                .filter(Boolean),
        };
        if (Object.keys(labels).length) {
            node.labels = labels;
        }
        const url = String(rawNode.url || '').trim();
        if (url) {
            node.url = url;
        }
        if (kind === 'route') {
            node.url_name = String(rawNode.url_name || id).trim() || id;
        }
        return node;
    }

    function readNavbarBuilderConfig(rawConfig) {
        const config = rawConfig && typeof rawConfig === 'object' ? rawConfig : {};
        const hierarchy = config.hierarchy && typeof config.hierarchy === 'object' ? config.hierarchy : {};
        const rawRoot = config.root && typeof config.root === 'object' ? config.root : {};
        const rootMode = ['neutral', 'home', 'route'].includes(rawRoot.mode) ? rawRoot.mode : 'neutral';
        const rootUrlName = rootMode === 'route' ? String(rawRoot.url_name || '').trim() : '';
        return {
            enabled: Boolean(config.enabled),
            default_mode: config.default_mode === 'history' ? 'history' : 'hierarchy',
            allow_user_mode_override: config.allow_user_mode_override !== false,
            root: {
                mode: rootMode === 'route' && !rootUrlName ? 'neutral' : rootMode,
                url_name: rootMode === 'route' ? rootUrlName : '',
            },
            hierarchy: {
                nodes: (Array.isArray(hierarchy.nodes) ? hierarchy.nodes : [])
                    .map(normalizeNavbarBuilderNode)
                    .filter(Boolean),
            },
        };
    }

    function navbarHierarchyHasNodes(config) {
        return Boolean(config && config.hierarchy && Array.isArray(config.hierarchy.nodes) && config.hierarchy.nodes.length);
    }

    function sidebarLabelPayload(entry, langCode) {
        const label = String(entry && entry.label ? entry.label : '').trim();
        return label ? { [langCode]: label } : {};
    }

    function sidebarNodeId(prefix, entry, index) {
        return String(
            (entry && (entry.url_name || entry.id || entry.url)) || `${prefix}-${index}`
        ).trim();
    }

    function sidebarEntryToNavbarNode(entry, index, langCode) {
        if (!entry || typeof entry !== 'object') {
            return null;
        }
        if ((entry.kind || 'item') === 'group') {
            const children = (Array.isArray(entry.items) ? entry.items : [])
                .map((child, childIndex) => sidebarEntryToNavbarNode(child, childIndex, langCode))
                .filter(Boolean);
            if (!children.length) {
                return null;
            }
            const urlName = String(entry.url_name || '').trim();
            const node = {
                kind: urlName ? 'route' : 'manual',
                id: sidebarNodeId('sidebar-group', entry, index),
                children,
            };
            if (urlName) {
                node.url_name = urlName;
            }
            const url = String(entry.url || '').trim();
            if (url) {
                node.url = url;
            }
            const labels = sidebarLabelPayload(entry, langCode);
            if (Object.keys(labels).length) {
                node.labels = labels;
            }
            return node;
        }

        const urlName = String(entry.url_name || '').trim();
        const url = String(entry.url || '').trim();
        if (!urlName && !url) {
            return null;
        }
        const node = {
            kind: urlName ? 'route' : 'manual',
            id: sidebarNodeId('sidebar-item', entry, index),
            children: [],
        };
        if (urlName) {
            node.url_name = urlName;
        }
        if (url) {
            node.url = url;
        }
        const labels = sidebarLabelPayload(entry, langCode);
        if (Object.keys(labels).length) {
            node.labels = labels;
        }
        return node;
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
                is_form_page: Boolean(entry.is_form_page),
            }));
    }

    function buildCatalogLookup(catalog) {
        const lookup = new Map();
        (catalog || []).forEach((entry) => {
            if (!entry || typeof entry !== 'object') {
                return;
            }
            const id = String(entry.id || '').trim();
            const urlName = String(entry.url_name || '').trim();
            if (id) {
                lookup.set(id, entry);
            }
            if (urlName) {
                lookup.set(urlName, entry);
            }
        });
        return lookup;
    }

    function findCatalogEntry(entry, catalogLookup) {
        if (!entry || typeof entry !== 'object' || !catalogLookup) {
            return null;
        }
        const id = String(entry.id || '').trim();
        const urlName = String(entry.url_name || '').trim();
        return catalogLookup.get(id) || catalogLookup.get(urlName) || null;
    }

    function cloneEntry(entry) {
        return JSON.parse(JSON.stringify(entry));
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
        // Form pages are discovered like any other route, but a sidebar lists
        // places rather than actions — they stay out of the list until asked for.
        return state.catalog.filter(item => (
            !selectedIds.has(item.id)
            && (state.showSystemItems || !item.is_system)
            && (state.showFormPages || !item.is_form_page)
        ));
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

    function insertEntryIntoConfig(configEntries, entry, target) {
        if (target.type === 'root-container') {
            configEntries.push(entry);
            return;
        }

        if (target.type === 'group-container') {
            const groupLocation = findEntryLocation(configEntries, target.groupId, 'group');
            if (groupLocation && groupLocation.entry.kind === 'group') {
                groupLocation.entry.items.push(entry);
            } else {
                configEntries.push(entry);
            }
            return;
        }

        if (target.type === 'root-node') {
            const targetLocation = findEntryLocation(configEntries, target.targetId, target.targetKind);
            if (!targetLocation) {
                configEntries.push(entry);
            } else {
                const insertIndex = target.before ? targetLocation.index : targetLocation.index + 1;
                configEntries.splice(insertIndex, 0, entry);
            }
            return;
        }

        if (target.type === 'group-node') {
            const groupLocation = findEntryLocation(configEntries, target.parentGroupId, 'group');
            if (!groupLocation || groupLocation.entry.kind !== 'group') {
                configEntries.push(entry);
                return;
            }
            const targetLocation = findEntryLocation(groupLocation.entry.items, target.targetId, target.targetKind);
            if (!targetLocation) {
                groupLocation.entry.items.push(entry);
            } else {
                const insertIndex = target.before ? targetLocation.index : targetLocation.index + 1;
                groupLocation.entry.items.splice(insertIndex, 0, entry);
            }
        }
    }

    function topLevelItems(entries) {
        return (entries || []).filter(entry => entry.kind === 'item' && entry.url_name);
    }

    function availableItemDisplayLabel(item) {
        // Trust the server-resolved catalog label directly, exactly like the navbar
        // builder (renderRoutes uses entry.label as-is). The catalog label already
        // went through the full translation chain server-side. The previous logic
        // discarded a label that merely equalled its group label and fell back to a
        // hardcoded English name ("<Group> Dashboard" / humanized url) — which
        // wrongly Anglicised valid translations whose name matches the group (e.g.
        // an Arabic "product_list" or "workspace dashboard"). Only humanize the URL
        // as a last resort when the server gave us no usable label at all.
        const label = String(item && item.label ? item.label : '').trim();
        if (label) {
            return label;
        }
        const urlName = String(item && item.url_name ? item.url_name : item && item.id ? item.id : '').trim();
        const groupLabel = String(item && item.group_label ? item.group_label : '').trim();
        return humanizeKey(urlName) || groupLabel || t('sidebar_group_label', 'Item');
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

    function extractImportedSettings(payload) {
        if (!payload || typeof payload !== 'object') return null;
        if (payload.format === 'django-lux.system-settings' && payload.settings && typeof payload.settings === 'object') {
            return payload.settings;
        }
        return payload;
    }

    function frameworkDefaultLabels(entry, discovered) {
        const labels = new Set();
        const candidates = [
            entry && entry.id,
            entry && entry.url_name,
            discovered && discovered.label,
            discovered && discovered.group_label,
            discovered && discovered.id,
            discovered && discovered.url_name,
        ];

        candidates.forEach((candidate) => {
            const value = String(candidate || '').trim();
            if (value) {
                labels.add(value);
            }
        });

        const humanized = humanizeKey((entry && (entry.url_name || entry.id)) || (discovered && (discovered.url_name || discovered.id)) || '');
        if (humanized) {
            labels.add(humanized);
        }

        if (discovered) {
            const displayLabel = availableItemDisplayLabel(discovered);
            if (displayLabel) {
                labels.add(displayLabel);
            }
        }

        return labels;
    }

    function humanizeKey(value) {
        return String(value || '')
            .split(':')
            .pop()
            .replace(/[_-]+/g, ' ')
            .replace(/\b\w/g, (char) => char.toUpperCase())
            .trim();
    }

    // Per-language name overrides, normalised the way the navbar nodes and the
    // server-side sanitizer already do it: codes lower-cased, values trimmed,
    // empties dropped.
    function normalizeBuilderLabels(rawLabels) {
        const labels = {};
        Object.entries(rawLabels && typeof rawLabels === 'object' ? rawLabels : {}).forEach(([rawCode, rawLabel]) => {
            const code = normalizeLanguageCode(rawCode);
            const label = String(rawLabel || '').trim();
            if (code && label) {
                labels[code] = label;
            }
        });
        return labels;
    }

    function normalizeEntry(entry, catalogLookup, fallbackCatalogLookup) {
        if (!entry || typeof entry !== 'object') {
            return null;
        }
        // `labels` is what the reader typed into the builder and what the server
        // stores; dropping it here meant every reopen of the Sidebar step silently
        // discarded the overrides and saved them away again.
        const labels = normalizeBuilderLabels(entry.labels);
        if ((entry.kind || 'item') === 'group') {
            const items = Array.isArray(entry.items)
                ? entry.items.map(item => normalizeEntry(item, catalogLookup, fallbackCatalogLookup)).filter(Boolean)
                : [];
            const group = {
                kind: 'group',
                id: entry.id || `group-${Date.now()}`,
                label: resolveBuilderGroupLabel(entry, items, fallbackCatalogLookup),
                icon: entry.icon || 'bi-folder2-open',
                items,
            };
            if (Object.keys(labels).length) {
                group.labels = labels;
            }
            return group;
        }
        if (!entry.id && !entry.url_name) {
            return null;
        }
        const currentDiscovered = findCatalogEntry(entry, catalogLookup);
        const fallbackDiscovered = findCatalogEntry(entry, fallbackCatalogLookup);
        const item = {
            kind: 'item',
            id: entry.id || entry.url_name,
            url_name: entry.url_name || entry.id,
            label: resolveBuilderItemLabel(entry, currentDiscovered, fallbackDiscovered),
            icon: entry.icon || (currentDiscovered && currentDiscovered.icon) || 'bi-link-45deg',
            permissions: Array.isArray(entry.permissions) ? entry.permissions : ((currentDiscovered && currentDiscovered.permissions) || []),
            group_key: entry.group_key || (currentDiscovered && currentDiscovered.group_key) || '',
            group_label: entry.group_label || (currentDiscovered && currentDiscovered.group_label) || '',
        };
        if (Object.keys(labels).length) {
            item.labels = labels;
        }
        return item;
    }

    function normalizeSidebarConfig(config, catalogLookup, fallbackCatalogLookup) {
        if (!config || typeof config !== 'object') {
            return { home_url_name: null, entries: [] };
        }

        const entries = Array.isArray(config.entries) ? config.entries : [];
        return {
            enabled: config.enabled !== false,
            home_url_name: config.home_url_name || null,
            entries: entries.map(entry => normalizeEntry(entry, catalogLookup, fallbackCatalogLookup)).filter(Boolean),
            enable_reorder: config.enable_reorder !== false,
            show_toolbar: config.show_toolbar !== false,
            show_sections_manager: config.show_sections_manager !== false,
            show_icons: config.show_icons !== false,
            density: config.density || 'balanced',
            allow_user_density: config.allow_user_density !== false,
            collapse_mode: config.collapse_mode || 'icons',
            toggle_icon: config.toggle_icon || 'bi-list',
        };
    }

    function resolveBuilderGroupLabel(entry, items, fallbackCatalogLookup) {
        const savedLabel = String(entry && entry.label ? entry.label : '').trim();
        const localizedLabel = String(
            (items || []).find((item) => String(item && item.group_label ? item.group_label : '').trim())?.group_label || ''
        ).trim();
        const fallbackReference = findCatalogEntry(((entry && entry.items) || []).find((item) => item && (item.id || item.url_name)), fallbackCatalogLookup);
        const fallbackGroupLabel = String(fallbackReference && fallbackReference.group_label ? fallbackReference.group_label : '').trim();
        const defaultLabels = new Set([
            fallbackGroupLabel,
            t('sidebar_group_label', 'Group'),
            'Group',
        ]);

        if (!savedLabel || (localizedLabel && defaultLabels.has(savedLabel))) {
            return localizedLabel || savedLabel || t('sidebar_group_label', 'Group');
        }

        return savedLabel;
    }

    function resolveBuilderItemLabel(entry, currentDiscovered, fallbackDiscovered) {
        const savedLabel = String(entry && entry.label ? entry.label : '').trim();
        const localizedLabel = currentDiscovered ? availableItemDisplayLabel(currentDiscovered) : '';
        const defaultLabels = new Set([
            ...frameworkDefaultLabels(entry, currentDiscovered),
            ...frameworkDefaultLabels(entry, fallbackDiscovered),
        ]);

        if (!savedLabel || defaultLabels.has(savedLabel)) {
            return localizedLabel || savedLabel || String(entry && (entry.url_name || entry.id) ? (entry.url_name || entry.id) : '').trim();
        }

        return savedLabel;
    }

    root.DluxSetupModel = {
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
    };
})(typeof window !== 'undefined' ? window : globalThis);
