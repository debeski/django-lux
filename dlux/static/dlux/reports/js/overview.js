(function () {
    'use strict';

    const btn = document.getElementById('reports-backup-btn');
    if (!btn) return;

    const note = document.getElementById('reports-backup-status');
    const POLL_INTERVAL_MS = 3000;
    const POLL_LIMIT = 1200;
    let busy = false;

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

    function poll(statusUrl, attempt) {
        if (attempt >= POLL_LIMIT) {
            finish(btn.dataset.msgFailed, 'error');
            return;
        }

        fetch(statusUrl, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (data.status === 'completed' && data.download_url) {
                    finish(btn.dataset.msgReady);
                    window.location.assign(data.download_url);
                } else if (data.status === 'failed') {
                    finish(btn.dataset.msgFailed, 'error');
                } else {
                    setTimeout(function () { poll(statusUrl, attempt + 1); }, POLL_INTERVAL_MS);
                }
            })
            .catch(function () {
                setTimeout(function () { poll(statusUrl, attempt + 1); }, POLL_INTERVAL_MS);
            });
    }

    btn.addEventListener('click', function () {
        if (busy) return;

        busy = true;
        btn.disabled = true;
        setNote(btn.dataset.msgPreparing);

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
                    poll(data.status_url, 0);
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
})();
