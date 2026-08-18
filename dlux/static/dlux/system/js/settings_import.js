/* Options-page config import.
 *
 * Pick a file -> POST it for review -> a modal shows what would change, with
 * every checkbox unticked -> apply only what was ticked.
 *
 * Nothing here decides what a change is. The server builds the change set, keeps
 * it in the session and re-reads it on apply, so this file only ever posts a
 * list of tokens the operator ticked. A doctored post cannot introduce a value
 * that was never reviewed.
 *
 * DSRP-1: no inline JS; everything is found through data-* attributes.
 */
(function () {
    'use strict';

    function t(key, fallback) {
        if (window.DLUX_STRINGS && typeof window.DLUX_STRINGS[key] === 'string' && window.DLUX_STRINGS[key]) {
            return window.DLUX_STRINGS[key];
        }
        return fallback;
    }

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function notify(kind, message) {
        if (window.dluxNotify && typeof window.dluxNotify[kind] === 'function') {
            window.dluxNotify[kind](message);
            return;
        }
        // The notification helper is optional on some layouts; never swallow
        // the outcome of a write silently.
        if (kind === 'error') console.error(message);
    }

    // Selection mirrors the permissions widget (users/js/permissions.js): a
    // master checkbox per card that ticks everything under it, going
    // indeterminate on a partial selection. Same markup classes, so it also
    // inherits users/css/permissions.css — one selection pattern in the app,
    // not two.
    //
    // Delegated from `document` because the review is injected by the dynamic
    // modal after an async fetch; binding to a root at load time binds nothing.
    function cardBoxes(card) {
        return Array.from(card.querySelectorAll('[data-settings-import-check]'))
            .filter((box) => !box.disabled);
    }

    function syncMaster(card) {
        const master = card.querySelector('.app-master-checkbox');
        if (!master) return;
        const boxes = cardBoxes(card);
        const checked = boxes.filter((b) => b.checked).length;
        master.checked = boxes.length > 0 && checked === boxes.length;
        master.indeterminate = checked > 0 && checked < boxes.length;
    }

    document.addEventListener('change', (event) => {
        const target = event.target;

        if (target.matches('.app-master-checkbox')) {
            const card = target.closest('[data-settings-import-group]');
            if (!card) return;   // the permissions widget owns its own masters
            cardBoxes(card).forEach((box) => { box.checked = target.checked; });
            target.indeterminate = false;
            return;
        }

        if (target.matches('[data-settings-import-check]')) {
            const card = target.closest('[data-settings-import-group]');
            if (card) syncMaster(card);
        }
    });

    document.addEventListener('click', (event) => {
        const submit = event.target.closest('[data-settings-import-apply]');
        if (!submit) return;

        const selected = Array.from(document.querySelectorAll('[data-settings-import-check]'))
            .filter((b) => b.checked).map((b) => b.value);
        if (!selected.length) {
            notify('warning', t('settings_import_nothing_selected', 'Select at least one change to apply.'));
            return;
        }
        const applyUrl = submit.getAttribute('data-settings-import-apply');
        const body = new FormData();
        body.append('csrfmiddlewaretoken', csrfToken());
        selected.forEach((value) => body.append('apply', value));

        submit.disabled = true;
        fetch(applyUrl, { method: 'POST', body, credentials: 'same-origin' })
            .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
            .then(({ ok, data }) => {
                if (!ok || !data.ok) {
                    submit.disabled = false;
                    notify('error', data.message || t('settings_import_failed', 'Import failed.'));
                    return;
                }
                // Settings drive the chrome already on screen, so reload rather
                // than try to patch a live page piecemeal.
                window.location.reload();
            })
            .catch(() => {
                submit.disabled = false;
                notify('error', t('settings_import_failed', 'Import failed.'));
            });
    });

    function openReview(reviewUrl) {
        // The dynamic modal is URL-driven — it fetches the address and injects
        // the response. Handing it raw HTML is not part of its protocol.
        document.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', {
            detail: {
                data: {
                    url: reviewUrl,
                    title: t('system_settings_import', 'Import setup file'),
                },
            },
        }));
    }

    function init(root) {
        (root.querySelectorAll ? root.querySelectorAll('[data-settings-import-open]') : []).forEach((button) => {
            if (button.dataset.settingsImportBound === 'true') return;
            button.dataset.settingsImportBound = 'true';

            // Created here rather than in the template: dlux templates must not
            // hand-render generic file inputs (guarded by
            // test_dlux_owned_templates_do_not_hand_render_generic_file_inputs),
            // and this is a programmatic trigger, not a form field.
            const file = document.createElement('input');
            file.type = 'file';
            file.accept = 'application/json,.json';
            file.className = 'd-none';
            file.setAttribute('data-settings-import-file', '');
            button.insertAdjacentElement('afterend', file);
            const previewUrl = button.getAttribute('data-settings-import-preview-url');

            button.addEventListener('click', () => file.click());

            file.addEventListener('change', () => {
                if (!file.files || !file.files.length) return;
                const body = new FormData();
                body.append('csrfmiddlewaretoken', csrfToken());
                body.append('config_file', file.files[0]);
                // Clear immediately so picking the same file twice still fires.
                file.value = '';

                fetch(previewUrl, { method: 'POST', body, credentials: 'same-origin' })
                    .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
                    .then(({ ok, data }) => {
                        if (!ok || !data.ok) {
                            notify('error', data.message || t('settings_import_failed', 'Import failed.'));
                            return;
                        }
                        openReview(data.review_url);
                    })
                    .catch(() => notify('error', t('settings_import_failed', 'Import failed.')));
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => init(document));
    } else {
        init(document);
    }
})();
