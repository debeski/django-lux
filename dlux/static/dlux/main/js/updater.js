(function () {
    'use strict';

    const TERMINAL = new Set(['completed', 'failed', 'rolled_back']);

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
        const modalElement = document.getElementById('dluxUpdateReviewModal');
        const modal = modalElement && window.bootstrap ? new window.bootstrap.Modal(modalElement) : null;
        const form = modalElement?.querySelector('[data-dlux-update-form]');
        const error = modalElement?.querySelector('[data-dlux-update-error]');
        const password = modalElement?.querySelector('[name="current_password"]');
        let state = null;
        let currentAction = 'apply';
        let runUrl = '';
        let pollTimer = null;
        let statePollTimer = null;

        function showError(message) {
            if (error) {
                error.textContent = message || '';
                error.hidden = !message;
            }
            if (message && window.showToast) {
                window.showToast(message, 'error');
            }
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
            if (run?.status === 'failed') showError(run.error || root.dataset.labelFailed);
            if (run?.status === 'completed' || run?.status === 'rolled_back') {
                if (window.showToast) window.showToast(root.dataset.labelCompleted || 'Completed');
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
            password.value = '';
            showError('');
            modal.show();
        }

        reviewButton?.addEventListener('click', () => openReview('apply'));
        rollbackButton?.addEventListener('click', () => openReview('rollback'));

        form?.addEventListener('submit', async (event) => {
            event.preventDefault();
            const submit = form.querySelector('[type="submit"]');
            submit.disabled = true;
            try {
                const url = currentAction === 'rollback' ? root.dataset.rollbackUrl : root.dataset.applyUrl;
                await queue(url, new FormData(form));
                modal.hide();
            } catch (requestError) {
                showError(requestError.message);
            } finally {
                submit.disabled = false;
            }
        });

        refreshState().catch((requestError) => showError(requestError.message));
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-dlux-updater]').forEach(initialize);
    });
}());
