/* Setup wizard: security and access options.
 *
 * Public page, public registration, client-IP resolution, auth hardening and
 * the login page layout. Small in lines, large in consequence — this is the UI
 * whose enabled/disabled state DSRP-1 requires to match what the backend will
 * accept.
 *
 * Depends on setup/js/dom.js, which must load first.
 */
(function (root) {
    'use strict';

    const {
        t,
        namedFieldSelector,
        getNamedFieldInputs,
        getNamedFieldValue,
        setNamedFieldDisabled,
        applyDependentTooltip,
        dependentReason,
        setDependentFieldEnabled
    } = root.DluxSetupDom;

    function syncPublicPageVisibility(form) {
        if (!form) {
            return;
        }

        const publicPageToggle = getNamedFieldInputs(form, 'public_root')[0] || null;
        const splitToggle = getNamedFieldInputs(form, 'public_root_split_enabled')[0] || null;
        const publicPageDependents = Array.from(form.querySelectorAll('[data-public-page-dependent]'));
        const splitDependents = Array.from(form.querySelectorAll('[data-public-page-split-dependent]'));
        if (!publicPageToggle || !splitToggle) {
            return;
        }

        const publicPageEnabled = Boolean(publicPageToggle.checked);
        if (!publicPageEnabled && splitToggle.checked) {
            splitToggle.checked = false;
        }
        const splitEnabled = publicPageEnabled && Boolean(splitToggle.checked);

        const pageReason = dependentReason(publicPageToggle);
        publicPageDependents.forEach((field) => setDependentFieldEnabled(field, publicPageEnabled, pageReason));
        const splitReason = dependentReason(splitToggle);
        splitDependents.forEach((field) => setDependentFieldEnabled(field, splitEnabled, splitReason));
        setNamedFieldDisabled(form, 'public_root_split_enabled', !publicPageEnabled);
        setNamedFieldDisabled(form, 'public_root_url_discovered', !splitEnabled);
        setNamedFieldDisabled(form, 'public_root_url', !splitEnabled);
    }

    function initPublicRegistrationOptions(root) {
        root.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            if (form.dataset.publicRegistrationBound === 'true') {
                return;
            }

            const publicRegistrationToggle = form.querySelector('#id_public_registration_enabled');
            const dependentFields = Array.from(form.querySelectorAll('[data-public-registration-dependent]'));
            if (!publicRegistrationToggle || !dependentFields.length) {
                return;
            }

            form.dataset.publicRegistrationBound = 'true';

            function syncPublicRegistrationVisibility() {
                const enabled = Boolean(publicRegistrationToggle.checked);
                const registrationReason = dependentReason(publicRegistrationToggle);
                dependentFields.forEach((field) => setDependentFieldEnabled(field, enabled, registrationReason));
                setNamedFieldDisabled(form, 'registration_activation_mode', !enabled);
                setNamedFieldDisabled(form, 'registration_throttle_enabled', !enabled);
            }

            publicRegistrationToggle.addEventListener('change', syncPublicRegistrationVisibility);
            syncPublicRegistrationVisibility();
        });
    }

    function initPublicPageOptions(root) {
        const forms = root.matches && root.matches('form.dlux-system-setup-form')
            ? [root]
            : Array.from(root.querySelectorAll('form.dlux-system-setup-form'));

        forms.forEach((form) => {
            if (form.dataset.publicPageBound === 'true') {
                syncPublicPageVisibility(form);
                return;
            }

            const publicPageToggle = getNamedFieldInputs(form, 'public_root')[0] || null;
            const splitToggle = getNamedFieldInputs(form, 'public_root_split_enabled')[0] || null;
            if (!publicPageToggle || !splitToggle) {
                return;
            }

            form.dataset.publicPageBound = 'true';

            form.addEventListener('change', (event) => {
                const target = event.target;
                if (!target || (target.name !== 'public_root' && target.name !== 'public_root_split_enabled')) {
                    return;
                }
                syncPublicPageVisibility(form);
            });
            syncPublicPageVisibility(form);
        });
    }

    function initClientIpOptions(root) {
        root.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            if (form.dataset.clientIpBound === 'true') {
                return;
            }

            const modeInput = form.querySelector('[data-client-ip-mode-input]');
            const hopsField = form.querySelector('[data-client-ip-hops]');
            const customHeaderField = form.querySelector('[data-client-ip-custom-header]');
            if (!modeInput || !hopsField || !customHeaderField) {
                return;
            }

            form.dataset.clientIpBound = 'true';

            function syncClientIpOptions() {
                const mode = String(modeInput.value || '');
                const showHops = mode === 'x_forwarded_for';
                const showCustomHeader = mode === 'custom';

                hopsField.classList.toggle('d-none', !showHops);
                hopsField.setAttribute('aria-hidden', showHops ? 'false' : 'true');
                customHeaderField.classList.toggle('d-none', !showCustomHeader);
                customHeaderField.setAttribute('aria-hidden', showCustomHeader ? 'false' : 'true');

                setNamedFieldDisabled(form, 'client_ip_trusted_proxy_hops', !showHops);
                setNamedFieldDisabled(form, 'client_ip_custom_header', !showCustomHeader);
            }

            modeInput.addEventListener('change', syncClientIpOptions);
            syncClientIpOptions();
        });
    }

    function initAuthSecurityOptions(root) {
        // Gate each tuning control through its own master switch.
        root.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            if (form.dataset.authSecurityBound === 'true') {
                return;
            }

            const lockoutRow = form.querySelector('[data-auth-lockout-fields]');
            const strongField = form.querySelector('[data-auth-strong-fields]');
            const inactivityField = form.querySelector('[data-auth-inactivity-fields]');
            if (!lockoutRow && !strongField && !inactivityField) {
                return;
            }

            form.dataset.authSecurityBound = 'true';

            function syncAuthSecurityOptions() {
                const lockoutInput = form.querySelector('input[name="login_lockout_enabled"]');
                const strongInput = form.querySelector('input[name="enforce_strong_passwords"]');
                const inactivityInput = form.querySelector('input[name="inactivity_timeout_enabled"]');
                if (lockoutRow && lockoutInput) {
                    setDependentFieldEnabled(lockoutRow, !!lockoutInput.checked, dependentReason(lockoutInput));
                }
                if (strongField && strongInput) {
                    setDependentFieldEnabled(strongField, !!strongInput.checked, dependentReason(strongInput));
                }
                if (inactivityField && inactivityInput) {
                    setDependentFieldEnabled(inactivityField, !!inactivityInput.checked, dependentReason(inactivityInput));
                }
            }

            form.addEventListener('change', (event) => {
                const name = event.target && event.target.name;
                if (name === 'login_lockout_enabled' || name === 'enforce_strong_passwords' || name === 'inactivity_timeout_enabled') {
                    syncAuthSecurityOptions();
                }
            });
            syncAuthSecurityOptions();
        });
    }

    function initLoginPageOptions(root) {
        root.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            if (form.dataset.loginPageBound === 'true') return;

            const hasStyle = getNamedFieldInputs(form, 'login_style').length > 0;
            const hasTreatment = getNamedFieldInputs(form, 'login_logo_treatment').length > 0;
            if (!hasStyle && !hasTreatment) return;

            form.dataset.loginPageBound = 'true';

            function syncLoginPageOptions() {
                const style = getNamedFieldValue(form, 'login_style') || 'split';
                const isFullpage = style === 'fullpage';
                const treatment = getNamedFieldValue(form, 'login_logo_treatment') || 'none';
                const isPlate = treatment === 'plate';

                form.querySelectorAll('[data-login-hero-field]').forEach((node) => {
                    node.classList.toggle('d-none', !isFullpage);
                    node.setAttribute('aria-hidden', isFullpage ? 'false' : 'true');
                    // Enable/disable all textareas inside the hero field
                    node.querySelectorAll('textarea').forEach((ta) => {
                        ta.disabled = !isFullpage;
                    });
                });

                form.querySelectorAll('[data-login-plate-shape]').forEach((node) => {
                    node.classList.toggle('d-none', !isPlate);
                    node.setAttribute('aria-hidden', isPlate ? 'false' : 'true');
                    setNamedFieldDisabled(form, 'login_logo_treatment_shape', !isPlate);
                });
                form.querySelectorAll('.dlux-login-logo-treatment-primary').forEach((node) => {
                    node.classList.toggle('dlux-logo-treatment-primary--wide', !isPlate);
                });
            }

            // Delegate from the form so ALL radio inputs in the selector fire it
            form.addEventListener('change', function (e) {
                const name = e.target && e.target.name;
                if (name === 'login_style' || name === 'login_logo_treatment') {
                    syncLoginPageOptions();
                }
            });

            syncLoginPageOptions();
        });
    }

    root.DluxSetup = Object.assign(root.DluxSetup || {}, {
        syncPublicPageVisibility,
        initPublicRegistrationOptions,
        initPublicPageOptions,
        initClientIpOptions,
        initAuthSecurityOptions,
        initLoginPageOptions
    });
})(typeof window !== 'undefined' ? window : globalThis);
