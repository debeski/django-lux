(function () {
    'use strict';

    const DENSITY_VALUES = new Set(['dense', 'balanced', 'roomy']);
    const COLUMN_RESIZE_MIN_WIDTH = 48;
    const COLUMN_RESIZE_KEY_PREFIX = 'dlux.table.columnWidths.v1:';
    let activeColumnResize = null;

    function syncDensityOptions(activeDensity) {
        document.querySelectorAll('[data-dlux-table-density-inline]').forEach((group) => {
            group.querySelectorAll('[data-dlux-table-density-option]').forEach((option) => {
                const isActive = option.getAttribute('data-dlux-table-density-option') === activeDensity;
                option.classList.toggle('is-active', isActive);
                option.setAttribute('aria-pressed', isActive ? 'true' : 'false');
            });
        });
    }

    function syncTableShells(activeDensity) {
        document.querySelectorAll('.dlux-table-shell[data-dlux-table-density]').forEach((shell) => {
            if (shell.hasAttribute('data-dlux-table-density-locked')) {
                return;
            }
            shell.setAttribute('data-dlux-table-density', activeDensity);
        });
    }

    function persistDensity(activeDensity) {
        if (typeof window.updatePreferences === 'function') {
            window.updatePreferences({ table_density: activeDensity });
            return;
        }

        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
        if (!csrfToken) {
            return;
        }

        const url = window.dluxEndpoint
            ? window.dluxEndpoint('preferencesUpdate', null, '/sys/api/preferences/update/')
            : (window.dluxUrl ? window.dluxUrl('/sys/api/preferences/update/') : '/sys/api/preferences/update/');
        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            body: JSON.stringify({ table_density: activeDensity }),
        }).catch((error) => {
            console.error('Failed to save table density preference:', error);
        });
    }

    function tableColumnResizingEnabled() {
        return document.body?.dataset?.dluxTableResize !== 'off';
    }

    function storageAvailable() {
        try {
            return Boolean(window.localStorage);
        } catch (error) {
            return false;
        }
    }

    function loadColumnWidths(tableKey) {
        if (!tableKey || !storageAvailable()) {
            return {};
        }
        try {
            const raw = window.localStorage.getItem(COLUMN_RESIZE_KEY_PREFIX + tableKey);
            const parsed = raw ? JSON.parse(raw) : {};
            return parsed && typeof parsed === 'object' ? parsed : {};
        } catch (error) {
            return {};
        }
    }

    function saveColumnWidths(tableKey, widths) {
        if (!tableKey || !storageAvailable()) {
            return;
        }
        try {
            window.localStorage.setItem(COLUMN_RESIZE_KEY_PREFIX + tableKey, JSON.stringify(widths || {}));
        } catch (error) {
            // Widths are a convenience preference; quota/privacy failures are harmless.
        }
    }

    function clearColumnWidths(tableKey) {
        if (!tableKey || !storageAvailable()) {
            return;
        }
        try {
            window.localStorage.removeItem(COLUMN_RESIZE_KEY_PREFIX + tableKey);
        } catch (error) {
            // Ignore best-effort reset failures.
        }
    }

    function getResizableTableParts(shell) {
        const table = shell?.querySelector?.('.dlux-data-table');
        const headers = table?.tHead?.rows?.length ? Array.from(table.tHead.rows[0].cells) : [];
        const cols = table ? Array.from(table.querySelectorAll('colgroup > col')) : [];
        if (!table || !headers.length || cols.length !== headers.length) {
            return null;
        }
        return { table, headers, cols };
    }

    function columnNameFor(headers, cols, index) {
        return (
            headers[index]?.getAttribute('data-dlux-table-col')
            || cols[index]?.getAttribute('data-dlux-table-col')
            || String(index)
        );
    }

    function numericWidth(value) {
        const width = Number(value);
        if (!Number.isFinite(width)) {
            return null;
        }
        return Math.max(1, Math.round(width));
    }

    function currentColumnWidths(headers) {
        return headers.map((header) => Math.max(
            1,
            Math.round(header.getBoundingClientRect().width || COLUMN_RESIZE_MIN_WIDTH)
        ));
    }

    function redistributeColumnWidths(startWidths, index, desiredWidth) {
        const widths = startWidths.map((width) => numericWidth(width) || 1);
        const totalWidth = widths.reduce((total, width) => total + width, 0);
        if (widths.length < 2 || index < 0 || index >= widths.length || totalWidth <= 0) {
            return widths;
        }

        // Keep one column from forcing the table wider than its scroll viewport.
        // On very narrow screens the minimum scales down so the table still fits.
        const minimumWidth = Math.min(
            COLUMN_RESIZE_MIN_WIDTH,
            Math.max(1, Math.floor(totalWidth / (widths.length + 1)))
        );
        const otherIndexes = widths.map((_width, columnIndex) => columnIndex).filter(
            (columnIndex) => columnIndex !== index
        );
        const maximumWidth = totalWidth - (minimumWidth * otherIndexes.length);
        const targetWidth = Math.min(maximumWidth, Math.max(minimumWidth, Math.round(desiredWidth)));
        const remainingWidth = totalWidth - targetWidth;
        const distributableWidth = remainingWidth - (minimumWidth * otherIndexes.length);
        const weights = otherIndexes.map((columnIndex) => Math.max(0, widths[columnIndex] - minimumWidth));
        const totalWeight = weights.reduce((total, weight) => total + weight, 0);
        let allocatedWidth = 0;

        widths[index] = targetWidth;
        otherIndexes.forEach((columnIndex, offset) => {
            const isLast = offset === otherIndexes.length - 1;
            const share = isLast
                ? distributableWidth - allocatedWidth
                : Math.floor(distributableWidth * (
                    totalWeight > 0 ? weights[offset] / totalWeight : 1 / otherIndexes.length
                ));
            widths[columnIndex] = minimumWidth + share;
            allocatedWidth += share;
        });
        return widths;
    }

    function applyColumnWidths(table, cols, widths) {
        const normalizedWidths = widths.map((width) => numericWidth(width) || 1);
        const totalWidth = normalizedWidths.reduce((total, width) => total + width, 0);
        normalizedWidths.forEach((width, index) => {
            if (cols[index]) {
                cols[index].style.width = `${(width / totalWidth) * 100}%`;
            }
        });
        if (totalWidth > 0) {
            table.classList.add('is-dlux-column-resized');
        }
    }

    function resetTableColumnWidths(shell) {
        const parts = getResizableTableParts(shell);
        if (!parts) {
            return;
        }
        parts.cols.forEach((col) => {
            col.style.width = '';
        });
        parts.table.classList.remove('is-dlux-column-resized');
        clearColumnWidths(shell.getAttribute('data-dlux-table-key') || '');
    }

    function persistedWidthsForShell(shell, headers, cols) {
        const tableKey = shell.getAttribute('data-dlux-table-key') || '';
        const stored = loadColumnWidths(tableKey);
        return headers.map((_header, index) => numericWidth(stored[columnNameFor(headers, cols, index)]));
    }

    function applyPersistedColumnWidths(shell) {
        const parts = getResizableTableParts(shell);
        if (!parts) {
            return;
        }
        const storedWidths = persistedWidthsForShell(shell, parts.headers, parts.cols);
        if (!storedWidths.some((width) => width !== null)) {
            return;
        }
        const fallbackWidths = currentColumnWidths(parts.headers);
        const widths = storedWidths.map((width, index) => width || fallbackWidths[index]);
        applyColumnWidths(parts.table, parts.cols, widths);
    }

    function initResizableTable(shell) {
        if (!shell || shell.getAttribute('data-dlux-table-resizable') !== 'true') {
            return;
        }
        if (shell.hasAttribute('data-dlux-table-resize-ready')) {
            return;
        }
        shell.setAttribute('data-dlux-table-resize-ready', 'true');
        applyPersistedColumnWidths(shell);
    }

    function initResizableTables(root) {
        const scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('.dlux-table-shell[data-dlux-table-resizable="true"]').forEach(initResizableTable);
        if (scope.matches?.('.dlux-table-shell[data-dlux-table-resizable="true"]')) {
            initResizableTable(scope);
        }
    }

    function persistColumnWidths(shell, headers, cols, widths) {
        const tableKey = shell.getAttribute('data-dlux-table-key') || '';
        if (!tableKey) {
            return;
        }
        const stored = {};
        widths.forEach((width, index) => {
            stored[columnNameFor(headers, cols, index)] = numericWidth(width) || COLUMN_RESIZE_MIN_WIDTH;
        });
        saveColumnWidths(tableKey, stored);
    }

    function stopActiveColumnResize() {
        if (!activeColumnResize) {
            return;
        }
        persistColumnWidths(
            activeColumnResize.shell,
            activeColumnResize.headers,
            activeColumnResize.cols,
            activeColumnResize.widths
        );
        try {
            activeColumnResize.handle.releasePointerCapture(activeColumnResize.pointerId);
        } catch (error) {
            // Pointer capture may already be released by the browser.
        }
        document.body?.classList.remove('dlux-table-resizing');
        activeColumnResize = null;
    }

    function startColumnResize(event, handle) {
        if (!tableColumnResizingEnabled() || (event.button !== undefined && event.button !== 0)) {
            return;
        }
        const shell = handle.closest('.dlux-table-shell[data-dlux-table-resizable="true"]');
        const th = handle.closest('th');
        if (!shell || !th) {
            return;
        }
        initResizableTable(shell);
        const parts = getResizableTableParts(shell);
        if (!parts) {
            return;
        }
        const index = parts.headers.indexOf(th);
        if (index < 0) {
            return;
        }

        const startWidths = currentColumnWidths(parts.headers);
        const widths = [...startWidths];
        applyColumnWidths(parts.table, parts.cols, widths);
        activeColumnResize = {
            shell,
            handle,
            table: parts.table,
            headers: parts.headers,
            cols: parts.cols,
            index,
            startX: event.clientX,
            startWidths,
            widths,
            directionFactor: getComputedStyle(parts.table).direction === 'rtl' ? -1 : 1,
            pointerId: event.pointerId,
        };
        document.body?.classList.add('dlux-table-resizing');
        try {
            handle.setPointerCapture(event.pointerId);
        } catch (error) {
            // Older pointer implementations can still resize through document events.
        }
        event.preventDefault();
        event.stopPropagation();
    }

    function updateActiveColumnResize(event) {
        if (!activeColumnResize) {
            return;
        }
        const state = activeColumnResize;
        const delta = (event.clientX - state.startX) * state.directionFactor;
        state.widths = redistributeColumnWidths(
            state.startWidths,
            state.index,
            state.startWidths[state.index] + delta
        );
        applyColumnWidths(state.table, state.cols, state.widths);
        event.preventDefault();
    }

    function nudgeColumnWidth(handle, amount) {
        if (!tableColumnResizingEnabled()) {
            return;
        }
        const shell = handle.closest('.dlux-table-shell[data-dlux-table-resizable="true"]');
        const th = handle.closest('th');
        if (!shell || !th) {
            return;
        }
        initResizableTable(shell);
        const parts = getResizableTableParts(shell);
        if (!parts) {
            return;
        }
        const index = parts.headers.indexOf(th);
        if (index < 0) {
            return;
        }
        const widths = currentColumnWidths(parts.headers);
        const directionFactor = getComputedStyle(parts.table).direction === 'rtl' ? -1 : 1;
        const resizedWidths = redistributeColumnWidths(
            widths,
            index,
            widths[index] + (amount * directionFactor)
        );
        applyColumnWidths(parts.table, parts.cols, resizedWidths);
        persistColumnWidths(shell, parts.headers, parts.cols, resizedWidths);
    }

    function applyDensity(activeDensity, persistPreference) {
        if (!DENSITY_VALUES.has(activeDensity)) {
            return;
        }

        syncDensityOptions(activeDensity);
        syncTableShells(activeDensity);

        if (window.USER_PREFS) {
            window.USER_PREFS.table_density = activeDensity;
        }

        if (persistPreference) {
            persistDensity(activeDensity);
        }
    }

    window.applyDluxTableDensityPreview = function(activeDensity) {
        applyDensity(activeDensity, false);
    };

    document.addEventListener('click', (event) => {
        const option = event.target.closest('[data-dlux-table-density-option]');
        if (!option) {
            return;
        }

        const activeDensity = option.getAttribute('data-dlux-table-density-option');
        applyDensity(activeDensity, true);
    });

    document.addEventListener('pointerdown', (event) => {
        const handle = event.target.closest('[data-dlux-table-resize-handle]');
        if (handle) {
            startColumnResize(event, handle);
        }
    });

    document.addEventListener('pointermove', updateActiveColumnResize);
    document.addEventListener('pointerup', stopActiveColumnResize);
    document.addEventListener('pointercancel', stopActiveColumnResize);

    document.addEventListener('click', (event) => {
        if (event.target.closest('[data-dlux-table-resize-handle]')) {
            event.preventDefault();
            event.stopPropagation();
        }
    });

    document.addEventListener('dblclick', (event) => {
        const handle = event.target.closest('[data-dlux-table-resize-handle]');
        if (!handle || !tableColumnResizingEnabled()) {
            return;
        }
        resetTableColumnWidths(handle.closest('.dlux-table-shell[data-dlux-table-resizable="true"]'));
        event.preventDefault();
        event.stopPropagation();
    });

    document.addEventListener('keydown', (event) => {
        const handle = event.target.closest?.('[data-dlux-table-resize-handle]');
        if (!handle) {
            return;
        }
        if (event.key === 'ArrowLeft') {
            nudgeColumnWidth(handle, -16);
        } else if (event.key === 'ArrowRight') {
            nudgeColumnWidth(handle, 16);
        } else if (event.key === 'Delete' || event.key === 'Backspace' || event.key === 'Enter') {
            resetTableColumnWidths(handle.closest('.dlux-table-shell[data-dlux-table-resizable="true"]'));
        } else {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
    });

    document.addEventListener('DOMContentLoaded', () => {
        const initialDensity = (window.USER_PREFS && window.USER_PREFS.table_density) || null;
        if (DENSITY_VALUES.has(initialDensity)) {
            applyDensity(initialDensity, false);
        }
        initResizableTables(document);
    });

    if (document.readyState !== 'loading') {
        initResizableTables(document);
    }

    const observer = new MutationObserver((entries) => {
        entries.forEach((entry) => {
            entry.addedNodes.forEach((node) => {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    initResizableTables(node);
                }
            });
        });
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
})();
