(function () {
    'use strict';

    const form = document.getElementById('general-report-form');
    const windowSelect = document.querySelector('[data-report-window]');
    const customPeriod = document.querySelector('[data-report-custom-period]');
    const customDates = document.querySelectorAll('[data-report-custom-date]');
    const modelCount = document.querySelector('[data-report-model-count]');
    const operationCount = document.querySelector('[data-report-operation-count]');

    function updateCustomPeriod() {
        const isCustom = windowSelect && windowSelect.value === 'custom';
        if (customPeriod) customPeriod.classList.toggle('d-none', !isCustom);
        customDates.forEach(function (field) {
            field.required = Boolean(isCustom);
            field.disabled = !isCustom;
        });
    }

    function updateCounts() {
        if (!form) return;
        if (modelCount) modelCount.textContent = String(form.querySelectorAll('input[name="models"]:checked').length);
        if (operationCount) operationCount.textContent = String(form.querySelectorAll('input[name="operations"]:checked').length);
    }

    let submitting = false;

    function submitBuilder() {
        if (!form || submitting) return;
        submitting = true;
        if (typeof form.requestSubmit === 'function') {
            form.requestSubmit();
        } else {
            form.submit();
        }
    }

    function bothCustomDatesFilled() {
        return Array.prototype.every.call(customDates, function (field) {
            return String(field.value || '').trim() !== '';
        });
    }

    document.querySelectorAll('[data-report-choice-panel]').forEach(function (panel) {
        const search = panel.querySelector('[data-report-choice-search]');
        const choices = panel.querySelectorAll('[data-report-choice]');
        if (search) {
            search.addEventListener('input', function () {
                const query = search.value.trim().toLowerCase();
                choices.forEach(function (choice) {
                    choice.classList.toggle('d-none', Boolean(query) && !choice.dataset.searchValue.includes(query));
                });
            });
        }
        panel.querySelectorAll('[data-report-select]').forEach(function (control) {
            control.addEventListener('click', function () {
                const checked = control.dataset.reportSelect === 'all';
                choices.forEach(function (choice) {
                    if (!choice.classList.contains('d-none')) {
                        const input = choice.querySelector('input[type="checkbox"]');
                        if (input) input.checked = checked;
                    }
                });
                updateCounts();
            });
        });
        panel.addEventListener('change', updateCounts);
    });

    /* Period drives the active window, the totals, and every export the builder
       hands off, so a new selection reloads the builder against it instead of
       leaving the page showing figures for the previous period. Switching *to*
       Custom only submits when a complete range is already present - a
       half-filled range would just trip the normalization warning, so the date
       fields stay on Apply. Model/operation ticks are carried along because they
       are fields of this same GET form. */
    if (windowSelect) {
        windowSelect.addEventListener('change', function () {
            updateCustomPeriod();
            if (windowSelect.value !== 'custom' || bothCustomDatesFilled()) {
                submitBuilder();
            }
        });
    }

    updateCustomPeriod();
    updateCounts();

    const btn = document.getElementById('reports-backup-btn');
    if (!btn) return;

    const note = document.getElementById('reports-backup-status');
    const latestLink = document.getElementById('reports-backup-latest');
    const latestMeta = latestLink ? latestLink.querySelector('[data-reports-backup-latest-meta]') : null;
    const btnLabel = btn.querySelector('[data-reports-backup-label]');
    const progress = document.getElementById('reports-backup-progress');
    const POLL_INTERVAL_MS = 3000;
    let busy = false;

    /* The bar shows how far along the build is; #reports-backup-status is the one
       and only place that narrates it. Writing the same message into both is what
       used to render every terminal message twice. */
    function setProgress(value, terminalTone) {
        if (!progress) return;
        const percent = Math.max(0, Math.min(parseInt(value || '0', 10) || 0, 100));
        const bar = progress.querySelector('progress');
        progress.classList.remove('d-none');
        progress.setAttribute('aria-valuenow', String(percent));
        if (bar) {
            bar.value = percent;
            bar.classList.toggle('dlux-backup-progress--error', terminalTone === 'error');
            bar.classList.toggle('dlux-backup-progress--success', terminalTone === 'success');
        }
    }

    function setNote(text, tone) {
        if (!note) return;
        note.textContent = text || '';
        note.classList.toggle('dlux-report-backup-status--error', tone === 'error');
        note.classList.toggle('dlux-report-backup-status--success', tone === 'success');
    }

    function setBusy(state) {
        busy = state;
        btn.disabled = state;
        if (btnLabel) {
            btnLabel.textContent = state
                ? (btn.dataset.labelBusy || btnLabel.textContent)
                : (btn.dataset.labelIdle || btnLabel.textContent);
        }
    }

    function formatBytes(bytes) {
        const size = Number(bytes);
        if (!size || size < 0) return '';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let index = 0;
        let value = size;
        while (value >= 1024 && index < units.length - 1) {
            value /= 1024;
            index += 1;
        }
        return (index === 0 ? value : value.toFixed(1)) + ' ' + units[index];
    }

    function revealLatest(downloadUrl, fileSize) {
        if (!latestLink) return;
        latestLink.href = downloadUrl;
        latestLink.classList.remove('d-none');
        if (latestMeta) {
            const size = formatBytes(fileSize);
            const when = btn.dataset.msgJustNow || '';
            latestMeta.textContent = [size, when].filter(Boolean).join(' · ');
        }
    }

    function finish(message, tone) {
        setBusy(false);
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
                    setProgress(100, 'success');
                    finish(btn.dataset.msgReady, 'success');
                    revealLatest(data.download_url, data.file_size);
                    window.location.assign(data.download_url);
                } else if (data.status === 'failed') {
                    setProgress(data.progress_percent, 'error');
                    finish(data.error || btn.dataset.msgFailed, 'error');
                } else {
                    setProgress(data.progress_percent);
                    setNote(data.progress_message || btn.dataset.msgPreparing);
                    setTimeout(function () { poll(statusUrl); }, POLL_INTERVAL_MS);
                }
            })
            .catch(function () {
                setTimeout(function () { poll(statusUrl); }, POLL_INTERVAL_MS);
            });
    }

    btn.addEventListener('click', function () {
        if (busy) return;

        setBusy(true);
        setNote(btn.dataset.msgPreparing);
        setProgress(0);

        const body = form ? new URLSearchParams(new FormData(form)) : new URLSearchParams();
        if (!body.has('window')) body.set('window', btn.dataset.window || 'all');

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
                    // Synchronous fallback: the response streams the zip itself,
                    // so there is no background job to show progress for.
                    if (progress) progress.classList.add('d-none');
                    finish(btn.dataset.msgReady, 'success');
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
        setBusy(true);
        setNote(btn.dataset.activeProgressMessage || btn.dataset.msgPreparing);
        setProgress(btn.dataset.activeProgress);
        poll(btn.dataset.activeStatusUrl);
    }
})();
