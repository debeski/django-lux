(function () {
    'use strict';
    let dragging = null;
    function formOf(node) {
        return node.closest('[data-personal-columns]') || document.querySelector('[data-personal-columns]');
    }
    function update(form) {
        const rows = Array.from(form.querySelectorAll('[data-column-name]'));
        const value = {order: rows.map(row => row.dataset.columnName),
            hidden: rows.filter(row => !row.querySelector('[data-column-visible]').checked).map(row => row.dataset.columnName).sort()};
        const field = form.querySelector('[data-personal-columns-value]');
        field.value = JSON.stringify(value);
        field.dispatchEvent(new Event('input', {bubbles: true}));
        const reset = document.querySelector('[data-personal-columns-reset]');
        if (reset) reset.disabled = !value.hidden.length && JSON.stringify(value.order) === form.dataset.defaultOrder.replace(/\s/g, '');
        rows.forEach((row, index) => {
            row.querySelector('[data-column-move="up"]').disabled = index === 0;
            row.querySelector('[data-column-move="down"]').disabled = index === rows.length - 1;
        });
    }
    document.addEventListener('change', event => {
        if (event.target.matches('[data-column-visible]')) update(formOf(event.target));
    });
    document.addEventListener('click', event => {
        const move = event.target.closest('[data-column-move]');
        const reset = event.target.closest('[data-personal-columns-reset]');
        if (!move && !reset) return;
        const form = formOf(move || reset);
        const list = form.querySelector('[data-personal-columns-list]');
        if (move) {
            const row = move.closest('[data-column-name]');
            const sibling = move.dataset.columnMove === 'up' ? row.previousElementSibling : row.nextElementSibling;
            if (sibling) list.insertBefore(move.dataset.columnMove === 'up' ? row : sibling, move.dataset.columnMove === 'up' ? sibling : row);
        } else {
            JSON.parse(form.dataset.defaultOrder).forEach(name => {
                const row = Array.from(list.children).find(item => item.dataset.columnName === name);
                row.querySelector('[data-column-visible]').checked = true;
                list.appendChild(row);
            });
        }
        update(form);
        if (reset) form.querySelector('[data-personal-columns-value]').value = JSON.stringify({reset: true});
    });
    document.addEventListener('dragstart', event => {
        dragging = event.target.closest('[data-personal-columns] [data-column-name]');
        if (dragging) { event.dataTransfer.setData('text/plain', dragging.dataset.columnName); event.dataTransfer.effectAllowed = 'move'; }
    });
    document.addEventListener('dragover', event => {
        const row = event.target.closest('[data-personal-columns] [data-column-name]');
        if (dragging && row && row.parentElement === dragging.parentElement) event.preventDefault();
    });
    document.addEventListener('drop', event => {
        const row = event.target.closest('[data-personal-columns] [data-column-name]');
        if (!dragging || !row || row.parentElement !== dragging.parentElement) return;
        event.preventDefault();
        const rect = row.getBoundingClientRect();
        row.parentElement.insertBefore(dragging, event.clientY > rect.top + rect.height / 2 ? row.nextSibling : row);
        update(formOf(row));
    });
    document.addEventListener('dragend', () => { dragging = null; });
})();
