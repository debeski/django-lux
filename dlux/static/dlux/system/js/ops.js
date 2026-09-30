// The deployment's two rows in the Updates card: the stack itself, and the
// resident Composer that operates it.
//
// They are rows and not a panel of buttons on purpose. The card already asks
// and answers this shape of question for DjangoLux and for the application
// image — one icon that checks, a second that appears only when there is
// something to install, and a tick when there is not — so the deployment reads
// the same way, and everything a check *found* lives in a modal instead of
// growing the card.
(function () {
    'use strict';

    const TERMINAL = new Set(['completed', 'failed']);
    const ICONS = { ok: 'bi-check-circle', warn: 'bi-exclamation-triangle', fail: 'bi-x-circle' };
    // What a row's check icon says: nothing checked yet (the arrow), or what the
    // last check found. A warning is not an invitation to check again as if
    // nothing had happened, so it does not look like one.
    const TONE_GLYPH = { ok: 'bi-check-circle-fill', warn: 'bi-exclamation-triangle-fill', fail: 'bi-x-circle-fill' };
    // Which row each operation belongs to: a run spins the icon of the row it
    // was started from, and leaves the other row alone.
    const ROW_OF = {
        'check': 'check',
        'check-fix-preview': 'check',
        'check-fix-apply': 'check',
        'agent-check': 'agent',
        'agent-update': 'agent',
    };

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
        const summaryEl = root.querySelector('[data-dlux-ops-summary]');
        const composerVersionEl = root.querySelector('[data-dlux-ops-composer-version]');
        const composerTargetEl = root.querySelector('[data-dlux-ops-composer-target]');
        const composerNoticeEl = root.querySelector('[data-dlux-ops-composer-notice]');
        const resultsButton = root.querySelector('[data-dlux-ops-results]');
        const checkButtons = new Map();
        root.querySelectorAll('[data-dlux-ops-check]').forEach((button) => {
            checkButtons.set(ROW_OF[button.dataset.dluxOpsCheck], button);
        });
        const actionButtons = new Map();
        root.querySelectorAll('[data-dlux-ops-open]').forEach((button) => {
            actionButtons.set(ROW_OF[button.dataset.dluxOpsOpen], button);
        });

        const modalElement = document.getElementById('dluxOpsResultModal');
        const modal = modalElement && window.bootstrap ? new window.bootstrap.Modal(modalElement) : null;
        const modalTitle = modalElement?.querySelector('[data-dlux-ops-modal-title]');
        const modalIntro = modalElement?.querySelector('[data-dlux-ops-modal-intro]');
        const findingsEl = modalElement?.querySelector('[data-dlux-ops-findings]');
        const repairsWrap = modalElement?.querySelector('[data-dlux-ops-repairs]');
        const diffsEl = modalElement?.querySelector('[data-dlux-ops-diffs]');
        const confirmWrap = modalElement?.querySelector('[data-dlux-ops-confirm]');
        const confirmNote = modalElement?.querySelector('[data-dlux-ops-confirm-note]');
        const passwordInput = modalElement?.querySelector('[data-dlux-ops-password]');
        const submitButton = modalElement?.querySelector('[data-dlux-ops-submit]');
        const offerButton = modalElement?.querySelector('[data-dlux-ops-offer]');
        const noRepairEl = modalElement?.querySelector('[data-dlux-ops-norepair]');
        const modalError = modalElement?.querySelector('[data-dlux-ops-error]');

        let state = { operations: [] };
        let pending = '';
        let pollTimer = null;
        let spinner = null;
        let spinning = '';

        function spec(name) {
            return (state.operations || []).find((operation) => operation.name === name) || null;
        }

        function setStatus(text, isError) {
            if (!statusEl) { return; }
            statusEl.textContent = text || '';
            statusEl.hidden = !text;
            statusEl.classList.toggle('text-danger', Boolean(isError));
        }

        function setModalError(text) {
            if (!modalError) { return; }
            modalError.textContent = text || '';
            modalError.hidden = !text;
        }

        // The row's own icon spins while its operation runs, through the same
        // helper the DjangoLux check uses, so both rows behave identically.
        function startSpinner(row) {
            if (spinning === row) { return; }
            stopSpinner();
            const button = checkButtons.get(row);
            if (!button) { return; }
            spinning = row;
            if (window.DluxLoadingButton) {
                spinner = window.DluxLoadingButton.start(button);
            } else {
                button.disabled = true;
            }
        }

        function stopSpinner() {
            if (spinner) { spinner.stop(); spinner = null; }
            spinning = '';
        }

        /** `base — Last check: <time>`, or `base` when nothing has checked yet. */
        function withCheckTime(element, iso) {
            if (!element) return;
            if (element.dataset.titleBase === undefined) { element.dataset.titleBase = element.title || ''; }
            const label = labels.labelLastCheck || 'Last check';
            const title = iso
                ? `${element.dataset.titleBase} — ${label}: ${new Date(iso).toLocaleString()}`
                : element.dataset.titleBase;
            element.title = title;
            if (element.hasAttribute('aria-label')) { element.setAttribute('aria-label', title); }
        }

        /** ``tone``: 'ok', 'warn', 'fail', or '' for a row nothing has checked. */
        function setGlyph(row, tone) {
            const button = checkButtons.get(row);
            const glyph = button?.querySelector('[data-dlux-ops-glyph]');
            if (!glyph) { return; }
            glyph.className = `bi ${TONE_GLYPH[tone] || 'bi-arrow-clockwise'}`;
            ['ok', 'warn', 'fail'].forEach((name) => button.classList.toggle(`is-${name}`, tone === name));
        }

        /** Is a repair on offer: Composer found one, a preview backs it, and this user may apply it. */
        function repairOffered(run) {
            return Boolean(run && repairsOf(run).length && state.has_preview && canManage
                && (spec('check-fix-apply') || {}).available !== false);
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
            const repairs = repairsOf(run);
            if (diffsEl) { diffsEl.innerHTML = ''; }
            if (repairsWrap) { repairsWrap.hidden = !repairs.length; }
            if (!repairs.length || !diffsEl) { return; }
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

        /** Open the modal over the last check: read-only, or offering ``action``. */
        function openModal(action) {
            if (!modal) { return; }
            const run = state.check;
            pending = action || '';
            setModalError('');
            if (modalTitle) {
                modalTitle.textContent = (action && (spec(action) || {}).label)
                    || labels.labelResultsTitle || modalTitle.textContent;
            }
            if (modalIntro) { modalIntro.hidden = false; }
            // Reading the last check: say what can be done about it. A repair is offered
            // here, where the findings are; with none, say so rather than leave a bare
            // Close button and a question.
            const reading = !action;
            const summary = (run && run.summary) || {};
            if (offerButton) { offerButton.hidden = !(reading && repairOffered(run)); }
            if (noRepairEl) {
                const unresolved = (summary.warn || 0) + (summary.fail || 0) > 0;
                noRepairEl.textContent = labels.labelNoRepair || 'No automatic repair is available for these findings.';
                noRepairEl.hidden = !(reading && unresolved && !repairsOf(run).length);
            }
            renderFindings(run);
            renderRepairs(action === 'check-fix-apply' || !action ? run : null);
            if (confirmWrap) { confirmWrap.hidden = !(action && (spec(action) || {}).changes_deployment); }
            if (confirmNote) { confirmNote.textContent = action ? ((spec(action) || {}).label || '') : ''; }
            if (passwordInput) { passwordInput.value = ''; }
            if (submitButton) {
                submitButton.hidden = !action;
                submitButton.disabled = false;
                submitButton.textContent = (spec(action) || {}).label || labels.labelApply || 'Apply';
            }
            modal.show();
            if (action && passwordInput) { window.setTimeout(() => passwordInput.focus(), 200); }
        }

        /** The resident-Composer row: version, news, and what its icons offer. */
        function renderComposerRow() {
            const resident = state.resident || {};
            const version = resident.version || state.composer_version || '';
            if (composerVersionEl) {
                composerVersionEl.textContent = version ? `v${String(version).replace(/^v/, '')}` : '';
            }
            const available = Boolean(resident.update_available);
            if (composerTargetEl) {
                composerTargetEl.hidden = !available;
                composerTargetEl.textContent = available
                    ? `v${String(resident.published_version || '').replace(/^v/, '')}`
                    : '';
            }
            const button = actionButtons.get('agent');
            if (button) { button.hidden = !(available && canManage); }
            withCheckTime(checkButtons.get('agent'), resident.checked_at);
            withCheckTime(button, resident.checked_at);
            // A tick means "checked, and there is nothing to install". A version
            // nobody has checked yet gets the plain re-check arrow, and a check that
            // ran but could not read the registry says so instead of going quiet.
            const unknown = Boolean(resident.checked_at) && !resident.checked;
            setGlyph('agent', unknown ? 'warn' : (resident.checked && !available ? 'ok' : ''));
            renderComposerNotice();
        }

        /** Says so when DjangoLux was updated ahead of its Composer, and who can fix it. */
        function renderComposerNotice() {
            if (!composerNoticeEl) { return; }
            const behind = state.composer_behind;
            const template = behind && (behind.ops_blocked
                ? labels.labelComposerBehindHost
                : labels.labelComposerBehindCard);
            const bare = (value) => String(value || '').replace(/^v/, '');
            const resident = state.resident || {};
            const unknown = Boolean(resident.checked_at) && !resident.checked;
            composerNoticeEl.textContent = template
                ? template.replace('{version}', bare(behind.version)).replace('{required}', bare(behind.required))
                : (unknown
                    ? (labels.labelComposerUnknown || 'Could not check for a Composer update: {reason}')
                        .replace('{reason}', resident.detail || '')
                    : '');
            composerNoticeEl.hidden = !composerNoticeEl.textContent;
        }

        /** The deployment row: what the last check found, and the repair it offers. */
        function renderDeploymentRow() {
            const run = state.check;
            const offered = repairOffered(run);
            if (summaryEl) { summaryEl.textContent = summaryText(run); }
            const button = actionButtons.get('check');
            if (button) { button.hidden = !offered; }
            if (resultsButton) { resultsButton.hidden = !run; }
            const checkedAt = run && run.completed_at;
            withCheckTime(checkButtons.get('check'), checkedAt);
            withCheckTime(button, checkedAt);
            withCheckTime(resultsButton, checkedAt);
            const summary = (run && run.summary) || {};
            setGlyph('check', !summary.total ? '' : (summary.fail ? 'fail' : (summary.warn ? 'warn' : 'ok')));
        }

        function applyAvailability() {
            checkButtons.forEach((button, row) => {
                const name = button.dataset.dluxOpsCheck;
                const operation = spec(name);
                const blocked = Boolean(operation && operation.available === false);
                const busy = Boolean(state.run && state.run.active);
                button.disabled = blocked || !canManage || (busy && spinning !== row);
                if (blocked) { button.title = operation.unavailable_reason; }
            });
        }

        function render(payload) {
            if (payload) { state = { ...state, ...payload }; }
            const run = state.run;
            const active = Boolean(run && !TERMINAL.has(run.status));
            if (active) {
                startSpinner(ROW_OF[run.operation] || 'check');
                setStatus(`${(spec(run.operation) || {}).label || run.operation}…`);
            } else {
                stopSpinner();
                setStatus(run && run.status === 'failed' ? (run.error || 'The operation failed.') : '', true);
            }
            renderDeploymentRow();
            renderComposerRow();
            applyAvailability();
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
            startSpinner(ROW_OF[operation] || 'check');
            try {
                const data = await jsonRequest(root.dataset.runUrl, { method: 'POST', body });
                render({ run: data.run });
                schedulePoll();
                return true;
            } catch (exc) {
                stopSpinner();
                const message = exc.message || 'Request failed';
                if (pending) { setModalError(message); } else { setStatus(message, true); }
                return false;
            }
        }

        checkButtons.forEach((button) => {
            button.addEventListener('click', () => { run(button.dataset.dluxOpsCheck); });
        });
        actionButtons.forEach((button) => {
            button.addEventListener('click', () => { openModal(button.dataset.dluxOpsOpen); });
        });
        if (resultsButton) { resultsButton.addEventListener('click', () => openModal('')); }
        if (offerButton) { offerButton.addEventListener('click', () => openModal('check-fix-apply')); }

        if (submitButton) {
            submitButton.addEventListener('click', async () => {
                if (!pending) { return; }
                submitButton.disabled = true;
                const started = await run(pending, {
                    current_password: passwordInput ? passwordInput.value : '',
                });
                submitButton.disabled = false;
                if (started) {
                    pending = '';
                    if (passwordInput) { passwordInput.value = ''; }
                    modal?.hide();
                }
            });
        }
        if (passwordInput) {
            passwordInput.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' && submitButton) { event.preventDefault(); submitButton.click(); }
            });
        }
        modalElement?.addEventListener('hidden.bs.modal', () => {
            pending = '';
            if (passwordInput) { passwordInput.value = ''; }
            setModalError('');
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
