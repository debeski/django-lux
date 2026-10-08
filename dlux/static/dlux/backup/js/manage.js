(function () {
    'use strict';

    const form = document.getElementById('sysbackup-create-form');
    const createBtn = document.getElementById('sysbackup-create-btn');
    const fields = document.getElementById('sysbackup-create-fields');
    const note = document.getElementById('sysbackup-create-status');
    const busyNote = document.getElementById('sysbackup-busy-note');
    const estimateNote = document.getElementById('sysbackup-estimate');
    const encryptionNote = document.getElementById('sysbackup-encryption-note');
    const encryptionSelect = document.getElementById('sysbackup-encryption');
    const scopeSelect = document.getElementById('sysbackup-scope');
    const passphraseInputs = [
        document.getElementById('sysbackup-passphrase'),
        document.getElementById('sysbackup-passphrase-confirm'),
    ].filter(Boolean);
    const tableBody = document.getElementById('sysbackup-table-body');
    const restoreTableBody = document.getElementById('sysrestore-table-body');
    const POLL_INTERVAL_MS = 4000;
    const DETAILS_POLL_MS = 2000;
    const POLL_LIMIT = 1800;
    const IDLE_LIST_POLL_MS = 15000;
    const STALL_WARN_SECONDS = 120;
    let listPollTimer = null;
    let listRequestActive = false;
    let restorePollTimer = null;
    let restoreRequestActive = false;

    function setNote(text, tone) {
        if (!note) return;
        note.textContent = text || '';
        note.className = 'text-center ' + (tone === 'error' ? 'text-danger' : 'text-muted');
    }

    function formatDuration(seconds) {
        if (seconds === null || seconds === undefined || seconds === '') return '';
        const units = form ? form.dataset : {};
        const total = Math.max(0, Math.round(Number(seconds)));
        const hours = Math.floor(total / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        const secs = total % 60;
        const pad = function (value) { return String(value).padStart(2, '0'); };
        if (hours) return hours + (units.unitH || 'h') + ' ' + pad(minutes) + (units.unitM || 'm');
        if (minutes) return minutes + (units.unitM || 'm') + ' ' + pad(secs) + (units.unitS || 's');
        return secs + (units.unitS || 's');
    }

    function clearPassphrases() {
        passphraseInputs.forEach(function (input) { input.value = ''; });
    }

    // While any backup is pending or running, a second one cannot start: the
    // server refuses it, and the form says so instead of failing on submit.
    function setBusy(busy) {
        if (!form) return;
        form.dataset.busy = busy ? '1' : '0';
        if (fields) fields.disabled = !!busy;
        if (busyNote) busyNote.hidden = !busy;
    }

    function syncEncryption() {
        if (!encryptionSelect) return;
        const mode = encryptionSelect.value;
        document.querySelectorAll('.dlux-backup-passphrase-field').forEach(function (field) {
            field.hidden = mode !== 'passphrase';
        });
        passphraseInputs.forEach(function (input) {
            input.required = mode === 'passphrase';
            if (mode !== 'passphrase') input.value = '';
        });
        if (encryptionNote) encryptionNote.hidden = mode !== 'none';
    }

    function syncEstimate() {
        if (!form || !estimateNote || !scopeSelect) return;
        const seconds = scopeSelect.value === 'data' ? form.dataset.estimateData : form.dataset.estimateFull;
        estimateNote.hidden = !seconds;
        if (seconds) {
            estimateNote.textContent = (form.dataset.msgEstimate || '{duration}').replace('{duration}', formatDuration(seconds));
        }
    }

    function finishRun(text, tone) {
        setNote(text, tone);
        setBusy(false);
        refreshBackupList(true);
    }

    function pollBackup(statusUrl, attempt) {
        if (!form) return;
        if (attempt >= POLL_LIMIT) {
            setNote(form.dataset.msgFailed, 'error');
            return;
        }
        fetch(statusUrl, {
            cache: 'no-store',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
            .then(function (resp) {
                if (!resp.ok) throw new Error('status failed');
                return resp.json();
            })
            .then(function (data) {
                if (data.status === 'completed') {
                    finishRun(form.dataset.msgReady);
                } else if (data.status === 'failed') {
                    finishRun(form.dataset.msgFailed + (data.error ? ' - ' + data.error : ''), 'error');
                } else if (data.status === 'cancelled') {
                    finishRun(form.dataset.msgCancelled);
                } else {
                    // Say what the run is actually doing and how long ago it last
                    // said anything — a bare "preparing..." for an hour is what
                    // made a dead backup look like a slow one.
                    const parts = [(data.progress_percent || 0) + '%'];
                    if (data.eta) parts.push((form.dataset.msgEta || '{duration}').replace('{duration}', data.eta));
                    if (data.progress_message) parts.push(data.progress_message);
                    if (data.attempt_count > 1) {
                        parts.push('#' + data.attempt_count + '/' + (data.max_attempts || data.attempt_count));
                    }
                    const quietFor = data.seconds_since_progress || 0;
                    parts.push((form.dataset.msgLastSignal || 'last update') + ' ' + quietFor + 's');
                    setNote(parts.join(' · '), quietFor > STALL_WARN_SECONDS ? 'error' : null);
                    setTimeout(function () { pollBackup(statusUrl, attempt + 1); }, POLL_INTERVAL_MS);
                }
            })
            .catch(function () {
                setTimeout(function () { pollBackup(statusUrl, attempt + 1); }, POLL_INTERVAL_MS);
            });
    }

    if (form && createBtn) {
        if (encryptionSelect) encryptionSelect.addEventListener('change', syncEncryption);
        if (scopeSelect) scopeSelect.addEventListener('change', syncEstimate);
        syncEncryption();
        syncEstimate();
        form.addEventListener('submit', function (event) {
            event.preventDefault();
            if (form.dataset.busy === '1') return;
            setNote(form.dataset.msgPreparing);
            const formData = new FormData(form);
            // The passphrase lives only in this request; never leave it typed
            // into the page once the backup has been handed off.
            clearPassphrases();
            setBusy(true);
            const csrfInput = form.querySelector('[name="csrfmiddlewaretoken"]');
            fetch(form.dataset.createUrl, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': csrfInput ? csrfInput.value : '',
                    'X-Requested-With': 'XMLHttpRequest',
                },
            })
                .then(function (resp) {
                    return resp.json().then(function (data) {
                        if (resp.status === 409) {
                            setNote(data.error || '', 'error');
                            refreshBackupList(true);
                            return null;
                        }
                        if (!resp.ok) throw new Error(data.error || 'create failed');
                        return data;
                    });
                })
                .then(function (data) {
                    if (!data) return;
                    if (data.status === 'completed') {
                        finishRun(form.dataset.msgReady);
                    } else if (data.status === 'failed') {
                        finishRun(form.dataset.msgFailed, 'error');
                    } else {
                        pollBackup(data.status_url, 0);
                        refreshBackupList(true);
                    }
                })
                .catch(function (error) {
                    setNote(error.message || form.dataset.msgFailed, 'error');
                    setBusy(false);
                });
        });
    }

    const detailsModal = document.getElementById('sysbackup-details-modal');
    let detailsUrl = '';
    let detailsTimer = null;

    function renderDetails(data) {
        if (!detailsModal) return;
        const progress = detailsModal.querySelector('[data-details-progress]');
        const facts = detailsModal.querySelector('[data-details-facts]');
        const consoleEl = detailsModal.querySelector('[data-details-console]');
        if (progress) progress.value = data.status === 'completed' ? 100 : (data.progress_percent || 0);
        if (facts) {
            facts.replaceChildren();
            const rows = [[detailsModal.dataset.msgElapsed, data.elapsed]];
            if (data.active && data.eta) rows.push([detailsModal.dataset.msgEta, data.eta]);
            rows.forEach(function (row) {
                if (!row[1]) return;
                const dt = document.createElement('dt');
                dt.textContent = row[0];
                const dd = document.createElement('dd');
                dd.textContent = row[1];
                facts.append(dt, dd);
            });
        }
        if (consoleEl) {
            const pinned = consoleEl.scrollTop + consoleEl.clientHeight >= consoleEl.scrollHeight - 8;
            const lines = (data.log || []).map(function (entry) {
                const at = entry.at ? new Date(entry.at).toLocaleTimeString() : '';
                return '[' + at + '] ' + String(entry.percent).padStart(3, ' ') + '%  ' + (entry.message || '');
            });
            if (data.error) lines.push('!! ' + data.error);
            consoleEl.textContent = lines.length ? lines.join('\n') : (detailsModal.dataset.msgEmpty || '');
            if (pinned) consoleEl.scrollTop = consoleEl.scrollHeight;
        }
    }

    function pollDetails() {
        if (!detailsUrl) return;
        fetch(detailsUrl, { cache: 'no-store', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (resp) {
                if (!resp.ok) throw new Error('details failed');
                return resp.json();
            })
            .then(function (data) {
                renderDetails(data);
                if (data.active && detailsUrl) detailsTimer = window.setTimeout(pollDetails, DETAILS_POLL_MS);
            })
            .catch(function () {
                if (detailsUrl) detailsTimer = window.setTimeout(pollDetails, POLL_INTERVAL_MS);
            });
    }

    function bindDetailsButtons(root) {
        if (!detailsModal || !window.bootstrap) return;
        root.querySelectorAll('.sysbackup-details-open:not([data-dlux-backup-bound])').forEach(function (btn) {
            btn.dataset.dluxBackupBound = 'true';
            btn.addEventListener('click', function () {
                const label = detailsModal.querySelector('[data-details-label]');
                if (label) label.textContent = btn.dataset.backupLabel || '';
                const consoleEl = detailsModal.querySelector('[data-details-console]');
                if (consoleEl) consoleEl.textContent = '';
                if (detailsTimer) window.clearTimeout(detailsTimer);
                detailsUrl = btn.dataset.statusUrl || '';
                window.bootstrap.Modal.getOrCreateInstance(detailsModal).show();
                pollDetails();
            });
        });
    }

    if (detailsModal) {
        detailsModal.addEventListener('hidden.bs.modal', function () {
            detailsUrl = '';
            if (detailsTimer) window.clearTimeout(detailsTimer);
        });
    }

    function bindCancelForms(root) {
        root.querySelectorAll('.sysbackup-cancel-form:not([data-dlux-backup-bound])').forEach(function (cancelForm) {
            cancelForm.dataset.dluxBackupBound = 'true';
            cancelForm.addEventListener('submit', function (event) {
                event.preventDefault();
                const button = cancelForm.querySelector('button');
                if (button) button.disabled = true;
                const csrfInput = cancelForm.querySelector('[name="csrfmiddlewaretoken"]');
                fetch(cancelForm.action, {
                    method: 'POST',
                    body: new FormData(cancelForm),
                    headers: {
                        'X-CSRFToken': csrfInput ? csrfInput.value : '',
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                })
                    .then(function (resp) { return resp.json(); })
                    .then(function (data) { setNote(data.message || ''); })
                    .catch(function () { if (button) button.disabled = false; })
                    .finally(function () { refreshBackupList(true); });
            });
        });
    }

    const panel = document.getElementById('sysrestore-panel');
    const tokenInput = document.getElementById('sysrestore-token');
    const fileInput = document.getElementById('sysrestore-file');
    const labelSpan = document.getElementById('sysrestore-label');

    const resumePanel = document.getElementById('sysbackup-resume-panel');
    const resumeForm = document.getElementById('sysbackup-resume-form');
    const resumeLabel = document.getElementById('sysbackup-resume-label');
    const resumePassphraseWrap = document.getElementById('sysbackup-resume-passphrase-wrap');
    const resumePassphrase = document.getElementById('sysbackup-resume-passphrase');

    function bindResumeButtons(root) {
        root.querySelectorAll('.sysbackup-resume-open:not([data-dlux-backup-bound])').forEach(function (btn) {
            btn.dataset.dluxBackupBound = 'true';
            btn.addEventListener('click', function () {
                if (!resumePanel || !resumeForm || !resumeLabel) return;
                resumeForm.action = btn.dataset.resumeUrl || '';
                resumeLabel.textContent = btn.dataset.backupLabel || '';
                const needsPassphrase = btn.dataset.needsPassphrase === '1';
                if (resumePassphraseWrap) {
                    resumePassphraseWrap.classList.toggle('d-none', !needsPassphrase);
                }
                if (resumePassphrase) {
                    resumePassphrase.value = '';
                    resumePassphrase.required = needsPassphrase;
                }
                resumePanel.classList.remove('d-none');
                resumePanel.scrollIntoView({ behavior: 'smooth', block: 'center' });
            });
        });
    }

    function bindRestoreButtons(root) {
        root.querySelectorAll('.sysrestore-open:not([data-dlux-backup-bound])').forEach(function (btn) {
            btn.dataset.dluxBackupBound = 'true';
            btn.addEventListener('click', function () {
                if (!panel || !tokenInput || !fileInput || !labelSpan) return;
                tokenInput.value = btn.dataset.backupToken || '';
                fileInput.value = btn.dataset.backupFile || '';
                labelSpan.textContent = btn.dataset.backupLabel || '';
                panel.classList.remove('d-none');
                panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
            });
        });
    }

    function tableStatuses() {
        const statuses = {};
        if (!tableBody) return statuses;
        tableBody.querySelectorAll('[data-system-backup-row]').forEach(function (row) {
            statuses[row.dataset.backupToken || ''] = row.dataset.backupStatus || '';
        });
        return statuses;
    }

    function tableHasActiveBackup() {
        return Object.values(tableStatuses()).some(function (status) {
            return status === 'pending' || status === 'running';
        });
    }

    function announceStatusChanges(previousStatuses, items) {
        let completed = false;
        let failed = false;
        let cancelled = false;
        (items || []).forEach(function (item) {
            const previous = previousStatuses[item.token];
            if (previous === item.status) return;
            if (item.status === 'completed') completed = true;
            if (item.status === 'failed') failed = true;
            if (item.status === 'cancelled') cancelled = true;
        });
        if (failed && form) {
            setNote(form.dataset.msgFailed, 'error');
        } else if (completed && form) {
            setNote(form.dataset.msgReady);
        } else if (cancelled && form) {
            setNote(form.dataset.msgCancelled);
        }
    }

    function announceStalledBackups(items) {
        if (!form) return;
        const stalled = (items || []).find(function (item) { return item.stalled; });
        if (!stalled) return;
        const template = form.dataset.msgStalled || '';
        setNote(
            template.replace('{seconds}', String(stalled.seconds_since_progress || 0)) +
                (stalled.progress_message ? ' - ' + stalled.progress_message : ''),
            'error',
        );
    }

    function scheduleListPoll(delay) {
        if (!tableBody) return;
        if (listPollTimer) window.clearTimeout(listPollTimer);
        listPollTimer = window.setTimeout(refreshBackupList, delay);
    }

    function refreshBackupList(forceRender) {
        if (!tableBody || !tableBody.dataset.statusUrl || listRequestActive) return;
        if (document.hidden) {
            scheduleListPoll(IDLE_LIST_POLL_MS);
            return;
        }
        listRequestActive = true;
        const previousStatuses = tableStatuses();
        fetch(tableBody.dataset.statusUrl, {
            cache: 'no-store',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
            .then(function (resp) {
                if (!resp.ok) throw new Error('backup list status failed');
                return resp.json();
            })
            .then(function (data) {
                if (forceRender || data.revision !== tableBody.dataset.revision) {
                    tableBody.innerHTML = data.html || '';
                    tableBody.dataset.revision = data.revision || '';
                    bindRestoreButtons(tableBody);
                    bindResumeButtons(tableBody);
                    bindDetailsButtons(tableBody);
                    bindCancelForms(tableBody);
                    announceStatusChanges(previousStatuses, data.items);
                }
                if (typeof data.busy === 'boolean') setBusy(data.busy);
                announceStalledBackups(data.items);
                scheduleListPoll(data.active ? POLL_INTERVAL_MS : IDLE_LIST_POLL_MS);
            })
            .catch(function () {
                scheduleListPoll(IDLE_LIST_POLL_MS);
            })
            .finally(function () {
                listRequestActive = false;
            });
    }

    function tableHasActiveRestore() {
        if (!restoreTableBody) return false;
        return Array.prototype.some.call(
            restoreTableBody.querySelectorAll('[data-system-restore-row]'),
            function (row) {
                const status = row.dataset.restoreStatus || '';
                return status === 'pending' || status === 'running';
            },
        );
    }

    function scheduleRestorePoll(delay) {
        if (!restoreTableBody) return;
        if (restorePollTimer) window.clearTimeout(restorePollTimer);
        restorePollTimer = window.setTimeout(refreshRestoreList, delay);
    }

    function refreshRestoreList() {
        if (!restoreTableBody || !restoreTableBody.dataset.statusUrl || restoreRequestActive) return;
        if (document.hidden) {
            scheduleRestorePoll(IDLE_LIST_POLL_MS);
            return;
        }
        restoreRequestActive = true;
        fetch(restoreTableBody.dataset.statusUrl, {
            cache: 'no-store',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
            .then(function (resp) {
                if (!resp.ok) throw new Error('restore list status failed');
                return resp.json();
            })
            .then(function (data) {
                const wasActive = tableHasActiveRestore();
                if (data.revision !== restoreTableBody.dataset.revision) {
                    restoreTableBody.innerHTML = data.html || '';
                    restoreTableBody.dataset.revision = data.revision || '';
                }
                // A finished restore replaced this session's data, so the rest of
                // the page (backups, external files, and the viewer's own login)
                // is stale — reload once rather than leave a half-truthful page.
                if (wasActive && !data.active) {
                    window.setTimeout(function () { window.location.reload(); }, 1500);
                    return;
                }
                scheduleRestorePoll(data.active ? POLL_INTERVAL_MS : IDLE_LIST_POLL_MS);
            })
            .catch(function () {
                scheduleRestorePoll(IDLE_LIST_POLL_MS);
            })
            .finally(function () {
                restoreRequestActive = false;
            });
    }

    bindRestoreButtons(document);
    bindResumeButtons(document);
    bindDetailsButtons(document);
    bindCancelForms(document);
    const resumeCancel = document.getElementById('sysbackup-resume-cancel');
    if (resumeCancel && resumePanel) {
        resumeCancel.addEventListener('click', function () { resumePanel.classList.add('d-none'); });
    }
    if (tableHasActiveBackup() && form) setNote(form.dataset.msgPreparing);
    scheduleListPoll(tableHasActiveBackup() ? POLL_INTERVAL_MS : IDLE_LIST_POLL_MS);
    scheduleRestorePoll(tableHasActiveRestore() ? POLL_INTERVAL_MS : IDLE_LIST_POLL_MS);
    document.addEventListener('visibilitychange', function () {
        if (document.hidden) return;
        refreshBackupList(false);
        refreshRestoreList();
    });

    const cancelBtn = document.getElementById('sysrestore-cancel');
    if (cancelBtn && panel) {
        cancelBtn.addEventListener('click', function () { panel.classList.add('d-none'); });
    }
})();
