let needsReload = false;
let pendingEmailSetup = null;

function setButtonLoading(button, loading) {
    if (!button) return;
    button.disabled = loading;
    button.classList.toggle("is-loading", loading);
    const spinner = button.querySelector(".spinner-border");
    if (spinner) spinner.classList.toggle("d-none", !loading);
}

document.addEventListener('DOMContentLoaded', function() {
    const setupButtons = document.querySelectorAll('.setup-2fa-btn');
    const disableButtons = document.querySelectorAll('.disable-2fa-btn');
    const otpSetupForm = document.getElementById('otpSetupForm');

    // Use Event Delegation for robust button handling
    document.body.addEventListener('click', function(e) {
        const setupBtn = e.target.closest('.setup-2fa-btn');
        if (setupBtn) {
            initiate2FASetup(setupBtn);
        }

        const disableBtn = e.target.closest('.disable-2fa-btn');
        if (disableBtn) {
            disable2FA(disableBtn);
        }
    });

    document.body.addEventListener('submit', function(e) {
        const revokeForm = e.target.closest('.profile-session-revoke-form');
        if (revokeForm) {
            e.preventDefault();
            confirmSessionRevoke(revokeForm);
            return;
        }

        const trustForm = e.target.closest('.profile-session-trust-form');
        if (trustForm) {
            e.preventDefault();
            confirmSessionTrust(trustForm);
        }
    });

    if (otpSetupForm) {
        otpSetupForm.addEventListener('submit', submitOTPSetup);
    }

    const emailConfirmBtn = document.getElementById('email2faConfirmBtn');
    if (emailConfirmBtn) {
        emailConfirmBtn.addEventListener('click', submitEmail2FAAddress);
    }

    const generateBackupBtn = document.getElementById('generateBackupCodesBtn');
    if (generateBackupBtn) {
        generateBackupBtn.addEventListener('click', handleBackupCodes);
    }

    const downloadBackupBtn = document.getElementById('downloadBackupCodesBtn');
    if (downloadBackupBtn) {
        downloadBackupBtn.addEventListener('click', downloadBackupCodes);
    }

    const confirmCodesSavedBtn = document.getElementById('confirmCodesSavedBtn');
    if (confirmCodesSavedBtn) {
        confirmCodesSavedBtn.addEventListener('click', function() {
            window.location.reload();
        });
    }

    const modalEl = document.getElementById('otpSetupModal');
    if (modalEl) {
        modalEl.addEventListener('hidden.bs.modal', function() {
            if (needsReload) {
                window.location.reload();
            }
        });
        
        // Ensure focus on input when shown
        modalEl.addEventListener('shown.bs.modal', function () {
            const emailConfirm = document.getElementById('email2faConfirm');
            const input = emailConfirm && !emailConfirm.classList.contains('d-none')
                ? document.getElementById('email2faAddressInput')
                : document.getElementById('otpSetupInput');
            if (input) input.focus();
        });
    }
});

function initiate2FASetup(btn) {
    const method = btn.dataset.method;
    const url = btn.dataset.url;
    const form = document.getElementById('otpSetupForm');
    if (!form) return;
    const csrfToken = form?.dataset.csrf || document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
    setButtonLoading(btn, true);
    
    resetOTPSetupModal(form);
    
    // Logic split for TOTP vs Email/Phone
    if (method === 'totp') {
        fetch(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(parseJsonResponse)
        .then(data => {
            if (data.status === 'success') {
                // Show QR Code
                const qrContainer = document.getElementById('totp-qr-container');
                const instructionText = document.getElementById('otp-instruction');
                
                qrContainer.innerHTML = `<img src="data:image/png;base64,${data.qr_code}" class="img-fluid rounded border p-2 mb-3">`;
                qrContainer.classList.remove('d-none');
                instructionText.textContent = form.dataset.transScanInstruction || 'Scan this QR code with your authenticator app';
                
                // Set form method hidden input
                document.getElementById('otpMethodInput').value = 'totp';
                
                showModal();
            } else {
                alert(data.message || 'Error generating QR');
            }
        })
        .catch(err => {
            console.error("Error fetching TOTP setup:", err);
            alert(err.message || 'Error generating QR');
        })
        .finally(() => setButtonLoading(btn, false));
    } else if (method === 'email') {
        pendingEmailSetup = { btn, url, method, csrfToken };
        const confirmSection = document.getElementById('email2faConfirm');
        const emailInput = document.getElementById('email2faAddressInput');
        const setupForm = document.getElementById('otpSetupForm');
        const instructionText = document.getElementById('otp-instruction');
        const titleEl = document.querySelector('#otpSetupModal .modal-title');
        const qrContainer = document.getElementById('totp-qr-container');

        if (titleEl && form.dataset.transConfirmEmailTitle) {
            titleEl.textContent = form.dataset.transConfirmEmailTitle;
        }
        if (instructionText) {
            instructionText.textContent = form.dataset.transConfirmEmailInstruction || 'Confirm or update the email address before we send a setup code.';
        }
        if (emailInput) {
            emailInput.value = btn.dataset.email || '';
        }
        if (setupForm) setupForm.classList.add('d-none');
        if (qrContainer) qrContainer.classList.add('d-none');
        if (confirmSection) confirmSection.classList.remove('d-none');

        showModal();
        setButtonLoading(btn, false);
    } else {
        // Email/Phone
        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: `method=${encodeURIComponent(method)}`
        })
        .then(parseJsonResponse)
        .then(data => {
            if (data.status === 'success') {
                // Hide QR, Show plain text
                document.getElementById('totp-qr-container').classList.add('d-none');
                document.getElementById('otp-instruction').textContent = (form.dataset.transOtpSent || 'Enter the code sent to your') + ' ' + method;
                
                document.getElementById('otpMethodInput').value = method;
                
                showModal();
            } else {
                alert(data.message || 'Error sending code');
            }
        })
        .catch(err => {
            console.error("Error initiating 2FA:", err);
            alert(err.message || 'Error sending code');
        })
        .finally(() => setButtonLoading(btn, false));
    }
}

function resetOTPSetupModal(form) {
    const errorEl = document.getElementById('otpSetupError');
    if (errorEl) errorEl.classList.add('d-none');

    const inputEl = document.getElementById('otpSetupInput');
    if (inputEl) inputEl.value = '';

    const emailInput = document.getElementById('email2faAddressInput');
    if (emailInput) emailInput.value = '';

    const emailConfirm = document.getElementById('email2faConfirm');
    if (emailConfirm) emailConfirm.classList.add('d-none');

    const setupForm = document.getElementById('otpSetupForm');
    if (setupForm) setupForm.classList.remove('d-none');

    const instruction = document.getElementById('otp-instruction');
    if (instruction) instruction.classList.remove('d-none');

    const success = document.getElementById('otpSetupSuccess');
    if (success) success.classList.add('d-none');

    const qrContainer = document.getElementById('totp-qr-container');
    if (qrContainer) {
        qrContainer.innerHTML = '';
        qrContainer.classList.add('d-none');
    }

    const closeBtn = document.querySelector('#otpSetupModal .btn-close');
    if (closeBtn) closeBtn.classList.remove('d-none');

    const iconContainer = document.querySelector('#otpSetupModal .bi-shield-lock-fill');
    if (iconContainer && iconContainer.parentElement) {
        iconContainer.parentElement.classList.remove('d-none');
    }

    const titleEl = document.querySelector('#otpSetupModal .modal-title');
    if (titleEl && form.dataset.transVerifyTitle) {
        titleEl.textContent = form.dataset.transVerifyTitle;
    }

    pendingEmailSetup = null;
    needsReload = false;
}

function submitEmail2FAAddress() {
    const state = pendingEmailSetup;
    const form = document.getElementById('otpSetupForm');
    const errorEl = document.getElementById('otpSetupError');
    const emailInput = document.getElementById('email2faAddressInput');
    const confirmBtn = document.getElementById('email2faConfirmBtn');
    if (!state || !form || !emailInput) return;

    const email = emailInput.value.trim();
    if (!emailInput.checkValidity()) {
        if (errorEl) {
            errorEl.textContent = form.dataset.transInvalidEmail || 'Enter a valid email address.';
            errorEl.classList.remove('d-none');
        }
        emailInput.focus();
        return;
    }

    if (errorEl) errorEl.classList.add('d-none');
    setButtonLoading(confirmBtn, true);

    const body = new URLSearchParams();
    body.set('method', 'email');
    body.set('email', email);

    fetch(state.url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': state.csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: body.toString()
    })
    .then(parseJsonResponse)
    .then(data => {
        if (data.status === 'success') {
            const confirmSection = document.getElementById('email2faConfirm');
            const instructionText = document.getElementById('otp-instruction');
            const titleEl = document.querySelector('#otpSetupModal .modal-title');
            if (confirmSection) confirmSection.classList.add('d-none');
            if (form) form.classList.remove('d-none');
            if (titleEl && form.dataset.transVerifyTitle) {
                titleEl.textContent = form.dataset.transVerifyTitle;
            }
            if (instructionText) {
                instructionText.textContent = `${form.dataset.transOtpSent || 'Enter the code sent to'} ${email}`;
            }
            document.getElementById('otpMethodInput').value = 'email';
            const inputEl = document.getElementById('otpSetupInput');
            if (inputEl) inputEl.focus();
        } else if (errorEl) {
            errorEl.textContent = data.message || 'Error sending code';
            errorEl.classList.remove('d-none');
        }
    })
    .catch(err => {
        console.error("Error initiating email 2FA:", err);
        if (errorEl) {
            errorEl.textContent = err.message || 'Error sending code';
            errorEl.classList.remove('d-none');
        }
    })
    .finally(() => setButtonLoading(confirmBtn, false));
}

function parseJsonResponse(response) {
    return response.text().then(text => {
        let data = {};
        try {
            data = text ? JSON.parse(text) : {};
        } catch (err) {
            throw new Error('Server returned an unexpected response.');
        }
        if (!response.ok) {
            throw new Error(data.message || 'Request failed.');
        }
        return data;
    });
}

function showModal() {
    const modalEl = document.getElementById('otpSetupModal');
    if (!modalEl) return;
    
    // Check if instance exists or create new
    let modal = bootstrap.Modal.getInstance(modalEl);
    if (!modal) {
        modal = new bootstrap.Modal(modalEl);
    }
    modal.show();
}

function submitOTPSetup(e) {
    e.preventDefault();
    const form = e.target;
    const url = form.dataset.url;
    const csrfToken = form.dataset.csrf;
    
    const code = document.getElementById('otpSetupInput').value;
    const method = document.getElementById('otpMethodInput').value;
    const errorDiv = document.getElementById('otpSetupError');
    const submitButton = form.querySelector('button[type="submit"]');
    setButtonLoading(submitButton, true);
    
    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: `otp_code=${code}&method=${method}&intent=enable_${method}`
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            if (data.backup_codes && data.backup_codes.length > 0) {
                // HIDE Form and Instructions
                form.classList.add('d-none');
                document.getElementById('otp-instruction').classList.add('d-none');
                document.getElementById('totp-qr-container').classList.add('d-none');
                document.querySelector('#otpSetupModal .bi-shield-lock-fill').parentElement.classList.add('d-none'); // Hide icon container
                document.querySelector('#otpSetupModal .btn-close').classList.add('d-none'); // Hide close button
                document.querySelector('#otpSetupModal .modal-title').textContent = form.dataset.transRecoveryCodes || "Recovery Codes";

                // SHOW Success Section
                const successDiv = document.getElementById('otpSetupSuccess');
                const codesContainer = document.getElementById('otpSetupBackupCodesContainer');
                
                let html = '<div class="row text-center">';
                data.backup_codes.forEach(code => {
                    html += `<div class="col-6 mb-2"><strong>${code}</strong></div>`;
                });
                html += '</div>';
                codesContainer.innerHTML = html;
                
                successDiv.classList.remove('d-none');
                needsReload = true;
                
                // Attach download handler
                document.getElementById('downloadSetupBackupCodesBtn').onclick = function() {
                     downloadCodes(data.backup_codes);
                };

            } else {
                window.location.reload(); 
            }
        } else {
            errorDiv.textContent = data.message || 'Invalid Code';
            errorDiv.classList.remove('d-none');
        }
    })
    .catch(err => {
        console.error(err);
        errorDiv.textContent = 'Connection error';
        errorDiv.classList.remove('d-none');
    })
    .finally(() => setButtonLoading(submitButton, false));
}

function downloadCodes(codes) {
    let text = "Dlux Backup Codes\n=====================\n\n";
    codes.forEach((code, index) => {
        text += `${index + 1}. ${code}\n`;
    });
    text += "\nKeep these codes safe!";
    
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "dlux_backup_codes.txt";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Helper for Confirmation Modal
function showConfirmation(message, onConfirm) {
    const config = typeof message === 'object' && message !== null
        ? message
        : { message, onConfirm };
    const modalEl = document.getElementById('confirmationModal');
    const msgEl = document.getElementById('confirmationMessage');
    const btnEl = document.getElementById('confirmationConfirmBtn');
    const passwordWrap = document.getElementById('confirmationPasswordWrap');
    const passwordInput = document.getElementById('confirmationPasswordInput');
    const passwordError = document.getElementById('confirmationPasswordError');
    
    if (!modalEl || !msgEl || !btnEl) return;
    
    msgEl.textContent = config.message || '';
    const requirePassword = !!config.requirePassword;
    if (passwordWrap) {
        passwordWrap.classList.toggle('d-none', !requirePassword);
    }
    if (passwordInput) {
        passwordInput.value = '';
        passwordInput.required = requirePassword;
        passwordInput.classList.remove('is-invalid');
    }
    if (passwordError) {
        passwordError.textContent = '';
        passwordError.classList.add('d-none');
    }
    
    // Create new modal instance
    const modal = new bootstrap.Modal(modalEl);
    
    // Remove old listeners to prevent stacking
    const newBtn = btnEl.cloneNode(true);
    btnEl.parentNode.replaceChild(newBtn, btnEl);

    const clearPasswordError = function() {
        if (passwordInput) passwordInput.classList.remove('is-invalid');
        if (passwordError) {
            passwordError.textContent = '';
            passwordError.classList.add('d-none');
        }
    };
    const showPasswordError = function(message) {
        if (passwordInput) {
            passwordInput.classList.add('is-invalid');
            passwordInput.focus();
        }
        if (passwordError) {
            passwordError.textContent = message || '';
            passwordError.classList.toggle('d-none', !message);
        }
    };
    
    const confirmCurrentModal = function() {
        const currentPassword = passwordInput ? passwordInput.value.trim() : '';
        if (requirePassword && !currentPassword) {
            showPasswordError(passwordInput?.dataset.requiredMsg || 'Please enter your current password.');
            return;
        }
        clearPasswordError();
        if (typeof config.onConfirm !== 'function') {
            modal.hide();
            return;
        }

        const result = config.onConfirm(currentPassword, { showError: showPasswordError });
        if (!result || typeof result.then !== 'function') {
            if (result !== false) modal.hide();
            return;
        }

        setButtonLoading(newBtn, true);
        result
            .then(shouldClose => {
                if (shouldClose !== false) modal.hide();
            })
            .catch(err => showPasswordError(err.message))
            .finally(() => setButtonLoading(newBtn, false));
    };

    newBtn.addEventListener('click', confirmCurrentModal);
    if (requirePassword && passwordInput) {
        const submitOnEnter = function(event) {
            if (event.key !== 'Enter') return;
            event.preventDefault();
            confirmCurrentModal();
        };
        const removeEnterHandler = function() {
            passwordInput.removeEventListener('keydown', submitOnEnter);
            passwordInput.removeEventListener('input', clearPasswordError);
        };

        passwordInput.addEventListener('keydown', submitOnEnter);
        passwordInput.addEventListener('input', clearPasswordError);
        modalEl.addEventListener('hidden.bs.modal', removeEnterHandler, { once: true });
    }
    
    modal.show();
    if (requirePassword && passwordInput) {
        setTimeout(() => passwordInput.focus(), 150);
    }
}

function disable2FA(e) {
    const btn = e && e.target && e.target.closest ? e.target.closest('button') : e;
    const method = btn.dataset.method;
    const url = btn.dataset.url;
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || document.getElementById('otpSetupForm').dataset.csrf;
    const confirmMsg = btn.dataset.confirmMsg || 'Are you sure?';
    
    showConfirmation({
        message: confirmMsg,
        requirePassword: true,
        onConfirm: function(currentPassword) {
            setButtonLoading(btn, true);
            return fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: `method=${encodeURIComponent(method)}&current_password=${encodeURIComponent(currentPassword)}`
            })
            .then(parseJsonResponse)
            .then(data => {
                if (data.status !== 'success') {
                    throw new Error(data.message || 'Error disabling 2FA');
                }
                window.location.reload();
                return true;
            })
            .finally(() => setButtonLoading(btn, false));
        }
    });
}

function handleBackupCodes(e) {
    const btn = e.target.closest('button');
    const url = btn.dataset.url;
    
    const performGeneration = (currentPassword) => {
        setButtonLoading(btn, true);
        let csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        if (!csrfToken) {
             csrfToken = document.getElementById('otpSetupForm')?.dataset.csrf;
        }
    
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: `current_password=${encodeURIComponent(currentPassword)}`
        })
        .then(parseJsonResponse)
        .then(data => {
            if (data.status !== 'success') {
                throw new Error(data.message || 'Error');
            }
            const container = document.getElementById('backupCodesContainer');
            const modalEl = document.getElementById('backupCodesModal');
            let modal = bootstrap.Modal.getInstance(modalEl);
            if (!modal) {
                modal = new bootstrap.Modal(modalEl);
            }

            const codes = data.codes;
            let html = '<div class="row text-center">';
            codes.forEach(code => {
                html += `<div class="col-6 mb-2"><strong>${code}</strong></div>`;
            });
            html += '</div>';
            container.innerHTML = html;
            document.getElementById('downloadBackupCodesBtn').classList.remove('d-none');
            modal.show();
            return true;
        })
        .finally(() => setButtonLoading(btn, false));
    };

    // Confirmation before generating new codes
    const confirmMsg = btn.dataset.confirmMsg || 'Are you sure?';
    showConfirmation({
        message: confirmMsg,
        requirePassword: true,
        onConfirm: performGeneration,
    });
}

function confirmSessionRevoke(form) {
    const confirmMsg = form.dataset.confirmMsg || 'Are you sure?';
    const csrfToken = form.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
    const submitButton = form.querySelector('button[type="submit"]');

    showConfirmation({
        message: confirmMsg,
        requirePassword: true,
        onConfirm: function(currentPassword) {
            const body = new URLSearchParams(new FormData(form));
            body.set('current_password', currentPassword);
            setButtonLoading(submitButton, true);

            return fetch(form.action, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: body.toString()
            })
            .then(parseJsonResponse)
            .then(data => {
                if (data.status !== 'success') {
                    throw new Error(data.message || 'Request failed.');
                }
                window.location.assign(data.redirect_url || window.location.href);
                return true;
            })
            .finally(() => setButtonLoading(submitButton, false));
        }
    });
}

function confirmSessionTrust(form) {
    const confirmMsg = form.dataset.confirmMsg || '';
    const csrfToken = form.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
    const submitButton = form.querySelector('button[type="submit"]');

    showConfirmation({
        message: confirmMsg,
        requirePassword: true,
        onConfirm: function(currentPassword) {
            const body = new URLSearchParams(new FormData(form));
            body.set('current_password', currentPassword);
            setButtonLoading(submitButton, true);

            return fetch(form.action, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: body.toString()
            })
            .then(parseJsonResponse)
            .then(data => {
                if (data.status !== 'success') {
                    throw new Error(data.message || 'Request failed.');
                }
                window.location.assign(data.redirect_url || window.location.href);
                return true;
            })
            .finally(() => setButtonLoading(submitButton, false));
        }
    });
}

function downloadBackupCodes() {
    const container = document.getElementById('backupCodesContainer');
    // Get text content effectively
    const codeElements = container.querySelectorAll('strong');
    let text = "Dlux Backup Codes\n=====================\n\n";
    codeElements.forEach((el, index) => {
        text += `${index + 1}. ${el.innerText}\n`;
    });
    
    text += "\nKeep these codes safe!";
    
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "dlux_backup_codes.txt";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}
