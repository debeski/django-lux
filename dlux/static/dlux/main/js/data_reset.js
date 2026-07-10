/*
 * Data-reset admin command (DSRP-1: external asset, no inline JS).
 *
 * Flow: launcher chip → global confirm-password prompt (window.dluxConfirmPassword)
 * → POST the password to the preview endpoint → open the selection modal populated
 * with the discovered models (row counts, scoped/media badges) → the operator picks
 * models + a delete-media toggle → the Reset button re-sends the password to the
 * execute endpoint. Scoped models are soft-deleted server-side; the rest are
 * permanently removed. Superusers and system settings are never listed.
 */
(function () {
    'use strict';

    function s(key, fallback) {
        var v = (window.DLUX_STRINGS || {})[key];
        return (typeof v === 'string' && v.length) ? v : fallback;
    }
    function csrf() {
        return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')
            || document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
    }
    function post(url, body) {
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': csrf(), 'X-Requested-With': 'XMLHttpRequest' },
            body: body,
        }).then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); });
    }

    function init() {
        var chip = document.querySelector('[data-data-reset-open]');
        var modalEl = document.querySelector('[data-data-reset-modal]');
        if (!chip || !modalEl || !window.bootstrap) { return; }

        var listEl = modalEl.querySelector('[data-data-reset-list]');
        var mediaEl = modalEl.querySelector('[data-data-reset-media]');
        var executeBtn = modalEl.querySelector('[data-data-reset-execute]');
        var resultEl = modalEl.querySelector('[data-data-reset-result]');
        var selectAll = modalEl.querySelector('[data-data-reset-select-all]');
        var selectNone = modalEl.querySelector('[data-data-reset-select-none]');
        var modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);

        var executeUrl = chip.getAttribute('data-execute-url');
        var password = '';   // held only while the selection modal is open

        modalEl.addEventListener('hidden.bs.modal', function () { password = ''; });

        function checkboxes() {
            return Array.prototype.slice.call(listEl.querySelectorAll('input[type="checkbox"][data-model]'));
        }
        function refreshExecuteState() {
            var any = checkboxes().some(function (cb) { return cb.checked; });
            executeBtn.disabled = !any;
        }

        function renderList(models) {
            listEl.innerHTML = '';
            resultEl.classList.add('d-none');
            resultEl.innerHTML = '';
            if (!models.length) {
                listEl.textContent = s('data_reset_empty', 'No models available to reset.');
                return;
            }
            models.forEach(function (m, i) {
                var row = document.createElement('label');
                row.className = 'dlux-data-reset-row d-flex align-items-center gap-2 py-2 border-bottom';

                var cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.className = 'form-check-input flex-shrink-0 m-0';
                cb.id = 'dlux-data-reset-' + i;
                cb.setAttribute('data-model', m.key);
                cb.disabled = !m.count;
                cb.addEventListener('change', refreshExecuteState);
                row.appendChild(cb);
                row.htmlFor = cb.id;

                var name = document.createElement('span');
                name.className = 'flex-grow-1';
                name.setAttribute('dir', 'auto');
                name.textContent = m.label;
                row.appendChild(name);

                var count = document.createElement('span');
                count.className = 'badge text-bg-secondary';
                count.textContent = String(m.count);
                row.appendChild(count);

                var kind = document.createElement('span');
                if (m.scoped) {
                    kind.className = 'badge text-bg-info';
                    kind.textContent = s('data_reset_soft_badge', 'soft-delete');
                } else {
                    kind.className = 'badge text-bg-danger';
                    kind.textContent = s('data_reset_hard_badge', 'permanent');
                }
                row.appendChild(kind);

                if (m.has_media) {
                    var media = document.createElement('i');
                    media.className = 'bi bi-paperclip text-muted';
                    media.title = s('data_reset_has_media', 'Has media files');
                    row.appendChild(media);
                }
                listEl.appendChild(row);
            });
            refreshExecuteState();
        }

        function openPrompt() {
            if (typeof window.dluxConfirmPassword !== 'function') { return; }
            window.dluxConfirmPassword({
                title: chip.getAttribute('data-title'),
                description: chip.getAttribute('data-description'),
                confirmLabel: chip.getAttribute('data-confirm-label'),
                icon: 'bi-trash3-fill',
                danger: true,
                requirePassword: true,
                onConfirm: function (pw, ctx) {
                    return post(chip.getAttribute('data-preview-url'), new URLSearchParams({ current_password: pw }))
                        .then(function (res) {
                            if (!res.ok || res.data.status !== 'success') {
                                throw new Error(res.data.message || s('data_reset_preview_failed', 'Unable to load models.'));
                            }
                            password = pw;
                            renderList(res.data.models || []);
                            modal.show();
                            return true;   // close the password prompt
                        });
                },
            });
        }

        function execute() {
            var selected = checkboxes().filter(function (cb) { return cb.checked; }).map(function (cb) { return cb.getAttribute('data-model'); });
            if (!selected.length || !password) { return; }
            var body = new URLSearchParams();
            body.set('current_password', password);
            body.set('delete_media', mediaEl && mediaEl.checked ? '1' : '0');
            selected.forEach(function (key) { body.append('models', key); });

            executeBtn.disabled = true;
            var original = executeBtn.innerHTML;
            executeBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>' + executeBtn.textContent.trim();

            post(executeUrl, body).then(function (res) {
                if (!res.ok || res.data.status !== 'success') {
                    throw new Error(res.data.message || s('data_reset_failed', 'Data reset failed.'));
                }
                resultEl.className = 'mt-3 alert alert-success';
                resultEl.setAttribute('data-autoclose', 'false');
                resultEl.textContent = res.data.message || '';
                resultEl.classList.remove('d-none');
                if (window.showToast && res.data.message) { window.showToast(res.data.message); }
                window.setTimeout(function () { window.location.reload(); }, 1500);
            }).catch(function (err) {
                resultEl.className = 'mt-3 alert alert-danger';
                resultEl.setAttribute('data-autoclose', 'false');
                resultEl.textContent = (err && err.message) || s('data_reset_failed', 'Data reset failed.');
                resultEl.classList.remove('d-none');
                executeBtn.disabled = false;
                executeBtn.innerHTML = original;
            });
        }

        chip.addEventListener('click', openPrompt);
        executeBtn.addEventListener('click', execute);
        if (selectAll) { selectAll.addEventListener('click', function () { checkboxes().forEach(function (cb) { if (!cb.disabled) { cb.checked = true; } }); refreshExecuteState(); }); }
        if (selectNone) { selectNone.addEventListener('click', function () { checkboxes().forEach(function (cb) { cb.checked = false; }); refreshExecuteState(); }); }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
