// Settings -> Ribbon -> Tab Strips.
//
// Each list is drawn the way its own page draws it — pills for a primary or a
// nested strip, a segmented control for an axis — so an operator recognises the
// page before reading a word. Reordering is dragging a tab; everything else
// happens in one inspector, the same shape the sidebar builder uses.
//
// Editing a page's pre-defined tabs lays an overlay over what the code declares.
// Admin-created strips are kept separately and can be added to any unlocked
// ribbon page.
(function () {
    const FIELD_NAME = 'ribbon_config';
    // The same list the sidebar builder's inspector draws from, exposed by
    // helpers/icon_picker. The grid is rendered here rather than through that
    // helper's field component: an inspector's picker is always open and is not
    // bound to a form field, which is exactly what the sidebar builder does.

    function parse(value, fallback) {
        try {
            const parsed = JSON.parse(value || '');
            return parsed && typeof parsed === 'object' ? parsed : fallback;
        } catch (error) {
            return fallback;
        }
    }

    function readDeclaredStrips(entry) {
        if (!entry || typeof entry !== 'object') return [];
        if (Array.isArray(entry.strips)) return entry.strips;
        return [];
    }

    function readExtraStrips(entry) {
        if (!entry || typeof entry !== 'object') return [];
        return Array.isArray(entry.extra_strips) ? entry.extra_strips : [];
    }

    function readCustomActions(entry) {
        if (!entry || typeof entry !== 'object') return null;
        const actions = entry.custom_actions;
        return actions && typeof actions === 'object'
            ? JSON.parse(JSON.stringify(actions))
            : null;
    }

    function init(root) {
        if (root.dataset.ribbonBuilderReady === '1') return;
        root.dataset.ribbonBuilderReady = '1';

        const catalog = parse(root.dataset.catalog, []);
        const destinations = parse(root.dataset.destinations, []);
        const strings = parse(root.dataset.strings, {});
        const languages = parse(root.dataset.languages, {});
        const stored = parse(root.dataset.config, {});
        const byKey = Object.fromEntries(catalog.map(m => [m.key, m]));
        const destinationsById = Object.fromEntries(destinations.map(d => [d.id, d]));
        const languageCodes = Object.keys(languages).length ? Object.keys(languages) : ['en'];
        function languageName(code) {
            const payload = languages[code];
            return (payload && (payload.name || payload.label)) || code;
        }
        const state = { showSystemItems: false };

        const declaredState = {};
        const extraState = {};
        const customActionState = {};
        // Administrator edits to buttons a view declared in code, keyed by
        // destination — the same overlay model the declared tab strips use.
        const actionOverlayState = {};
        let nextExtraId = 1;
        let nextActionId = 1;

        Object.keys(stored).forEach(function (modelKey) {
            readDeclaredStrips(stored[modelKey]).forEach(function (strip) {
                declaredEntryFor(modelKey, strip);
            });
            readExtraStrips(stored[modelKey]).forEach(function (strip) {
                extraState[modelKey] = extraState[modelKey] || [];
                extraState[modelKey].push(hydrateExtra(strip));
            });
            const overlays = stored[modelKey] && stored[modelKey].actions;
            if (overlays && typeof overlays === 'object') {
                actionOverlayState[modelKey] = {};
                Object.keys(overlays).forEach(function (key) {
                    const overlay = overlays[key];
                    if (!overlay || typeof overlay !== 'object') return;
                    actionOverlayState[modelKey][key] = {
                        enabled: overlay.enabled !== false,
                        labels: Object.assign({}, overlay.labels),
                        icon: String(overlay.icon || '')
                    };
                });
            }
            const customActions = readCustomActions(stored[modelKey]);
            if (customActions) {
                customActionState[modelKey] = {};
                Object.keys(customActions).forEach(function (hostKey) {
                    if (!Array.isArray(customActions[hostKey])) return;
                    customActionState[modelKey][hostKey] = customActions[hostKey].map(function (action) {
                        return hydrateAction(action);
                    });
                });
            }
        });

        function actionOverlayFor(modelKey, key) {
            actionOverlayState[modelKey] = actionOverlayState[modelKey] || {};
            if (!actionOverlayState[modelKey][key]) {
                actionOverlayState[modelKey][key] = { enabled: true, labels: {}, icon: '' };
            }
            return actionOverlayState[modelKey][key];
        }

        function actionOverlayDirty(overlay) {
            if (!overlay) return false;
            return overlay.enabled === false
                || Boolean(overlay.icon)
                || Object.keys(overlay.labels || {}).length > 0;
        }

        function dropActionOverlay(modelKey, key) {
            if (actionOverlayState[modelKey]) {
                delete actionOverlayState[modelKey][key];
                if (!Object.keys(actionOverlayState[modelKey]).length) {
                    delete actionOverlayState[modelKey];
                }
            }
        }

        function baseOverlay(data) {
            return {
                order: Array.isArray(data && data.order) ? data.order.slice() : [],
                labels: Object.assign({}, data && data.labels),
                icons: Object.assign({}, data && data.icons),
                hidden: Array.isArray(data && data.hidden) ? data.hidden.slice() : []
            };
        }

        function declaredEntryFor(modelKey, strip) {
            declaredState[modelKey] = declaredState[modelKey] || [];
            const index = Number.isInteger(strip && strip.index) ? strip.index : null;
            const param = strip && strip.param ? String(strip.param) : '';
            let entry = declaredState[modelKey].find(function (candidate) {
                return param && candidate.param === param;
            });
            if (!entry && index !== null) {
                entry = declaredState[modelKey].find(function (candidate) {
                    return candidate.index === index;
                });
            }
            if (!entry) {
                entry = Object.assign(baseOverlay(strip), {
                    param: param,
                    index: index,
                    enabled: !(strip && strip.enabled === false)
                });
                declaredState[modelKey].push(entry);
            }
            return entry;
        }

        function hydrateExtra(data) {
            return Object.assign(baseOverlay(data), {
                _id: nextExtraId++,
                param: (data && data.param) || 'tab',
                relation: (data && data.relation) || '',
                label: (data && data.label) || '',
                default: (data && data.default) || '',
                drop: Array.isArray(data && data.drop) ? data.drop.slice() : [],
                when: Array.isArray(data && data.when)
                    ? data.when.slice()
                    : ((data && data.when) || ''),
                sources: Array.isArray(data && data.sources) ? data.sources : []
            });
        }

        function actionLabels(data) {
            return Object.assign({}, data && data.labels);
        }

        // `firstLabel` always answers with something, which is right for a pill that
        // must read as *something* and wrong for asking "did the administrator
        // rename this?" — an overlay carrying only an icon would claim the name
        // "New button" and overwrite the developer's.
        function overrideLabel(labels) {
            for (const code of languageCodes) {
                if (labels && labels[code]) return labels[code];
            }
            return '';
        }

        function firstLabel(labels, fallback) {
            for (const code of languageCodes) {
                if (labels && labels[code]) return labels[code];
            }
            return fallback || t('new_button', 'New button');
        }

        function hydrateAction(data) {
            const destination = data && data.destination && typeof data.destination === 'object'
                ? JSON.parse(JSON.stringify(data.destination))
                : null;
            return {
                _id: nextActionId++,
                id: (data && (data.id || data.key)) || ('custom-' + Date.now() + '-' + nextActionId),
                label: (data && data.label) || '',
                labels: actionLabels(data),
                icon: (data && data.icon) || '',
                url: (data && data.url) || '',
                attrs: Object.assign({}, data && data.attrs),
                css_class: (data && data.css_class) || '',
                type: (data && data.type) || '',
                permission: (data && data.permission) || '',
                permissions: Array.isArray(data && data.permissions) ? data.permissions.slice() : [],
                destination: destination
            };
        }

        function serializeAction(action) {
            const out = { id: action.id };
            if (Object.keys(action.labels || {}).length) out.labels = action.labels;
            else if (action.label) out.label = action.label;
            if (action.icon) out.icon = action.icon;
            if (action.url) out.url = action.url;
            if (action.attrs && Object.keys(action.attrs).length) out.attrs = action.attrs;
            if (action.css_class) out.css_class = action.css_class;
            if (action.type) out.type = action.type;
            if (action.permission) out.permission = action.permission;
            if (action.permissions && action.permissions.length) out.permissions = action.permissions;
            if (action.destination) out.destination = action.destination;
            return out;
        }

        // The same identity the server uses: a button is its destination.
        function customActionDestinationKey(action) {
            const attrs = (action && action.attrs) || {};
            const candidates = [
                attrs['data-dynamic-modal'],
                attrs['data-url'],
                action && action.url
            ];
            for (const candidate of candidates) {
                const endpoint = String(candidate || '').trim();
                if (endpoint) return 'dest:' + endpoint;
            }
            return '';
        }

        function customActionsFor(modelKey) {
            const storageKey = modelStateKey(modelKey);
            return ((customActionState[storageKey] || {})[modelKey] || []);
        }

        function customActionById(modelKey, id) {
            return customActionsFor(modelKey).find(function (action) {
                return action._id === id;
            }) || null;
        }

        const refs = {
            models: root.querySelector('[data-ribbon-models]'),
            systemToggle: root.querySelector('[data-ribbon-system-toggle]'),
            inspectorShell: root.querySelector('[data-ribbon-inspector-shell]'),
            iconValue: root.querySelector('[data-ribbon-icon-value]'),
            iconPicker: root.querySelector('[data-dlux-icon-picker][data-icon-field="ribbon_builder_entry_icon"]'),
            iconPickerHolder: root.querySelector('[data-ribbon-icon-picker-holder]')
        };
        const templates = {
            model: document.querySelector('[data-ribbon-model-template]'),
            stripRow: document.querySelector('[data-ribbon-strip-row-template]'),
            pill: document.querySelector('[data-ribbon-pill-template]'),
            action: document.querySelector('[data-ribbon-action-template]')
        };
        if (!refs.models || !templates.model || !templates.pill) return;

        let selected = null;   // {type, modelKey, origin, key, tabKey|actionId}
        let dragging = null;   // {modelKey, origin, key, tabKey}

        function t(key, fallback) {
            return strings[key] || fallback;
        }

        function hiddenField() {
            const form = root.closest('form');
            return form ? form.querySelector('[name="' + FIELD_NAME + '"]') : null;
        }

        function hostFor(hostKey) {
            return byKey[hostKey] || null;
        }

        function modelStateKey(hostKey) {
            const host = hostFor(hostKey);
            return (host && (host.model_key || host.key)) || hostKey;
        }

        function hostVisible(hostKey) {
            const host = hostFor(hostKey);
            return Boolean(host && (state.showSystemItems || !host.is_system));
        }

        function visibleCatalog() {
            return catalog.filter(function (host) {
                return state.showSystemItems || !host.is_system;
            });
        }

        function isEmpty(overlay) {
            return !overlay.order.length
                && !Object.keys(overlay.labels).length
                && !Object.keys(overlay.icons).length
                && !overlay.hidden.length;
        }

        function declaredDirty(entry) {
            return entry.enabled === false || !isEmpty(entry);
        }

        function stripKey(strip) {
            if (strip.origin === 'extra') return String(strip._id);
            if (Number.isInteger(strip.index)) return 'index:' + strip.index;
            return 'param:' + (strip.param || '');
        }

        function overlayForStrip(modelKey, strip) {
            if (strip.origin === 'extra') return strip;
            return declaredEntryFor(modelStateKey(modelKey), strip);
        }

        function relationLabel(value) {
            const relation = value || 'primary';
            return t('relation_' + relation, relation);
        }

        function removeDeclaredEntry(modelKey, entry) {
            const storageKey = modelStateKey(modelKey);
            declaredState[storageKey] = (declaredState[storageKey] || []).filter(function (item) {
                return item !== entry;
            });
            if (!declaredState[storageKey].length) delete declaredState[storageKey];
        }

        // Only what an operator actually changed is written; an untouched page
        // stores nothing and keeps following the code.
        function commit() {
            const field = hiddenField();
            if (!field) return;
            const out = {};
            const modelKeys = new Set(
                Object.keys(declaredState).concat(
                    Object.keys(extraState),
                    Object.keys(customActionState),
                    Object.keys(actionOverlayState)
                )
            );
            modelKeys.forEach(function (modelKey) {
                const modelEntry = {};
                const declared = (declaredState[modelKey] || [])
                    .filter(declaredDirty)
                    .map(function (entry) {
                        const strip = {};
                        if (entry.param) strip.param = entry.param;
                        if (Number.isInteger(entry.index)) strip.index = entry.index;
                        if (entry.enabled === false) strip.enabled = false;
                        if (entry.order.length) strip.order = entry.order;
                        if (Object.keys(entry.labels).length) strip.labels = entry.labels;
                        if (Object.keys(entry.icons).length) strip.icons = entry.icons;
                        if (entry.hidden.length) strip.hidden = entry.hidden;
                        return strip;
                    });
                const extra = (extraState[modelKey] || [])
                    .filter(function (strip) { return Array.isArray(strip.sources) && strip.sources.length; })
                    .map(function (entry) {
                        const strip = { param: entry.param || 'tab', sources: entry.sources };
                        if (entry.relation) strip.relation = entry.relation;
                        if (entry.label) strip.label = entry.label;
                        if (entry.default) strip.default = entry.default;
                        if (entry.drop.length) strip.drop = entry.drop;
                        if (entry.when && (!Array.isArray(entry.when) || entry.when.length)) {
                            strip.when = entry.when;
                        }
                        if (entry.order.length) strip.order = entry.order;
                        if (Object.keys(entry.labels).length) strip.labels = entry.labels;
                        if (Object.keys(entry.icons).length) strip.icons = entry.icons;
                        if (entry.hidden.length) strip.hidden = entry.hidden;
                        return strip;
                });
                if (declared.length) modelEntry.strips = declared;
                if (extra.length) modelEntry.extra_strips = extra;
                const customGroups = customActionState[modelKey] || {};
                const customOut = {};
                Object.keys(customGroups).forEach(function (hostKey) {
                    const actions = (customGroups[hostKey] || []).map(serializeAction);
                    if (actions.length) customOut[hostKey] = actions;
                });
                if (Object.keys(customOut).length) modelEntry.custom_actions = customOut;
                const overlays = {};
                Object.keys(actionOverlayState[modelKey] || {}).forEach(function (key) {
                    const overlay = actionOverlayState[modelKey][key];
                    if (!actionOverlayDirty(overlay)) return;
                    const out = {};
                    if (overlay.enabled === false) out.enabled = false;
                    if (Object.keys(overlay.labels || {}).length) out.labels = overlay.labels;
                    if (overlay.icon) out.icon = overlay.icon;
                    overlays[key] = out;
                });
                if (Object.keys(overlays).length) modelEntry.actions = overlays;
                if (declared.length || extra.length || Object.keys(customOut).length
                    || Object.keys(overlays).length) {
                    out[modelKey] = modelEntry;
                }
            });
            field.value = JSON.stringify(out);
        }

        // ---- reading a strip the way the page will render it ---------------

        function stripsOf(modelKey) {
            const model = hostFor(modelKey);
            const storageKey = modelStateKey(modelKey);
            const out = [];
            ((model && model.strips) || []).forEach(function (strip) {
                out.push(Object.assign({}, strip, { origin: 'declared' }));
            });
            (extraState[storageKey] || []).forEach(function (strip) {
                out.push(Object.assign(strip, {
                    origin: 'extra',
                    tabs: tabsFor(modelKey, strip.param, strip.sources)
                }));
            });
            return out;
        }

        // ---- tabs for a strip that has not been saved yet -------------------
        //
        // Resolved by the server, because a strip over a relation is one tab per
        // row and the browser cannot know those. Cached by what actually decides
        // the answer, so re-rendering after a drag does not re-ask.

        const tabCache = {};

        function tabsFor(modelKey, param, sources) {
            const storageKey = modelStateKey(modelKey);
            const key = storageKey + '|' + param + '|' + JSON.stringify(sources);
            const hit = tabCache[key];
            if (hit) return hit.tabs;
            tabCache[key] = { tabs: [], pending: true };
            fetch(root.dataset.previewUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken(),
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ model: storageKey, param: param, sources: sources })
            })
                .then(response => response.ok ? response.json() : { tabs: [] })
                .catch(() => ({ tabs: [] }))
                .then(function (payload) {
                    tabCache[key] = { tabs: payload.tabs || [], pending: false };
                    renderAll();
                });
            return [];
        }

        function pendingTabs(modelKey, param, sources) {
            const entry = tabCache[modelStateKey(modelKey) + '|' + param + '|' + JSON.stringify(sources)];
            return !entry || entry.pending;
        }

        function csrfToken() {
            const input = root.closest('form') &&
                root.closest('form').querySelector('[name="csrfmiddlewaretoken"]');
            return input ? input.value : '';
        }

        function orderedTabs(modelKey, strip) {
            const overlay = overlayForStrip(modelKey, strip);
            const tabs = (strip.tabs || []).slice();
            if (!overlay.order.length) return tabs;
            const rank = {};
            overlay.order.forEach(function (key, index) { rank[key] = index; });
            return tabs
                .map(function (tab, index) { return { tab: tab, index: index }; })
                .sort(function (a, b) {
                    const ra = rank[a.tab.key] === undefined ? overlay.order.length : rank[a.tab.key];
                    const rb = rank[b.tab.key] === undefined ? overlay.order.length : rank[b.tab.key];
                    return ra - rb || a.index - b.index;
                })
                .map(function (pair) { return pair.tab; });
        }

        // ---- the previews ---------------------------------------------------

        function renderPill(modelKey, strip, tab, host, locked, disabled) {
            const overlay = overlayForStrip(modelKey, strip);
            const node = templates.pill.content.firstElementChild.cloneNode(true);
            const key = stripKey(strip);
            const icon = overlay.icons[tab.key] || tab.icon;
            const iconEl = node.querySelector('[data-pill-icon]');
            if (icon) {
                iconEl.className = icon.indexOf('bi-') === 0 ? 'bi ' + icon : icon;
                iconEl.hidden = false;
            }
            const renamed = overlay.labels[tab.key];
            const shownLabel = (renamed && typeof renamed === 'object')
                ? (renamed[languageCodes[0]] || Object.values(renamed).find(Boolean) || tab.label)
                : (renamed || tab.label);
            node.querySelector('[data-pill-label]').textContent = shownLabel;

            if (strip.relation === 'axis') node.classList.add('is-segment');
            else if (strip.relation === 'child') node.classList.add('is-child');
            if (overlay.hidden.indexOf(tab.key) !== -1) node.classList.add('is-hidden-tab');
            if (selected && selected.modelKey === modelKey
                && selected.origin === strip.origin && selected.key === key
                && selected.tabKey === tab.key) {
                node.classList.add('is-active');
            }

            if (disabled) {
                node.draggable = false;
                host.appendChild(node);
                return;
            }

            node.addEventListener('click', function () {
                selected = {
                    type: 'tab',
                    modelKey: modelKey,
                    origin: strip.origin,
                    key: key,
                    tabKey: tab.key,
                    locked: locked
                };
                renderAll();
            });

            node.addEventListener('dragstart', function () {
                dragging = { modelKey: modelKey, origin: strip.origin, key: key, tabKey: tab.key };
                node.classList.add('is-dragging');
            });
            node.addEventListener('dragend', function () {
                dragging = null;
                node.classList.remove('is-dragging');
            });
            node.addEventListener('dragover', function (event) {
                if (!dragging) return;
                if (dragging.modelKey !== modelKey
                    || dragging.origin !== strip.origin || dragging.key !== key) return;
                event.preventDefault();
                node.classList.add('is-drop-target');
            });
            node.addEventListener('dragleave', function () { node.classList.remove('is-drop-target'); });
            node.addEventListener('drop', function (event) {
                node.classList.remove('is-drop-target');
                if (!dragging) return;
                if (dragging.modelKey !== modelKey
                    || dragging.origin !== strip.origin || dragging.key !== key) return;
                event.preventDefault();
                const keys = orderedTabs(modelKey, strip).map(function (one) { return one.key; });
                const from = keys.indexOf(dragging.tabKey);
                const to = keys.indexOf(tab.key);
                if (from === -1 || to === -1 || from === to) return;
                keys.splice(to, 0, keys.splice(from, 1)[0]);
                overlay.order = keys;
                commit();
                renderAll();
            });

            host.appendChild(node);
        }

        function renderStripRow(modelKey, strip, host, locked) {
            const node = templates.stripRow.content.firstElementChild.cloneNode(true);
            const overlay = overlayForStrip(modelKey, strip);
            const disabled = strip.origin === 'declared' && overlay.enabled === false;
            const caption = strip.label || relationLabel(strip.relation);
            node.querySelector('[data-strip-kind]').textContent = caption;
            node.dataset.relation = strip.relation;
            if (disabled) node.classList.add('dlux-ribbon-builder__strip--off');
            const pills = node.querySelector('[data-strip-pills]');
            if (strip.relation === 'axis') pills.classList.add('is-segmented');
            orderedTabs(modelKey, strip).forEach(function (tab) {
                renderPill(modelKey, strip, tab, pills, locked, disabled);
            });
            if (!strip.tabs.length) {
                const note = document.createElement('span');
                note.className = 'text-muted small';
                note.textContent = strip.sources && pendingTabs(modelKey, strip.param, strip.sources)
                    ? t('drawing_note', 'Drawing…')
                    : t('drawn_note', 'This split produces no tabs on the current data.');
                pills.appendChild(note);
            }
            // A strip with no tabs has no pill to select, and Remove/Restore now live
            // in the inspector — so the caption itself selects the strip, or the
            // strip could never be reached again.
            const kind = node.querySelector('[data-strip-kind]');
            if (kind) {
                if (disabled) {
                    kind.classList.add('is-off');
                    kind.title = t('removed_strip_hint', 'Removed — select to restore it.');
                    const flag = document.createElement('span');
                    flag.className = 'dlux-ribbon-builder__removed-flag';
                    flag.textContent = t('removed_strip', 'removed');
                    kind.appendChild(flag);
                }
                if (selected && selected.type === 'strip' && selected.modelKey === modelKey
                    && selected.origin === strip.origin && selected.key === stripKey(strip)) {
                    kind.classList.add('is-active');
                }
                kind.addEventListener('click', function () {
                    selected = {
                        type: 'strip',
                        modelKey: modelKey,
                        origin: strip.origin,
                        key: stripKey(strip),
                        locked: locked
                    };
                    renderAll();
                });
            }

            const picker = node.querySelector('[data-strip-field]');
            if (picker && strip.origin === 'extra') {
                picker.hidden = false;
                fillFieldOptions(picker, hostFor(modelKey),
                                 splitFieldOf(strip.sources), true);
                picker.addEventListener('change', function () {
                    const extra = extraById(modelKey, strip._id);
                    if (!extra) return;
                    extra.sources = sourcesFor(picker.value, hostFor(modelKey));
                    extra.order = [];
                    extra.labels = {};
                    extra.icons = {};
                    extra.hidden = [];
                    if (selected && selected.modelKey === modelKey
                        && selected.origin === 'extra' && selected.key === stripKey(strip)) selected = null;
                    commit();
                    renderAll();
                });
            }
            const relation = node.querySelector('[data-strip-relation]');
            if (relation && strip.origin === 'extra') {
                relation.hidden = false;
                fillRelationOptions(relation, strip.relation || '');
                relation.addEventListener('change', function () {
                    const extra = extraById(modelKey, strip._id);
                    if (!extra) return;
                    extra.relation = relation.value;
                    commit();
                    renderAll();
                });
            }
            host.appendChild(node);
        }

        function renderActionPill(modelKey, action, host, locked) {
            if (!templates.action || !host) return;
            const node = templates.action.content.firstElementChild.cloneNode(true);
            // A code-declared button carries its destination as `key`; that is what
            // an administrator's edits hang off, so one that has none (raw html)
            // stays as fixed as it ever was.
            const overlayKey = locked ? String(action.key || '') : '';
            const overlay = overlayKey ? (actionOverlayState[modelKey] || {})[overlayKey] : null;
            const disabled = Boolean(overlay && overlay.enabled === false);
            const label = (overlay && overrideLabel(overlay.labels)) || action.label
                || overrideLabel(action.labels);
            const icon = (overlay && overlay.icon) || action.icon || '';
            node.querySelector('[data-action-label]').textContent = label || t('new_button', 'New button');
            const iconNode = node.querySelector('[data-action-icon]');
            if (iconNode && icon) {
                iconNode.hidden = false;
                iconNode.className = icon.indexOf('bi-') === 0 ? 'bi ' + icon : icon;
            }
            if (disabled) node.classList.add('is-hidden-tab');

            if (locked && !overlayKey) {
                node.disabled = true;
                node.classList.add('is-locked');
                node.title = t('action_locked', 'Defined in code');
                host.appendChild(node);
                return;
            }

            const type = locked ? 'declared-action' : 'action';
            const matches = locked
                ? (selected && selected.type === 'declared-action'
                    && selected.modelKey === modelKey && selected.key === overlayKey)
                : (selected && selected.type === 'action'
                    && selected.modelKey === modelKey && selected.actionId === action._id);
            if (matches) node.classList.add('is-active');
            node.addEventListener('click', function () {
                selected = locked
                    ? { type: type, modelKey: modelKey, key: overlayKey, label: action.label,
                        labels: action.labels, icon: action.icon }
                    : { type: type, modelKey: modelKey, actionId: action._id };
                renderAll();
            });
            host.appendChild(node);
        }

        function setupAddStripControls(model, node) {
            const controls = node.querySelector('[data-model-add-strip]');
            if (!controls) return;
            const field = controls.querySelector('[data-ribbon-new-field]');
            const relation = controls.querySelector('[data-ribbon-new-relation]');
            const param = controls.querySelector('[data-ribbon-new-param]');
            const add = controls.querySelector('[data-ribbon-add-strip]');
            const unavailable = model.locked || !model.fields.length;
            controls.hidden = unavailable;
            if (unavailable) return;
            fillFieldOptions(field, model, '');
            fillRelationOptions(relation, hasAnyStrip(model.key) ? 'axis' : '');
            if (add) {
                add.addEventListener('click', function () {
                    const fieldName = field ? field.value : '';
                    if (!fieldName) return;
                    const storageKey = modelStateKey(model.key);
                    extraState[storageKey] = extraState[storageKey] || [];
                    extraState[storageKey].push(hydrateExtra({
                        param: ((param && param.value) || '').trim() || fieldName,
                        relation: relation ? relation.value : '',
                        sources: sourcesFor(fieldName, model)
                    }));
                    if (param) param.value = '';
                    commit();
                    renderAll();
                });
            }
        }

        function addCustomAction(model) {
            const destination = availableDestinations()[0];
            if (!destination) return;
            const storageKey = modelStateKey(model.key);
            customActionState[storageKey] = customActionState[storageKey] || {};
            customActionState[storageKey][model.key] = customActionState[storageKey][model.key] || [];
            const action = hydrateAction({
                id: 'custom-' + Date.now() + '-' + nextActionId,
                labels: { [languageCodes[0]]: destination.label },
                icon: destination.icon || ''
            });
            applyDestination(action, destination);
            customActionState[storageKey][model.key].push(action);
            selected = { type: 'action', modelKey: model.key, actionId: action._id };
            commit();
            renderAll();
        }

        function renderModels() {
            refs.models.innerHTML = '';
            let rendered = 0;
            visibleCatalog().forEach(function (model) {
                const strips = stripsOf(model.key);
                const node = templates.model.content.firstElementChild.cloneNode(true);
                node.querySelector('[data-model-label]').textContent = model.label;
                const keyNode = node.querySelector('[data-model-key]');
                keyNode.textContent = model.route_name || model.key;
                if (model.model_key) keyNode.title = model.model_key;

                const badge = node.querySelector('[data-model-badge]');
                if (model.locked) {
                    badge.hidden = false;
                    badge.textContent = t('locked', 'fixed in code');
                    badge.title = t('locked_hint', '');
                }

                const actionHost = node.querySelector('[data-model-actions]');
                const actionSection = node.querySelector('[data-actions-section]');
                const devActions = model.actions || [];
                const customActions = customActionsFor(model.key);
                // Mirror the runtime: one button per destination, code before
                // configuration. Showing a duplicate here that the page will drop
                // would be teaching the wrong thing about what was saved.
                const seenDestinations = new Set();
                function withoutDuplicates(action, key) {
                    if (!key) return true;
                    if (seenDestinations.has(key)) return false;
                    seenDestinations.add(key);
                    return true;
                }
                devActions.forEach(function (action) {
                    if (!withoutDuplicates(action, String(action.key || ''))) return;
                    renderActionPill(model.key, action, actionHost, true);
                });
                customActions.forEach(function (action) {
                    if (!withoutDuplicates(action, customActionDestinationKey(action))) return;
                    renderActionPill(model.key, action, actionHost, false);
                });
                if (actionSection) actionSection.hidden = !(devActions.length || customActions.length);
                const addAction = node.querySelector('[data-model-add-action]');
                if (addAction) {
                    addAction.disabled = availableDestinations().length === 0;
                    addAction.addEventListener('click', function () { addCustomAction(model); });
                }

                const declared = strips.filter(function (strip) { return strip.origin === 'declared'; });
                const extra = strips.filter(function (strip) { return strip.origin === 'extra'; });
                const declaredSection = node.querySelector('[data-declared-section]');
                const extraSection = node.querySelector('[data-extra-section]');
                const declaredHost = node.querySelector('[data-model-declared-strips]');
                const extraHost = node.querySelector('[data-model-extra-strips]');
                const empty = node.querySelector('[data-model-empty]');
                if (declaredSection) declaredSection.hidden = !declared.length;
                if (extraSection) extraSection.hidden = !extra.length;
                if (empty) empty.hidden = Boolean(declared.length || extra.length);
                declared.forEach(function (strip) {
                    renderStripRow(model.key, strip, declaredHost || extraHost, model.locked);
                });
                extra.forEach(function (strip) {
                    renderStripRow(model.key, strip, extraHost || declaredHost, model.locked);
                });
                setupAddStripControls(model, node);
                refs.models.appendChild(node);
                rendered += 1;
            });
            if (!rendered) {
                const empty = document.createElement('p');
                empty.className = 'text-muted small mb-0';
                empty.textContent = t('no_hosts', 'No ribbon pages match these settings.');
                refs.models.appendChild(empty);
            }
        }

        // ---- the inspector --------------------------------------------------

        function selectedTab() {
            if (!selected || selected.type !== 'tab') return null;
            if (!hostVisible(selected.modelKey)) return null;
            const strips = stripsOf(selected.modelKey);
            for (const strip of strips) {
                if (strip.origin !== selected.origin || stripKey(strip) !== selected.key) continue;
                for (const tab of (strip.tabs || [])) {
                    if (tab.key === selected.tabKey) {
                        return { strip: strip, tab: tab, overlay: overlayForStrip(selected.modelKey, strip) };
                    }
                }
            }
            return null;
        }

        function selectedDeclaredAction() {
            if (!selected || selected.type !== 'declared-action') return null;
            if (!hostVisible(selected.modelKey)) return null;
            const host = hostFor(selected.modelKey);
            const action = ((host && host.actions) || []).find(function (candidate) {
                return String(candidate.key || '') === selected.key;
            });
            if (!action) return null;
            return { action: action, overlay: actionOverlayFor(selected.modelKey, selected.key) };
        }

        function selectedAction() {
            if (!selected || selected.type !== 'action') return null;
            if (!hostVisible(selected.modelKey)) return null;
            const action = customActionById(selected.modelKey, selected.actionId);
            return action ? { action: action } : null;
        }

        function selectedStrip() {
            if (!selected || (selected.type !== 'strip' && selected.type !== 'tab')) return null;
            if (!hostVisible(selected.modelKey)) return null;
            for (const strip of stripsOf(selected.modelKey)) {
                if (strip.origin === selected.origin && stripKey(strip) === selected.key) {
                    return { strip: strip, overlay: overlayForStrip(selected.modelKey, strip) };
                }
            }
            return null;
        }

        // Remove and Restore act on the strip that owns the entry being inspected —
        // a declared strip is switched off and can be restored, an extra strip is
        // dropped outright.
        function removeStripOf(found) {
            if (!found) return;
            const modelKey = selected.modelKey;
            if (found.strip.origin === 'declared') {
                const overlay = found.overlay;
                overlay.enabled = false;
                overlay.order = [];
                overlay.labels = {};
                overlay.icons = {};
                overlay.hidden = [];
                // Stay on the strip rather than clearing the selection. Its tabs are
                // inert once it is off, so a cleared selection leaves Restore with
                // nothing to reach it by; keeping it selected puts the undo exactly
                // where the action was.
                selected = {
                    type: 'strip',
                    modelKey: modelKey,
                    origin: found.strip.origin,
                    key: stripKey(found.strip),
                    locked: selected.locked
                };
            } else {
                const storageKey = modelStateKey(modelKey);
                extraState[storageKey] = (extraState[storageKey] || []).filter(function (entry) {
                    return entry._id !== found.strip._id;
                });
                if (!extraState[storageKey].length) delete extraState[storageKey];
                // An extra strip is gone for good; there is nothing left to select.
                selected = null;
            }
            commit();
            renderAll();
        }

        function restoreStripOf(found) {
            if (!found || found.strip.origin !== 'declared') return;
            removeDeclaredEntry(selected.modelKey, found.overlay);
            selected = null;
            commit();
            renderAll();
        }

        function stripIsOff(found) {
            return Boolean(found && found.strip.origin === 'declared' && found.overlay.enabled === false);
        }

        // The ribbon has no builder-level toolbar to hang per-entry actions off, so
        // the actions ride inside the inspector panel above the fields.
        function stripActions(found) {
            if (!found) return [];
            const locked = Boolean(selected && selected.locked);
            const actions = [];
            if (found.strip.origin === 'declared') {
                actions.push({
                    id: 'restore-strip',
                    label: t('restore_strip', 'Restore'),
                    icon: 'bi bi-arrow-counterclockwise',
                    disabled: !declaredDirty(found.overlay),
                    onClick: function () { restoreStripOf(found); },
                });
            }
            actions.push({
                id: 'remove-strip',
                label: t('remove_strip', 'Remove'),
                icon: 'bi bi-trash3',
                variant: 'outline-danger',
                disabled: locked || stripIsOff(found),
                title: locked ? t('locked_hint', '') : '',
                onClick: function () { removeStripOf(found); },
            });
            return actions;
        }

        // The shared Dlux icon picker, borrowed the way the Sidebar builder borrows
        // it: server-rendered once into a hidden holder, moved into the inspector's
        // custom field, handed back on the next render. It builds its ~600-button
        // grid only while open, where the builder's own always-open grid rebuilt it
        // on every single inspector render.
        let iconTarget = null;

        function setIconPickerValue(icon) {
            // Empty stays empty: a tab with no override keeps whatever icon the page
            // gives it, and clearing the box is how an override is dropped.
            const value = String(icon || '').trim();
            if (refs.iconValue) refs.iconValue.value = value;
            const input = refs.iconPicker && refs.iconPicker.querySelector('[data-icon-input]');
            const preview = refs.iconPicker && refs.iconPicker.querySelector('[data-icon-preview]');
            if (input) input.value = value;
            if (preview) {
                preview.className = 'bi ' + (value || 'bi-tag');
                preview.classList.toggle('dlux-icon-picker-preview--empty', !value);
            }
        }

        if (refs.iconValue) {
            refs.iconValue.addEventListener('input', function () {
                if (!iconTarget) return;
                iconTarget(String(refs.iconValue.value || '').trim());
            });
        }

        function iconField(id, active, onChange) {
            return {
                id: id,
                type: 'custom',
                render: function () {
                    if (!refs.iconPicker) return null;
                    iconTarget = onChange;
                    setIconPickerValue(active);
                    return {
                        node: refs.iconPicker,
                        cleanup: function () {
                            iconTarget = null;
                            if (refs.iconPickerHolder
                                && refs.iconPicker.parentNode !== refs.iconPickerHolder) {
                                refs.iconPickerHolder.appendChild(refs.iconPicker);
                            }
                        },
                    };
                },
            };
        }

        function labelFields(labels, fallback, onChange) {
            let current = Object.assign({}, labels);
            return languageCodes.map(function (code) {
                return {
                    id: 'label-' + code,
                    type: 'text',
                    label: languageName(code) + ' (' + code + ')',
                    value: current[code] || '',
                    placeholder: fallback || '',
                    commitOn: 'input',
                    onInput: function (context) {
                        const next = Object.assign({}, current);
                        const value = String(context.value || '').trim();
                        if (value) next[code] = value;
                        else delete next[code];
                        current = next;
                        onChange(next);
                    },
                };
            });
        }

        function tabFields(found) {
            const overlay = found.overlay;
            const stored = overlay.labels[found.tab.key];
            const labels = (stored && typeof stored === 'object') ? Object.assign({}, stored) : {};
            if (stored && typeof stored === 'string') {
                languageCodes.forEach(function (code) { labels[code] = stored; });
            }
            const icon = overlay.icons[found.tab.key] || found.tab.icon || '';
            return labelFields(labels, found.tab.label, function (next) {
                if (Object.keys(next).length) overlay.labels[found.tab.key] = next;
                else delete overlay.labels[found.tab.key];
            }).concat([
                iconField('icon', icon, function (value) {
                    if (value) overlay.icons[found.tab.key] = value;
                    else delete overlay.icons[found.tab.key];
                    commit();
                }),
            ]);
        }

        function actionFields(action) {
            return labelFields(action.labels, action.label, function (next) {
                action.labels = next;
                action.label = '';
            }).concat([
                iconField('icon', action.icon || '', function (value) {
                    action.icon = value;
                    commit();
                }),
                {
                    id: 'destination',
                    type: 'select',
                    label: t('destination', 'Destination'),
                    value: (destinationForAction(action) || {}).id || '',
                    disabled: availableDestinations().length === 0,
                    options: availableDestinations().map(function (destination) {
                        // A dlux page and a project page can read alike — "Reports",
                        // "Activity Log" — so say which is which.
                        const scope = destination.is_system
                            ? t('system_destination', 'System') + ' \u00b7 '
                            : '';
                        return {
                            value: destination.id,
                            label: scope + destination.label + ' \u00b7 ' + destination.kind,
                        };
                    }),
                    onChange: function (context) {
                        const destination = destinationsById[context.value];
                        if (!destination) return null;
                        applyDestination(action, destination);
                        if (!Object.keys(action.labels).length && !action.label) {
                            action.labels[languageCodes[0]] = destination.label;
                        }
                        commit();
                        renderAll();
                        return null;
                    },
                },
            ]);
        }

        function removeAction(action) {
            const storageKey = modelStateKey(selected.modelKey);
            const groups = customActionState[storageKey] || {};
            groups[selected.modelKey] = (groups[selected.modelKey] || []).filter(function (entry) {
                return entry._id !== action._id;
            });
            if (!groups[selected.modelKey].length) delete groups[selected.modelKey];
            if (!Object.keys(groups).length) delete customActionState[storageKey];
            selected = null;
            commit();
            renderAll();
        }

        const ribbonInspectorShell = window.DluxInspectorShell && refs.inspectorShell
            ? window.DluxInspectorShell.create(refs.inspectorShell, {
                adapter: {
                    getActions: function () {
                        if (!selected) return [];
                        if (selected.type === 'declared-action') {
                            const found = selectedDeclaredAction();
                            if (!found) return [];
                            const overlay = found.overlay;
                            return [
                                {
                                    id: 'restore-action',
                                    label: t('restore_strip', 'Restore'),
                                    icon: 'bi bi-arrow-counterclockwise',
                                    disabled: !actionOverlayDirty(overlay),
                                    onClick: function () {
                                        dropActionOverlay(selected.modelKey, selected.key);
                                        selected = null;
                                        commit();
                                        renderAll();
                                        return null;
                                    },
                                },
                                {
                                    id: 'remove-action',
                                    label: t('remove_button', 'Remove button'),
                                    icon: 'bi bi-trash3',
                                    variant: 'outline-danger',
                                    disabled: overlay.enabled === false,
                                    onClick: function () {
                                        overlay.enabled = false;
                                        commit();
                                        renderAll();
                                        return null;
                                    },
                                },
                            ];
                        }
                        if (selected.type === 'action') {
                            const found = selectedAction();
                            if (!found) return [];
                            return [{
                                id: 'remove-action',
                                label: t('remove_button', 'Remove button'),
                                icon: 'bi bi-trash3',
                                variant: 'outline-danger',
                                onClick: function () { removeAction(found.action); },
                            }];
                        }
                        const found = selectedStrip();
                        const actions = stripActions(found);
                        if (selected.type === 'tab') {
                            const tab = selectedTab();
                            if (tab) {
                                actions.push({
                                    id: 'tab-shown',
                                    type: 'toggle',
                                    label: t('enabled', 'Shown'),
                                    checked: tab.overlay.hidden.indexOf(tab.tab.key) === -1,
                                    disabled: Boolean(selected.locked),
                                    title: selected.locked ? t('locked_hint', '') : '',
                                    onChange: function (context) {
                                        const at = tab.overlay.hidden.indexOf(tab.tab.key);
                                        if (context.value && at !== -1) tab.overlay.hidden.splice(at, 1);
                                        else if (!context.value && at === -1) tab.overlay.hidden.push(tab.tab.key);
                                        commit();
                                        renderAll();
                                        return null;
                                    },
                                });
                            }
                        }
                        return actions;
                    },
                    getTitle: function () {
                        if (!selected) return '';
                        if (selected.type === 'declared-action') {
                            const found = selectedDeclaredAction();
                            if (!found) return '';
                            return overrideLabel(found.overlay.labels)
                                || found.action.label
                                || overrideLabel(found.action.labels);
                        }
                        if (selected.type === 'action') {
                            const found = selectedAction();
                            return found ? firstLabel(found.action.labels, found.action.label) : '';
                        }
                        if (selected.type === 'tab') {
                            const found = selectedTab();
                            return found ? found.tab.label : '';
                        }
                        const found = selectedStrip();
                        return found ? (found.strip.label || relationLabel(found.strip.relation)) : '';
                    },
                    getBadge: function () {
                        if (!selected) return '';
                        if (selected.type === 'declared-action') {
                            return t('action_locked', 'Defined in code');
                        }
                        if (selected.type === 'action') {
                            const found = selectedAction();
                            return found ? found.action.id : '';
                        }
                        if (selected.type === 'tab') {
                            const found = selectedTab();
                            return found ? (found.tab.key || '(all)') : '';
                        }
                        const found = selectedStrip();
                        return found ? (found.strip.param || found.strip.relation || '') : '';
                    },
                    getFields: function () {
                        if (!selected) return [];
                        if (selected.type === 'declared-action') {
                            const found = selectedDeclaredAction();
                            if (!found) return [];
                            // Rendered markup carries its own labels and glyphs; there
                            // is nothing here to rename. It can still be removed.
                            if (found.action.kind === 'html') return [];
                            const overlay = found.overlay;
                            const fallback = found.action.label || firstLabel(found.action.labels, '');
                            return labelFields(overlay.labels, fallback, function (next) {
                                overlay.labels = next;
                                renderModels();
                            }).concat([
                                iconField('icon', overlay.icon || found.action.icon || '', function (value) {
                                    overlay.icon = value;
                                    commit();
                                    renderAll();
                                }),
                            ]);
                        }
                        if (selected.type === 'action') {
                            const found = selectedAction();
                            return found ? actionFields(found.action) : [];
                        }
                        if (selected.type === 'tab') {
                            const found = selectedTab();
                            return found ? tabFields(found) : [];
                        }
                        // A strip carries no label or icon of its own; its panel is the
                        // Remove/Restore row.
                        return [];
                    },
                    getAnchor: function () {
                        return root.querySelector(
                            '.dlux-ribbon-builder__pill.is-active, .dlux-ribbon-builder__preview-kind.is-active'
                        );
                    },
                    clearSelection: function () {
                        selected = null;
                        renderModels();
                    },
                    commit: commit,
                },
                strings: {
                    clearSelection: t('clear_selection', 'Clear selection'),
                    empty: t('inspector_empty', 'Select a tab or button to edit it.'),
                },
                presentation: 'popover',
                actionsPlacement: 'panel',
                dismissOnOutsideClick: true,
                dismissIgnoreSelector: '.dlux-ribbon-builder__pill, .dlux-ribbon-builder__preview-kind',
            })
            : null;

        function renderInspector() {
            if (ribbonInspectorShell) ribbonInspectorShell.render(selected || null);
        }

        // ---- the field an extra strip splits on -----------------------------
        //
        // An extra strip with no split is one "All" tab: nothing to order,
        // rename or hide. So the field is asked for when an admin-created strip
        // is created and stays changeable on that extra strip.

        function sourcesFor(fieldName, model) {
            if (!model) return [{ type: 'all' }];
            const field = (model.fields || []).find(f => f.name === fieldName);
            if (!field) return [{ type: 'all' }];
            // Led by "All", the way a hand-written strip is: without it a reader
            // has no way back to the unfiltered list.
            return [{ type: 'all' }, { type: field.kind, field: field.name }];
        }

        function splitFieldOf(sources) {
            const source = (sources || []).find(s => s && s.field);
            return source ? source.field : '';
        }

        function fillFieldOptions(select, model, current, describeEmpty) {
            if (!select) return;
            select.innerHTML = '';
            if (!model) {
                select.disabled = true;
                return;
            }
            const fields = model.fields || [];
            // A strip can split on something this list cannot name — a relation
            // path, a Q lookup, a mix of sources. Saying so is the point: with
            // nothing selected the browser shows whichever field sorts first,
            // which reads as the answer and is not one.
            const known = current && fields.some(f => f.name === current);
            if (describeEmpty && !known) {
                const option = document.createElement('option');
                option.value = '';
                option.textContent = current
                    ? t('split_custom', 'Currently: ') + current
                    : t('split_none', 'Not split by a field');
                option.selected = true;
                option.disabled = true;
                select.appendChild(option);
            }
            fields.forEach(function (field) {
                const option = document.createElement('option');
                option.value = field.name;
                option.textContent = field.label;
                if (field.name === current) option.selected = true;
                select.appendChild(option);
            });
            select.disabled = !fields.length;
        }

        function extraById(modelKey, id) {
            return (extraState[modelStateKey(modelKey)] || []).find(function (entry) {
                return entry._id === id;
            }) || null;
        }

        function fillRelationOptions(select, current) {
            if (!select) return;
            const options = [
                ['', t('relation_primary', 'Tabs')],
                ['child', t('relation_child', 'Within')],
                ['axis', t('relation_axis', 'Across')]
            ];
            select.innerHTML = '';
            options.forEach(function (pair) {
                const option = document.createElement('option');
                option.value = pair[0];
                option.textContent = pair[1];
                if (pair[0] === current) option.selected = true;
                select.appendChild(option);
            });
        }

        function availableDestinations() {
            return destinations.filter(function (destination) {
                if (destination.permitted === false) return false;
                return state.showSystemItems || !destination.is_system;
            });
        }

        function copyPayload(value) {
            return JSON.parse(JSON.stringify(value || {}));
        }

        function applyDestination(action, destination) {
            if (!destination) return;
            const spec = destination.action_spec || {};
            action.destination = copyPayload(spec.destination || {
                kind: destination.kind,
                route_name: destination.route_name,
                url: destination.url,
                label: destination.label,
                permissions: destination.permissions || []
            });
            action.permissions = Array.isArray(spec.permissions)
                ? spec.permissions.slice()
                : (destination.permissions || []).slice();
            action.icon = action.icon || destination.icon || '';
            if (destination.kind === 'modal') {
                action.url = '';
                action.attrs = copyPayload(spec.attrs || {
                    'data-dynamic-modal': destination.url,
                    'data-modal-title': destination.label
                });
            } else {
                action.url = spec.url || destination.url || '';
                action.attrs = {};
            }
        }

        function destinationForAction(action) {
            const routeName = action.destination && action.destination.route_name;
            if (routeName && destinationsById[routeName]) return destinationsById[routeName];
            return destinations.find(function (destination) {
                return destination.url === action.url
                    || (action.attrs && destination.url === action.attrs['data-dynamic-modal']);
            }) || null;
        }

        function hasAnyStrip(modelKey) {
            const model = hostFor(modelKey);
            return Boolean(((model && model.strips) || []).length
                || (extraState[modelStateKey(modelKey)] || []).length);
        }

        if (refs.systemToggle) {
            refs.systemToggle.addEventListener('change', function () {
                state.showSystemItems = refs.systemToggle.checked;
                if (selected && !hostVisible(selected.modelKey)) selected = null;
                renderAll();
            });
        }

        function renderAll() {
            renderModels();
            renderInspector();
        }

        // Deliberately no commit() here. The field already holds the server's
        // own serialisation, and rewriting it with this one — same data, but
        // `param` first and no spaces after the separators — makes the unsaved
        // guard read an untouched form as dirty and prompt on every close.
        // Every edit below commits; opening the step is not an edit.
        renderAll();
    }

    function boot(scope) {
        (scope || document).querySelectorAll('[data-ribbon-builder]').forEach(init);
    }

    document.addEventListener('shown.bs.modal', function (event) { boot(event.target); });
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { boot(document); });
    } else {
        boot(document);
    }
})();
