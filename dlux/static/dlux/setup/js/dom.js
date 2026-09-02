/* Shared DOM helpers for the setup wizard's feature modules.
 *
 * Grown on demand rather than lifted wholesale: this holds exactly what the
 * modules split out so far need, not all 59 helpers the dependency scan found.
 * Each cluster adds only what it uses, so every addition arrives with tests
 * that exercise it.
 *
 * `t` is the string lookup; the rest are the named-field accessors and the
 * dependent-field machinery implementing DSRP-1's rule that a disabled master
 * must lock its dependents.
 */
(function (root) {
    'use strict';

    function t(key, fallback) {
        if (window.DLUX_STRINGS && typeof window.DLUX_STRINGS[key] === 'string' && window.DLUX_STRINGS[key]) {
            return window.DLUX_STRINGS[key];
        }
        return fallback;
    }

    function namedFieldSelector(name) {
        return `[name="${String(name || '').replace(/"/g, '\\"')}"]`;
    }

    function getNamedFieldInputs(form, name) {
        return Array.from(form.querySelectorAll(namedFieldSelector(name)));
    }

    function getNamedFieldValue(form, name) {
        const inputs = getNamedFieldInputs(form, name);
        if (!inputs.length) {
            return '';
        }

        if (inputs[0].type === 'radio') {
            const checked = inputs.find((input) => input.checked);
            return checked ? checked.value : '';
        }

        return inputs[0].value;
    }

    function setNamedFieldDisabled(form, name, isDisabled) {
        const inputs = getNamedFieldInputs(form, name);
        if (!inputs.length) {
            return;
        }

        const selectorRoot = inputs[0].closest('[data-dlux-selector]');
        if (selectorRoot) {
            selectorRoot.classList.toggle('is-disabled', Boolean(isDisabled));
            selectorRoot.setAttribute('aria-disabled', isDisabled ? 'true' : 'false');
        }

        inputs.forEach((input) => {
            // A choice-selector option the server locked (an unreachable relay, a
            // theme picker host that no longer exists) stays disabled when the
            // group is switched back on.
            const locked = input.dataset && input.dataset.dluxSelectorLocked === 'true';
            input.disabled = locked || Boolean(isDisabled);
            if (input.disabled) {
                input.setAttribute('aria-disabled', 'true');
            } else {
                input.removeAttribute('aria-disabled');
            }
        });
    }

    function applyDependentTooltip(el, enabled, reason) {
        if (!el) {
            return;
        }
        if (enabled || !reason) {
            el.removeAttribute('data-dlux-tooltip');
        } else {
            el.setAttribute('data-dlux-tooltip', reason);
        }
    }

    function dependentReason(toggle) {
        const field = toggle && toggle.closest ? toggle.closest('[data-dlux-settings-toggle-field]') : null;
        const labelEl = field ? field.querySelector('.dlux-settings-toggle-field__label') : null;
        const name = labelEl ? String(labelEl.textContent || '').trim() : '';
        const template = t('settings_dependent_disabled', 'Turn on “{name}” to change these settings.');
        return name ? template.replace('{name}', name) : t('settings_dependent_disabled_generic', 'Turn on the setting above to change these.');
    }

    function setDependentFieldEnabled(field, enabled, reason) {
        if (!field) {
            return;
        }
        applyDependentTooltip(field, enabled, reason);
        field.classList.remove('d-none');
        field.classList.add('dlux-dependent-settings');
        field.classList.toggle('is-disabled', !enabled);
        field.setAttribute('aria-disabled', enabled ? 'false' : 'true');
        field.removeAttribute('aria-hidden');
        const selectorRoots = new Set();
        field.querySelectorAll('input, select, textarea, button').forEach((control) => {
            control.disabled = !enabled;
            if (enabled) {
                control.removeAttribute('aria-disabled');
            } else {
                control.setAttribute('aria-disabled', 'true');
            }
            const selectorRoot = control.closest('[data-dlux-selector]');
            if (selectorRoot && field.contains(selectorRoot)) {
                selectorRoots.add(selectorRoot);
            }
        });
        selectorRoots.forEach((selectorRoot) => {
            selectorRoot.classList.toggle('is-disabled', !enabled);
            selectorRoot.setAttribute('aria-disabled', enabled ? 'false' : 'true');
        });
    }

    function getSetupStepControls(step) {
        if (!step) return [];
        return Array.from(step.querySelectorAll('input, select, textarea')).filter((field) => {
            const type = String(field.type || '').toLowerCase();
            return (
                type !== 'hidden' &&
                type !== 'button' &&
                type !== 'submit' &&
                type !== 'reset' &&
                !field.disabled &&
                !isElementHiddenInsideStep(field, step)
            );
        });
    }

    function isElementHiddenInsideStep(element, step) {
        let node = element;
        while (node && node !== step) {
            if (
                node.hidden ||
                node.getAttribute('aria-hidden') === 'true' ||
                (node.classList && node.classList.contains('d-none'))
            ) {
                return true;
            }
            node = node.parentElement;
        }
        return false;
    }

    function restoreImportedEmailPasswordNotice(form) {
        if (!form) return;
        const importProcessed = String(getNamedFieldValue(form, 'settings_import_processed') || '').toLowerCase() === 'true';
        if (!importProcessed) return;
        setImportedEmailPasswordNotice(form, setupRequiresEmailPassword(form));
    }

    function setBuilderSectionEnabled(section, enabled, reason) {
        if (!section) {
            return;
        }
        applyDependentTooltip(section, enabled, reason);
        section.classList.remove('d-none');
        section.classList.add('dlux-dependent-settings');
        section.classList.toggle('is-disabled', !enabled);
        section.setAttribute('aria-disabled', enabled ? 'false' : 'true');
        section.removeAttribute('aria-hidden');
        section.querySelectorAll('input, select, textarea, button').forEach((control) => {
            control.disabled = !enabled;
        });
    }

    function setCheckboxField(form, name, value) {
        const field = form.querySelector(`[name="${name}"]`);
        if (!field || field.type !== 'checkbox') return;
        field.checked = Boolean(value);
        field.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function setDependentSectionEnabled(form, section, enabled, fieldNames, reason) {
        if (section) {
            applyDependentTooltip(section, enabled, reason);
            section.classList.toggle('is-disabled', !enabled);
            section.setAttribute('aria-disabled', enabled ? 'false' : 'true');
            // The section stays in the accessibility tree — its whole purpose is
            // to be readable while off — so aria-hidden must not linger from the
            // previous hide-based behaviour.
            section.removeAttribute('aria-hidden');
            section.classList.remove('d-none');
        }
        (fieldNames || []).forEach((name) => setNamedFieldDisabled(form, name, !enabled));
    }

    function setImportedEmailPasswordNotice(form, needed) {
        if (!form) return;
        const passwordField = form.querySelector('[name="email_config_password"]');
        form.dataset.importNeedsEmailPassword = needed ? 'true' : '';
        let notice = form.querySelector('[data-import-email-password-notice]');
        if (!needed) {
            if (notice) notice.classList.add('d-none');
            if (passwordField) passwordField.classList.remove('is-invalid');
            syncSetupCustomValidation(form);
            updateSetupStepValidationState(form);
            return;
        }
        if (!notice && passwordField) {
            notice = document.createElement('div');
            notice.setAttribute('data-import-email-password-notice', '');
            notice.setAttribute('data-autoclose', 'false');
            notice.className = 'alert alert-warning dlux-import-email-password-notice mt-2 mb-0';
            notice.textContent = t(
                'system_setup_import_needs_email_password',
                'The SMTP password is never included in an exported setup file for security. Re-enter it below to finish setup.'
            );
            const wrapper = passwordField.closest('.dlux-email-config-password-field')
                || passwordField.closest('div')
                || passwordField.parentElement;
            if (wrapper) wrapper.appendChild(notice);
        }
        if (notice) notice.classList.remove('d-none');
        if (passwordField) {
            passwordField.classList.add('is-invalid');
            if (passwordField.dataset.importPwBound !== 'true') {
                passwordField.dataset.importPwBound = 'true';
                passwordField.addEventListener('input', () => {
                    if (passwordField.value.trim().length === 0) return;
                    form.dataset.importNeedsEmailPassword = '';
                    passwordField.classList.remove('is-invalid');
                    const current = form.querySelector('[data-import-email-password-notice]');
                    if (current) current.classList.add('d-none');
                    setImportedSetupFinishVisible(form, true);
                    updateSetupStepValidationState(form);
                });
            }
        }
        updateSetupStepValidationState(form);
    }

    function setImportedSetupFinishVisible(form, visible) {
        const finish = form && form.querySelector('[data-settings-import-finish]');
        if (!finish) return;
        finish.classList.toggle('d-none', !visible);
    }

    function setNamedFieldValue(form, name, value) {
        const inputs = getNamedFieldInputs(form, name);
        if (!inputs.length) {
            return;
        }

        if (inputs[0].type === 'radio') {
            inputs.forEach((input) => {
                input.checked = String(input.value) === String(value);
            });
            // Choice-selector widgets track their highlighted option from a 'change'
            // event on the checked input; without this they keep the previously-selected
            // option visually marked (two options appearing selected at once).
            const checked = inputs.find((input) => input.checked) || inputs[0];
            checked.dispatchEvent(new Event('change', { bubbles: true }));
            return;
        }

        inputs[0].value = value;
        inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
        inputs[0].dispatchEvent(new Event('change', { bubbles: true }));
    }

    function setupRequiresEmailPassword(form) {
        // Mirrors the server rule: an SMTP password is only required when an email feature
        // is enabled, encrypted-DB secret storage is selected, and a username is set, with
        // no password present. A config that doesn't meet all of these is completable as-is
        // and must NOT block "Finish setup" just because an export redacted the secret.
        if (!form) return false;
        const emailFeaturesEnabled = Boolean(
            getNamedFieldInputs(form, 'public_registration_enabled')[0]?.checked ||
            getNamedFieldInputs(form, 'email_2fa')[0]?.checked
        );
        if (!emailFeaturesEnabled) return false;
        if (getNamedFieldValue(form, 'email_config_secret_storage') !== 'encrypted_db') return false;
        if (!String(getNamedFieldValue(form, 'email_config_username') || '').trim()) return false;
        const passwordField = form.querySelector('[name="email_config_password"]');
        const password = String(passwordField && passwordField.value ? passwordField.value : '').trim();
        return !password;
    }

    function stepHasRenderedServerError(step) {
        if (!step || step.dataset.dluxStepUserEdited === 'true') return false;
        return Array.from(step.querySelectorAll('.invalid-feedback, .errorlist, .alert-danger'))
            .some((error) => (
                String(error.textContent || '').trim() &&
                !isElementHiddenInsideStep(error, step)
            ));
    }

    function stepHasValidationError(step) {
        if (!step) return false;
        if (stepHasRenderedServerError(step)) return true;
        return getSetupStepControls(step).some((field) => {
            if (typeof field.checkValidity !== 'function') return false;
            return !field.checkValidity();
        });
    }

    function syncSetupCustomValidation(form) {
        if (!form) return;
        const passwordField = form.querySelector('[name="email_config_password"]');
        if (!passwordField || typeof passwordField.setCustomValidity !== 'function') return;

        if (passwordField.dataset.dluxSetupCustomInvalid === 'true') {
            passwordField.classList.remove('is-invalid');
            passwordField.dataset.dluxSetupCustomInvalid = '';
        }
        passwordField.setCustomValidity('');

        // Single live source of truth — recomputed here so the flag can never go stale as
        // email features / username / password are toggled after an import.
        const needsPassword = setupRequiresEmailPassword(form);
        form.dataset.importNeedsEmailPassword = needsPassword ? 'true' : '';

        if (needsPassword) {
            passwordField.dataset.dluxSetupCustomInvalid = 'true';
            passwordField.classList.add('is-invalid');
            passwordField.setCustomValidity(t(
                'system_setup_import_needs_email_password',
                'The SMTP password is never included in an exported setup file for security. Re-enter it below to finish setup.'
            ));
        }

        // Keep the import warning and the "Finish setup" CTA in sync with the live state.
        const notice = form.querySelector('[data-import-email-password-notice]');
        if (notice) {
            notice.classList.toggle('d-none', !needsPassword);
        }
        const importProcessed = String(getNamedFieldValue(form, 'settings_import_processed') || '').toLowerCase() === 'true';
        if (importProcessed) {
            setImportedSetupFinishVisible(form, !needsPassword);
        }
    }

    function updateSetupStepValidationState(form) {
        if (!form) return -1;
        syncSetupCustomValidation(form);
        const steps = Array.from(form.querySelectorAll('.wizard-step'));
        const navItems = Array.from(form.querySelectorAll('[data-dlux-wizard-step-target]'));
        let firstInvalidStep = -1;

        steps.forEach((step, index) => {
            const hasError = stepHasValidationError(step);
            if (hasError && firstInvalidStep === -1) {
                firstInvalidStep = index;
            }
            step.classList.toggle('dlux-setup-step-has-error', hasError);
            step.setAttribute('data-dlux-step-validation', hasError ? 'error' : 'ok');

            const navItem = navItems.find((item) => Number(item.dataset.dluxWizardStepTarget) === index);
            if (!navItem) return;
            navItem.classList.toggle('has-validation-error', hasError);
            navItem.setAttribute('aria-invalid', hasError ? 'true' : 'false');
            const bullet = navItem.querySelector('.dlux-setup-step-nav__bullet');
            if (!bullet) return;
            if (!bullet.dataset.dluxStepNumber) {
                bullet.dataset.dluxStepNumber = String(bullet.textContent || index + 1).trim();
            }
            bullet.textContent = hasError ? '!' : bullet.dataset.dluxStepNumber;
        });

        return firstInvalidStep;
    }

    root.DluxSetupDom = Object.assign(root.DluxSetupDom || {}, {
        t,
        namedFieldSelector,
        getNamedFieldInputs,
        getNamedFieldValue,
        setNamedFieldDisabled,
        applyDependentTooltip,
        dependentReason,
        setDependentFieldEnabled,
        getSetupStepControls,
        isElementHiddenInsideStep,
        restoreImportedEmailPasswordNotice,
        setBuilderSectionEnabled,
        setCheckboxField,
        setDependentSectionEnabled,
        setImportedEmailPasswordNotice,
        setImportedSetupFinishVisible,
        setNamedFieldValue,
        setupRequiresEmailPassword,
        stepHasRenderedServerError,
        stepHasValidationError,
        syncSetupCustomValidation,
        updateSetupStepValidationState
    });
})(typeof window !== 'undefined' ? window : globalThis);
