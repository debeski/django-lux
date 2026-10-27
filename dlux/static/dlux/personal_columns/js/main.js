(function () {
    'use strict';
    function init(form) {
        if (form.dataset.personalColumnsReady) return;
        form.dataset.personalColumnsReady = 'true';
        const list = form.querySelector('[data-personal-columns-list]');
        const field = form.querySelector('[data-personal-columns-value]');
        const defaults = JSON.parse(form.dataset.defaultOrder);
        const columns = new Map();
        const visibility = {show:form.dataset.show, hide:form.dataset.hide, keepOne:form.dataset.keepOne};
        let dragging = null;
        const reset = document.querySelector('[data-personal-columns-reset]');
        const rows = () => Array.from(list.children);
        const shownCount = () => [...columns.values()].filter(column => column.visible).length;
        function move(cell, offset) {
            const sibling = offset < 0 ? cell.previousElementSibling : cell.nextElementSibling;
            if (!sibling) return;
            list.insertBefore(offset < 0 ? cell : sibling, offset < 0 ? sibling : cell);
            commit();
            cell.querySelector('[data-column-handle]').focus({preventScroll:true});
        }
        for (const placeholder of rows()) {
            const name = placeholder.dataset.columnName;
            const column = {label:placeholder.dataset.columnLabel, visible:placeholder.dataset.columnVisible === 'true'};
            const {cell, handle, arrows, eye} = window.DluxColumnStrip.header({
                name, label:column.label, enabled:column.visible, previous:form.dataset.previous, next:form.dataset.next,
                visibility,
            });
            column.cell = cell;
            column.arrows = arrows;
            column.eye = eye;
            columns.set(name, column);
            cell.dataset.columnName = name;
            cell.draggable = true;
            handle.dataset.columnHandle = '';
            eye.addEventListener('click', () => {
                if (column.visible && shownCount() === 1) return;
                column.visible = !column.visible;
                commit();
            });
            handle.addEventListener('keydown', event => {
                if (!['ArrowLeft','ArrowRight'].includes(event.key)) return;
                event.preventDefault();
                move(cell, (event.key === 'ArrowRight' ? 1 : -1) * (getComputedStyle(list).direction === 'rtl' ? -1 : 1));
            });
            arrows.forEach((arrow, index) => arrow.addEventListener('click', () => move(cell, index ? 1 : -1)));
            cell.addEventListener('dragstart', event => {
                dragging = cell;
                cell.classList.add('is-dragging');
                event.dataTransfer.setData('text/plain', name);
            });
            cell.addEventListener('dragover', event => { if (dragging && dragging !== cell) event.preventDefault(); });
            cell.addEventListener('drop', event => {
                if (!dragging || dragging === cell) return;
                event.preventDefault();
                const rect = cell.getBoundingClientRect();
                const after = (event.clientX > rect.left + rect.width / 2) !== (getComputedStyle(list).direction === 'rtl');
                list.insertBefore(dragging, after ? cell.nextSibling : cell);
                commit();
            });
            cell.addEventListener('dragend', () => { cell.classList.remove('is-dragging'); dragging = null; });
            placeholder.replaceWith(cell);
        }
        function paint() {
            rows().forEach((cell, index, all) => {
                const column = columns.get(cell.dataset.columnName);
                cell.classList.toggle('is-removed', !column.visible);
                window.DluxColumnStrip.setVisibility(column.eye, column.visible, visibility, column.label,
                    column.visible && shownCount() === 1);
                column.arrows[0].disabled = index === 0;
                column.arrows[1].disabled = index === all.length - 1;
            });
            if (reset) reset.disabled = shownCount() === columns.size && JSON.stringify(rows().map(row => row.dataset.columnName)) === JSON.stringify(defaults);
        }
        function commit() {
            field.value = JSON.stringify({order:rows().map(row => row.dataset.columnName),
                hidden:rows().filter(row => !columns.get(row.dataset.columnName).visible).map(row => row.dataset.columnName).sort()});
            field.dispatchEvent(new Event('input', {bubbles:true}));
            paint();
        }
        reset?.addEventListener('click', () => {
            defaults.forEach(name => { const column = columns.get(name);column.visible = true;list.appendChild(column.cell); });
            commit();
        });
        paint();
    }
    function boot(scope) {
        (scope || document).querySelectorAll('[data-personal-columns]').forEach(init);
        (scope || document).querySelectorAll('[data-personal-columns-launch]').forEach(button => {
            if (button.dataset.placed) return;
            const table = button.closest('.dlux-table-shell');
            if (!table) return;
            const area = table.closest('.modal') || table.closest('main') || document;
            const ribbon = [...area.querySelectorAll('.dlux-ribbon-header')]
                .filter(node => node.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).at(-1);
            let host = ribbon?.querySelector('.dlux-ribbon-actions');
            if (ribbon && !host) {
                host = document.createElement('div');host.className = 'dlux-ribbon-actions';ribbon.appendChild(host);
            }
            host ||= table.querySelector('.dlux-table-footer-meta') || table.querySelector('.dlux-table-head-content');
            if (!host) return;
            button.dataset.placed = 'true';
            host.appendChild(button);
        });
    }
    document.addEventListener('dlux:modal-content-loaded', event => boot(event.target));
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => boot(document));
    else boot(document);
}());
