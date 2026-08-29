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
    const ICON_SUGGESTIONS = (window.DluxIconPicker && window.DluxIconPicker.suggestions) || [];

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

    function init(root) {
        if (root.dataset.ribbonBuilderReady === '1') return;
        root.dataset.ribbonBuilderReady = '1';

        const catalog = parse(root.dataset.catalog, []);
        const strings = parse(root.dataset.strings, {});
        const languages = parse(root.dataset.languages, {});
        const stored = parse(root.dataset.config, {});
        const byKey = Object.fromEntries(catalog.map(m => [m.key, m]));
        const languageCodes = Object.keys(languages).length ? Object.keys(languages) : ['en'];

        const declaredState = {};
        const extraState = {};
        let nextExtraId = 1;

        Object.keys(stored).forEach(function (modelKey) {
            readDeclaredStrips(stored[modelKey]).forEach(function (strip) {
                declaredEntryFor(modelKey, strip);
            });
            readExtraStrips(stored[modelKey]).forEach(function (strip) {
                extraState[modelKey] = extraState[modelKey] || [];
                extraState[modelKey].push(hydrateExtra(strip));
            });
        });

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

        const refs = {
            models: root.querySelector('[data-ribbon-models]'),
            modelSelect: root.querySelector('[data-ribbon-model]'),
            newParam: root.querySelector('[data-ribbon-new-param]'),
            newField: root.querySelector('[data-ribbon-new-field]'),
            newRelation: root.querySelector('[data-ribbon-new-relation]'),
            addStrip: root.querySelector('[data-ribbon-add-strip]'),
            inspector: root.querySelector('[data-ribbon-inspector]'),
            inspectorEmpty: root.querySelector('[data-ribbon-inspector-empty]'),
            inspectorName: root.querySelector('[data-ribbon-inspector-name]'),
            inspectorKey: root.querySelector('[data-ribbon-inspector-key]'),
            labelInputs: root.querySelector('[data-ribbon-label-inputs]'),
            iconInput: root.querySelector('[data-ribbon-icon-input]'),
            iconPreview: root.querySelector('[data-ribbon-icon-preview]'),
            iconSearch: root.querySelector('[data-ribbon-icon-search]'),
            iconSuggestions: root.querySelector('[data-ribbon-icon-suggestions]'),
            shown: root.querySelector('[data-ribbon-shown]'),
            shownWrap: root.querySelector('[data-ribbon-shown-wrap]')
        };
        const templates = {
            model: document.querySelector('[data-ribbon-model-template]'),
            stripRow: document.querySelector('[data-ribbon-strip-row-template]'),
            pill: document.querySelector('[data-ribbon-pill-template]')
        };
        if (!refs.models || !templates.model || !templates.pill) return;

        let selected = null;   // {modelKey, origin, key, tabKey}
        let dragging = null;   // {modelKey, origin, key, tabKey}

        function t(key, fallback) {
            return strings[key] || fallback;
        }

        function hiddenField() {
            const form = root.closest('form');
            return form ? form.querySelector('[name="' + FIELD_NAME + '"]') : null;
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
            return declaredEntryFor(modelKey, strip);
        }

        function relationLabel(value) {
            const relation = value || 'primary';
            return t('relation_' + relation, relation);
        }

        function removeDeclaredEntry(modelKey, entry) {
            declaredState[modelKey] = (declaredState[modelKey] || []).filter(function (item) {
                return item !== entry;
            });
            if (!declaredState[modelKey].length) delete declaredState[modelKey];
        }

        // Only what an operator actually changed is written; an untouched page
        // stores nothing and keeps following the code.
        function commit() {
            const field = hiddenField();
            if (!field) return;
            const out = {};
            const modelKeys = new Set(
                Object.keys(declaredState).concat(Object.keys(extraState))
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
                if (declared.length || extra.length) out[modelKey] = modelEntry;
            });
            field.value = JSON.stringify(out);
        }

        // ---- reading a strip the way the page will render it ---------------

        function stripsOf(modelKey) {
            const model = byKey[modelKey];
            const out = [];
            ((model && model.strips) || []).forEach(function (strip) {
                out.push(Object.assign({}, strip, { origin: 'declared' }));
            });
            (extraState[modelKey] || []).forEach(function (strip) {
                out.push(Object.assign({}, strip, {
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
            const key = modelKey + '|' + param + '|' + JSON.stringify(sources);
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
                body: JSON.stringify({ model: modelKey, param: param, sources: sources })
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
            const entry = tabCache[modelKey + '|' + param + '|' + JSON.stringify(sources)];
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
            const tools = node.querySelector('[data-strip-tools]');
            if (tools) {
                if (strip.origin === 'declared') {
                    const restore = document.createElement('button');
                    restore.type = 'button';
                    restore.className = 'btn btn-sm btn-outline-secondary rounded-pill';
                    restore.textContent = t('restore_strip', 'Restore');
                    restore.disabled = !declaredDirty(overlay);
                    restore.addEventListener('click', function () {
                        removeDeclaredEntry(modelKey, overlay);
                        if (selected && selected.modelKey === modelKey
                            && selected.origin === 'declared' && selected.key === stripKey(strip)) {
                            selected = null;
                        }
                        commit();
                        renderAll();
                    });
                    tools.appendChild(restore);
                    if (!locked) {
                        const remove = document.createElement('button');
                        remove.type = 'button';
                        remove.className = 'btn btn-sm btn-outline-danger rounded-pill';
                        remove.textContent = t('remove_strip', 'Remove');
                        remove.disabled = disabled;
                        remove.addEventListener('click', function () {
                            overlay.enabled = false;
                            overlay.order = [];
                            overlay.labels = {};
                            overlay.icons = {};
                            overlay.hidden = [];
                            if (selected && selected.modelKey === modelKey
                                && selected.origin === 'declared' && selected.key === stripKey(strip)) {
                                selected = null;
                            }
                            commit();
                            renderAll();
                        });
                        tools.appendChild(remove);
                    }
                } else {
                    const remove = document.createElement('button');
                    remove.type = 'button';
                    remove.className = 'btn btn-sm btn-outline-danger rounded-pill';
                    remove.textContent = t('remove_strip', 'Remove');
                    remove.addEventListener('click', function () {
                        extraState[modelKey] = (extraState[modelKey] || []).filter(function (entry) {
                            return entry._id !== strip._id;
                        });
                        if (!extraState[modelKey].length) delete extraState[modelKey];
                        if (selected && selected.modelKey === modelKey
                            && selected.origin === 'extra' && selected.key === stripKey(strip)) {
                            selected = null;
                        }
                        commit();
                        renderAll();
                    });
                    tools.appendChild(remove);
                }
            }

            const picker = node.querySelector('[data-strip-field]');
            if (picker && strip.origin === 'extra') {
                picker.hidden = false;
                fillFieldOptions(picker, byKey[modelKey],
                                 splitFieldOf(strip.sources), true);
                picker.addEventListener('change', function () {
                    const extra = extraById(modelKey, strip._id);
                    if (!extra) return;
                    extra.sources = sourcesFor(picker.value, byKey[modelKey]);
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

        function renderModels() {
            refs.models.innerHTML = '';
            catalog.forEach(function (model) {
                const strips = stripsOf(model.key);
                if (!strips.length) return;
                const node = templates.model.content.firstElementChild.cloneNode(true);
                node.querySelector('[data-model-label]').textContent = model.label;
                node.querySelector('[data-model-key]').textContent = model.key;

                const badge = node.querySelector('[data-model-badge]');
                if (model.locked) {
                    badge.hidden = false;
                    badge.textContent = t('locked', 'fixed in code');
                    badge.title = t('locked_hint', '');
                }

                const declared = strips.filter(function (strip) { return strip.origin === 'declared'; });
                const extra = strips.filter(function (strip) { return strip.origin === 'extra'; });
                const declaredSection = node.querySelector('[data-declared-section]');
                const extraSection = node.querySelector('[data-extra-section]');
                const declaredHost = node.querySelector('[data-model-declared-strips]');
                const extraHost = node.querySelector('[data-model-extra-strips]');
                if (declaredSection) declaredSection.hidden = !declared.length;
                if (extraSection) extraSection.hidden = !extra.length;
                declared.forEach(function (strip) {
                    renderStripRow(model.key, strip, declaredHost || extraHost, model.locked);
                });
                extra.forEach(function (strip) {
                    renderStripRow(model.key, strip, extraHost || declaredHost, model.locked);
                });
                refs.models.appendChild(node);
            });
        }

        // ---- the inspector --------------------------------------------------

        function selectedTab() {
            if (!selected) return null;
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

        function renderInspector() {
            const found = selectedTab();
            if (!found) {
                refs.inspector.classList.add('d-none');
                refs.inspectorEmpty.classList.remove('d-none');
                return;
            }
            refs.inspector.classList.remove('d-none');
            refs.inspectorEmpty.classList.add('d-none');

            const overlay = found.overlay;
            refs.inspectorName.textContent = found.tab.label;
            refs.inspectorKey.textContent = found.tab.key || '(all)';

            refs.labelInputs.innerHTML = '';
            const stored = overlay.labels[found.tab.key];
            const perLanguage = (stored && typeof stored === 'object') ? stored : {};
            const flat = (stored && typeof stored === 'string') ? stored : '';
            languageCodes.forEach(function (code) {
                const wrap = document.createElement('div');
                wrap.className = 'input-group input-group-sm mb-2';
                const tag = document.createElement('span');
                tag.className = 'input-group-text text-uppercase';
                tag.textContent = code;
                const input = document.createElement('input');
                input.type = 'text';
                input.className = 'form-control glass-input';
                input.placeholder = found.tab.label;
                input.value = perLanguage[code] || flat || '';
                input.addEventListener('input', function () {
                    const next = Object.assign({}, perLanguage);
                    if (input.value.trim()) next[code] = input.value.trim();
                    else delete next[code];
                    if (Object.keys(next).length) overlay.labels[found.tab.key] = next;
                    else delete overlay.labels[found.tab.key];
                    commit();
                    renderModels();
                });
                wrap.appendChild(tag);
                wrap.appendChild(input);
                refs.labelInputs.appendChild(wrap);
            });

            const icon = overlay.icons[found.tab.key] || found.tab.icon || '';
            if (refs.iconInput) refs.iconInput.value = icon;
            if (refs.iconPreview) refs.iconPreview.className = 'bi ' + (icon || 'bi-stars');
            renderIconSuggestions(icon);
            refs.shown.checked = overlay.hidden.indexOf(found.tab.key) === -1;
            // A locked page keeps its tabs: which ones exist is the developer's
            // call, how they read is not.
            refs.shown.disabled = !!selected.locked;
            refs.shownWrap.title = selected.locked ? t('locked_hint', '') : '';
        }


        function setIcon(value) {
            const found = selectedTab();
            if (!found) return;
            const overlay = found.overlay;
            if (value) overlay.icons[found.tab.key] = value;
            else delete overlay.icons[found.tab.key];
            commit();
            // Not renderAll(): that rebuilds the inspector, and rebuilding the
            // input a glyph is being typed into loses the caret mid-word.
            renderModels();
            if (refs.iconPreview) refs.iconPreview.className = 'bi ' + (value || 'bi-stars');
            if (refs.iconInput && refs.iconInput.value !== value) refs.iconInput.value = value;
            renderIconSuggestions(value);
        }

        function renderIconSuggestions(active) {
            if (!refs.iconSuggestions) return;
            const needle = ((refs.iconSearch && refs.iconSearch.value) || '')
                .trim().toLowerCase().replace(/\s+/g, '-');
            const matches = needle
                ? ICON_SUGGESTIONS.filter(function (icon) { return icon.includes(needle); })
                : ICON_SUGGESTIONS;
            const fragment = document.createDocumentFragment();
            matches.forEach(function (icon) {
                const button = document.createElement('button');
                button.type = 'button';
                // The sidebar inspector's own class, so the grid looks the same
                // here rather than inventing a second style for the same thing.
                button.className = 'btn btn-sm dlux-builder-icon-choice'
                    + (icon === active ? ' is-active' : '');
                button.setAttribute('title', icon);
                button.setAttribute('aria-label', icon);
                button.innerHTML = '<i class="bi ' + icon + '"></i>';
                button.addEventListener('click', function () { setIcon(icon); });
                fragment.appendChild(button);
            });
            refs.iconSuggestions.innerHTML = '';
            if (!matches.length) {
                refs.iconSuggestions.innerHTML =
                    '<div class="text-muted small p-2">' + t('no_icons', 'No icons match your search.') + '</div>';
                return;
            }
            refs.iconSuggestions.appendChild(fragment);
        }

        if (refs.iconInput) {
            refs.iconInput.addEventListener('input', function () {
                setIcon(refs.iconInput.value.trim());
            });
        }
        if (refs.iconSearch) {
            refs.iconSearch.addEventListener('input', function () {
                const found = selectedTab();
                if (!found) { renderIconSuggestions(''); return; }
                const overlay = found.overlay;
                renderIconSuggestions(overlay.icons[found.tab.key] || found.tab.icon || '');
            });
        }
        if (refs.shown) {
            refs.shown.addEventListener('change', function () {
                const found = selectedTab();
                if (!found) return;
                const overlay = found.overlay;
                const at = overlay.hidden.indexOf(found.tab.key);
                if (refs.shown.checked && at !== -1) overlay.hidden.splice(at, 1);
                else if (!refs.shown.checked && at === -1) overlay.hidden.push(found.tab.key);
                commit();
                renderAll();
            });
        }


        // ---- the field an extra strip splits on -----------------------------
        //
        // An extra strip with no split is one "All" tab: nothing to order,
        // rename or hide. So the field is asked for when an admin-created strip
        // is created and stays changeable on that extra strip.

        function sourcesFor(fieldName, model) {
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
            if (!select || !model) return;
            select.innerHTML = '';
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
            return (extraState[modelKey] || []).find(function (entry) {
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

        function hasAnyStrip(modelKey) {
            const model = byKey[modelKey];
            return Boolean(((model && model.strips) || []).length
                || (extraState[modelKey] || []).length);
        }

        // ---- adding an admin-defined strip ----------------------------------

        function fillModelSelect() {
            if (!refs.modelSelect) return;
            refs.modelSelect.innerHTML = '';
            let offered = 0;
            catalog.forEach(function (model) {
                if (model.locked) return;
                if (!model.fields.length) return;         // nothing to draw with
                const option = document.createElement('option');
                option.value = model.key;
                option.textContent = model.label;
                refs.modelSelect.appendChild(option);
                offered += 1;
            });
            refs.modelSelect.disabled = offered === 0;
            if (refs.addStrip) refs.addStrip.disabled = offered === 0;
            if (refs.newParam) refs.newParam.disabled = offered === 0;
            if (refs.newField) refs.newField.disabled = offered === 0;
            if (refs.newRelation) refs.newRelation.disabled = offered === 0;
            fillFieldOptions(refs.newField, byKey[refs.modelSelect.value], '');
            fillRelationOptions(refs.newRelation, hasAnyStrip(refs.modelSelect.value) ? 'axis' : '');
        }

        if (refs.modelSelect) {
            refs.modelSelect.addEventListener('change', function () {
                fillFieldOptions(refs.newField, byKey[refs.modelSelect.value], '');
                fillRelationOptions(refs.newRelation, hasAnyStrip(refs.modelSelect.value) ? 'axis' : '');
            });
        }

        if (refs.addStrip) {
            refs.addStrip.addEventListener('click', function () {
                const modelKey = refs.modelSelect.value;
                if (!modelKey) return;
                const model = byKey[modelKey];
                const fieldName = refs.newField ? refs.newField.value : '';
                if (!fieldName) return;
                // Named after the field unless the operator said otherwise, so
                // the address bar reads `?category=` rather than `?tab=`.
                const param = (refs.newParam.value || '').trim() || fieldName;
                extraState[modelKey] = extraState[modelKey] || [];
                extraState[modelKey].push(hydrateExtra({
                    param: param,
                    relation: refs.newRelation ? refs.newRelation.value : '',
                    sources: sourcesFor(fieldName, model)
                }));
                refs.newParam.value = '';
                commit();
                renderAll();
            });
        }

        function renderAll() {
            renderModels();
            renderInspector();
            fillModelSelect();
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
