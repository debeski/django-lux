document.addEventListener('DOMContentLoaded', function () {
    const form = document.querySelector('.left form');
    const stateEl = document.getElementById('dlux-twofa-login-state');
    const loginState = stateEl ? JSON.parse(stateEl.textContent || '{}') : null;
    const emailBtn = document.getElementById('sendEmailOtpBtn');
    const backupBtn = document.getElementById('useBackupCodeBtn');
    const totpBtn = document.getElementById('useTotpBtn');
    const primaryBtn = document.getElementById('usePrimaryMethodBtn');
    const textEl = document.getElementById('otp-instruction-text');
    const statusEl = document.getElementById('emailOtpStatusText');
    const inputEl = document.getElementById('otp_code');
    const submitBtn = document.getElementById('submit');
    const errorEl = document.getElementById('otp-inline-error');
    const methodEl = document.getElementById('otp_method');

    if (!form || !inputEl) {
        return;
    }

    const emailInitialLabel = emailBtn && emailBtn.querySelector('.btn-label')
        ? emailBtn.querySelector('.btn-label').innerHTML
        : '';
    let currentMethod = (methodEl && methodEl.value) || (loginState && loginState.current_method) || 'email';
    let cooldownTimer = null;
    let verifyInFlight = false;

    function setButtonLoading(button, loading) {
        if (!button) {
            return;
        }
        button.disabled = loading;
        const spinner = button.querySelector('.spinner-border');
        if (spinner) {
            spinner.classList.toggle('d-none', !loading);
        }
    }

    function showError(message) {
        if (!errorEl) {
            return;
        }
        if (!message) {
            errorEl.classList.add('d-none');
            errorEl.textContent = '';
            return;
        }
        errorEl.classList.remove('d-none');
        errorEl.innerHTML = '<i class="bi bi-exclamation-triangle-fill me-2"></i>' + message;
    }

    function updateModeActions() {
        if (!primaryBtn || !loginState) {
            return;
        }
        const defaultMethod = loginState.default_method || 'email';
        const showPrimary = currentMethod !== defaultMethod;
        primaryBtn.classList.toggle('d-none', !showPrimary);
        primaryBtn.dataset.method = defaultMethod;
        const labelEl = primaryBtn.querySelector('.btn-label');
        if (!labelEl) {
            return;
        }
        if (defaultMethod === 'email') {
            labelEl.textContent = primaryBtn.dataset.labelEmail || '';
        } else if (defaultMethod === 'totp') {
            labelEl.textContent = primaryBtn.dataset.labelTotp || '';
        } else {
            labelEl.textContent = primaryBtn.dataset.labelDefault || '';
        }
    }

    function requiredCodeLength() {
        return currentMethod === 'backup_code' ? 8 : 6;
    }

    function setInputState(disabled) {
        inputEl.readOnly = disabled;
        if (submitBtn) {
            submitBtn.disabled = disabled;
        }
        if (!disabled) {
            inputEl.focus();
        }
    }

    function setMethod(method) {
        currentMethod = method;
        if (methodEl) {
            methodEl.value = method;
        }
        const backupMode = method === 'backup_code';
        inputEl.maxLength = requiredCodeLength();
        inputEl.placeholder = backupMode ? 'XXXXXXXX' : 'XXXXXX';
        inputEl.value = '';
        showError('');

        if (textEl) {
            if (backupMode && backupBtn) {
                textEl.textContent = backupBtn.dataset.instructionText || '';
            } else if (method === 'totp' && totpBtn) {
                textEl.textContent = totpBtn.dataset.instructionText || '';
            } else if (method === 'email' && emailBtn) {
                const sentText = emailBtn.dataset.sentText || '';
                const requestText = emailBtn.dataset.requestText || '';
                textEl.textContent = loginState && loginState.emailSent ? sentText : requestText;
            }
        }
        updateModeActions();
        inputEl.focus();
    }

    function renderCooldown(seconds) {
        if (!emailBtn) {
            return;
        }
        const labelEl = emailBtn.querySelector('.btn-label');
        const canSend = seconds <= 0;
        if (!verifyInFlight) {
            emailBtn.disabled = !canSend;
        }
        if (labelEl) {
            if (canSend) {
                labelEl.innerHTML = loginState && loginState.emailSent
                    ? '<i class="bi bi-envelope me-1"></i>' + (emailBtn.dataset.resendLabel || '')
                    : emailInitialLabel;
            } else {
                labelEl.innerHTML = '<i class="bi bi-envelope me-1"></i>' + (emailBtn.dataset.resendLabel || '') + ' (' + seconds + 's)';
            }
        }
        if (statusEl) {
            statusEl.textContent = canSend
                ? ''
                : (emailBtn.dataset.cooldownTemplate || '').replace('{seconds}', String(seconds));
        }
    }

    function startCooldown(seconds) {
        if (!emailBtn) {
            return;
        }
        window.clearInterval(cooldownTimer);
        let remaining = Math.max(0, parseInt(seconds || 0, 10) || 0);
        renderCooldown(remaining);
        if (remaining <= 0) {
            return;
        }
        cooldownTimer = window.setInterval(function () {
            remaining -= 1;
            renderCooldown(remaining);
            if (remaining <= 0) {
                window.clearInterval(cooldownTimer);
            }
        }, 1000);
    }

    function submitCode() {
        if (!loginState || verifyInFlight || inputEl.value.length !== requiredCodeLength()) {
            return;
        }
        verifyInFlight = true;
        setInputState(true);
        if (methodEl) {
            methodEl.value = currentMethod;
        }
        if (typeof form.requestSubmit === 'function') {
            form.requestSubmit(submitBtn || undefined);
            return;
        }
        form.submit();
    }

    if (loginState) {
        loginState.emailSent = Boolean(loginState.email_sent || loginState.emailSent);
        setMethod(currentMethod);
        startCooldown(loginState.email_resend_cooldown_seconds || 0);
    }

    inputEl.addEventListener('input', function () {
        inputEl.value = (inputEl.value || '').replace(/\D+/g, '').slice(0, requiredCodeLength());
        showError('');
        if (loginState && inputEl.value.length === requiredCodeLength()) {
            submitCode();
        }
    });

    if (emailBtn && loginState) {
        emailBtn.addEventListener('click', function () {
            if (emailBtn.disabled) {
                return;
            }
            setButtonLoading(emailBtn, true);
            fetch(emailBtn.dataset.url, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': emailBtn.dataset.csrf || '',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                },
                body: new URLSearchParams({ method: 'email' }),
            })
                .then(function (response) {
                    return response.json().then(function (data) {
                        return { ok: response.ok, data: data };
                    });
                })
                .then(function (payload) {
                    if (!payload.ok || payload.data.status !== 'success') {
                        if (payload.data.cooldown_seconds) {
                            startCooldown(payload.data.cooldown_seconds);
                        }
                        throw new Error(payload.data.message || emailBtn.dataset.errorText || '');
                    }
                    loginState.emailSent = true;
                    setMethod('email');
                    startCooldown(payload.data.cooldown_seconds || 0);
                })
                .catch(function (error) {
                    showError(error.message || emailBtn.dataset.errorText || '');
                })
                .finally(function () {
                    setButtonLoading(emailBtn, false);
                });
        });
    }

    if (backupBtn) {
        backupBtn.addEventListener('click', function () {
            setMethod(backupBtn.dataset.method || 'backup_code');
        });
    }

    if (totpBtn) {
        totpBtn.addEventListener('click', function () {
            setMethod(totpBtn.dataset.method || 'totp');
        });
    }

    if (primaryBtn) {
        primaryBtn.addEventListener('click', function () {
            setMethod(primaryBtn.dataset.method || (loginState && loginState.default_method) || 'email');
        });
    }
});
