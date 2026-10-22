(function () {
    'use strict';

    function object(value) {
        return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    }

    function parse(value, fallback) {
        try { return JSON.parse(value); } catch (_) { return fallback; }
    }

    function canonical(value) {
        if (Array.isArray(value)) return value.map(canonical);
        if (value && typeof value === 'object') return Object.fromEntries(
            Object.keys(value).sort().map(key => [key, canonical(value[key])])
        );
        return value;
    }

    function element(tag, className, text) {
        const node = document.createElement(tag);
        node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function button(className, text, label) {
        const node = element('button', className, text);
        node.type = 'button';
        if (label) node.setAttribute('aria-label', label);
        return node;
    }

    function init(root) {
        if (root.dataset.tableColumnsReady) return;
        const hidden = root.closest('form')?.querySelector('[name="tables_config"]');
        if (!hidden) return;
        let initialValue;
        let initialConfig;
        root.dataset.tableColumnsReady = '1';
        const catalog = parse(root.dataset.catalog, []);
        const strings = object(parse(root.dataset.strings, {}));
        const host = root.querySelector('[data-table-column-models]');
        const systemToggle = root.querySelector('[data-table-columns-system-toggle]');
        const empty = root.querySelector('[data-table-columns-empty]');
        const emptyMessage = empty.textContent;
        let showSystemItems = false;
        let writing = false;
        let dragging = null;
        let selected = null;
        const languages = object(parse(root.dataset.languages, {}));
        const language = root.dataset.language || document.documentElement.lang;
        const iconHolder = root.querySelector('[data-table-column-icon-holder]');
        const iconPicker = iconHolder.querySelector('[data-dlux-icon-picker]');
        const iconValue = root.querySelector('[data-table-column-icon-value]');
        let iconTarget = null;

        function config() { return object(parse(hidden.value, {})); }

        function state(model) {
            const entry = object(object(config().columns)[model.key]);
            const names = model.columns.map(column => column.name);
            const hiddenNames = Array.isArray(entry.hidden) ? entry.hidden : [];
            const ordered = Array.isArray(entry.order) ? entry.order : [];
            const all = [...new Set([...ordered.filter(name => names.includes(name)), ...names])];
            let visible = all.filter(name => !hiddenNames.includes(name));
            if (!visible.length && names.length) visible = [names[0]];
            return {entry, names, visible};
        }

        function write(value, refreshInspector = true) {
            if (initialValue === undefined) {
                initialValue = hidden.value;
                initialConfig = JSON.stringify(canonical(parse(initialValue, {})));
            }
            hidden.value = JSON.stringify(canonical(value)) === initialConfig ? initialValue : JSON.stringify(value);
            writing = true;
            hidden.dispatchEvent(new Event('input', {bubbles: true}));
            hidden.dispatchEvent(new Event('change', {bubbles: true}));
            writing = false;
            render(refreshInspector);
        }

        function edit(model, change, refreshInspector = true) {
            const value = config();
            const columns = {...object(value.columns)};
            const entry = {...object(columns[model.key])};
            change(entry);
            if (Object.keys(entry).length) columns[model.key] = entry;
            else delete columns[model.key];
            value.columns = columns;
            write(value, refreshInspector);
        }

        function headerSettings(model, name) { return object(object(state(model).entry.headers)[name]); }
        function columnChanged(model, name) {
            const header = headerSettings(model, name);
            return Boolean(header.icon || Object.values(object(header.labels)).some(Boolean))
                || !state(model).visible.includes(name)
                || sortingOf(model).some(alias => alias.replace(/^-/, '') === name);
        }
        function sortingOf(model) {
            const sorting = state(model).entry.sorting;
            return Array.isArray(sorting) ? sorting.filter(alias => typeof alias === 'string') : [];
        }

        function updateHeader(model, name, change, refreshInspector = true) {
            edit(model, entry => {
                const headers = {...object(entry.headers)};
                const header = {...object(headers[name])};
                change(header);
                if (Object.keys(header).length) headers[name] = header; else delete headers[name];
                if (Object.keys(headers).length) entry.headers = headers; else delete entry.headers;
            }, refreshInspector);
        }

        function label(model, name) {
            const column = model.columns.find(column => column.name === name);
            const labels = object(headerSettings(model, name).labels);
            return labels[language] || labels[language.split('-')[0]] || column.label;
        }

        function commit(model, visible, reset) {
            const value = config();
            const columns = {...object(value.columns)};
            const {entry, names} = state(model);
            if (reset) {
                delete columns[model.key];
            } else {
                const next = {...entry};
                const staleHidden = (Array.isArray(entry.hidden) ? entry.hidden : []).filter(name => !names.includes(name));
                const staleOrder = (Array.isArray(entry.order) ? entry.order : []).filter(name => !names.includes(name));
                const hiddenNames = [...staleHidden, ...names.filter(name => !visible.includes(name))];
                const previousOrder = [...new Set([
                    ...(Array.isArray(entry.order) ? entry.order : []).filter(name => names.includes(name)), ...names,
                ])];
                const replacements = visible[Symbol.iterator]();
                const fullOrder = previousOrder.map(name => visible.includes(name) ? replacements.next().value : name);
                const order = JSON.stringify(names) === JSON.stringify(fullOrder) ? staleOrder : [...staleOrder, ...fullOrder];
                if (hiddenNames.length) next.hidden = hiddenNames; else delete next.hidden;
                if (order.length) next.order = order; else delete next.order;
                if (Object.keys(next).length) columns[model.key] = next; else delete columns[model.key];
            }
            value.columns = columns;
            write(value);
            root.querySelector('[data-table-columns-status]').textContent = model.label + ': ' + visible.map(name =>
                model.columns.find(column => column.name === name)?.label || name).join(', ');
        }

        function focus(model, name, selector) {
            const section = [...host.children].find(node => node.dataset.tableModel === model.key);
            const node = [...section.querySelectorAll(selector)].find(node => node.dataset.columnName === name);
            node?.focus({preventScroll: true});
        }

        function move(model, name, offset) {
            const visible = state(model).visible;
            const index = visible.indexOf(name);
            const target = index + offset;
            if (target < 0 || target >= visible.length) return;
            visible.splice(index, 1);
            visible.splice(target, 0, name);
            commit(model, visible);
            focus(model, name, '[data-column-handle]');
        }

        function render(refreshInspector = true) {
            host.replaceChildren();
            const visibleCatalog = catalog.filter(model => showSystemItems || !model.is_system);
            if (selected && !visibleCatalog.some(model => model.key === selected.modelKey)) selected = null;
            empty.hidden = visibleCatalog.length > 0;
            empty.textContent = catalog.length ? root.dataset.emptyProjectLabel : emptyMessage;
            visibleCatalog.forEach(model => {
                const {names, visible} = state(model);
                const labels = new Map(model.columns.map(column => [column.name, label(model, column.name)]));
                const section = element('section', 'dlux-ribbon-builder__model');
                section.dataset.tableModel = model.key;
                const head = element('header', 'dlux-ribbon-builder__model-head');
                const title = button('btn p-0 fw-semibold dlux-ribbon-builder__model-name', model.label);
                title.dataset.tableSelect = '';
                title.addEventListener('click', () => { selected = {modelKey:model.key}; render(); });
                head.appendChild(title);
                section.appendChild(head);
                const strip = element('div', 'dlux-table-columns__headers');
                strip.setAttribute('role', 'group');
                strip.setAttribute('aria-label', strings.headers + ': ' + model.label);
                const rawOrder = state(model).entry.order;
                const ordered = Array.isArray(rawOrder) ? rawOrder : [];
                [...new Set([...ordered.filter(name => names.includes(name)), ...names])].forEach(name => {
                    const index = visible.indexOf(name);
                    const enabled = index !== -1;
                    const cell = element('div', 'dlux-table-columns__header');
                    cell.dataset.columnHeader = name;
                    cell.dataset.columnEnabled = String(enabled);
                    cell.classList.toggle('is-removed', !enabled);
                    cell.classList.toggle('is-active', selected?.modelKey === model.key && selected.name === name);
                    cell.draggable = !hidden.disabled && enabled;
                    const handle = button('btn btn-sm dlux-table-columns__handle', labels.get(name));
                    handle.title = enabled ? strings.reorder : strings.removed;
                    const icon = headerSettings(model, name).icon;
                    if (/^bi-[a-z0-9-]+$/.test(icon || '')) {
                        const glyph = element('i', 'bi ' + icon + ' me-1');
                        glyph.setAttribute('aria-hidden', 'true');
                        handle.prepend(glyph);
                    }
                    handle.dataset.columnHandle = '';
                    handle.dataset.columnName = name;
                    handle.disabled = hidden.disabled;
                    handle.addEventListener('click', () => { selected = {modelKey:model.key,name}; render(); });
                    handle.addEventListener('keydown', event => {
                        if (!enabled || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
                        event.preventDefault();
                        const rtl = getComputedStyle(root).direction === 'rtl';
                        move(model, name, (event.key === 'ArrowRight' ? 1 : -1) * (rtl ? -1 : 1));
                    });
                    cell.appendChild(handle);
                    [-1, 1].forEach(offset => {
                        const label = offset < 0 ? strings.previous : strings.next;
                        const arrow = button('btn btn-sm px-1', '', label + ': ' + labels.get(name));
                        const icon = element('i', 'bi dlux-table-columns__arrow bi-chevron-' + (offset < 0 ? 'left' : 'right'));
                        icon.setAttribute('aria-hidden', 'true');
                        arrow.appendChild(icon);
                        arrow.title = label;
                        arrow.dataset.columnMove = String(offset);
                        arrow.disabled = hidden.disabled || !enabled || (offset < 0 ? index === 0 : index === visible.length - 1);
                        arrow.addEventListener('click', () => move(model, name, offset));
                        cell.appendChild(arrow);
                    });
                    cell.addEventListener('dragstart', event => {
                        dragging = {model: model.key, name};
                        event.dataTransfer.setData('text/plain', name);
                        event.dataTransfer.effectAllowed = 'move';
                        cell.classList.add('is-dragging');
                    });
                    cell.addEventListener('dragend', () => {
                        dragging = null;
                        root.querySelectorAll('.is-dragging, .is-drop-target').forEach(node =>
                            node.classList.remove('is-dragging', 'is-drop-target'));
                    });
                    cell.addEventListener('dragover', event => {
                        if (!enabled || !dragging || dragging.model !== model.key || dragging.name === name) return;
                        event.preventDefault();
                        cell.classList.add('is-drop-target');
                    });
                    cell.addEventListener('dragleave', () => cell.classList.remove('is-drop-target'));
                    cell.addEventListener('drop', event => {
                        event.preventDefault();
                        if (!enabled || !dragging || dragging.model !== model.key || dragging.name === name) return;
                        const source = dragging.name;
                        const ordered = state(model).visible;
                        const from = ordered.indexOf(source);
                        const to = ordered.indexOf(name);
                        ordered.splice(from, 1);
                        ordered.splice(to, 0, source);
                        dragging = null;
                        commit(model, ordered);
                        focus(model, source, '[data-column-handle]');
                    });
                    strip.appendChild(cell);
                });
                section.appendChild(strip);
                host.appendChild(section);
            });
            if (refreshInspector) inspector.render(selected);
            else {
                const found = selection();
                const restore = root.querySelector('[data-inspector-action="reset-column"]');
                if (restore && found?.column) restore.disabled = hidden.disabled || !columnChanged(found.model, found.column.name);
                inspector.reposition();
            }
        }

        function selection() {
            const model = selected && catalog.find(model => model.key === selected.modelKey);
            if (!model) return null;
            return {model, column: model.columns.find(column => column.name === selected.name)};
        }

        function setShown(model, name, shown) {
            const visible = state(model).visible;
            const {entry, names} = state(model);
            const all = [...new Set([...(Array.isArray(entry.order) ? entry.order : []).filter(item => names.includes(item)), ...names])];
            const next = shown ? all.filter(item => item === name || visible.includes(item)) : visible.filter(item => item !== name);
            if (!next.length) return;
            commit(model, next);
        }

        function resetColumn(model, name) {
            edit(model, entry => {
                const headers = {...object(entry.headers)};
                delete headers[name];
                if (Object.keys(headers).length) entry.headers = headers; else delete entry.headers;
                ['hidden', 'sorting'].forEach(key => {
                    const next = (Array.isArray(entry[key]) ? entry[key] : []).filter(item =>
                        typeof item === 'string' && item.replace(/^-/, '') !== name);
                    if (next.length) entry[key] = next; else delete entry[key];
                });
            });
        }

        iconValue.addEventListener('input', () => { if (iconTarget) iconTarget(iconValue.value.trim()); });

        const inspector = window.DluxInspectorShell.create(root.querySelector('[data-table-column-inspector]'), {
            presentation: 'popover', actionsPlacement: 'panel', dismissOnOutsideClick: true,
            dismissIgnoreSelector: '.dlux-table-columns__header, [data-table-select]',
            strings: {empty: strings.empty_inspector, clearSelection: strings.clear},
            adapter: {
                getTitle: () => {
                    const found = selection();
                    return found ? (found.column ? label(found.model, found.column.name) : found.model.label) : '';
                },
                getActions: () => {
                    const found = selection();
                    if (!found) return [];
                    const {model, column} = found;
                    if (!column) return [{id:'reset-table', label:strings.reset, icon:'bi bi-arrow-counterclockwise',
                        disabled:hidden.disabled || !Object.hasOwn(object(config().columns), model.key),
                        onClick:() => commit(model, state(model).names, true)}];
                    const shown = state(model).visible.includes(column.name);
                    const last = shown && state(model).visible.length === 1;
                    return [
                        {id:'reset-column', label:strings.column_reset, icon:'bi bi-arrow-counterclockwise',
                            disabled:hidden.disabled || !columnChanged(model, column.name), onClick:() => resetColumn(model, column.name)},
                        {id:'remove-column', label:strings.remove, icon:'bi bi-trash3', variant:'outline-danger',
                            disabled:hidden.disabled || !shown || last,
                            onClick:() => setShown(model, column.name, false)},
                        {id:'shown', type:'toggle', label:strings.shown, checked:shown,
                            title:last ? strings.keepOne : '', disabled:hidden.disabled || last,
                            onChange:context => setShown(model, column.name, context.value)},
                    ];
                },
                getFields: () => {
                    const found = selection();
                    if (!found?.column) return [];
                    const {model, column} = found;
                    const header = headerSettings(model, column.name);
                    const sorting = sortingOf(model);
                    const rank = sorting.findIndex(alias => alias.replace(/^-/, '') === column.name);
                    const sortable = column.orderable && state(model).visible.includes(column.name) && !hidden.disabled;
                    return [
                        {id:'labels', type:'localized-text', label:strings.labels,
                            languages:Object.entries(languages).map(([code, info]) => ({code, label:info.name || info.label || code})),
                            values:object(header.labels), disabled:hidden.disabled, commitOn:'input',
                            onInput:context => updateHeader(model, column.name, value => {
                                const labels = {...object(value.labels)};
                                if (context.value.trim()) labels[context.language] = context.value.trim();
                                else delete labels[context.language];
                                if (Object.keys(labels).length) value.labels = labels; else delete value.labels;
                            }, false)},
                        {id:'icon', type:'custom', render:() => {
                            const value = headerSettings(model, column.name).icon || '';
                            iconValue.value = value;
                            iconPicker.querySelector('[data-icon-input]').value = value;
                            const preview = iconPicker.querySelector('[data-icon-preview]');
                            preview.className = 'bi ' + (value || 'bi-table');
                            preview.classList.toggle('dlux-icon-picker-preview--empty', !value);
                            iconTarget = value => updateHeader(model, column.name, header => {
                                if (value) header.icon = value; else delete header.icon;
                            }, false);
                            return {node:iconPicker, cleanup:() => { iconTarget = null; iconHolder.appendChild(iconPicker); }};
                        }},
                        {id:'sort-priority', type:'select', label:strings.priority, disabled:!sortable,
                            value:rank === -1 ? '' : String(rank), options:[
                                {value:'',label:strings.none}, {value:'0',label:strings.primary},
                                {value:'1',label:strings.secondary,disabled:!sorting.some(alias => alias.replace(/^-/, '') !== column.name)},
                            ], onChange:context => edit(model, entry => {
                                const existing = sortingOf(model);
                                const alias = existing.find(alias => alias.replace(/^-/, '') === column.name) || column.name;
                                let next = existing.filter(alias => alias.replace(/^-/, '') !== column.name);
                                if (context.value === '0') next = [alias, ...next].slice(0,2);
                                if (context.value === '1' && next.length) next = [next[0], alias];
                                if (next.length) entry.sorting = next; else delete entry.sorting;
                            })},
                        {id:'sort-direction', type:'select', label:strings.direction, disabled:!sortable || rank === -1,
                            value:sorting[rank]?.startsWith('-') ? 'desc' : 'asc',
                            options:[{value:'asc',label:strings.ascending},{value:'desc',label:strings.descending}],
                            onChange:context => edit(model, entry => {
                                entry.sorting = sortingOf(model).map(alias => alias.replace(/^-/, '') === column.name
                                    ? (context.value === 'desc' ? '-' : '') + column.name : alias);
                            })},
                    ];
                },
                getAnchor: () => {
                    if (!selected) return null;
                    const section = [...host.children].find(node => node.dataset.tableModel === selected.modelKey);
                    return selected.name ? [...(section?.querySelectorAll('[data-column-header]') || [])]
                        .find(node => node.dataset.columnHeader === selected.name) : section?.querySelector('[data-table-select]');
                },
                clearSelection: () => {
                    const previous = selection();
                    selected = null;
                    render(false);
                    if (previous?.column) focus(previous.model, previous.column.name, '[data-column-handle]');
                    else if (previous) [...host.children].find(node => node.dataset.tableModel === previous.model.key)
                        ?.querySelector('[data-table-select]')?.focus({preventScroll:true});
                },
            },
        });

        hidden.addEventListener('change', () => { if (!writing) render(); });
        systemToggle.checked = false;
        systemToggle.addEventListener('change', () => {
            showSystemItems = systemToggle.checked;
            dragging = null;
            render();
        });
        render();
    }

    function boot(scope) {
        (scope || document).querySelectorAll('[data-table-column-builder]').forEach(init);
    }
    document.addEventListener('shown.bs.modal', event => boot(event.target));
    document.addEventListener('dlux:modal-content-loaded', event => boot(event.target));
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => boot(document));
    else boot(document);
})();
