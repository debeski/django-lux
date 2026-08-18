/* Publish a ScanLink installer from the Extra Features modal.
 *
 * Document-delegated: the form arrives via the dynamic modal after an async
 * fetch, so binding to a root at load time binds nothing.
 *
 * The file input is created here rather than in the template — dlux templates
 * must not hand-render generic file inputs (guarded by
 * test_dlux_owned_templates_do_not_hand_render_generic_file_inputs) — and this
 * is a programmatic trigger, not a form field.
 */
(function () {
    'use strict';

    function t(key, fallback) {
        const strings = window.DLUX_STRINGS || {};
        return (typeof strings[key] === 'string' && strings[key]) || fallback;
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
        if (kind === 'error') console.error(message);
    }

    function pickedFile(form) {
        // DluxFileInput renders the real input; read from it rather than
        // creating a second picker beside the dlux widget.
        const input = form.querySelector('input[type="file"]');
        return input && input.files && input.files.length ? input.files[0] : null;
    }

    document.addEventListener('submit', (event) => {
        const form = event.target.closest('[data-scanlink-upload-form]');
        if (!form) return;
        event.preventDefault();

        const file = pickedFile(form);
        if (!file) {
            notify('warning', t('scanlink_choose_installer_first', 'Choose an installer file first.'));
            return;
        }

        const submit = form.querySelector('[data-scanlink-publish]');
        const body = new FormData();
        body.append('csrfmiddlewaretoken', csrfToken());
        ['version', 'arch', 'notes'].forEach((name) => {
            const field = form.querySelector(`[name="${name}"]`);
            if (field) body.append(name, field.value);
        });
        const active = form.querySelector('[name="is_active"]');
        if (active && active.checked) body.append('is_active', 'on');
        body.append('installer', file);

        if (submit) submit.disabled = true;
        fetch(form.getAttribute('data-upload-url'), {
            method: 'POST', body, credentials: 'same-origin',
        })
            .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
            .then(({ ok, data }) => {
                if (!ok || !data.ok) {
                    if (submit) submit.disabled = false;
                    notify('error', (data && data.message) || t('scanlink_release_failed', 'Could not publish the release.'));
                    return;
                }
                // The releases table is rendered server-side, so reload rather
                // than patch a list that the manifest also depends on.
                window.location.reload();
            })
            .catch(() => {
                if (submit) submit.disabled = false;
                notify('error', t('scanlink_release_failed', 'Could not publish the release.'));
            });
    });

    // The switch takes effect on click, not on save: managing installers is
    // gated on ScanLink being on, so requiring a save-and-reopen first put a
    // detour between the operator and the thing they opened the step to do.
    document.addEventListener('change', (event) => {
        const toggle = event.target.closest('[name="scanlink_enabled"]');
        if (!toggle) return;
        const body = new FormData();
        body.append('csrfmiddlewaretoken', csrfToken());
        body.append('enabled', toggle.checked ? 'true' : 'false');
        fetch('/scanlink/toggle/', { method: 'POST', body, credentials: 'same-origin' })
            .then((response) => response.json())
            .then((data) => {
                if (!data || !data.ok) return;
                document.querySelectorAll('[data-scanlink-requires-enabled]').forEach((el) => {
                    el.toggleAttribute('disabled', !data.enabled);
                    el.classList.toggle('disabled', !data.enabled);
                });
            })
            .catch(() => notify('error', t('scanlink_toggle_failed', 'Could not change the ScanLink setting.')));
    });
})();