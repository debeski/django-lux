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
        const imageButton = root.querySelector('[data-dlux-update-image]');
        const rollbackButton = root.querySelector('[data-dlux-update-rollback]');
        const appVersionEl = root.querySelector('[data-dlux-app-version]');
        const imageTargetEl = root.querySelector('[data-dlux-image-target]');
        const imageNameEl = root.querySelector('[data-dlux-image-name]');
        const imageDigestEl = root.querySelector('[data-dlux-image-digest]');
        const imageOkEl = root.querySelector('[data-dlux-image-ok]');
        const imageCheckedEl = root.querySelector('[data-dlux-image-checked]');
        const checkGlyph = root.querySelector('[data-dlux-check-glyph]');
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
        const failedWarning = modalElement?.querySelector('[data-dlux-update-failed-warning]');
        const failedAck = modalElement?.querySelector('[data-dlux-update-failed-ack]');
        const failedText = modalElement?.querySelector('[data-dlux-update-failed-text]');
        const skipButton = modalElement?.querySelector('[data-dlux-update-skip]');
        const skippedWrap = root.querySelector('[data-dlux-skipped-wrap]');
        const skippedList = root.querySelector('[data-dlux-skipped-list]');
        const dismissButtons = modalElement?.querySelectorAll('[data-bs-dismiss="modal"]') || [];
        const dismissAction = modalElement?.querySelector('[data-dlux-update-dismiss]');
        const dismissActionLabel = dismissAction ? dismissAction.textContent : '';
        let state = null;
        let currentAction = 'apply';
        let runUrl = '';
        let pollTimer = null;
        let statePollTimer = null;
        let lastTerminalNotice = '';
        let trackedRunToken = '';
        let rootStatusTimer = null;
        let checkHandle = null;
        // Image-level (full container) update: not a DluxUpdateRun, so it is
        // tracked via the state endpoint's `image_update` object rather than a
        // run_url. The recreate takes this page into maintenance, so tracking is
        // best-effort (poll until the connection drops; the final state shows on
        // the next successful load).
        let imageUpdate = null;
        let imageStatePollTimer = null;
        let lastImageNotice = '';
        // Image updates recreate `web`, so once it goes down the web state API is
        // unreachable. Instead we track the update via the proxy-served deploy
        // status/log (written by composer to the shared volume, served by the
        // proxy which stays up) — so the modal keeps showing progress without a
        // refresh, and returns the user here on completion.
        const deployStatusUrl = root.dataset.deployStatusUrl || '/_update/status.json';
        const deployLogUrl = root.dataset.deployLogUrl || '/_update/log.txt';
        const DEPLOY_PCT = { preparing: 8, starting: 12, pulling: 38, recreating: 62, migrating: 84, restarting: 72, ready: 100, failed: 100 };
        const DEPLOY_LABEL = {
            preparing: 'Preparing…', starting: 'Starting…', pulling: 'Pulling the new image…',
            recreating: 'Recreating containers…', migrating: 'Applying migrations…',
            restarting: 'Restarting…', ready: 'Finishing…', failed: 'Update failed',
        };
        const DEPLOY_INPROG = { preparing: 1, starting: 1, pulling: 1, recreating: 1, migrating: 1, restarting: 1 };
        let imgStarted = 0;
        let imgSawProgress = false;

        function imageActive(iu) {
            return Boolean(iu && iu.active);
        }

        function imageStatusLabel(status, deployStatus) {
            const base = {
                pending: 'Image update queued…',
                backing_up: 'Creating pre-update backup…',
                awaiting_recreate: 'Updating containers…',
                completed: 'Image update completed.',
                failed: 'Image update failed.',
            }[status] || status || '';
            if (status === 'awaiting_recreate' && deployStatus) {
                const phase = {
                    starting: 'starting', pulling: 'pulling new image…',
                    recreating: 'recreating containers…', migrating: 'running migrations…',
                    ready: 'finishing…', failed: 'failed',
                }[deployStatus];
                if (phase) return `Updating — ${phase}`;
            }
            return base;
        }

        function fmtTime(iso) {
            if (!iso) return '—';
            const d = new Date(iso);
            return isNaN(d.getTime()) ? '—' : d.toLocaleString();
        }
        function shortDigest(digest) {
            if (!digest) return '';
            return 'sha256:' + String(digest).replace(/^sha256:/, '').slice(0, 12);
        }
        function shortImageName(ref) {
            // "debeski/sales:latest" -> "debeski/sales"
            if (!ref) return '';
            return String(ref).split('@')[0].replace(/:[^/:]+$/, '');
        }

        // The "Check for updates" button spins via the shared loading-button
        // helper while the check is in flight (replacing the old root status line).
        function startCheckSpinner() {
            if (checkButton && window.DluxLoadingButton && !checkHandle) {
                checkHandle = window.DluxLoadingButton.start(checkButton);
            }
        }
        function stopCheckSpinner() {
            if (checkHandle) { checkHandle.stop(); checkHandle = null; }
        }

        function setRootStatus(message, clearAfter = 0) {
            if (!rootRunStatus) return;
            window.clearTimeout(rootStatusTimer);
            rootRunStatus.textContent = message || '';
            rootRunStatus.hidden = !message;
            if (message && clearAfter > 0) {
                rootStatusTimer = window.setTimeout(() => setRootStatus(''), clearAfter);
            }
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
            // On a successful finish, turn the lone "Cancel" into a clear green
            // "Finish" so the result reads as success (not a dismissable error).
            const succeeded = terminal && (run.status === 'completed' || run.status === 'rolled_back');
            if (dismissAction && succeeded) {
                dismissAction.textContent = root.dataset.labelFinish || dismissActionLabel;
                dismissAction.classList.remove('btn-secondary');
                dismissAction.classList.add('btn-success');
            }
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

        function showImageStarted() {
            if (!modal) return;
            reviewPanel.hidden = true;
            progressPanel.hidden = false;
            submit.hidden = true;
            if (password) password.disabled = true;
            dismissButtons.forEach((button) => { button.disabled = false; });
            if (progressBar) {
                progressBar.style.width = '100%';
                progressBar.classList.add('progress-bar-animated');
                progressBar.classList.remove('bg-danger', 'bg-success', 'bg-warning');
            }
            if (progressStatus) progressStatus.textContent = root.dataset.labelImageStarted || 'Image update started.';
            if (progressLog && typeof imageUpdate?.progress_log === 'string') {
                progressLog.textContent = imageUpdate.progress_log;
                progressLog.scrollTop = progressLog.scrollHeight;
            }
            modal.show();
        }

        function finishImageNotice() {
            if (!imageUpdate || imageActive(imageUpdate)) return;
            const terminal = imageUpdate.status === 'completed' || imageUpdate.status === 'failed';
            if (!terminal) return;
            const succeeded = imageUpdate.status === 'completed';
            if (lastImageNotice !== imageUpdate.token && window.showToast) {
                lastImageNotice = imageUpdate.token;
                window.showToast(
                    succeeded ? (root.dataset.labelCompleted || 'Completed')
                        : (imageUpdate.error || root.dataset.labelFailed || 'Failed'),
                    succeeded ? 'success' : 'error',
                );
            }
            if (progressPanel && !progressPanel.hidden) {
                if (progressBar) {
                    progressBar.classList.remove('progress-bar-animated');
                    progressBar.classList.toggle('bg-success', succeeded);
                    progressBar.classList.toggle('bg-danger', !succeeded);
                }
                if (progressStatus) progressStatus.textContent = imageStatusLabel(imageUpdate.status);
            }
        }

        function scheduleImagePoll() {
            window.clearTimeout(imageStatePollTimer);
            imageStatePollTimer = window.setTimeout(pollImageState, 2000);
        }

        function renderDeployProgress(doc, logText) {
            if (!modal) return;
            const st = doc && typeof doc.status === 'string' ? doc.status : '';
            const pct = DEPLOY_PCT[st] != null ? DEPLOY_PCT[st] : 100;
            if (progressBar) {
                progressBar.style.width = `${pct}%`;
                progressBar.classList.toggle('progress-bar-animated', st !== 'ready' && st !== 'failed');
                progressBar.classList.toggle('bg-danger', st === 'failed');
                progressBar.classList.toggle('bg-success', st === 'ready');
            }
            if (progressStatus) {
                progressStatus.textContent = st === 'failed' && doc && doc.error
                    ? String(doc.error)
                    : (DEPLOY_LABEL[st] || root.dataset.labelImageStarted || 'Updating…');
            }
            if (progressLog && logText) {
                progressLog.textContent = logText;
                progressLog.scrollTop = progressLog.scrollHeight;
            }
        }

        // Poll the proxy-served deploy status/log (works whether or not web is up).
        async function pollImageState() {
            if (!imgStarted) imgStarted = Date.now();
            let doc = null;
            let logText = '';
            try {
                const response = await fetch(deployStatusUrl, { headers: { Accept: 'application/json' }, cache: 'no-store' });
                if (response.ok) doc = await response.json();
            } catch (_error) { /* web/proxy briefly unreachable — keep polling */ }
            try {
                const logResponse = await fetch(deployLogUrl, { cache: 'no-store' });
                if (logResponse.ok) logText = (await logResponse.text()).trim();
            } catch (_error) { /* no console yet */ }

            const st = doc && typeof doc.status === 'string' ? doc.status : '';
            if (DEPLOY_INPROG[st]) imgSawProgress = true;
            renderDeployProgress(doc, logText);

            if (st === 'failed') {
                dismissButtons.forEach((button) => { button.disabled = false; });
                return; // stop polling; operator dismisses
            }
            // Honor 'ready' only after real progress this session (ignore a stale
            // 'ready' from a previous update) or after a safety timeout — then
            // reload in place to return the operator where they were.
            if (st === 'ready' && (imgSawProgress || Date.now() - imgStarted > 20000)) {
                window.location.reload();
                return;
            }
            scheduleImagePoll();
        }

        async function postSkip(version, unskip) {
            version = String(version || '').trim();
            if (!root.dataset.skipUrl || !version) { return; }
            const body = new FormData();
            body.append('version', version);
            if (unskip) { body.append('unskip', 'true'); }
            try {
                await jsonRequest(root.dataset.skipUrl, { method: 'POST', body });
                // Close the review modal via its dismiss control (the codebase
                // avoids calling the Bootstrap instance's hide directly).
                if (!unskip && dismissButtons && dismissButtons[0]) { dismissButtons[0].click(); }
                await refreshState();
            } catch (exc) {
                if (window.showToast) { window.showToast(exc.message || 'Request failed', 'error'); }
            }
        }

        function renderSkipped(versions) {
            if (!skippedWrap || !skippedList) { return; }
            const list = Array.isArray(versions) ? versions.filter(Boolean) : [];
            skippedList.innerHTML = '';
            if (!list.length) { skippedWrap.classList.add('d-none'); return; }
            const canManage = root.dataset.canManage === 'true';
            const unskipLabel = root.dataset.labelUnskip || 'Un-skip';
            list.forEach((version) => {
                const chip = document.createElement('span');
                chip.className = 'dlux-upd-skip-chip';
                const label = document.createElement('span');
                label.textContent = 'v' + String(version).replace(/^v/, '');
                chip.appendChild(label);
                if (canManage) {
                    const btn = document.createElement('button');
                    btn.type = 'button';
                    btn.textContent = '×';
                    btn.title = unskipLabel;
                    btn.setAttribute('aria-label', unskipLabel + ' v' + version);
                    btn.addEventListener('click', () => postSkip(version, true));
                    chip.appendChild(btn);
                }
                skippedList.appendChild(chip);
            });
            skippedWrap.classList.remove('d-none');
        }

        function render(nextState, run) {
            state = nextState || state;
            if (!state) return;
            renderSkipped(state.skipped_versions);
            active.textContent = state.active_version ? `v${state.active_version}` : '—';
            latest.textContent = state.latest_version ? `v${state.latest_version}` : '—';
            checked.textContent = state.last_checked_at
                ? new Date(state.last_checked_at).toLocaleString()
                : '—';
            const updateAvailable = Boolean(
                state.latest_compatible && state.latest_version &&
                state.latest_version !== state.active_version
            );
            // Translated status line (replaces the old "in progress"/"completed"
            // root status): a check error, else a clear update-ready / up-to-date
            // message, else whatever reason the backend supplied.
            if (reason) {
                if (state.last_check_error) {
                    reason.textContent = state.last_check_error;
                } else if (updateAvailable) {
                    reason.textContent = root.dataset.labelReady || state.latest_reason || '';
                } else if (state.last_checked_at && (!state.latest_version || state.latest_version === state.active_version)) {
                    reason.textContent = root.dataset.labelUptodate || state.latest_reason || '';
                } else {
                    reason.textContent = state.latest_reason || '';
                }
            }
            const imageAvailable = Boolean(state.image_update_available);
            const imgActive = imageActive(imageUpdate);
            // DjangoLux row: the check icon doubles as the status — a green
            // check when up to date, hidden when an update is available (the
            // down-arrow review icon takes its place); rollback icon if a
            // previous version exists.
            const checkedOnce = Boolean(state.last_checked_at);
            const fwOk = checkedOnce && !updateAvailable && !state.last_check_error;
            if (checkButton) {
                checkButton.hidden = updateAvailable;
                checkButton.classList.toggle('is-ok', fwOk);
                if (checkGlyph) checkGlyph.className = fwOk ? 'bi bi-check-circle-fill' : 'bi bi-arrow-clockwise';
            }
            if (reviewButton) reviewButton.hidden = !updateAvailable;
            if (rollbackButton) rollbackButton.hidden = !state.previous_version;
            // Application image row: version + short digest; green check when up
            // to date, down-arrow (start update) when a newer image is available.
            const img = state.image || {};
            // The deployed project's own version (from DLUX_APP_VERSION or a VERSION
            // file at BASE_DIR); the state view nests it under `image`, so read it
            // from there rather than the top level (which is never set).
            const appVersion = img.app_version || state.app_version || '';
            if (appVersionEl) appVersionEl.textContent = appVersion ? ('v' + String(appVersion).replace(/^v/, '')) : '';
            if (imageNameEl) { const nm = shortImageName(img.image); if (nm) imageNameEl.textContent = nm; }
            if (imageDigestEl) {
                imageDigestEl.textContent = shortDigest(img.running_digest);
                if (img.running_digest) imageDigestEl.title = img.running_digest;
            }
            if (imageCheckedEl) imageCheckedEl.textContent = fmtTime(img.checked_at);
            // When an update is available, show what it would update to: the target
            // version composer published, or the short remote digest as a fallback.
            if (imageTargetEl) {
                const tv = String(state.image_update_target || '').trim();
                if (imageAvailable && tv) {
                    imageTargetEl.textContent = '→ ' + (tv.indexOf('sha256:') === 0 ? shortDigest(tv) : (tv.charAt(0) === 'v' ? tv : 'v' + tv));
                    imageTargetEl.hidden = false;
                } else {
                    imageTargetEl.hidden = true;
                }
            }
            if (imageOkEl) imageOkEl.hidden = imageAvailable || imgActive;
            if (imageButton) imageButton.hidden = !imageAvailable;
            const running = Boolean(run?.active || state.active_run_token || imgActive);
            root.classList.toggle('is-running', running);
            if (checkButton) checkButton.disabled = running || Boolean(checkHandle);
            if (reviewButton) reviewButton.disabled = running;
            if (imageButton) imageButton.disabled = running;
            if (rollbackButton) rollbackButton.disabled = running;
            // While an image update is in flight, surface its phase on the root
            // status line (the inline run panel doesn't apply to image updates).
            if (imgActive) {
                setRootStatus(imageStatusLabel(imageUpdate.status, imageUpdate.deploy_status?.status));
            }
            const tracked = Boolean(run?.token && run.token === trackedRunToken);
            if (run && ['apply', 'rollback'].includes(run.action) && (run.active || !progressPanel?.hidden)) {
                showProgress(run);
            }
            if (run?.status === 'failed') {
                const message = run.error || root.dataset.labelFailed;
                showError(message, false);
                if (tracked && lastTerminalNotice !== run.token && window.showToast) {
                    lastTerminalNotice = run.token;
                    window.showToast(message, 'error');
                }
            }
            // Only a real apply/rollback announces completion — a background
            // "check" run must never claim that an update finished.
            if (tracked && ['apply', 'rollback'].includes(run?.action)
                && (run?.status === 'completed' || run?.status === 'rolled_back')) {
                if (lastTerminalNotice !== run.token && window.showToast) {
                    lastTerminalNotice = run.token;
                    window.showToast(root.dataset.labelCompleted || 'Completed');
                }
            }
        }

        async function refreshState() {
            window.clearTimeout(statePollTimer);
            const payload = await jsonRequest(root.dataset.stateUrl, { method: 'GET' });
            if (payload.run?.active && payload.run.token) {
                trackedRunToken = payload.run.token;
            }
            imageUpdate = payload.image_update || null;
            render(payload.state, payload.run);
            if (imageActive(imageUpdate)) {
                scheduleImagePoll();
            } else {
                finishImageNotice();
            }
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
                    stopCheckSpinner(); // no-op unless a check spinner is active
                    await refreshState();
                }
            } catch (_error) {
                schedulePoll();
            }
        }

        async function queue(url, body) {
            showError('');
            const payload = await jsonRequest(url, { method: 'POST', body });
            if (payload.run?.token) trackedRunToken = payload.run.token;
            render(payload.state, payload.run);
            if (payload.run_url) {
                runUrl = payload.run_url;
                schedulePoll();
            }
            return payload;
        }

        checkButton?.addEventListener('click', async () => {
            startCheckSpinner();
            try {
                await queue(root.dataset.checkUrl, new FormData());
                if (!runUrl) {
                    // Synchronous check: state is refreshed and we're done.
                    await refreshState();
                    stopCheckSpinner();
                }
                // Async check (run_url present): the spinner is stopped when the
                // tracked run reaches a terminal status in pollRun().
            } catch (requestError) {
                stopCheckSpinner();
                showError(requestError.message);
            }
        });

        // Render release notes as short bullet highlights instead of the long
        // prose summary (which made the modal very tall). The generic
        // "Bug fixes and improvements" entry is ALWAYS appended last, even when
        // a release ships no curated highlights.
        function renderReleaseNotes(container, manifest) {
            if (!container) return;
            container.textContent = '';
            const list = document.createElement('ul');
            list.className = 'dlux-update-highlights mb-0';
            const items = Array.isArray(manifest?.highlights) ? manifest.highlights : [];
            items.forEach((text) => {
                const clean = String(text || '').trim();
                if (!clean) return;
                const li = document.createElement('li');
                li.textContent = clean;
                list.appendChild(li);
            });
            const generic = document.createElement('li');
            generic.className = 'text-muted';
            generic.textContent = root.dataset.labelGenericChanges || 'Bug fixes and improvements';
            list.appendChild(generic);
            container.appendChild(list);
        }

        function openReview(action) {
            if (!modal || !state) return;
            currentAction = action;
            const isRollback = action === 'rollback';
            const isImage = action === 'image';
            let title = root.dataset.labelUpdateTitle;
            let confirm = root.dataset.labelUpdateConfirm;
            let target = state.latest_version;
            let manifest = state.latest_manifest;
            let compatibility = state.latest_reason || root.dataset.labelReady;
            if (isRollback) {
                title = root.dataset.labelRollbackTitle;
                confirm = root.dataset.labelRollbackConfirm;
                target = state.previous_version;
                manifest = state.previous_manifest;
                compatibility = state.previous_version ? root.dataset.labelLocalVerified : '—';
            } else if (isImage) {
                title = root.dataset.labelImageTitle;
                confirm = root.dataset.labelImageConfirm;
                target = state.image_update_target || state.latest_version;
                manifest = state.latest_manifest;
                compatibility = state.image_update_reason || state.latest_reason || '';
            }
            modalElement.querySelector('[data-dlux-update-modal-title]').textContent = title;
            modalElement.querySelector('[data-dlux-update-submit]').textContent = confirm;
            modalElement.querySelector('[data-dlux-update-target]').textContent = target;
            renderReleaseNotes(modalElement.querySelector('[data-dlux-update-summary]'), manifest);
            modalElement.querySelector('[data-dlux-update-compatibility]').textContent = compatibility;
            const maintenanceEl = modalElement.querySelector('[data-dlux-update-maintenance]');
            if (maintenanceEl) {
                maintenanceEl.textContent = isImage
                    ? (root.dataset.imageMaintenanceNote || root.dataset.maintenanceNote || maintenanceEl.textContent)
                    : (root.dataset.maintenanceNote || maintenanceEl.textContent);
            }
            // Re-apply guard: warn (and require an explicit acknowledgment) when
            // re-installing a wheel version that already failed a previous apply.
            // Only for a normal wheel apply — a rollback/image target is different.
            const failure = (!isRollback && !isImage) ? (state.latest_version_failure || null) : null;
            const requireAck = Boolean(
                failure && failure.version && String(failure.version) === String(target)
            );
            if (failedWarning) {
                if (requireAck) {
                    const tpl = root.dataset.labelRetryFailed || 'Version {version} already failed to install{when}.';
                    const whenStr = failure.at ? (' on ' + new Date(failure.at).toLocaleString()) : '';
                    let msg = tpl
                        .replace('{version}', 'v' + String(failure.version).replace(/^v/, ''))
                        .replace('{when}', whenStr);
                    if (failure.error) { msg += ' — ' + failure.error; }
                    if (failedText) { failedText.textContent = msg; }
                    if (failedAck) { failedAck.checked = false; }
                    failedWarning.classList.remove('d-none');
                } else {
                    failedWarning.classList.add('d-none');
                }
            }
            // "Skip this version" is only meaningful for a wheel apply of an
            // actually-offered version (not a rollback/image target).
            if (skipButton) {
                if (!isRollback && !isImage && target && String(target) !== String(state.active_version || '')) {
                    skipButton.dataset.skipVersion = String(target);
                    skipButton.classList.remove('d-none');
                } else {
                    skipButton.classList.add('d-none');
                }
            }
            reviewPanel.hidden = false;
            progressPanel.hidden = true;
            submit.hidden = false;
            // When a prior failure requires acknowledgment, the confirm button
            // stays disabled until the operator ticks the "retry anyway" box.
            submit.disabled = requireAck;
            password.disabled = false;
            dismissButtons.forEach((button) => { button.disabled = false; });
            if (dismissAction) {
                dismissAction.textContent = dismissActionLabel;
                dismissAction.classList.remove('btn-success');
                dismissAction.classList.add('btn-secondary');
            }
            password.value = '';
            showError('');
            modal.show();
        }

        if (failedAck) {
            failedAck.addEventListener('change', () => {
                // Gate the confirm button on the acknowledgment only while the
                // prior-failure warning is actually shown.
                if (failedWarning && !failedWarning.classList.contains('d-none')) {
                    submit.disabled = !failedAck.checked;
                }
            });
        }
        skipButton?.addEventListener('click', () => {
            const v = skipButton.dataset.skipVersion;
            if (v) { postSkip(v, false); }
        });
        reviewButton?.addEventListener('click', () => openReview('apply'));
        imageButton?.addEventListener('click', () => openReview('image'));
        rollbackButton?.addEventListener('click', () => openReview('rollback'));

        async function submitImage() {
            submit.disabled = true;
            try {
                const body = new FormData();
                body.append('current_password', password.value);
                const backupMode = modalElement?.querySelector('[data-dlux-update-backup-mode]');
                if (backupMode) body.append('backup_mode', backupMode.value);
                const payload = await jsonRequest(root.dataset.imageUrl, { method: 'POST', body });
                imageUpdate = payload.image_update || null;
                password.value = '';
                imgStarted = Date.now();
                imgSawProgress = false;
                showImageStarted();
                scheduleImagePoll();
            } catch (requestError) {
                showError(requestError.message);
                submit.disabled = false;
            }
        }

        async function submitAction() {
            if (!password.value) {
                password.reportValidity();
                return;
            }
            if (currentAction === 'image') {
                await submitImage();
                return;
            }
            submit.disabled = true;
            try {
                const url = currentAction === 'rollback' ? root.dataset.rollbackUrl : root.dataset.applyUrl;
                const body = new FormData();
                body.append('current_password', password.value);
                const backupMode = modalElement?.querySelector('[data-dlux-update-backup-mode]');
                if (backupMode && currentAction === 'apply') {
                    body.append('backup_mode', backupMode.value);
                }
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
