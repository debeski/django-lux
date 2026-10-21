// The resident Composer's row in the Updates card.
//
// One icon checks whether the channel publishes a newer Composer, a second
// appears only when there is one to install, and a tick says there is not — the
// same shape as the DjangoLux and application-image rows. Checking and repairing
// the deployment itself lives in the Operations panel (operations_panel.js).
(function () {
    'use strict';

    const TERMINAL = new Set(['completed', 'failed']);
    const TONE_GLYPH = { ok: 'bi-check-circle-fill', warn: 'bi-exclamation-triangle-fill', fail: 'bi-x-circle-fill' };
    const AGENT_OPERATIONS = new Set(['agent-check', 'agent-update']);

    function csrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.content || '';
    }

    async function jsonRequest(url, options) {
        const response = await fetch(url, {
            credentials: 'same-origin',
            headers: {
                Accept: 'application/json',
                'X-CSRFToken': csrfToken(),
                'X-Requested-With': 'XMLHttpRequest',
            },
            ...options,
        });
        let payload = null;
        try { payload = await response.json(); } catch (_error) { payload = null; }
        if (!response.ok || !payload || payload.ok === false) {
            throw new Error((payload && (payload.error || payload.message)) || `Request failed (${response.status})`);
        }
        return payload;
    }

    function init(root) {
        const labels = root.dataset;
        const canManage = root.dataset.canManage === 'true';
        const statusEl = root.querySelector('[data-dlux-ops-status]');
        const versionEl = root.querySelector('[data-dlux-ops-composer-version]');
        const targetEl = root.querySelector('[data-dlux-ops-composer-target]');
        const noticeEl = root.querySelector('[data-dlux-ops-composer-notice]');
        const checkButton = root.querySelector('[data-dlux-ops-check="agent-check"]');
        const updateButton = root.querySelector('[data-dlux-ops-open="agent-update"]');

        let state = { operations: [] };
        let pollTimer = null;
        let spinner = null;

        function spec(name) {
            return (state.operations || []).find((operation) => operation.name === name) || null;
        }

        function setStatus(text, isError) {
            if (!statusEl) { return; }
            statusEl.textContent = text || '';
            statusEl.hidden = !text;
            statusEl.classList.toggle('text-danger', Boolean(isError));
        }

        function startSpinner() {
            if (spinner || !checkButton) { return; }
            if (window.DluxLoadingButton) {
                spinner = window.DluxLoadingButton.start(checkButton);
            } else {
                checkButton.disabled = true;
            }
        }

        function stopSpinner() {
            if (spinner) { spinner.stop(); spinner = null; }
        }

        /** `base — Last check: <time>`, or `base` when nothing has checked yet. */
        function withCheckTime(element, iso) {
            if (!element) return;
            if (element.dataset.titleBase === undefined) { element.dataset.titleBase = element.title || ''; }
            const label = labels.labelLastCheck || 'Last check';
            element.title = iso
                ? `${element.dataset.titleBase} — ${label}: ${new Date(iso).toLocaleString()}`
                : element.dataset.titleBase;
            if (element.hasAttribute('aria-label')) { element.setAttribute('aria-label', element.title); }
        }

        function setGlyph(tone) {
            const glyph = checkButton?.querySelector('[data-dlux-ops-glyph]');
            if (!glyph) { return; }
            glyph.className = `bi ${TONE_GLYPH[tone] || 'bi-arrow-clockwise'}`;
            ['ok', 'warn', 'fail'].forEach((name) => checkButton.classList.toggle(`is-${name}`, tone === name));
        }

        function renderNotice() {
            if (!noticeEl) { return; }
            const behind = state.composer_behind;
            const template = behind && (behind.ops_blocked
                ? labels.labelComposerBehindHost
                : labels.labelComposerBehindCard);
            const bare = (value) => String(value || '').replace(/^v/, '');
            const resident = state.resident || {};
            const unknown = Boolean(resident.checked_at) && !resident.checked;
            noticeEl.textContent = template
                ? template.replace('{version}', bare(behind.version)).replace('{required}', bare(behind.required))
                : (unknown
                    ? (labels.labelComposerUnknown || 'Could not check for a Composer update: {reason}')
                        .replace('{reason}', resident.detail || '')
                    : '');
            noticeEl.hidden = !noticeEl.textContent;
        }

        function renderRow() {
            const resident = state.resident || {};
            const version = resident.version || state.composer_version || '';
            if (versionEl) { versionEl.textContent = version ? `v${String(version).replace(/^v/, '')}` : ''; }
            const available = Boolean(resident.update_available);
            if (targetEl) {
                targetEl.hidden = !available;
                targetEl.textContent = available ? `v${String(resident.published_version || '').replace(/^v/, '')}` : '';
            }
            if (updateButton) { updateButton.hidden = !(available && canManage); }
            withCheckTime(checkButton, resident.checked_at);
            withCheckTime(updateButton, resident.checked_at);
            // A tick means "checked, and there is nothing to install"; a check that
            // ran but could not read the registry says so instead of going quiet.
            const unknown = Boolean(resident.checked_at) && !resident.checked;
            setGlyph(unknown ? 'warn' : (resident.checked && !available ? 'ok' : ''));
            renderNotice();
        }

        function render(payload) {
            if (payload) { state = { ...state, ...payload }; }
            const run = state.run;
            const ours = Boolean(run && AGENT_OPERATIONS.has(run.operation));
            if (ours && !TERMINAL.has(run.status)) {
                startSpinner();
                setStatus(`${(spec(run.operation) || {}).label || run.operation}…`);
            } else {
                stopSpinner();
                setStatus(ours && run.status === 'failed' ? (run.error || 'The operation failed.') : '', true);
            }
            renderRow();
            if (checkButton) {
                const operation = spec('agent-check');
                const blocked = Boolean(operation && operation.available === false);
                const busy = Boolean(run && run.active);
                checkButton.disabled = blocked || !canManage || (busy && !spinner);
                if (blocked) { checkButton.title = operation.unavailable_reason; }
            }
        }

        async function refresh() {
            try {
                const data = await jsonRequest(root.dataset.stateUrl, { method: 'GET' });
                render(data);
                if (data.run && !TERMINAL.has(data.run.status)) { schedulePoll(); }
            } catch (_error) {
                // A transient failure must not wipe what is already rendered.
            }
        }

        function schedulePoll() {
            window.clearTimeout(pollTimer);
            pollTimer = window.setTimeout(refresh, 2000);
        }

        async function run(operation, extra) {
            const body = new FormData();
            body.append('operation', operation);
            Object.entries(extra || {}).forEach(([key, value]) => body.append(key, value));
            startSpinner();
            const data = await jsonRequest(root.dataset.runUrl, { method: 'POST', body });
            render({ run: data.run });
            schedulePoll();
        }

        checkButton?.addEventListener('click', () => {
            run('agent-check').catch((exc) => { stopSpinner(); setStatus(exc.message, true); });
        });
        updateButton?.addEventListener('click', () => {
            if (typeof window.dluxConfirmPassword !== 'function') { return; }
            window.dluxConfirmPassword({
                title: (spec('agent-update') || {}).label || labels.labelAgentUpdate || 'Update the Composer agent',
                description: labels.labelAgentUpdateNote || '',
                confirmLabel: labels.labelAgentUpdate || 'Update',
                requirePassword: true,
                icon: 'bi-arrow-down-circle',
                onConfirm: (password, { showError }) => run('agent-update', { current_password: password })
                    .then(() => true)
                    .catch((exc) => { stopSpinner(); showError(exc.message); return false; }),
            });
        });

        refresh();
    }

    function boot() {
        document.querySelectorAll('[data-dlux-ops]').forEach(init);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
}());
