document.addEventListener('DOMContentLoaded', function () {
    const emailBtn = document.getElementById('sendEmailOtpBtn');
    const backupBtn = document.getElementById('useBackupCodeBtn');
    const textEl = document.getElementById('otp-instruction-text');
    const inputEl = document.getElementById('otp_code');

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

    if (emailBtn) {
        emailBtn.addEventListener('click', function () {
            setButtonLoading(emailBtn, true);
            fetch(emailBtn.dataset.url, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': emailBtn.dataset.csrf || '',
                    'X-Requested-With': 'XMLHttpRequest',
                },
            })
                .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
                .then(({ ok, data }) => {
                    if (!ok || data.status !== 'success') {
                        throw new Error(data.message || emailBtn.dataset.errorText || 'Unable to send code');
                    }
                    if (textEl) {
                        textEl.textContent = emailBtn.dataset.sentText || '';
                    }
                    if (inputEl) {
                        inputEl.setAttribute('maxlength', '6');
                        inputEl.setAttribute('placeholder', 'XXXXXX');
                        inputEl.focus();
                    }
                })
                .catch((error) => {
                    if (textEl) {
                        textEl.textContent = error.message || emailBtn.dataset.errorText || 'Unable to send code';
                    }
                })
                .finally(() => setButtonLoading(emailBtn, false));
        });
    }

    if (backupBtn) {
        backupBtn.addEventListener('click', function () {
            if (textEl) {
                textEl.textContent = backupBtn.dataset.instructionText || '';
            }
            if (inputEl) {
                inputEl.setAttribute('maxlength', '8');
                inputEl.setAttribute('placeholder', 'XXXXXXXX');
                inputEl.focus();
            }
        });
    }
});
