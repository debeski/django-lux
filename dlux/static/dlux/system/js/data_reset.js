/*
 * Data-reset admin command (DSRP-1: external asset, no inline JS).
 *
 * Flow: launcher chip → global confirm-password prompt (window.dluxConfirmPassword)
 * → POST the password to the preview endpoint → open the selection modal populated
 * with the discovered models (row counts, scoped/media badges) → the operator picks
 * models + a delete-media toggle → the Reset button re-sends the password to the
 * execute endpoint. Scoped models are soft-deleted server-side; the rest are
 * permanently removed. Superusers and system settings are never listed.
 *
 * The permanent switch turns the whole run into a hard delete — every badge
 * flips, the counts grow by each model's recycle bin, and the Reset button stays
 * disabled until the confirmation word is typed. The server re-checks that word;
 * this is the part that makes the operator read the sentence above it.
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
        var permanentEl = modalEl.querySelector('[data-data-reset-permanent]');
        var permanentPanel = modalEl.querySelector('[data-data-reset-permanent-panel]');
        var confirmEl = modalEl.querySelector('[data-data-reset-confirm]');
        var confirmLabelEl = modalEl.querySelector('[data-data-reset-confirm-label]');
        var modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);

        var executeUrl = chip.getAttribute('data-execute-url');
        var password = '';   // held only while the selection modal is open
        var softLabel = executeBtn.innerHTML;
        var rows = [];       // [{model, cb, count, kind}] — repainted per mode

        modalEl.addEventListener('hidden.bs.modal', function () {
            password = '';
            // The dangerous mode never survives a close: reopening starts safe.
            if (permanentEl) { permanentEl.checked = false; }
            if (confirmEl) { confirmEl.value = ''; }
            applyMode();
        });

        function isPermanent() { return !!(permanentEl && permanentEl.checked); }

        function confirmWord() {
            return (confirmEl && confirmEl.getAttribute('data-confirm-word')) || 'DELETE';
        }
        function confirmOk() {
            if (!isPermanent()) { return true; }
            if (!confirmEl) { return false; }
            return confirmEl.value.trim().toLocaleLowerCase() === confirmWord().trim().toLocaleLowerCase();
        }

        function checkboxes() {
            return Array.prototype.slice.call(listEl.querySelectorAll('input[type="checkbox"][data-model]'));
        }
        function refreshExecuteState() {
            var any = checkboxes().some(function (cb) { return cb.checked; });
            executeBtn.disabled = !any || !confirmOk();
        }

        /* Repaint everything the mode changes: the warning panel, the per-row
           badge and count, and the button that carries out the run. */
        function applyMode() {
            var permanent = isPermanent();
            if (permanentPanel) { permanentPanel.classList.toggle('d-none', !permanent); }
            if (confirmLabelEl) {
                var template = (confirmEl && confirmEl.getAttribute('data-confirm-template')) || 'Type {word} to confirm';
                confirmLabelEl.textContent = template.replace('{word}', confirmWord());
            }
            modalEl.classList.toggle('dlux-data-reset-permanent', permanent);
            executeBtn.innerHTML = permanent
                ? '<i class="bi bi-fire me-1"></i>' + s('data_reset_execute_permanent', 'Permanently delete selected data')
                : softLabel;
            rows.forEach(function (entry) {
                var scopedSoft = entry.model.scoped && !permanent;
                entry.kind.className = scopedSoft ? 'badge text-bg-info' : 'badge text-bg-danger';
                entry.kind.textContent = scopedSoft
                    ? s('data_reset_soft_badge', 'soft-delete')
                    : s('data_reset_hard_badge', 'permanent');
                var trashed = permanent ? (entry.model.trashed || 0) : 0;
                var total = (entry.model.count || 0) + trashed;
                entry.count.textContent = String(total);
                entry.count.title = trashed
                    ? s('data_reset_trashed', '{count} already soft-deleted').replace('{count}', String(trashed))
                    : '';
                // A model with nothing live but a full recycle bin is only
                // actionable in permanent mode.
                entry.cb.disabled = !total;
                if (entry.cb.disabled) { entry.cb.checked = false; }
            });
            refreshExecuteState();
        }

        function renderList(models) {
            listEl.innerHTML = '';
            rows = [];
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
                row.appendChild(count);

                var kind = document.createElement('span');
                row.appendChild(kind);
                rows.push({ model: m, cb: cb, count: count, kind: kind });

                if (m.has_media) {
                    var media = document.createElement('i');
                    media.className = 'bi bi-paperclip text-muted';
                    media.title = s('data_reset_has_media', 'Has media files');
                    row.appendChild(media);
                }
                listEl.appendChild(row);
            });
            applyMode();   // paints counts and badges for the current mode
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
            if (!confirmOk()) { return; }
            var body = new URLSearchParams();
            body.set('current_password', password);
            body.set('delete_media', mediaEl && mediaEl.checked ? '1' : '0');
            body.set('mode', isPermanent() ? 'permanent' : 'soft');
            if (isPermanent()) { body.set('confirm_permanent', confirmEl.value.trim()); }
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
        if (permanentEl) { permanentEl.addEventListener('change', applyMode); }
        if (confirmEl) { confirmEl.addEventListener('input', refreshExecuteState); }
        if (selectAll) { selectAll.addEventListener('click', function () { checkboxes().forEach(function (cb) { if (!cb.disabled) { cb.checked = true; } }); refreshExecuteState(); }); }
        if (selectNone) { selectNone.addEventListener('click', function () { checkboxes().forEach(function (cb) { cb.checked = false; }); refreshExecuteState(); }); }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
