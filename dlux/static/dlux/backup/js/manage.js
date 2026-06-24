(function () {
    'use strict';

    const form = document.getElementById('sysbackup-create-form');
    const createBtn = document.getElementById('sysbackup-create-btn');
    const note = document.getElementById('sysbackup-create-status');
    const tableBody = document.getElementById('sysbackup-table-body');
    const POLL_INTERVAL_MS = 4000;
    const POLL_LIMIT = 1800;
    const IDLE_LIST_POLL_MS = 15000;
    let listPollTimer = null;
    let listRequestActive = false;

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
                    announceStatusChanges(previousStatuses, data.items);
                }
                scheduleListPoll(data.active ? POLL_INTERVAL_MS : IDLE_LIST_POLL_MS);
            })
            .catch(function () {
                scheduleListPoll(IDLE_LIST_POLL_MS);
            })
            .finally(function () {
                listRequestActive = false;
            });
    }

    bindRestoreButtons(document);
    if (tableHasActiveBackup() && form) setNote(form.dataset.msgPreparing);
    scheduleListPoll(tableHasActiveBackup() ? POLL_INTERVAL_MS : IDLE_LIST_POLL_MS);
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) refreshBackupList(false);
    });

    const cancelBtn = document.getElementById('sysrestore-cancel');
    if (cancelBtn && panel) {
        cancelBtn.addEventListener('click', function () { panel.classList.add('d-none'); });
    }
})();
