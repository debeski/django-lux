(function () {
    'use strict';

    function object(value) {
        return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    }

    function parse(value, fallback) {
        try { return JSON.parse(value); } catch (_) { return fallback; }
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
        root.dataset.tableColumnsReady = '1';
        const catalog = parse(root.dataset.catalog, []);
        const strings = object(parse(root.dataset.strings, {}));
        const host = root.querySelector('[data-table-column-models]');
        let writing = false;
        let dragging = null;

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
                const natural = names.filter(name => visible.includes(name));
                const order = JSON.stringify(natural) === JSON.stringify(visible) ? staleOrder : [...staleOrder, ...visible];
                if (hiddenNames.length) next.hidden = hiddenNames; else delete next.hidden;
                if (order.length) next.order = order; else delete next.order;
                if (Object.keys(next).length) columns[model.key] = next; else delete columns[model.key];
            }
            value.columns = columns;
            hidden.value = JSON.stringify(value);
            writing = true;
            hidden.dispatchEvent(new Event('input', {bubbles: true}));
            hidden.dispatchEvent(new Event('change', {bubbles: true}));
            writing = false;
            render();
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

        function render() {
            host.replaceChildren();
            root.querySelector('[data-table-columns-empty]').hidden = catalog.length > 0;
            catalog.forEach(model => {
                const {names, visible} = state(model);
                const labels = new Map(model.columns.map(column => [column.name, column.label]));
                const section = element('section', 'dlux-ribbon-builder__model');
                section.dataset.tableModel = model.key;
                const head = element('header', 'dlux-ribbon-builder__model-head');
                head.appendChild(element('strong', 'dlux-ribbon-builder__model-name', model.label));
                const reset = button('btn btn-sm btn-outline-secondary rounded-pill', strings.reset);
                reset.dataset.tableColumnsReset = '';
                reset.disabled = hidden.disabled || !Object.hasOwn(object(config().columns), model.key);
                reset.addEventListener('click', () => {
                    commit(model, names, true);
                    [...host.children].find(node => node.dataset.tableModel === model.key)
                        ?.querySelector('[data-column-handle]')?.focus({preventScroll: true});
                });
                head.appendChild(reset);
                section.appendChild(head);
                const strip = element('div', 'dlux-table-columns__headers');
                strip.setAttribute('role', 'group');
                strip.setAttribute('aria-label', strings.headers + ': ' + model.label);
                visible.forEach((name, index) => {
                    const cell = element('div', 'dlux-table-columns__header');
                    cell.dataset.columnHeader = name;
                    cell.draggable = !hidden.disabled;
                    const handle = button('btn btn-sm dlux-table-columns__handle', labels.get(name));
                    handle.title = strings.reorder;
                    handle.dataset.columnHandle = '';
                    handle.dataset.columnName = name;
                    handle.disabled = hidden.disabled;
                    handle.addEventListener('keydown', event => {
                        if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
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
                        arrow.disabled = hidden.disabled || (offset < 0 ? index === 0 : index === visible.length - 1);
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
                        if (!dragging || dragging.model !== model.key || dragging.name === name) return;
                        event.preventDefault();
                        cell.classList.add('is-drop-target');
                    });
                    cell.addEventListener('dragleave', () => cell.classList.remove('is-drop-target'));
                    cell.addEventListener('drop', event => {
                        event.preventDefault();
                        if (!dragging || dragging.model !== model.key || dragging.name === name) return;
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
                const chips = element('div', 'dlux-ribbon-builder__pills');
                chips.setAttribute('role', 'group');
                chips.setAttribute('aria-label', strings.available + ': ' + model.label);
                model.columns.forEach(column => {
                    const checked = visible.includes(column.name);
                    const chip = button('dlux-ribbon-builder__pill dlux-table-columns__chip');
                    chip.setAttribute('role', 'checkbox');
                    chip.setAttribute('aria-checked', String(checked));
                    chip.dataset.columnToggle = '';
                    chip.dataset.columnName = column.name;
                    const icon = element('i', 'bi bi-' + (checked ? 'check-square' : 'square'));
                    icon.setAttribute('aria-hidden', 'true');
                    chip.append(icon, document.createTextNode(column.label));
                    chip.disabled = hidden.disabled || (checked && visible.length === 1);
                    if (checked && visible.length === 1) chip.title = strings.keepOne;
                    chip.addEventListener('click', () => {
                        const next = checked ? visible.filter(name => name !== column.name) : [...visible, column.name];
                        if (!next.length) return;
                        commit(model, next);
                        focus(model, column.name, '[data-column-toggle]');
                    });
                    chips.appendChild(chip);
                });
                section.appendChild(chips);
                host.appendChild(section);
            });
        }

        hidden.addEventListener('change', () => { if (!writing) render(); });
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
