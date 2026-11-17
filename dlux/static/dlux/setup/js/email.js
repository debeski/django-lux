/* Setup wizard: the email apply and send-test actions.
 *
 * `initEmailDeliveryOptions` joined them once the dependency analysis was
 * corrected: what disqualifies a move is reaching main.js's mutually-recursive
 * core, not merely calling a shell helper. Its closure stops short of the core,
 * so it and the helpers it needs moved together.
 *
 * Depends on setup/js/dom.js.
 */
(function (root) {
    'use strict';

    const {
        dependentReason,
        getNamedFieldInputs,
        getNamedFieldValue,
        restoreImportedEmailPasswordNotice,
        setCheckboxField,
        setDependentSectionEnabled,
        setNamedFieldDisabled,
        setNamedFieldValue,
        t
    } = root.DluxSetupDom;

    function unlockEmailDependentFields(form, button) {
        const names = String(button.getAttribute('data-email-dependent-fields') || '')
            .split(',')
            .map((name) => name.trim())
            .filter(Boolean);
        names.forEach((name) => {
            const wrapper = form.querySelector(`[data-dlux-settings-toggle-field="${name}"]`);
            if (!wrapper) return;
            wrapper.classList.remove('dlux-settings-toggle-field--locked', 'dlux-dependent-settings', 'is-disabled');
            wrapper.removeAttribute('data-dlux-tooltip');
            wrapper.removeAttribute('title');
            wrapper.setAttribute('aria-disabled', 'false');
            wrapper.querySelectorAll('input').forEach((input) => {
                input.disabled = false;
            });
        });
    }

    function initEmailApply(form) {
        const button = form.querySelector('[data-email-apply]');
        const result = form.querySelector('[data-email-apply-result]');
        if (!button || button.dataset.bound === 'true') {
            return;
        }
        button.dataset.bound = 'true';

        button.addEventListener('click', () => {
            const url = button.getAttribute('data-email-apply-url');
            const csrfInput = form.querySelector('[name="csrfmiddlewaretoken"]');
            if (!url || !csrfInput) {
                return;
            }

            function show(ok, message) {
                if (!result) return;
                result.textContent = message || '';
                result.classList.toggle('text-success', Boolean(ok && message));
                result.classList.toggle('text-danger', Boolean(!ok && message));
            }

            function setBusy(busy) {
                button.disabled = busy;
                const spinner = button.querySelector('[data-email-apply-spinner]');
                if (spinner) spinner.classList.toggle('d-none', !busy);
            }

            // Post the whole step. The endpoint binds the form in single-step mode
            // for Email, so other steps keep their stored values and only
            // email_config is written.
            const body = new URLSearchParams(new FormData(form));
            setBusy(true);
            show(true, '');

            fetch(url, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfInput.value,
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                credentials: 'same-origin',
                body: body.toString(),
            })
                .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
                .then(({ ok, data }) => {
                    show(Boolean(ok && data && data.ok), (data && data.message) || '');
                    const reasonNode = form.querySelector('[data-email-service-reason]');
                    if (reasonNode && data && data.service_reason) {
                        reasonNode.textContent = t(`email_status_${data.service_reason}`, data.service_reason.replace(/_/g, ' '));
                    }
                })
                .catch(() => {
                    show(false, t('email_apply_failed', 'Could not apply the email settings.'));
                })
                .finally(() => setBusy(false));
        });
    }

    function initEmailSendTest(form) {
        const button = form.querySelector('[data-email-send-test]');
        const result = form.querySelector('[data-email-send-test-result]');
        if (!button || button.dataset.bound === 'true') {
            return;
        }
        button.dataset.bound = 'true';

        button.addEventListener('click', () => {
            const recipientInput = form.querySelector('[data-email-test-recipient]');
            const recipient = String(recipientInput && recipientInput.value ? recipientInput.value : '').trim();
            const url = button.getAttribute('data-email-send-test-url');
            const csrfInput = form.querySelector('[name="csrfmiddlewaretoken"]');
            if (!url || !csrfInput) {
                return;
            }

            function showResult(ok, message) {
                if (!result) return;
                result.textContent = message || '';
                result.classList.toggle('text-success', Boolean(ok && message));
                result.classList.toggle('text-danger', Boolean(!ok && message));
            }

            function setButtonBusy(busy) {
                button.disabled = busy;
                button.classList.toggle('dlux-email-test-btn--busy', busy);
                const spinner = button.querySelector('[data-email-send-test-spinner]');
                if (spinner) {
                    spinner.classList.toggle('d-none', !busy);
                }
            }

            if (!recipient) {
                showResult(false, t('email_test_invalid_recipient', 'Enter a valid recipient email address.'));
                return;
            }

            const body = new URLSearchParams();
            body.append('recipient', recipient);
            // In-place spinner on the button: the old approach printed "Sending…"
            // into the result line, which then had to be overwritten by the verdict.
            setButtonBusy(true);
            showResult(true, '');

            fetch(url, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfInput.value,
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                credentials: 'same-origin',
                body: body.toString(),
            })
                .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
                .then(({ ok, data }) => {
                    const passed = Boolean(ok && data && data.ok);
                    showResult(passed, (data && data.message) || '');
                    if (passed) {
                        unlockEmailDependentFields(form, button);
                    }
                })
                .catch(() => {
                    showResult(false, t('email_test_failed', 'Sending failed. Check the SMTP host, credentials, and from address.'));
                })
                .finally(() => {
                    setButtonBusy(false);
                });
        });
    }

    function initEmailDeliveryOptions(root) {
        root.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            if (form.dataset.emailDeliveryBound === 'true') {
                return;
            }

            const section = form.querySelector('[data-email-config-section]');
            // Email owns its own wizard step now: the SMTP fields follow the step's
            // own enable toggle, not whichever feature happens to need mail.
            const emailEnabledToggle = form.querySelector('#id_email_config_enabled');
            if (!section || !emailEnabledToggle) {
                return;
            }

            form.dataset.emailDeliveryBound = 'true';

            // Mirrors EMAIL_CONFIG_PROVIDER_PRESETS in dlux/system/constants.py.
            const PROVIDER_PRESETS = {
                gmail: { host: 'smtp.gmail.com', port: 587, use_tls: true, use_ssl: false },
                outlook: { host: 'smtp.office365.com', port: 587, use_tls: true, use_ssl: false },
                ses: { host: 'email-smtp.us-east-1.amazonaws.com', port: 587, use_tls: true, use_ssl: false },
                mailgun: { host: 'smtp.mailgun.org', port: 587, use_tls: true, use_ssl: false },
            };
            // The provider-server fields. With environment storage the provider
            // comes from the deployment, so they are hidden and not posted; the
            // server keeps their stored values for a later switch back.
            const PROVIDER_FIELDS = [
                'email_config_provider_preset',
                'email_config_host',
                'email_config_port',
                'email_config_use_tls',
                'email_config_use_ssl',
                'email_config_username',
                'email_config_password',
            ];
            // The timeout stays live while email is off, as it always has: a
            // disabled field posts nothing and the save would reset it.
            const STEP_FIELDS = [
                'email_config_transport',
                'email_config_secret_storage',
                'email_config_default_from_email',
                'email_config_failure_recipients',
            ];
            // Delivery path, provider preset and secret storage are Dlux choice
            // selectors: a group of radios, not one <select>. Reading `.value` off
            // the first element returns the first option regardless of what is
            // checked, so go through the named-field accessors instead.
            const presetInputs = getNamedFieldInputs(form, 'email_config_provider_preset');
            const secretStorageInputs = getNamedFieldInputs(form, 'email_config_secret_storage');
            const transportInputs = getNamedFieldInputs(form, 'email_config_transport');
            const providerGroup = section.querySelector('[data-email-provider-fields]');
            const envPanels = Array.from(section.querySelectorAll('[data-email-env-panel]'));
            // The certificate switch belongs to the relay: Direct SMTP keeps
            // Django's own verification, so the switch is hidden and not posted.
            const tlsVerifyToggle = section.querySelector('[data-dlux-email-toggle-field="email_config_tls_verify"]');
            const tlsVerifyColumn = tlsVerifyToggle ? tlsVerifyToggle.parentElement : null;
            const testRecipient = section.querySelector('[data-email-test-recipient]');

            function syncEmailConfigVisibility() {
                const enabled = Boolean(emailEnabledToggle && emailEnabledToggle.checked);
                const secretStorage = getNamedFieldValue(form, 'email_config_secret_storage') || 'env';
                const transport = getNamedFieldValue(form, 'email_config_transport') || 'direct';
                const enteredHere = secretStorage === 'encrypted_db';
                setDependentSectionEnabled(form, section, enabled, [], dependentReason(emailEnabledToggle));
                STEP_FIELDS.forEach((name) => setNamedFieldDisabled(form, name, !enabled));
                PROVIDER_FIELDS.forEach((name) => setNamedFieldDisabled(form, name, !(enabled && enteredHere)));
                const relaySwitchLive = enabled && enteredHere && transport === 'relay';
                setNamedFieldDisabled(form, 'email_config_tls_verify', !relaySwitchLive);
                setNamedFieldDisabled(form, 'email_config_tls_verify_shown', !relaySwitchLive);
                if (tlsVerifyColumn) {
                    tlsVerifyColumn.classList.toggle('d-none', transport !== 'relay');
                }
                if (providerGroup) {
                    providerGroup.classList.toggle('d-none', !enteredHere);
                    providerGroup.setAttribute('aria-hidden', enteredHere ? 'false' : 'true');
                }
                envPanels.forEach((panel) => {
                    const shown = !enteredHere && panel.getAttribute('data-email-env-panel') === transport;
                    panel.classList.toggle('d-none', !shown);
                    panel.setAttribute('aria-hidden', shown ? 'false' : 'true');
                });
                if (testRecipient) {
                    testRecipient.disabled = !enabled;
                }
                // Plain buttons carry no field name, so the name-based disabling
                // above misses them — the apply/test actions stayed live and
                // clickable while the rest of the step was switched off.
                section.querySelectorAll('button, a.btn').forEach((control) => {
                    if (control.tagName === 'BUTTON') {
                        control.disabled = !enabled;
                    } else {
                        control.classList.toggle('disabled', !enabled);
                        control.setAttribute('aria-disabled', enabled ? 'false' : 'true');
                    }
                });
                restoreImportedEmailPasswordNotice(form);
            }

            function applyProviderPreset() {
                const preset = PROVIDER_PRESETS[getNamedFieldValue(form, 'email_config_provider_preset')];
                if (!preset) {
                    return;
                }
                if (preset.host) {
                    setNamedFieldValue(form, 'email_config_host', preset.host);
                }
                setNamedFieldValue(form, 'email_config_port', String(preset.port));
                setCheckboxField(form, 'email_config_use_tls', preset.use_tls);
                setCheckboxField(form, 'email_config_use_ssl', preset.use_ssl);
            }

            [emailEnabledToggle].concat(secretStorageInputs, transportInputs).forEach((field) => {
                if (field) {
                    field.addEventListener('change', syncEmailConfigVisibility);
                }
            });
            presetInputs.forEach((field) => {
                field.addEventListener('change', applyProviderPreset);
            });
            initEmailApply(form);
            initEmailSendTest(form);
            syncEmailConfigVisibility();
        });
    }

    root.DluxSetup = Object.assign(root.DluxSetup || {}, {
        unlockEmailDependentFields,
        initEmailApply,
        initEmailSendTest,
        initEmailDeliveryOptions
    });
})(typeof window !== 'undefined' ? window : globalThis);
