(function () {
    'use strict';

    const form = document.getElementById('sysbackup-create-form');
    const createBtn = document.getElementById('sysbackup-create-btn');
    const note = document.getElementById('sysbackup-create-status');
    const POLL_INTERVAL_MS = 4000;
    const POLL_LIMIT = 1800;

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
        fetch(statusUrl, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (data.status === 'completed') {
                    setNote(form.dataset.msgReady);
                    window.location.reload();
                } else if (data.status === 'failed') {
                    setNote(form.dataset.msgFailed + (data.error ? ' - ' + data.error : ''), 'error');
                    createBtn.disabled = false;
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
                    if (data.status === 'completed' || data.status === 'failed') {
                        window.location.reload();
                    } else {
                        pollBackup(data.status_url, 0);
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
    document.querySelectorAll('.sysrestore-open').forEach(function (btn) {
        btn.addEventListener('click', function () {
            if (!panel || !tokenInput || !fileInput || !labelSpan) return;
            tokenInput.value = btn.dataset.backupToken || '';
            fileInput.value = btn.dataset.backupFile || '';
            labelSpan.textContent = btn.dataset.backupLabel || '';
            panel.classList.remove('d-none');
            panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
    });
    const cancelBtn = document.getElementById('sysrestore-cancel');
    if (cancelBtn && panel) {
        cancelBtn.addEventListener('click', function () { panel.classList.add('d-none'); });
    }
})();
