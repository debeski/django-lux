// The Operations panel (Options > admin rail): check and repair the deployment,
// restart or recreate a service, and read a service's recent logs.
//
// Every action is one named operation sent to the same endpoint the Updates
// card uses (dlux_ops_run); the panel only renders state. Anything Composer
// returns — findings, diffs, service names, log lines — becomes text nodes,
// never HTML.
(function () {
    'use strict';

    const TERMINAL = new Set(['completed', 'failed']);
    const ICONS = { ok: 'bi-check-circle', warn: 'bi-exclamation-triangle', fail: 'bi-x-circle' };
    const PANEL_OPERATIONS = new Set([
        'check', 'check-fix-apply', 'services', 'service-start', 'service-stop', 'service-restart', 'service-recreate', 'logs-tail',
    ]);

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

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) { node.className = className; }
        if (text !== undefined) { node.textContent = String(text); }
        return node;
    }

    // Composer reports in English; `auto` keeps that text readable in an RTL page.
    function composerText(tag, className, text) {
        const node = element(tag, className, text);
        node.dir = 'auto';
        return node;
    }

    function init(root) {
        if (root.dataset.bound === 'true' || root.dataset.enabled !== 'true') { return; }
        root.dataset.bound = 'true';
        const labels = root.dataset;
        const errorEl = root.querySelector('[data-dlux-ops-panel-error]');
        const summaryEl = root.querySelector('[data-dlux-ops-panel-summary]');
        const statusEl = root.querySelector('[data-dlux-ops-panel-status]');
        const findingsEl = root.querySelector('[data-dlux-ops-panel-findings]');
        const noRepairEl = root.querySelector('[data-dlux-ops-panel-norepair]');
        const repairsWrap = root.querySelector('[data-dlux-ops-panel-repairs]');
        const diffsEl = root.querySelector('[data-dlux-ops-panel-diffs]');
        const applyButton = root.querySelector('[data-dlux-ops-panel-apply]');
        const servicesEl = root.querySelector('[data-dlux-ops-panel-services]');
        const findingsToggle = root.querySelector('[data-dlux-ops-panel-findings-toggle]');
        const logsAllButton = root.querySelector('[data-dlux-ops-panel-logs-all]');
        const logsTitle = root.querySelector('[data-dlux-ops-panel-logs-title]');
        const logsEl = root.querySelector('[data-dlux-ops-panel-logs]');
        const runButtons = Array.from(root.querySelectorAll('[data-dlux-ops-panel-run]'));

        let state = { operations: [] };
        let pollTimer = null;
        let spinner = null;
        let shownLogsToken = '';
        let refreshAfter = '';

        function spec(name) {
            return (state.operations || []).find((operation) => operation.name === name) || null;
        }

        function available(name) {
            const operation = spec(name);
            return Boolean(operation && operation.available !== false);
        }

        function setError(text) {
            if (!errorEl) { return; }
            errorEl.textContent = text || '';
            errorEl.hidden = !text;
        }

        function busy() {
            return Boolean(state.run && !TERMINAL.has(state.run.status));
        }

        function startSpinner(button) {
            stopSpinner();
            if (button && window.DluxLoadingButton) { spinner = window.DluxLoadingButton.start(button); }
        }

        function stopSpinner() {
            if (spinner) { spinner.stop(); spinner = null; }
        }

        function summaryText(run) {
            const summary = (run && run.summary) || {};
            if (!summary.total) { return labels.labelNever || 'Not checked yet'; }
            if (!summary.fail && !summary.warn) { return labels.labelClean || 'No problems found'; }
            return (labels.labelSummary || '{fail} problem(s), {warn} warning(s)')
                .replace('{fail}', String(summary.fail || 0))
                .replace('{warn}', String(summary.warn || 0));
        }

        function repairsOf(run) {
            return ((run && run.repairs) || []).filter((repair) => repair.diff);
        }

        function renderCheck() {
            const run = state.check;
            if (summaryEl) { summaryEl.textContent = summaryText(run); }
            if (findingsEl) {
                findingsEl.replaceChildren();
                ((run && run.findings) || []).forEach((finding) => {
                    const level = String(finding.level || 'ok').toLowerCase();
                    const item = element('li', `dlux-ops-finding dlux-ops-finding--${level}`);
                    item.appendChild(element('i', `bi ${ICONS[level] || ICONS.ok}`));
                    const body = element('div');
                    body.appendChild(composerText('span', 'dlux-ops-finding-name', finding.name || ''));
                    body.appendChild(composerText('span', 'dlux-ops-finding-message', finding.message || ''));
                    if (finding.fix) { body.appendChild(composerText('span', 'dlux-ops-finding-fix small text-muted', finding.fix)); }
                    item.appendChild(body);
                    findingsEl.appendChild(item);
                });
                const count = findingsEl.children.length;
                if (findingsToggle) {
                    findingsToggle.hidden = count <= 2;
                    const collapsed = findingsEl.classList.contains('is-collapsed');
                    findingsToggle.textContent = collapsed
                        ? (labels.labelShowAll || 'Show all ({count})').replace('{count}', String(count))
                        : (labels.labelShowLess || 'Show less');
                }
            }
            const repairs = repairsOf(run);
            if (diffsEl) {
                diffsEl.replaceChildren();
                repairs.forEach((repair) => {
                    const block = element('div', 'dlux-ops-repair');
                    block.appendChild(composerText('div', 'small fw-semibold',
                        [repair.name, (repair.files || []).join(', ')].filter(Boolean).join(' — ')));
                    const diff = element('pre', 'dlux-ops-diff', repair.diff);
                    diff.dir = 'ltr';
                    block.appendChild(diff);
                    if (repair.note) { block.appendChild(composerText('div', 'small text-muted', repair.note)); }
                    diffsEl.appendChild(block);
                });
            }
            const offered = repairs.length > 0 && state.has_preview && available('check-fix-apply');
            if (repairsWrap) { repairsWrap.hidden = !repairs.length; }
            if (applyButton) { applyButton.hidden = !offered; applyButton.disabled = busy(); }
            if (noRepairEl) {
                const summary = (run && run.summary) || {};
                const unresolved = (summary.warn || 0) + (summary.fail || 0) > 0;
                noRepairEl.textContent = labels.labelNoRepair || 'No automatic repair is available for these findings.';
                noRepairEl.hidden = !(unresolved && !repairs.length);
            }
        }

        function actionButton(label, icon, onClick, disabled) {
            const button = element('button', 'btn btn-sm dlux-ops-icon');
            button.type = 'button';
            button.title = label;
            button.setAttribute('aria-label', label);
            button.appendChild(element('i', `bi ${icon}`));
            button.disabled = disabled;
            button.addEventListener('click', () => onClick(button));
            return button;
        }

        function renderServices() {
            if (!servicesEl) { return; }
            servicesEl.replaceChildren();
            const rows = (state.services && state.services.services) || [];
            if (!rows.length) {
                const empty = element('tr');
                const cell = element('td', 'small text-muted', labels.labelNoServices || '');
                cell.colSpan = 3;
                empty.appendChild(cell);
                servicesEl.appendChild(empty);
                return;
            }
            const locked = busy();
            rows.forEach((service) => {
                const row = element('tr');
                row.appendChild(element('td', 'fw-semibold', service.name));
                const stateText = service.state === 'absent'
                    ? (labels.labelAbsent || 'not created')
                    : [service.state, service.health].filter(Boolean).join(' · ');
                const tone = service.state === 'running' && service.health !== 'unhealthy' ? 'ok' : 'warn';
                row.appendChild(element('td', `small dlux-ops-state dlux-ops-state--${tone}`, stateText));
                const actions = element('td', 'text-end text-nowrap');
                if (!service.can_restart) {
                    actions.appendChild(element('span', 'dlux-ops-note', labels.labelProtected || ''));
                }
                const group = element('span', 'dlux-ops-actions');
                if (service.can_restart) {
                    group.appendChild(actionButton(labels.labelStart, 'bi-play-fill',
                        (button) => confirmServiceOperation('service-start', service.name, button),
                        locked || !service.can_start || !available('service-start')));
                    group.appendChild(actionButton(labels.labelStop, 'bi-stop-fill',
                        (button) => confirmServiceOperation('service-stop', service.name, button),
                        locked || !service.can_stop || !available('service-stop')));
                    group.appendChild(actionButton(labels.labelRestart || 'Restart', 'bi-arrow-repeat',
                        (button) => confirmServiceOperation('service-restart', service.name, button),
                        locked || !available('service-restart')));
                    group.appendChild(actionButton(labels.labelRecreate || 'Recreate', 'bi-box-arrow-in-up',
                        (button) => confirmServiceOperation('service-recreate', service.name, button),
                        locked || !available('service-recreate')));
                }
                group.appendChild(actionButton(labels.labelLogs || 'Logs', 'bi-journal-text',
                    (button) => start('logs-tail', { service: service.name, lines: 200 }, button),
                    locked || !available('logs-tail')));
                actions.appendChild(group);
                row.appendChild(actions);
                servicesEl.appendChild(row);
            });
        }

        function renderLogs() {
            const run = state.logs;
            if (!run) {
                if (logsTitle) { logsTitle.textContent = ''; }
                if (logsEl && !logsEl.textContent) { logsEl.textContent = labels.labelNoLogs || ''; }
                return;
            }
            if (run.token === shownLogsToken) { return; }
            shownLogsToken = run.token;
            const params = run.params || {};
            const template = params.service
                ? (labels.labelLogsOf || 'Last {lines} lines of {service}')
                : (labels.labelLogsAll || 'Last {lines} lines of all services');
            if (logsTitle) {
                logsTitle.textContent = template
                    .replace('{lines}', String(params.lines || ''))
                    .replace('{service}', String(params.service || ''));
            }
            if (logsEl) {
                logsEl.textContent = run.logs || '';
                logsEl.scrollTop = logsEl.scrollHeight;
            }
        }

        function render(payload) {
            if (payload) { state = { ...state, ...payload }; }
            const run = state.run;
            const ours = Boolean(run && PANEL_OPERATIONS.has(run.operation));
            root.setAttribute('aria-busy', String(busy()));
            if (statusEl) {
                statusEl.hidden = !busy();
                statusEl.textContent = busy()
                    ? [spec(run.operation)?.label, labels.labelRunning].filter(Boolean).join(' — ')
                    : '';
            }
            if (!busy()) { stopSpinner(); }
            if (ours && run.status === 'failed') { setError(run.error || labels.labelFailed || 'The operation failed.'); }
            runButtons.forEach((button) => {
                button.disabled = busy() || !available(button.dataset.dluxOpsPanelRun);
                const operation = spec(button.dataset.dluxOpsPanelRun);
                if (operation && operation.available === false) { button.title = operation.unavailable_reason; }
            });
            renderCheck();
            renderServices();
            renderLogs();
            if (logsAllButton) { logsAllButton.disabled = busy() || !available('logs-tail'); }
            // A restart or recreate changes what the service list shows.
            if (ours && run.status === 'completed' && refreshAfter === run.token) {
                refreshAfter = '';
                start('services');
            }
        }

        async function refresh() {
            if (!root.isConnected) { return; }
            try {
                const data = await jsonRequest(root.dataset.stateUrl, { method: 'GET' });
                render(data);
                if (data.run && !TERMINAL.has(data.run.status)) { schedulePoll(); }
            } catch (error) {
                setError(error.message);
                if (statusEl) { statusEl.hidden = true; }
            }
        }

        function schedulePoll() {
            window.clearTimeout(pollTimer);
            pollTimer = window.setTimeout(refresh, 2000);
        }

        async function start(operation, extra, button) {
            const body = new FormData();
            body.append('operation', operation);
            Object.entries(extra || {}).forEach(([key, value]) => body.append(key, value));
            setError('');
            startSpinner(button);
            try {
                const data = await jsonRequest(root.dataset.runUrl, { method: 'POST', body });
                if (['service-start', 'service-stop', 'service-restart', 'service-recreate'].includes(operation)) {
                    refreshAfter = data.run.token;
                }
                render({ run: data.run });
                schedulePoll();
                return true;
            } catch (exc) {
                stopSpinner();
                setError(exc.message);
                throw exc;
            }
        }

        function confirmed(operation, description, button, extra) {
            if (typeof window.dluxConfirmPassword !== 'function') { return; }
            window.dluxConfirmPassword({
                title: (spec(operation) || {}).label || operation,
                description,
                confirmLabel: (spec(operation) || {}).label || operation,
                requirePassword: true,
                danger: operation === 'service-recreate' || operation === 'service-stop',
                icon: 'bi-tools',
                onConfirm: (password, { showError }) => start(operation, { ...extra, current_password: password }, button)
                    .then(() => true)
                    .catch((exc) => { showError(exc.message); return false; }),
            });
        }

        function confirmServiceOperation(operation, service, button) {
            const note = {
                'service-start': labels.labelStartNote,
                'service-stop': labels.labelStopNote,
                'service-recreate': labels.labelRecreateNote,
                'service-restart': labels.labelRestartNote,
            }[operation];
            confirmed(operation, String(note || '').replace('{service}', service), button, { service });
        }

        runButtons.forEach((button) => {
            button.addEventListener('click', () => {
                start(button.dataset.dluxOpsPanelRun, {}, button).catch(() => {});
            });
        });
        findingsToggle?.addEventListener('click', () => {
            findingsEl.classList.toggle('is-collapsed');
            renderCheck();
        });
        logsAllButton?.addEventListener('click', () => {
            start('logs-tail', { lines: 200 }, logsAllButton).catch(() => {});
        });
        applyButton?.addEventListener('click', () => {
            confirmed('check-fix-apply', labels.labelApplyNote || '', applyButton, {});
        });

        refresh();
    }

    function boot(scope) {
        (scope || document).querySelectorAll('[data-dlux-ops-panel]').forEach(init);
    }

    // The panel arrives inside the dynamic modal after the page has loaded, and the
    // modal re-runs this script on every open: bind what is there, listen once.
    boot();
    if (!window.dluxOpsPanelListening) {
        window.dluxOpsPanelListening = true;
        document.addEventListener('dlux:modal-content-loaded', (event) => boot(event.target || document));
    }
}());
