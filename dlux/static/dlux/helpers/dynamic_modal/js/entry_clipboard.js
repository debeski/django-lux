(() => {
    'use strict';
    const script = document.currentScript;
    if (!script?.dataset.user?.trim()) return;
    const key = `dlux:entry-clipboard:${script.dataset.user}`;
    const labels = script.dataset;
    let nextId = 0;
    let state = { snippets: [] };
    try { state = JSON.parse(sessionStorage.getItem(key)) || state; } catch (_) {}
    if (!state || typeof state !== 'object') state = { snippets: [] };
    state = { snippets: Array.isArray(state.snippets) ? state.snippets.filter(item => typeof item === 'string').slice(0, 20) : [] };
    const save = () => {
        try { sessionStorage.setItem(key, JSON.stringify(state)); } catch (_) {}
    };
    const excluded = '[data-dlux-entry-clipboard="false"], .dlux-ribbon, [data-dlux-ribbon-autosubmit], '
        + '.dlux-reports-page, .dlux-report-builder, .dlux-user-report, [data-dlux-user-report]';
    const eligible = field => !field.closest(excluded)
        && field.name && !field.disabled && !field.readOnly
        && (field.tagName === 'TEXTAREA'
            || (field.tagName === 'INPUT' && ['text', 'search', 'tel', 'url', 'email', 'number', 'date'].includes(field.type)))
        && !/password|token|secret|csrf/i.test(field.name)
        && !/password|one-time-code|cc-/i.test(field.autocomplete || '');
    const fields = form => Array.from(form.elements).filter(eligible);
    function init(root) {
        window.dluxAssistedEntry?.scan(root);
        for (const form of root.querySelectorAll('form')) {
            const available = fields(form);
            if (!available.length || form.dataset.dluxClipboardReady) continue;
            form.dataset.dluxClipboardReady = 'true';
            let bar = form.querySelector('[data-dlux-assist-bar]');
            if (!bar) {
                bar = document.createElement('div');
                bar.className = 'dlux-assist-bar';
                bar.setAttribute('data-dlux-assist-bar', '');
                const legend = document.createElement('span');
                legend.className = 'dlux-assist-bar__legend';
                const magic = document.createElement('i');
                magic.className = 'bi bi-magic';
                magic.setAttribute('aria-hidden', 'true');
                legend.append(magic, ` ${window.DLUX_STRINGS?.assist_bar_legend || 'Assisted entry'}`);
                bar.append(legend);
                form.prepend(bar);
            }
            const trigger = document.createElement('button');
            trigger.type = 'button';
            trigger.className = 'btn btn-sm btn-outline-secondary dlux-entry-clipboard-trigger';
            trigger.title = labels.title;
            trigger.setAttribute('aria-label', labels.title);
            const icon = document.createElement('i');
            icon.className = 'bi bi-clipboard';
            icon.setAttribute('aria-hidden', 'true');
            trigger.append(icon);
            trigger.setAttribute('aria-haspopup', 'dialog');
            trigger.setAttribute('aria-expanded', 'false');
            bar.append(trigger);
            const tray = document.createElement('div');
            tray.className = 'dlux-entry-clipboard-popover';
            tray.setAttribute('popover', 'auto');
            tray.setAttribute('role', 'dialog');
            tray.setAttribute('aria-label', labels.title);
            tray.id = `dlux-entry-clipboard-${nextId++}`;
            trigger.setAttribute('aria-controls', tray.id);
            form.append(tray);
            let selection = null;
            const remember = field => { selection = { field, start: field.selectionStart, end: field.selectionEnd }; };
            const select = document.createElement('select');
            select.className = 'form-select form-select-sm';
            select.setAttribute('aria-label', labels.field);
            for (const field of available) {
                const option = document.createElement('option');
                option.value = field.name;
                const label = field.labels?.[0]?.cloneNode(true);
                label?.querySelectorAll('input, textarea, select').forEach(control => control.remove());
                option.textContent = label?.textContent.trim() || field.name;
                select.append(option);
            }
            const targetRow = document.createElement('div');
            targetRow.className = 'dlux-clipboard-controls';
            targetRow.append(select);
            tray.append(targetRow);
            const selected = () => available.find(field => field.name === select.value);
            for (const field of available) {
                field.addEventListener('focus', () => { select.value = field.name; remember(field); });
                field.addEventListener('select', () => remember(field));
                field.addEventListener('blur', () => remember(field));
            }
            select.addEventListener('change', () => { selection = null; });
            const position = () => {
                const rect = trigger.getBoundingClientRect();
                const width = Math.min(360, window.innerWidth - 24);
                tray.style.left = `${Math.max(12, Math.min(rect.left, window.innerWidth - width - 12))}px`;
                tray.style.top = `${Math.max(12, Math.min(rect.bottom + 6, window.innerHeight - tray.offsetHeight - 12))}px`;
                tray.style.maxHeight = `${window.innerHeight - parseFloat(tray.style.top) - 12}px`;
            };
            const open = () => {
                if (!tray.matches(':popover-open')) tray.showPopover();
                position();
                trigger.setAttribute('aria-expanded', 'true');
                select.focus();
            };
            trigger.addEventListener('click', () => tray.matches(':popover-open') ? tray.hidePopover() : open());
            tray.addEventListener('toggle', () => trigger.setAttribute('aria-expanded', String(tray.matches(':popover-open'))));
            tray.addEventListener('keydown', event => {
                if (event.key === 'Escape') {
                    event.preventDefault();
                    event.stopPropagation();
                    tray.hidePopover();
                    trigger.focus();
                }
            });
            form._dluxOpenClipboard = open;
            tray._dluxPosition = position;
            const button = (label, action, parent, icon) => {
                const node = document.createElement('button');
                node.type = 'button';
                node.className = 'btn btn-sm dlux-clipboard-action';
                node.title = label;
                node.setAttribute('aria-label', label);
                const glyph = document.createElement('i');
                glyph.className = `bi bi-${icon}`;
                glyph.setAttribute('aria-hidden', 'true');
                node.append(glyph);
                node.addEventListener('click', action);
                parent.append(node);
                return node;
            };
            const snippets = document.createElement('div');
            snippets.className = 'dlux-clipboard-list';
            const detail = document.createElement('div');
            detail.className = 'dlux-clipboard-detail';
            detail.hidden = true;
            const content = document.createElement('div');
            content.className = 'dlux-clipboard-content';
            button(labels.back || 'Back to snippets', () => {
                detail.hidden = true;
                snippets.hidden = false;
                search.focus();
                position();
            }, detail, 'arrow-left');
            detail.append(content);
            const search = document.createElement('input');
            search.type = 'search';
            search.className = 'form-control form-control-sm';
            search.placeholder = labels.search || 'Find a snippet';
            search.setAttribute('aria-label', search.placeholder);
            const searchRow = document.createElement('div');
            searchRow.className = 'dlux-clipboard-controls';
            searchRow.append(search);
            tray.append(searchRow);
            const paste = (snippet, replace) => {
                const field = selected();
                if (!field || !eligible(field)) return;
                const range = selection;
                field.focus();
                if (replace || typeof field.selectionStart !== 'number') field.value = snippet;
                else {
                    const cursor = range?.field === field ? range.end : field.selectionEnd;
                    field.setRangeText(snippet, cursor, cursor, 'end');
                }
                field.dispatchEvent(new Event('input', { bubbles: true }));
                field.dispatchEvent(new Event('change', { bubbles: true }));
                remember(field);
            };
            const render = () => {
                detail.hidden = true;
                snippets.hidden = false;
                snippets.replaceChildren();
                if (!state.snippets.length) snippets.textContent = labels.empty || 'Copy text from a field to save a snippet.';
                for (const snippet of state.snippets.filter(item => item.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()))) {
                    const row = document.createElement('div');
                    row.className = 'dlux-clipboard-row';
                    const entry = document.createElement('button');
                    entry.type = 'button';
                    entry.className = 'dlux-clipboard-entry';
                    entry.textContent = snippet;
                    entry.addEventListener('click', () => {
                        content.textContent = snippet;
                        snippets.hidden = true;
                        detail.hidden = false;
                        detail.querySelector('button').focus();
                        position();
                    });
                    row.append(entry);
                    button(labels.add || 'Add to field', () => paste(snippet, false), row, 'plus');
                    button(labels.replace || 'Replace field', () => paste(snippet, true), row, 'arrow-counterclockwise');
                    snippets.append(row);
                }
                if (tray.matches(':popover-open')) position();
            };
            button(labels.copy, () => {
                const field = selected();
                if (!field || !eligible(field)) return;
                const range = selection?.field === field ? selection : { start: field.selectionStart, end: field.selectionEnd };
                const snippet = (typeof range.start === 'number' && range.start !== range.end
                    ? field.value.slice(range.start, range.end) : field.value).slice(0, 2000);
                if (!snippet) return;
                state.snippets = [snippet, ...state.snippets.filter(item => item !== snippet)].slice(0, 20);
                save();
                render();
            }, targetRow, 'copy');
            button(labels.clear, () => { state.snippets = []; save(); render(); }, searchRow, 'x-lg');
            search.addEventListener('input', render);
            tray.append(snippets, detail);
            render();
        }
    }
    window.DluxEntryClipboard = {
        init,
    };
    window.addEventListener('dlux:clipboard:identity-changed', () => {
        state.snippets = [];
        for (const node of document.querySelectorAll('.dlux-entry-clipboard-popover, .dlux-entry-clipboard-trigger')) node.remove();
    });
    document.addEventListener('DOMContentLoaded', () => init(document));
    window.addEventListener('resize', () => {
        for (const panel of document.querySelectorAll('.dlux-entry-clipboard-popover:popover-open')) panel._dluxPosition();
    });
    document.addEventListener('keydown', event => {
        if (event.altKey && event.shiftKey && event.code === 'KeyC') {
            const form = document.activeElement?.closest('form');
            if (form?._dluxOpenClipboard) { event.preventDefault(); form._dluxOpenClipboard(); }
        }
    });
})();
