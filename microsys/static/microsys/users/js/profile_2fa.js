let needsReload = false;

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

    if (otpSetupForm) {
        otpSetupForm.addEventListener('submit', submitOTPSetup);
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
            const input = document.getElementById('otpSetupInput');
            if (input) input.focus();
        });
    }
});

function initiate2FASetup(btn) {
    const method = btn.dataset.method;
    const url = btn.dataset.url;
    
    // Reset Modal State
    const errorEl = document.getElementById('otpSetupError');
    if (errorEl) errorEl.classList.add('d-none');
    
    const inputEl = document.getElementById('otpSetupInput');
    if (inputEl) inputEl.value = '';
    
    document.getElementById('otpSetupForm').classList.remove('d-none');
    document.getElementById('otp-instruction').classList.remove('d-none');
    document.getElementById('otpSetupSuccess').classList.add('d-none');
    
    const closeBtn = document.querySelector('#otpSetupModal .btn-close');
    if (closeBtn) closeBtn.classList.remove('d-none');
    
    const iconContainer = document.querySelector('#otpSetupModal .bi-shield-lock-fill');
    if (iconContainer && iconContainer.parentElement) {
        iconContainer.parentElement.classList.remove('d-none');
    }

    const form = document.getElementById('otpSetupForm');
    const titleEl = document.querySelector('#otpSetupModal .modal-title');
    if (titleEl && form.dataset.transVerifyTitle) {
        titleEl.textContent = form.dataset.transVerifyTitle;
    }
    
    needsReload = false;
    
    // Logic split for TOTP vs Email/Phone
    if (method === 'totp') {
        fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' }})
        .then(res => res.json())
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
        .catch(err => console.error("Error fetching TOTP setup:", err));
    } else {
        // Email/Phone
        fetch(`${url}?method=${method}&ajax=1`, { headers: { 'X-Requested-With': 'XMLHttpRequest' }})
        .then(res => res.json())
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
        .catch(err => console.error("Error initiating 2FA:", err));
    }
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
    });
}

function downloadCodes(codes) {
    let text = "Microsys Backup Codes\n=====================\n\n";
    codes.forEach((code, index) => {
        text += `${index + 1}. ${code}\n`;
    });
    text += "\nKeep these codes safe!";
    
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "microsys_backup_codes.txt";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Helper for Confirmation Modal
function showConfirmation(message, onConfirm) {
    const modalEl = document.getElementById('confirmationModal');
    const msgEl = document.getElementById('confirmationMessage');
    const btnEl = document.getElementById('confirmationConfirmBtn');
    
    if (!modalEl || !msgEl || !btnEl) return;
    
    msgEl.textContent = message;
    
    // Create new modal instance
    const modal = new bootstrap.Modal(modalEl);
    
    // Remove old listeners to prevent stacking
    const newBtn = btnEl.cloneNode(true);
    btnEl.parentNode.replaceChild(newBtn, btnEl);
    
    newBtn.addEventListener('click', function() {
        modal.hide();
        onConfirm();
    });
    
    modal.show();
}

function disable2FA(e) {
    const btn = e.target.closest('button');
    const method = btn.dataset.method;
    const url = btn.dataset.url;
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || document.getElementById('otpSetupForm').dataset.csrf;
    const confirmMsg = btn.dataset.confirmMsg || 'Are you sure?';
    
    showConfirmation(confirmMsg, function() {
        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: `method=${method}`
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                window.location.reload();
            } else {
                alert(data.message || 'Error disabling 2FA');
            }
        })
        .catch(err => {
            console.error(err);
            alert('Server connection error');
        });
    });
}

function handleBackupCodes(e) {
    const btn = e.target.closest('button');
    const url = btn.dataset.url;
    
    const performGeneration = () => {
        const container = document.getElementById('backupCodesContainer');
        
        // Show modal first with loader
        const modalEl = document.getElementById('backupCodesModal');
        let modal = bootstrap.Modal.getInstance(modalEl);
        if (!modal) {
            modal = new bootstrap.Modal(modalEl);
        }
        modal.show();
    
        // Fetch Codes
        let csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        if (!csrfToken) {
             csrfToken = document.getElementById('otpSetupForm')?.dataset.csrf;
        }
    
        fetch(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                const codes = data.codes;
                let html = '<div class="row text-center">';
                codes.forEach(code => {
                    html += `<div class="col-6 mb-2"><strong>${code}</strong></div>`;
                });
                html += '</div>';
                container.innerHTML = html;
                
                // Show download button
                document.getElementById('downloadBackupCodesBtn').classList.remove('d-none');
            } else {
                container.innerHTML = `<div class="text-danger">${data.message || 'Error'}</div>`;
            }
        })
        .catch(err => {
            container.innerHTML = `<div class="text-danger">Connection Error</div>`;
        });
    };

    // Confirmation before generating new codes
    const confirmMsg = btn.dataset.confirmMsg || 'Are you sure?';
    showConfirmation(confirmMsg, performGeneration);
}

function downloadBackupCodes() {
    const container = document.getElementById('backupCodesContainer');
    // Get text content effectively
    const codeElements = container.querySelectorAll('strong');
    let text = "Microsys Backup Codes\n=====================\n\n";
    codeElements.forEach((el, index) => {
        text += `${index + 1}. ${el.innerText}\n`;
    });
    
    text += "\nKeep these codes safe!";
    
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "microsys_backup_codes.txt";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}
