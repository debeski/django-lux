(function () {
    'use strict';

    const form = document.getElementById('sysbackup-create-form');
    const createBtn = document.getElementById('sysbackup-create-btn');
    const note = document.getElementById('sysbackup-create-status');
    const tableBody = document.getElementById('sysbackup-table-body');
    const restoreTableBody = document.getElementById('sysrestore-table-body');
    const POLL_INTERVAL_MS = 4000;
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

    function pollBackup(statusUrl, attempt) {
        if (!form || !createBtn) return;
        if (attempt >= POLL_LIMIT) {
            setNote(form.dataset.msgFailed, 'error');
            createBtn.disabled = false;
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
                    setNote(form.dataset.msgReady);
                    createBtn.disabled = false;
                    refreshBackupList(true);
                } else if (data.status === 'failed') {
                    setNote(form.dataset.msgFailed + (data.error ? ' - ' + data.error : ''), 'error');
                    createBtn.disabled = false;
                    refreshBackupList(true);
                } else {
                    // Say what the run is actually doing and how long ago it last
                    // said anything — a bare "preparing..." for an hour is what
                    // made a dead backup look like a slow one.
                    const parts = [(data.progress_percent || 0) + '%'];
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
        form.addEventListener('submit', function (event) {
            event.preventDefault();
            createBtn.disabled = true;
            setNote(form.dataset.msgPreparing);
            const formData = new FormData(form);
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
                        if (!resp.ok) throw new Error(data.error || 'create failed');
                        return data;
                    });
                })
                .then(function (data) {
                    if (data.status === 'completed') {
                        setNote(form.dataset.msgReady);
                        createBtn.disabled = false;
                        refreshBackupList(true);
                    } else if (data.status === 'failed') {
                        setNote(form.dataset.msgFailed, 'error');
                        createBtn.disabled = false;
                        refreshBackupList(true);
                    } else {
                        pollBackup(data.status_url, 0);
                        refreshBackupList(true);
                    }
                })
                .catch(function (error) {
                    setNote(error.message || form.dataset.msgFailed, 'error');
                    createBtn.disabled = false;
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
        (items || []).forEach(function (item) {
            const previous = previousStatuses[item.token];
            if (previous === item.status) return;
            if (item.status === 'completed') completed = true;
            if (item.status === 'failed') failed = true;
        });
        if (failed && form) {
            setNote(form.dataset.msgFailed, 'error');
        } else if (completed && form) {
            setNote(form.dataset.msgReady);
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
                    announceStatusChanges(previousStatuses, data.items);
                }
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
