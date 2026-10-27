(function () {
    'use strict';
    function node(tag, css, text) {
        const element = document.createElement(tag);
        element.className = css;
        if (text !== undefined) element.textContent = text;
        return element;
    }
    function header(options) {
        const cell = node('div', 'dlux-table-columns__header');
        cell.dataset.columnHeader = options.name;
        cell.classList.toggle('is-removed', !options.enabled);
        cell.classList.toggle('is-active', Boolean(options.selected));
        const handle = node('button', 'btn btn-sm dlux-table-columns__handle', options.label);
        handle.type = 'button';
        handle.disabled = Boolean(options.disabled);
        if (/^bi-[a-z0-9-]+$/.test(options.icon || '')) {
            const glyph = node('i', 'bi ' + options.icon + ' me-1');
            glyph.setAttribute('aria-hidden', 'true');
            handle.prepend(glyph);
        }
        cell.appendChild(handle);
        // Optional per-column eye (the personal organizer): it carries the
        // shown/hidden state, so no inspector is needed to change it.
        let eye = null;
        if (options.visibility) {
            eye = node('button', 'btn btn-sm px-1 dlux-table-columns__eye');
            eye.type = 'button';
            eye.appendChild(node('i', 'bi'));
            cell.classList.add('dlux-table-columns__header--eye');
            cell.insertBefore(eye, handle);
            setVisibility(eye, options.enabled, options.visibility, options.label);
        }
        const arrows = [-1, 1].map(offset => {
            const button = node('button', 'btn btn-sm px-1');
            const label = offset < 0 ? options.previous : options.next;
            button.type = 'button';
            button.title = label;
            button.setAttribute('aria-label', label + ': ' + options.label);
            button.dataset.columnMove = String(offset);
            const icon = node('i', 'bi dlux-table-columns__arrow bi-chevron-' + (offset < 0 ? 'left' : 'right'));
            icon.setAttribute('aria-hidden', 'true');
            button.appendChild(icon);
            cell.appendChild(button);
            return button;
        });
        return {cell, handle, arrows, eye};
    }
    // labels: {show, hide, keepOne}; `locked` keeps the last shown column on.
    function setVisibility(eye, shown, labels, columnLabel, locked) {
        const action = shown ? labels.hide : labels.show;
        eye.firstChild.className = 'bi ' + (shown ? 'bi-eye' : 'bi-eye-slash');
        eye.firstChild.setAttribute('aria-hidden', 'true');
        eye.setAttribute('aria-pressed', String(!shown));
        eye.setAttribute('aria-label', action + ': ' + columnLabel);
        eye.disabled = Boolean(locked);
        eye.title = locked && labels.keepOne ? labels.keepOne : action;
    }
    window.DluxColumnStrip = {header, setVisibility};
}());
