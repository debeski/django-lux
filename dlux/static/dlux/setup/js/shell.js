/* Setup wizard: shell interactions.
 *
 * Step validation marking, the Enter-key policy, the home-URL fields and the
 * global-search options.
 *
 * The Enter policy is the load-bearing part. In a 14-step form, Enter must not
 * submit: it advances the wizard instead — except inside a textarea, where it
 * types a newline, and inside the language editor, where it adds the language
 * being typed. Each branch is a separate way for an operator to lose work.
 *
 * Depends on setup/js/dom.js and setup/js/state.js, in that order.
 */
(function (root) {
    'use strict';

    const {
        getNamedFieldInputs,
        getNamedFieldValue,
        getSetupStepControls,
        setDependentFieldEnabled,
        t,
        updateSetupStepValidationState
    } = root.DluxSetupDom;

    // The step-validation binding records and caches wizard state, which lives
    // in setup/js/state.js — that must load before this file.
    const { persistSetupFormState, rememberSetupWizardStep } = root.DluxSetup;

    function firstInvalidControlInStep(step) {
        return getSetupStepControls(step).find((field) => {
            if (typeof field.checkValidity !== 'function') return false;
            return !field.checkValidity();
        }) || null;
    }

    function getSetupAllowedThemeCount(form) {
        const checkboxes = Array.from(form.querySelectorAll('[data-setup-theme-allowed]'));
        if (checkboxes.length) {
            return checkboxes.filter((checkbox) => checkbox.checked).length;
        }
        const preservedCount = Number(form.dataset.dluxAllowedThemeCount);
        return Number.isFinite(preservedCount) && preservedCount >= 0 ? preservedCount : 0;
    }

    function initGlobalSearchOptions(root) {
        // Reveal the "include data in search" toggle only while global search is
        // enabled (mode !== 'disabled'). The mode is a toggle choice-selector, so
        // its value is the checked radio named titlebar_global_search_mode.
        root.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            if (form.dataset.globalSearchBound === 'true') return;
            const dataRow = form.querySelector('[data-global-search-data-field]');
            if (!dataRow) return;
            form.dataset.globalSearchBound = 'true';

            function sync() {
                const checked = form.querySelector('input[name="titlebar_global_search_mode"]:checked');
                const mode = checked ? checked.value : 'icon';
                setDependentFieldEnabled(
                    dataRow,
                    mode !== 'disabled',
                    t('global_search_disabled_reason', 'Enable global search to include record data in results.'),
                );
            }

            form.addEventListener('change', (event) => {
                if (event.target && event.target.name === 'titlebar_global_search_mode') sync();
            });
            sync();
        });
    }

    function initSetupHomeFields(root) {
        root.querySelectorAll('form').forEach((form) => {
            if (form.dataset.setupHomeFieldsBound === 'true') {
                return;
            }

            const fieldPairs = [
                { discoveredName: 'home_url_discovered', inputName: 'home_url' },
                { discoveredName: 'public_root_url_discovered', inputName: 'public_root_url' },
            ];
            if (!fieldPairs.some(({ discoveredName, inputName }) => (
                getNamedFieldInputs(form, discoveredName).length && form.querySelector(`[name="${inputName}"]`)
            ))) {
                return;
            }

            form.dataset.setupHomeFieldsBound = 'true';

            fieldPairs.forEach(({ discoveredName, inputName }) => {
                const routeFields = getNamedFieldInputs(form, discoveredName);
                const urlInput = form.querySelector(`[name="${inputName}"]`);
                if (!routeFields.length || !urlInput) {
                    return;
                }

                const routeSelect = routeFields.find((field) => field.tagName === 'SELECT');
                const routeRadios = routeFields.filter((field) => field.type === 'radio');

                function selectableValues() {
                    if (routeSelect) {
                        return new Set(
                            Array.from(routeSelect.options || [])
                                .map((option) => option.value)
                                .filter(Boolean)
                        );
                    }
                    return new Set(routeRadios.map((field) => field.value).filter(Boolean));
                }

                function syncSelectFromInput() {
                    const currentValue = (urlInput.value || '').trim();
                    const values = selectableValues();
                    if (routeSelect) {
                        routeSelect.value = values.has(currentValue) ? currentValue : '';
                        return;
                    }
                    routeRadios.forEach((field) => {
                        if (!currentValue && !field.value) {
                            field.checked = true;
                            return;
                        }
                        field.checked = values.has(currentValue) && field.value === currentValue;
                    });
                }

                if (routeSelect) {
                    routeSelect.addEventListener('change', () => {
                        if (!routeSelect.value) {
                            return;
                        }
                        urlInput.value = routeSelect.value;
                        urlInput.dispatchEvent(new Event('input', { bubbles: true }));
                        urlInput.dispatchEvent(new Event('change', { bubbles: true }));
                    });
                }

                routeRadios.forEach((field) => {
                    field.addEventListener('change', () => {
                        if (!field.checked || !field.value) {
                            return;
                        }
                        urlInput.value = field.value;
                        urlInput.dispatchEvent(new Event('input', { bubbles: true }));
                        urlInput.dispatchEvent(new Event('change', { bubbles: true }));
                    });
                });

                urlInput.addEventListener('input', syncSelectFromInput);
                urlInput.addEventListener('change', syncSelectFromInput);
                syncSelectFromInput();
            });
        });
    }

    function initSystemSetupEnterBehavior(root) {
        root.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            if (form.dataset.enterBehaviorBound === 'true') return;
            form.dataset.enterBehaviorBound = 'true';

            form.addEventListener('keydown', (event) => {
                if (event.key !== 'Enter' || event.defaultPrevented || event.isComposing) {
                    return;
                }
                const target = event.target;
                const tagName = target && target.tagName ? target.tagName.toLowerCase() : '';
                if (tagName === 'textarea') {
                    return;
                }

                const languageEditor = target && target.closest && target.closest('[data-language-catalog-editor]');
                if (languageEditor && target.matches('input, select')) {
                    const addButton = languageEditor.querySelector('[data-language-add]');
                    if (addButton) {
                        event.preventDefault();
                        addButton.click();
                    }
                    return;
                }

                const steps = Array.from(form.querySelectorAll('.wizard-step'));
                if (steps.length < 2) {
                    return;
                }
                const visibleStepIndex = steps.findIndex((step) => isElementVisible(step));
                const nextButton = form.querySelector('.dlux-btn-next');
                if (visibleStepIndex >= 0 && visibleStepIndex < steps.length - 1 && nextButton && isElementVisible(nextButton)) {
                    event.preventDefault();
                    nextButton.click();
                }
            });
        });
    }

    function initSystemSetupStepValidation(root) {
        root.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            if (form.dataset.stepValidationBound === 'true') return;
            form.dataset.stepValidationBound = 'true';

            let pendingFrame = null;
            const syncSoon = () => {
                if (pendingFrame) return;
                pendingFrame = window.requestAnimationFrame(() => {
                    pendingFrame = null;
                    updateSetupStepValidationState(form);
                });
            };

            form.addEventListener('input', (event) => {
                const step = event.target && event.target.closest ? event.target.closest('.wizard-step') : null;
                if (step) step.dataset.dluxStepUserEdited = 'true';
                syncSoon();
            });
            form.addEventListener('change', (event) => {
                const step = event.target && event.target.closest ? event.target.closest('.wizard-step') : null;
                if (step) step.dataset.dluxStepUserEdited = 'true';
                syncSoon();
            });
            form.addEventListener('invalid', syncSoon, true);
            form.addEventListener('dlux:wizard-step-change', (event) => {
                rememberSetupWizardStep(form, event.detail && event.detail.currentStep);
                syncSoon();
            });
            form.querySelectorAll('.dlux-btn-submit').forEach((button) => {
                button.addEventListener('click', (event) => {
                    persistSetupFormState(form);
                    const firstInvalidStep = updateSetupStepValidationState(form);
                    if (firstInvalidStep < 0) return;
                    const firstInvalidControl = firstInvalidControlInStep(form.querySelectorAll('.wizard-step')[firstInvalidStep]);
                    if (!firstInvalidControl) return;
                    event.preventDefault();
                    const navItem = form.querySelector(`[data-dlux-wizard-step-target="${firstInvalidStep}"]`);
                    if (navItem) navItem.click();
                    window.setTimeout(() => {
                        if (typeof firstInvalidControl.reportValidity === 'function') {
                            firstInvalidControl.reportValidity();
                        }
                        if (typeof firstInvalidControl.focus === 'function') {
                            firstInvalidControl.focus({ preventScroll: false });
                        }
                    }, 0);
                });
            });
            form.addEventListener('submit', (event) => {
                persistSetupFormState(form);
                const firstInvalidStep = updateSetupStepValidationState(form);
                if (firstInvalidStep < 0) return;
                const firstInvalidControl = firstInvalidControlInStep(form.querySelectorAll('.wizard-step')[firstInvalidStep]);
                if (!firstInvalidControl) return;
                event.preventDefault();
                const navItem = form.querySelector(`[data-dlux-wizard-step-target="${firstInvalidStep}"]`);
                if (navItem) navItem.click();
                window.setTimeout(() => {
                    if (typeof firstInvalidControl.reportValidity === 'function') {
                        firstInvalidControl.reportValidity();
                    }
                    if (typeof firstInvalidControl.focus === 'function') {
                        firstInvalidControl.focus({ preventScroll: false });
                    }
                }, 0);
            });

            updateSetupStepValidationState(form);
        });
    }

    function isElementVisible(element) {
        if (!element) return false;
        return window.getComputedStyle(element).display !== 'none' && window.getComputedStyle(element).visibility !== 'hidden';
    }

    function setJsonField(form, name, value) {
        const field = form.querySelector(`[name="${name}"]`);
        if (!field) return;
        field.value = JSON.stringify(value || {});
        field.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function setNamedFieldReadonly(form, name, isReadonly) {
        const inputs = getNamedFieldInputs(form, name);
        if (!inputs.length) {
            return;
        }

        const selectorRoot = inputs[0].closest('[data-dlux-selector]');
        if (selectorRoot) {
            selectorRoot.classList.toggle('is-readonly', Boolean(isReadonly));
        }

        inputs.forEach((input) => {
            if (isReadonly) {
                input.setAttribute('tabindex', '-1');
                input.setAttribute('aria-disabled', 'true');
            } else {
                input.removeAttribute('tabindex');
                input.removeAttribute('aria-disabled');
            }
        });
    }

    // Both layouts order their titlebar actions now; the Dropdown layout simply
    // offers fewer of them, because its user shortcuts stay in the hub card.
    const TITLEBAR_ACTIONS_ONLY_KEYS = [
        'profile', 'help', 'users', 'activity', 'reports', 'settings', 'auth',
    ];

    function syncTitlebarActionsBuilderVisibility(form) {
        const style = getNamedFieldValue(form, 'titlebar_user_hub_style') || 'dropdown';
        const titlebarActions = style === 'titlebar_actions';
        form.querySelectorAll('[data-titlebar-actions-order-builder]').forEach((builder) => {
            builder.classList.remove('d-none');
            builder.setAttribute('aria-hidden', 'false');
            builder.querySelectorAll('[data-titlebar-action-order-item]').forEach((item) => {
                const key = item.getAttribute('data-action-key');
                const offered = titlebarActions || TITLEBAR_ACTIONS_ONLY_KEYS.indexOf(key) === -1;
                // Hidden, never removed: the stored order keeps every key so
                // switching layouts back restores the arrangement untouched.
                item.classList.toggle('d-none', !offered);
            });
        });
    }

    root.DluxSetup = Object.assign(root.DluxSetup || {}, {
        firstInvalidControlInStep,
        getSetupAllowedThemeCount,
        initGlobalSearchOptions,
        initSetupHomeFields,
        initSystemSetupEnterBehavior,
        initSystemSetupStepValidation,
        isElementVisible,
        setJsonField,
        setNamedFieldReadonly,
        syncTitlebarActionsBuilderVisibility
    });
})(typeof window !== 'undefined' ? window : globalThis);
