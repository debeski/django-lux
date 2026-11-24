(function () {
    'use strict';
    const confirmed = new WeakSet();
    const gated = new WeakSet();

    // Everything below Enable OCR waits on it: greyed out with the shared
    // dependent tooltip naming the switch, and live again as soon as it is on.
    function gateDependents(panel) {
        const helpers = window.DluxSetupDom;
        const toggle = panel.querySelector('[name="ocr_enabled"]');
        const dependent = panel.querySelector('[data-ocr-dependent]');
        if (!helpers || !toggle || !dependent || toggle.disabled || gated.has(panel)) return;
        gated.add(panel);
        const sync = () => helpers.setDependentFieldEnabled(dependent, toggle.checked, helpers.dependentReason(toggle));
        toggle.addEventListener('change', sync);
        sync();
    }

    function initialize(root) {
        root.querySelectorAll('[data-ocr-settings]').forEach((panel) => {
            gateDependents(panel);
            if (typeof window.dluxConfirmPassword !== 'function') return;
            const field = panel.querySelector('[name="ocr_current_password"]');
            if (field) {
                field.value = '';
                const wrapper = field.closest('.mb-3');
                if (wrapper) wrapper.hidden = !wrapper.querySelector('.invalid-feedback, .errorlist');
            }
        });
    }

    document.addEventListener('submit', (event) => {
        const form = event.target;
        const panel = form.querySelector?.('[data-ocr-settings]');
        const enabled = panel?.querySelector('[name="ocr_enabled"]');
        const password = panel?.querySelector('[name="ocr_current_password"]');
        if (!enabled || enabled.disabled || !password || typeof window.dluxConfirmPassword !== 'function') return;
        const changed = enabled.checked !== (panel.dataset.ocrInitialEnabled === 'true');
        if (!changed) return;
        if (confirmed.has(form)) {
            confirmed.delete(form);
            return;
        }
        event.preventDefault();
        event.stopImmediatePropagation();
        const submitter = event.submitter;
        window.dluxConfirmPassword({
            title: panel.dataset.ocrConfirmTitle,
            description: panel.dataset.ocrConfirmDescription,
            requirePassword: true,
            icon: 'bi-file-text',
            onConfirm(value) {
                password.value = value;
                confirmed.add(form);
                form.requestSubmit(submitter || undefined);
                window.setTimeout(() => { password.value = ''; confirmed.delete(form); }, 0);
            },
        });
    }, true);

    document.addEventListener('dlux:modal-content-loaded', (event) => initialize(event.target));
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initialize(document));
    else initialize(document);
})();
