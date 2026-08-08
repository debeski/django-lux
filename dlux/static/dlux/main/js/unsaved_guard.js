/*
 * Unsaved-changes guard for modal forms (DSRP-1: external asset, no inline JS).
 *
 * A form marked `data-dlux-unsaved-guard` inside a modal is snapshotted once its
 * initializers have settled. Closing the modal while the current values differ
 * from that snapshot — backdrop click, the X button, or Escape — is intercepted
 * and the #dluxUnsavedModal prompt offers three outcomes:
 *
 *   Save changes  → submits the form through its own validation
 *   Discard       → closes and drops the edits
 *   Go back       → cancels the close and returns to the form
 *
 * The prompt carries a "don't ask again" switch. Turning it on stores
 * `skip_unsaved_settings_prompt` on the profile, after which closing a dirty
 * form always discards without prompting.
 *
 * Why a snapshot rather than an input listener: the settings form rewrites its
 * own hidden JSON carriers (sidebar_config, navbar_config…) during init and
 * live preview, and those writes dispatch synthetic input/change events. A
 * listener would call the form dirty before the admin touched anything.
 */
(function () {
    'use strict';

    const GUARD_SELECTOR = 'form[data-dlux-unsaved-guard]';
    const SKIP_PREFERENCE = 'skip_unsaved_settings_prompt';

    function shouldSkipPrompt() {
        return Boolean(window.USER_PREFS && window.USER_PREFS[SKIP_PREFERENCE]);
    }

    // Same shape as the setup wizard's own state serializer: one entry per named
    // control, so a rewritten hidden JSON carrier counts as a change.
    function serializeForm(form) {
        const values = {};
        const byName = new Map();
        form.querySelectorAll('input[name], select[name], textarea[name]').forEach((field) => {
            if (!field.name || field.name === 'csrfmiddlewaretoken' || field.type === 'file') {
                return;
            }
            if (!byName.has(field.name)) {
                byName.set(field.name, []);
            }
            byName.get(field.name).push(field);
        });

        byName.forEach((fields, name) => {
            const first = fields[0];
            if (first.type === 'radio') {
                const checked = fields.find((field) => field.checked);
                values[name] = checked ? checked.value : null;
                return;
            }
            if (first.type === 'checkbox') {
                values[name] = fields.length === 1
                    ? Boolean(first.checked)
                    : fields.filter((field) => field.checked).map((field) => field.value);
                return;
            }
            if (first.multiple && first.options) {
                values[name] = Array.from(first.selectedOptions).map((option) => option.value);
                return;
            }
            values[name] = first.value;
        });

        try {
            return JSON.stringify(values);
        } catch (err) {
            return '';
        }
    }

    function baselineForm(form) {
        if (!form) {
            return;
        }
        form.dataset.dluxUnsavedBaseline = serializeForm(form);
    }

    function isDirty(form) {
        if (!form || form.dataset.dluxUnsavedBaseline === undefined) {
            return false;
        }
        return serializeForm(form) !== form.dataset.dluxUnsavedBaseline;
    }

    function guardedForms(root) {
        if (!root || !root.querySelectorAll) {
            return [];
        }
        return Array.from(root.querySelectorAll(GUARD_SELECTOR));
    }

    function dirtyFormIn(modalEl) {
        return guardedForms(modalEl).find(isDirty) || null;
    }

    function persistSkipPreference() {
        if (window.USER_PREFS) {
            window.USER_PREFS[SKIP_PREFERENCE] = true;
        }
        if (typeof window.updatePreferences === 'function') {
            window.updatePreferences({ [SKIP_PREFERENCE]: true });
        }
    }

    /*
     * config: { form, onDiscard, onStay }
     * Returns nothing; the chosen outcome drives the callbacks.
     */
    function showUnsavedPrompt(config) {
        const modalEl = document.querySelector('[data-dlux-unsaved-modal]');
        if (!modalEl || !window.bootstrap) {
            // No prompt available — never trap the admin inside the modal.
            if (config && typeof config.onDiscard === 'function') {
                config.onDiscard();
            }
            return;
        }

        const form = config.form;
        const skipToggle = modalEl.querySelector('[data-dlux-unsaved-skip]');
        const errorEl = modalEl.querySelector('[data-dlux-unsaved-error]');
        const saveBtn = modalEl.querySelector('[data-dlux-unsaved-save]');
        const discardBtn = modalEl.querySelector('[data-dlux-unsaved-discard]');
        const stayBtns = Array.from(modalEl.querySelectorAll('[data-dlux-unsaved-stay]'));

        if (skipToggle) {
            skipToggle.checked = false;
        }
        if (errorEl) {
            errorEl.textContent = '';
            errorEl.classList.add('d-none');
        }

        const instance = window.bootstrap.Modal.getOrCreateInstance(modalEl, {
            backdrop: 'static',
            keyboard: false,
        });
        // Raise the backdrop this prompt adds above the modal underneath it;
        // the CSS keys off the body class (see .dlux-modal-stacked in main.css).
        document.body.classList.add('dlux-modal-stacked-open');

        let outcome = 'stay';

        function finish(next) {
            outcome = next;
            instance.hide();
        }

        function onSave() {
            const submitter = form ? form.querySelector('.dlux-btn-submit, button[type="submit"]') : null;
            // requestSubmit runs the form's own validation and submit handlers,
            // which a direct programmatic submit would bypass. The named
            // submitter matters because the wizard branches on it server-side.
            if (form && typeof form.requestSubmit === 'function') {
                finish('save');
                if (submitter) {
                    form.requestSubmit(submitter);
                } else {
                    form.requestSubmit();
                }
                return;
            }
            if (submitter) {
                finish('save');
                submitter.click();
                return;
            }
            if (errorEl) {
                errorEl.textContent = errorEl.getAttribute('data-fallback')
                    || 'Could not submit this form automatically.';
                errorEl.classList.remove('d-none');
            }
        }

        function onDiscard() {
            if (skipToggle && skipToggle.checked) {
                persistSkipPreference();
            }
            finish('discard');
        }

        function cleanup() {
            if (saveBtn) { saveBtn.removeEventListener('click', onSave); }
            if (discardBtn) { discardBtn.removeEventListener('click', onDiscard); }
            stayBtns.forEach((btn) => btn.removeEventListener('click', onStay));
            modalEl.removeEventListener('hidden.bs.modal', onHidden);

            if (outcome === 'discard' && typeof config.onDiscard === 'function') {
                config.onDiscard();
            } else if (outcome === 'stay' && typeof config.onStay === 'function') {
                config.onStay();
            }
        }

        function onStay() {
            finish('stay');
        }

        function onHidden() {
            document.body.classList.remove('dlux-modal-stacked-open');
            // Bootstrap strips `modal-open` when any modal hides, including this
            // one closing over a modal that is staying put — restore it so the
            // page underneath does not start scrolling behind the settings modal.
            if (document.querySelector('.modal.show')) {
                document.body.classList.add('modal-open');
            }
            cleanup();
        }

        if (saveBtn) { saveBtn.addEventListener('click', onSave); }
        if (discardBtn) { discardBtn.addEventListener('click', onDiscard); }
        stayBtns.forEach((btn) => btn.addEventListener('click', onStay));
        modalEl.addEventListener('hidden.bs.modal', onHidden);

        instance.show();
    }

    // Bootstrap fires hide.bs.modal for the backdrop, the X button and Escape
    // alike, so one interception covers every way out of the modal.
    function guardModal(modalEl) {
        if (!modalEl || modalEl.dataset.dluxUnsavedGuardBound === 'true') {
            return;
        }
        modalEl.dataset.dluxUnsavedGuardBound = 'true';

        modalEl.addEventListener('hide.bs.modal', function (event) {
            if (modalEl.dataset.dluxUnsavedRelease === 'true') {
                delete modalEl.dataset.dluxUnsavedRelease;
                return;
            }
            const form = dirtyFormIn(modalEl);
            if (!form) {
                return;
            }
            if (shouldSkipPrompt()) {
                return;
            }

            event.preventDefault();
            showUnsavedPrompt({
                form: form,
                onDiscard: function () {
                    modalEl.dataset.dluxUnsavedRelease = 'true';
                    window.bootstrap.Modal.getOrCreateInstance(modalEl).hide();
                },
            });
        });

        modalEl.addEventListener('hidden.bs.modal', function () {
            guardedForms(modalEl).forEach((form) => {
                delete form.dataset.dluxUnsavedBaseline;
            });
        });
    }

    function scanGuards(root) {
        guardedForms(root || document).forEach((form) => {
            if (form.dataset.dluxUnsavedBound === 'true') {
                return;
            }
            form.dataset.dluxUnsavedBound = 'true';

            const modalEl = form.closest('.modal');
            if (modalEl) {
                guardModal(modalEl);
            }
            // A submitted form is no longer dirty; the page or modal is about to
            // be replaced by the server's response either way.
            form.addEventListener('submit', () => baselineForm(form));
        });

        // Snapshot after the current task and one paint, so the setup form's own
        // initializers (which rewrite hidden JSON carriers) are already done.
        window.requestAnimationFrame(() => {
            window.requestAnimationFrame(() => {
                guardedForms(root || document).forEach((form) => {
                    if (form.dataset.dluxUnsavedBaseline === undefined) {
                        baselineForm(form);
                    }
                });
            });
        });
    }

    window.dluxUnsavedGuard = {
        scan: scanGuards,
        baseline: baselineForm,
        isDirty: isDirty,
        serialize: serializeForm,
    };

    document.addEventListener('DOMContentLoaded', () => scanGuards(document));

    // The dynamic modal injects its form with innerHTML and dispatches no
    // lifecycle event, so guarded forms are picked up the same way the setup
    // wizard picks up its own controls.
    const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            for (const node of mutation.addedNodes) {
                if (node.nodeType !== 1) {
                    continue;
                }
                if ((node.matches && node.matches(GUARD_SELECTOR)) || (node.querySelector && node.querySelector(GUARD_SELECTOR))) {
                    scanGuards(node);
                    return;
                }
            }
        }
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
})();
