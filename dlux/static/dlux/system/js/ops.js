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
        let pollTimer = null;

        function setStatus(text) {
            if (statusEl) { statusEl.textContent = text || ''; }
        }

        function setBusy(busy) {
            buttons.forEach((button) => { button.disabled = busy; });
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
