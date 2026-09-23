(function () {
    'use strict';

    const TERMINAL = new Set(['completed', 'failed']);
    const ICONS = { ok: 'bi-check-circle', warn: 'bi-exclamation-triangle', fail: 'bi-x-circle' };

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
        const statusEl = root.querySelector('[data-dlux-ops-status]');
        const findingsEl = root.querySelector('[data-dlux-ops-findings]');
        const repairsWrap = root.querySelector('[data-dlux-ops-repairs]');
        const diffsEl = root.querySelector('[data-dlux-ops-diffs]');
        const confirmWrap = root.querySelector('[data-dlux-ops-confirm]');
        const confirmNote = root.querySelector('[data-dlux-ops-confirm-note]');
        const submitButton = root.querySelector('[data-dlux-ops-submit]');
        const cancelButton = root.querySelector('[data-dlux-ops-cancel]');
        const passwordInput = root.querySelector('[data-dlux-ops-password]');
        const buttons = Array.from(root.querySelectorAll('[data-dlux-ops-run]'));
        const canManage = root.dataset.canManage === 'true';
        let operations = [];
        let pending = '';
        let pollTimer = null;

        function setStatus(text) {
            if (statusEl) { statusEl.textContent = text || ''; }
        }

        function spec(name) {
            return operations.find((operation) => operation.name === name) || null;
        }

        // An operation the resident Composer is too old to perform is disabled
        // with its reason, rather than offered and then failed on a timeout.
        function applyAvailability(busy) {
            buttons.forEach((button) => {
                const operation = spec(button.dataset.dluxOpsRun);
                const blocked = Boolean(operation && operation.available === false);
                button.disabled = busy || blocked || !canManage;
                button.title = blocked ? operation.unavailable_reason : '';
            });
            if (submitButton) { submitButton.disabled = busy; }
        }

        function closeConfirm() {
            pending = '';
            if (confirmWrap) { confirmWrap.hidden = true; }
            if (passwordInput) { passwordInput.value = ''; }
        }

        function openConfirm(operation) {
            const operationSpec = spec(operation);
            pending = operation;
            if (confirmNote) { confirmNote.textContent = operationSpec ? operationSpec.label : ''; }
            if (submitButton) {
                submitButton.textContent = (operationSpec && operationSpec.label)
                    || root.dataset.labelConfirm || 'Confirm';
            }
            if (confirmWrap) { confirmWrap.hidden = false; }
            if (passwordInput) { passwordInput.focus(); }
        }

        // Composer's findings and diffs are data: they become text nodes on
        // elements this file creates, never innerHTML.
        function renderFindings(run) {
            if (!findingsEl) { return; }
            findingsEl.innerHTML = '';
            ((run && run.findings) || []).forEach((finding) => {
                const level = String(finding.level || 'ok').toLowerCase();
                const item = document.createElement('li');
                item.className = `dlux-ops-finding dlux-ops-finding--${level}`;
                const icon = document.createElement('i');
                icon.className = `bi ${ICONS[level] || ICONS.ok}`;
                item.appendChild(icon);
                const body = document.createElement('div');
                const name = document.createElement('span');
                name.className = 'dlux-ops-finding-name';
                name.textContent = String(finding.name || '');
                body.appendChild(name);
                const message = document.createElement('span');
                message.className = 'dlux-ops-finding-message';
                message.textContent = String(finding.message || '');
                body.appendChild(message);
                if (finding.fix) {
                    const fix = document.createElement('span');
                    fix.className = 'dlux-ops-finding-fix small text-muted';
                    fix.textContent = String(finding.fix);
                    body.appendChild(fix);
                }
                item.appendChild(body);
                findingsEl.appendChild(item);
            });
        }

        function renderRepairs(run) {
            const applyButton = buttons.find((button) => button.dataset.dluxOpsRun === 'check-fix-apply');
            const repairs = ((run && run.repairs) || []).filter((repair) => repair.diff);
            const fromCheck = Boolean(run && run.operation === 'check' && run.status === 'completed');
            if (diffsEl) { diffsEl.innerHTML = ''; }
            if (repairsWrap) { repairsWrap.hidden = !(fromCheck && repairs.length); }
            // The apply exists only once a check has found something to repair.
            if (applyButton) { applyButton.hidden = !(fromCheck && repairs.length); }
            if (!fromCheck || !repairs.length || !diffsEl) { return; }
            repairs.forEach((repair) => {
                const block = document.createElement('div');
                block.className = 'dlux-ops-repair';
                const title = document.createElement('div');
                title.className = 'small fw-semibold';
                title.textContent = [repair.name, (repair.files || []).join(', ')].filter(Boolean).join(' — ');
                block.appendChild(title);
                const diff = document.createElement('pre');
                diff.className = 'dlux-ops-diff';
                diff.textContent = repair.diff;
                block.appendChild(diff);
                if (repair.note) {
                    const note = document.createElement('div');
                    note.className = 'small text-muted';
                    note.textContent = repair.note;
                    block.appendChild(note);
                }
                diffsEl.appendChild(block);
            });
        }

        function summaryText(run) {
            const summary = (run && run.summary) || {};
            if (!summary.fail && !summary.warn) { return root.dataset.labelClean || 'No problems found.'; }
            return (root.dataset.labelSummary || '{fail} problem(s), {warn} warning(s)')
                .replace('{fail}', String(summary.fail || 0))
                .replace('{warn}', String(summary.warn || 0));
        }

        function render(payload) {
            if (payload && Array.isArray(payload.operations)) { operations = payload.operations; }
            const run = payload && payload.run;
            const composer = payload && payload.composer_version;
            if (!run) {
                applyAvailability(false);
                setStatus(composer
                    ? `${root.dataset.labelComposer || 'Resident Composer'} ${composer}`
                    : (root.dataset.labelNever || 'Not run yet.'));
                return;
            }
            renderFindings(run);
            renderRepairs(run);
            if (!TERMINAL.has(run.status)) {
                applyAvailability(true);
                setStatus(root.dataset.labelRunning || 'Running on the deployment…');
                return;
            }
            applyAvailability(false);
            if (run.status === 'failed') {
                setStatus(run.error || 'The operation failed.');
            } else if (run.operation === 'check') {
                setStatus(summaryText(run));
            } else {
                setStatus(`${(spec(run.operation) || {}).label || run.operation} ✓`);
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
            applyAvailability(true);
            try {
                const data = await jsonRequest(root.dataset.runUrl, { method: 'POST', body });
                closeConfirm();
                render({ operations, run: data.run });
                schedulePoll();
            } catch (exc) {
                applyAvailability(false);
                setStatus(exc.message || 'Request failed');
            }
        }

        buttons.forEach((button) => {
            button.addEventListener('click', () => {
                const operation = button.dataset.dluxOpsRun;
                // Anything that writes to the deployment asks for the password
                // in the same request, exactly as applying an update does.
                if ((spec(operation) || {}).changes_deployment) {
                    openConfirm(operation);
                    return;
                }
                run(operation);
            });
        });

        if (submitButton) {
            submitButton.addEventListener('click', () => {
                if (!pending) { return; }
                run(pending, { current_password: passwordInput ? passwordInput.value : '' });
            });
        }
        if (cancelButton) { cancelButton.addEventListener('click', closeConfirm); }
        if (passwordInput) {
            passwordInput.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' && submitButton) { event.preventDefault(); submitButton.click(); }
            });
        }

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
