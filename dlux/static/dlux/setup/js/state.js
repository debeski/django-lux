/* Setup wizard: the form-state cache.
 *
 * The wizard mirrors the form into sessionStorage under
 * `dlux.systemSetupState:<surface>` so a rejected submit does not lose whatever
 * the operator already typed. Session-scoped on purpose: it survives a reload,
 * not a new tab. Written on submit and on settings-import only — a step change
 * merely records the index in a dataset attribute.
 *
 * Covered by tests-e2e/wizard.test.mjs ("submitting caches the form",
 * "a cached state is restored").
 *
 * Depends on setup/js/dom.js.
 */
(function (root) {
    'use strict';

    const SETUP_STATE_KEY_PREFIX = 'dlux.systemSetupState:';

    function applySetupFormStateValues(form, values, options) {
        const config = options && typeof options === 'object' ? options : {};
        const dispatchEvents = Boolean(config.dispatchEvents);
        const fieldsToDispatch = [];
        Object.entries(values || {}).forEach(([name, value]) => {
            const safeName = String(name).replace(/"/g, '\\"');
            const fields = Array.from(form.querySelectorAll(`[name="${safeName}"]`));
            if (!fields.length) {
                return;
            }

            if (fields[0].type === 'radio') {
                fields.forEach((field) => {
                    field.checked = field.value === value;
                });
                if (dispatchEvents) {
                    const checked = fields.find((field) => field.checked);
                    if (checked) {
                        fieldsToDispatch.push({ field: checked, input: false, change: true });
                    }
                }
                return;
            }

            fields.forEach((field) => {
                if (field.type === 'checkbox') {
                    if (Array.isArray(value)) {
                        const allowedValues = value.map((item) => String(item));
                        field.checked = allowedValues.includes(String(field.value));
                    } else {
                        field.checked = Boolean(value);
                    }
                } else if (field.multiple && field.options && Array.isArray(value)) {
                    const selectedValues = value.map((item) => String(item));
                    Array.from(field.options).forEach((option) => {
                        option.selected = selectedValues.includes(String(option.value));
                    });
                } else if (field.type !== 'file') {
                    field.value = value;
                }
                if (dispatchEvents && field.type !== 'file') {
                    fieldsToDispatch.push({ field, input: field.type !== 'checkbox', change: true });
                }
            });
        });
        fieldsToDispatch.forEach(({ field, input, change }) => {
            if (input) {
                field.dispatchEvent(new Event('input', { bubbles: true }));
            }
            if (change) {
                field.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    }

    function getSetupStateKey(form) {
        return `${SETUP_STATE_KEY_PREFIX}${resolveSetupStateSurface(form)}`;
    }

    function persistSetupFormState(form) {
        if (!form || !form.classList.contains('dlux-system-setup-form')) {
            return;
        }

        const state = {
            surface: resolveSetupStateSurface(form),
            values: {},
        };
        const currentStep = readSetupWizardCurrentStep(form);
        if (currentStep !== null) {
            state.currentStep = currentStep;
        }

        const fieldsByName = new Map();
        form.querySelectorAll('input[name], select[name], textarea[name]').forEach((field) => {
            if (!field.name || field.name === 'csrfmiddlewaretoken' || field.disabled || field.type === 'file') {
                return;
            }
            if (!fieldsByName.has(field.name)) {
                fieldsByName.set(field.name, []);
            }
            fieldsByName.get(field.name).push(field);
        });

        fieldsByName.forEach((fields, name) => {
            if (!fields.length) {
                return;
            }
            const firstField = fields[0];

            if (firstField.type === 'radio') {
                const checked = fields.find((field) => field.checked);
                if (checked) {
                    state.values[name] = checked.value;
                }
                return;
            }

            if (firstField.type === 'checkbox') {
                if (fields.length === 1) {
                    state.values[name] = Boolean(firstField.checked);
                } else {
                    state.values[name] = fields
                        .filter((field) => field.checked)
                        .map((field) => field.value);
                }
                return;
            }

            if (firstField.multiple && firstField.options) {
                state.values[name] = Array.from(firstField.selectedOptions).map((option) => option.value);
                return;
            }

            state.values[name] = firstField.value;
        });

        sessionStorage.setItem(getSetupStateKey(form), JSON.stringify(state));
    }

    function readSetupWizardCurrentStep(form) {
        if (!form) {
            return null;
        }
        const datasetStep = Number(form.dataset.dluxWizardCurrentStep);
        if (Number.isInteger(datasetStep) && datasetStep >= 0) {
            return datasetStep;
        }
        const activeNavItem = form.querySelector('[data-dlux-wizard-step-target].is-active');
        const activeNavStep = activeNavItem ? Number(activeNavItem.getAttribute('data-dlux-wizard-step-target')) : NaN;
        if (Number.isInteger(activeNavStep) && activeNavStep >= 0) {
            return activeNavStep;
        }
        const steps = Array.from(form.querySelectorAll('.wizard-step'));
        const visibleIndex = steps.findIndex((step) => (
            !step.classList.contains('d-none') &&
            step.getAttribute('aria-hidden') !== 'true' &&
            step.style.display !== 'none'
        ));
        return visibleIndex >= 0 ? visibleIndex : null;
    }

    function rememberSetupWizardStep(form, step) {
        const resolvedStep = Number(step);
        if (!form || !Number.isInteger(resolvedStep) || resolvedStep < 0) {
            return;
        }
        form.dataset.dluxWizardCurrentStep = String(resolvedStep);
    }

    function resolveSetupStateSurface(form) {
        const action = form && form.getAttribute ? (form.getAttribute('action') || '') : '';
        try {
            const url = new URL(action || window.location.href, window.location.origin);
            return `${url.pathname}${url.search}`;
        } catch (err) {
            return `${window.location.pathname}${window.location.search}`;
        }
    }

    root.DluxSetup = Object.assign(root.DluxSetup || {}, {
        applySetupFormStateValues,
        getSetupStateKey,
        persistSetupFormState,
        readSetupWizardCurrentStep,
        rememberSetupWizardStep,
        resolveSetupStateSurface
    });
})(typeof window !== 'undefined' ? window : globalThis);
