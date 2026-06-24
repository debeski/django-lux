(function () {
    'use strict';

    const btn = document.getElementById('reports-backup-btn');
    if (!btn) return;

    const note = document.getElementById('reports-backup-status');
    const latestLink = document.getElementById('reports-backup-latest');
    const progress = document.getElementById('reports-backup-progress');
    const POLL_INTERVAL_MS = 3000;
    let busy = false;

    function setProgress(value, message, terminalTone) {
        if (!progress) return;
        const percent = Math.max(0, Math.min(parseInt(value || '0', 10) || 0, 100));
        const bar = progress.querySelector('progress');
        const label = progress.querySelector('[data-reports-backup-progress-label]');
        progress.classList.remove('d-none');
        progress.setAttribute('aria-valuenow', String(percent));
        if (bar) {
            bar.value = percent;
            bar.classList.toggle('dlux-backup-progress--error', terminalTone === 'error');
            bar.classList.toggle('dlux-backup-progress--success', terminalTone === 'success');
        }
        if (label) label.textContent = message || (percent + '%');
    }

    function setNote(text, tone) {
        if (!note) return;
        note.textContent = text || '';
        note.className = 'text-center ' + (tone === 'error' ? 'text-danger' : 'text-muted');
    }

    function finish(message, tone) {
        busy = false;
        btn.disabled = false;
        setNote(message, tone);
    }

    function poll(statusUrl) {
        fetch(statusUrl, {
            cache: 'no-store',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
            .then(function (resp) {
                if (!resp.ok) throw new Error('status failed');
                return resp.json();
            })
            .then(function (data) {
                if (data.status === 'completed' && data.download_url) {
                    setProgress(100, data.progress_message || btn.dataset.msgReady, 'success');
                    finish(btn.dataset.msgReady);
                    if (latestLink) {
                        latestLink.href = data.download_url;
                        latestLink.classList.remove('d-none');
                    }
                    window.location.assign(data.download_url);
                } else if (data.status === 'failed') {
                    setProgress(data.progress_percent, data.error || data.progress_message, 'error');
                    finish(data.error || btn.dataset.msgFailed, 'error');
                } else {
                    setProgress(data.progress_percent, data.progress_message || btn.dataset.msgPreparing);
                    setTimeout(function () { poll(statusUrl); }, POLL_INTERVAL_MS);
                }
            })
            .catch(function () {
                setTimeout(function () { poll(statusUrl); }, POLL_INTERVAL_MS);
            });
    }

    btn.addEventListener('click', function () {
        if (busy) return;

        busy = true;
        btn.disabled = true;
        setNote(btn.dataset.msgPreparing);
        setProgress(0, btn.dataset.msgPreparing);

        const windowSelect = document.getElementById('reports-window');
        const selectedWindow = (windowSelect && windowSelect.value) || btn.dataset.window || 'all';
        const body = new URLSearchParams();
        body.set('window', selectedWindow);

        fetch(btn.dataset.startUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': btn.dataset.csrf || '',
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: body.toString(),
        })
            .then(function (resp) {
                if (!resp.ok) throw new Error('start failed');
                return resp.json();
            })
            .then(function (data) {
                if (data.async && data.status_url) {
                    poll(data.status_url);
                } else if (data.download_url) {
                    finish('');
                    window.location.assign(data.download_url);
                } else {
                    finish(btn.dataset.msgFailed, 'error');
                }
            })
            .catch(function () {
                finish(btn.dataset.msgFailed, 'error');
            });
    });

    if (btn.dataset.activeStatusUrl) {
        busy = true;
        btn.disabled = true;
        setNote(btn.dataset.msgPreparing);
        setProgress(btn.dataset.activeProgress, btn.dataset.activeProgressMessage || btn.dataset.msgPreparing);
        poll(btn.dataset.activeStatusUrl);
    }
})();
