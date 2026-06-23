(function () {
    'use strict';

    const TERMINAL = new Set(['completed', 'failed', 'rolled_back']);
    const PROGRESS = {
        queued: 3,
        checking: 8,
        downloading: 12,
        verifying: 22,
        staging: 32,
        preflight: 42,
        backing_up: 52,
        maintenance: 60,
        migrating: 68,
        collecting_static: 78,
        switching: 86,
        restarting: 92,
        verifying_health: 96,
        completed: 100,
        failed: 100,
        rolled_back: 100,
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
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.ok === false) {
            throw new Error(payload.error || payload.message || `Request failed (${response.status})`);
        }
        return payload;
    }

    function initialize(root) {
        const active = root.querySelector('[data-dlux-update-active]');
        const latest = root.querySelector('[data-dlux-update-latest]');
        const reason = root.querySelector('[data-dlux-update-reason]');
        const checked = root.querySelector('[data-dlux-update-checked]');
        const checkButton = root.querySelector('[data-dlux-update-check]');
        const reviewButton = root.querySelector('[data-dlux-update-review]');
        const rollbackButton = root.querySelector('[data-dlux-update-rollback]');
        const rootRunStatus = root.querySelector('[data-dlux-update-run-status]');
        const modalElement = document.getElementById('dluxUpdateReviewModal');
        const modal = modalElement && window.bootstrap ? new window.bootstrap.Modal(modalElement) : null;
        const error = modalElement?.querySelector('[data-dlux-update-error]');
        const password = modalElement?.querySelector('[name="current_password"]');
        const reviewPanel = modalElement?.querySelector('[data-dlux-update-review-panel]');
        const progressPanel = modalElement?.querySelector('[data-dlux-update-progress-panel]');
        const progress = modalElement?.querySelector('[data-dlux-update-progress]');
        const progressBar = modalElement?.querySelector('[data-dlux-update-progress-bar]');
        const progressStatus = modalElement?.querySelector('[data-dlux-update-progress-status]');
        const progressLog = modalElement?.querySelector('[data-dlux-update-progress-log]');
        const submit = modalElement?.querySelector('[data-dlux-update-submit]');
        const dismissButtons = modalElement?.querySelectorAll('[data-bs-dismiss="modal"]') || [];
        let state = null;
        let currentAction = 'apply';
        let runUrl = '';
        let pollTimer = null;
        let statePollTimer = null;
        let lastTerminalNotice = '';

        function setRootStatus(message) {
            if (!rootRunStatus) return;
            rootRunStatus.textContent = message || '';
            rootRunStatus.hidden = !message;
        }

        function showError(message, notify = true) {
            if (error) {
                error.textContent = message || '';
                error.hidden = !message;
            }
            setRootStatus(message);
            if (notify && message && window.showToast) {
                window.showToast(message, 'error');
            }
        }

        function showProgress(run) {
            if (!modal || !run || !['apply', 'rollback'].includes(run.action)) return;
            const terminal = TERMINAL.has(run.status);
            const percent = PROGRESS[run.status] ?? 5;
            reviewPanel.hidden = true;
            progressPanel.hidden = false;
            submit.hidden = true;
            password.disabled = true;
            dismissButtons.forEach((button) => { button.disabled = !terminal; });
            if (progress) {
                progress.setAttribute('aria-valuenow', String(percent));
                progress.setAttribute('aria-valuetext', run.status.replaceAll('_', ' '));
            }
            if (progressBar) {
                progressBar.style.width = `${percent}%`;
                progressBar.classList.toggle('progress-bar-animated', !terminal);
                progressBar.classList.toggle('bg-danger', run.status === 'failed');
                progressBar.classList.toggle('bg-warning', run.status === 'rolled_back');
                progressBar.classList.toggle('bg-success', run.status === 'completed');
            }
            if (progressStatus) {
                const label = run.status === 'failed'
                    ? root.dataset.labelFailed
                    : (terminal ? root.dataset.labelCompleted : root.dataset.labelRunning);
                progressStatus.textContent = `${label || run.status} · ${percent}%`;
            }
            if (progressLog && typeof run.progress_log === 'string') {
                progressLog.textContent = run.progress_log;
                progressLog.scrollTop = progressLog.scrollHeight;
            }
            modal.show();
        }

        function render(nextState, run) {
            state = nextState || state;
            if (!state) return;
            active.textContent = state.active_version ? `v${state.active_version}` : '—';
            latest.textContent = state.latest_version ? `v${state.latest_version}` : '—';
            reason.textContent = state.last_check_error || state.latest_reason || '';
            checked.textContent = state.last_checked_at
                ? new Date(state.last_checked_at).toLocaleString()
                : '—';
            const updateAvailable = Boolean(
                state.latest_compatible && state.latest_version &&
                state.latest_version !== state.active_version
            );
            if (reviewButton) reviewButton.hidden = !updateAvailable;
            if (rollbackButton) rollbackButton.hidden = !state.previous_version;
            const running = Boolean(run?.active || state.active_run_token);
            root.classList.toggle('is-running', running);
            if (checkButton) checkButton.disabled = running;
            if (reviewButton) reviewButton.disabled = running;
            if (rollbackButton) rollbackButton.disabled = running;
            if (running) setRootStatus(root.dataset.labelRunning || 'Update operation in progress');
            if (run && ['apply', 'rollback'].includes(run.action) && (run.active || !progressPanel?.hidden)) {
                showProgress(run);
            }
            if (run?.status === 'failed') {
                const message = run.error || root.dataset.labelFailed;
                showError(message, false);
                if (lastTerminalNotice !== run.token && window.showToast) {
                    lastTerminalNotice = run.token;
                    window.showToast(message, 'error');
                }
            }
            if (run?.status === 'completed' || run?.status === 'rolled_back') {
                const message = root.dataset.labelCompleted || 'Completed';
                setRootStatus(message);
                if (lastTerminalNotice !== run.token && window.showToast) {
                    lastTerminalNotice = run.token;
                    window.showToast(message);
                }
            }
        }

        async function refreshState() {
            window.clearTimeout(statePollTimer);
            const payload = await jsonRequest(root.dataset.stateUrl, { method: 'GET' });
            render(payload.state, payload.run);
            if (payload.run?.active && payload.run.token) {
                if (payload.state?.can_manage) {
                    runUrl = root.dataset.stateUrl.replace(/state\/$/, `runs/${payload.run.token}/`);
                    schedulePoll();
                } else {
                    statePollTimer = window.setTimeout(pollReadOnlyState, 1500);
                }
            }
        }

        async function pollReadOnlyState() {
            try {
                await refreshState();
            } catch (_error) {
                statePollTimer = window.setTimeout(pollReadOnlyState, 1500);
            }
        }

        function schedulePoll() {
            window.clearTimeout(pollTimer);
            pollTimer = window.setTimeout(pollRun, 1500);
        }

        async function pollRun() {
            if (!runUrl) return;
            try {
                const payload = await jsonRequest(runUrl, { method: 'GET' });
                render(state, payload.run);
                if (!TERMINAL.has(payload.run.status)) {
                    schedulePoll();
                } else {
                    runUrl = '';
                    await refreshState();
                }
            } catch (_error) {
                schedulePoll();
            }
        }

        async function queue(url, body) {
            showError('');
            const payload = await jsonRequest(url, { method: 'POST', body });
            render(payload.state, payload.run);
            if (payload.run_url) {
                runUrl = payload.run_url;
                schedulePoll();
            }
            return payload;
        }

        checkButton?.addEventListener('click', async () => {
            try {
                await queue(root.dataset.checkUrl, new FormData());
                if (!runUrl) await refreshState();
            } catch (requestError) {
                showError(requestError.message);
            }
        });

        function openReview(action) {
            if (!modal || !state) return;
            currentAction = action;
            const isRollback = action === 'rollback';
            modalElement.querySelector('[data-dlux-update-modal-title]').textContent = isRollback
                ? root.dataset.labelRollbackTitle : root.dataset.labelUpdateTitle;
            modalElement.querySelector('[data-dlux-update-submit]').textContent = isRollback
                ? root.dataset.labelRollbackConfirm : root.dataset.labelUpdateConfirm;
            modalElement.querySelector('[data-dlux-update-target]').textContent = isRollback
                ? state.previous_version : state.latest_version;
            modalElement.querySelector('[data-dlux-update-summary]').textContent = isRollback
                ? (state.previous_manifest?.summary || '—')
                : (state.latest_manifest?.summary || '—');
            modalElement.querySelector('[data-dlux-update-compatibility]').textContent = isRollback
                ? (state.previous_version ? root.dataset.labelLocalVerified : '—')
                : (state.latest_reason || root.dataset.labelReady);
            reviewPanel.hidden = false;
            progressPanel.hidden = true;
            submit.hidden = false;
            submit.disabled = false;
            password.disabled = false;
            dismissButtons.forEach((button) => { button.disabled = false; });
            password.value = '';
            showError('');
            modal.show();
        }

        reviewButton?.addEventListener('click', () => openReview('apply'));
        rollbackButton?.addEventListener('click', () => openReview('rollback'));

        async function submitAction() {
            if (!password.value) {
                password.reportValidity();
                return;
            }
            submit.disabled = true;
            try {
                const url = currentAction === 'rollback' ? root.dataset.rollbackUrl : root.dataset.applyUrl;
                const body = new FormData();
                body.append('current_password', password.value);
                await queue(url, body);
                password.value = '';
            } catch (requestError) {
                showError(requestError.message);
                submit.disabled = false;
            } finally {
                if (!runUrl) submit.disabled = false;
            }
        }

        submit?.addEventListener('click', submitAction);
        password?.addEventListener('keydown', (event) => {
            if (event.key !== 'Enter') return;
            event.preventDefault();
            submitAction();
        });

        refreshState().catch((requestError) => showError(requestError.message));
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-dlux-updater]').forEach(initialize);
    });
}());
