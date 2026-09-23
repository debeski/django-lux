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
            throw new Error((payload && payload.error) || `Request failed (${response.status})`);
        }
        return payload;
    }

    function init(root) {
        const statusEl = root.querySelector('[data-dlux-ops-status]');
        const findingsEl = root.querySelector('[data-dlux-ops-findings]');
        const buttons = Array.from(root.querySelectorAll('[data-dlux-ops-run]'));
        const repairsWrap = root.querySelector('[data-dlux-ops-repairs]');
        const diffsEl = root.querySelector('[data-dlux-ops-diffs]');
        const applyWrap = root.querySelector('[data-dlux-ops-apply-wrap]');
        const applyButton = root.querySelector('[data-dlux-ops-apply]');
        const passwordInput = root.querySelector('[data-dlux-ops-password]');
        let pollTimer = null;

        function setStatus(text) {
            if (statusEl) { statusEl.textContent = text || ''; }
        }

        function setBusy(busy) {
            buttons.forEach((button) => { button.disabled = busy; });
            if (applyButton) { applyButton.disabled = busy; }
        }

        // A repair is shown as Composer's own unified diff, as text. The
        // operator confirms THIS, and the apply refuses if the files moved.
        function renderRepairs(run) {
            if (!repairsWrap || !diffsEl) { return; }
            const repairs = (run && run.repairs) || [];
            const previewed = run && run.operation === 'check-fix-preview' && run.status === 'completed';
            diffsEl.innerHTML = '';
            if (!repairs.length) {
                repairsWrap.hidden = !previewed;
                if (previewed) {
                    const none = document.createElement('div');
                    none.className = 'small text-muted';
                    none.textContent = root.dataset.labelNoRepairs || 'Nothing to repair.';
                    diffsEl.appendChild(none);
                }
                if (applyWrap) { applyWrap.hidden = true; }
                return;
            }
            repairs.forEach((repair) => {
                const block = document.createElement('div');
                block.className = 'dlux-ops-repair';
                const title = document.createElement('div');
                title.className = 'small fw-semibold';
                title.textContent = [repair.name, (repair.files || []).join(', ')].filter(Boolean).join(' — ');
                block.appendChild(title);
                if (repair.diff) {
                    const diff = document.createElement('pre');
                    diff.className = 'dlux-ops-diff';
                    diff.textContent = repair.diff;
                    block.appendChild(diff);
                }
                if (repair.note) {
                    const note = document.createElement('div');
                    note.className = 'small text-muted';
                    note.textContent = repair.note;
                    block.appendChild(note);
                }
                diffsEl.appendChild(block);
            });
            repairsWrap.hidden = false;
            if (applyWrap) {
                // Only a preview offers the apply, and only while it is current.
                applyWrap.hidden = !previewed || !repairs.some((repair) => repair.diff);
            }
        }

        // Composer's findings are data, not markup: each one becomes text nodes
        // on elements this file creates, never innerHTML.
        function renderFindings(run) {
            if (!findingsEl) { return; }
            findingsEl.innerHTML = '';
            const findings = (run && run.findings) || [];
            findings.forEach((finding) => {
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

        function summaryText(run) {
            const summary = (run && run.summary) || {};
            if (!summary.total) { return root.dataset.labelClean || 'No problems found.'; }
            if (!summary.fail && !summary.warn) { return root.dataset.labelClean || 'No problems found.'; }
            return (root.dataset.labelSummary || '{fail} problem(s), {warn} warning(s)')
                .replace('{fail}', String(summary.fail || 0))
                .replace('{warn}', String(summary.warn || 0));
        }

        function render(run) {
            if (!run) {
                setStatus(root.dataset.labelNever || 'Not run yet.');
                setBusy(false);
                return;
            }
            renderFindings(run);
            renderRepairs(run);
            if (!TERMINAL.has(run.status)) {
                setStatus(root.dataset.labelRunning || 'Running on the deployment…');
                setBusy(true);
                return;
            }
            setBusy(false);
            setStatus(run.status === 'failed' ? (run.error || 'The operation failed.') : summaryText(run));
        }

        async function refresh() {
            try {
                const data = await jsonRequest(root.dataset.stateUrl, { method: 'GET' });
                render(data.run);
                if (data.run && !TERMINAL.has(data.run.status)) {
                    schedulePoll();
                }
            } catch (_error) {
                // A transient failure must not wipe what is already rendered.
            }
        }

        function schedulePoll() {
            window.clearTimeout(pollTimer);
            pollTimer = window.setTimeout(refresh, 2000);
        }

        async function runOperation(operation, extra) {
            const body = new FormData();
            body.append('operation', operation);
            Object.entries(extra || {}).forEach(([key, value]) => body.append(key, value));
            setBusy(true);
            try {
                const data = await jsonRequest(root.dataset.runUrl, { method: 'POST', body });
                render(data.run);
                schedulePoll();
            } catch (exc) {
                setBusy(false);
                setStatus(exc.message || 'Request failed');
            }
        }

        if (applyButton) {
            applyButton.addEventListener('click', async () => {
                const password = passwordInput ? passwordInput.value : '';
                await runOperation('check-fix-apply', { current_password: password });
                if (passwordInput) { passwordInput.value = ''; }
            });
        }

        buttons.forEach((button) => {
            button.addEventListener('click', async () => {
                const body = new FormData();
                body.append('operation', button.dataset.dluxOpsRun);
                setBusy(true);
                try {
                    const data = await jsonRequest(root.dataset.runUrl, { method: 'POST', body });
                    render(data.run);
                    schedulePoll();
                } catch (exc) {
                    setBusy(false);
                    setStatus(exc.message || 'Request failed');
                }
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
