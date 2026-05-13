document.addEventListener("DOMContentLoaded", function() {
    const loginThemeData = document.getElementById('login-theme-data');
    if (loginThemeData) {
        try {
            const theme = JSON.parse(loginThemeData.textContent) || {};
            const themeMap = {
                selection_bg: '--selection-bg',
                selection_moz_bg: '--selection-moz-bg',
                left_bg: '--left-bg',
                left_shadow: '--left-shadow',
                right_bg: '--right-bg',
                right_shadow: '--right-shadow',
                right_text: '--right-text',
                label_color: '--label-color',
                input_text: '--input-text',
                submit_color: '--submit-color',
                submit_focus: '--submit-focus',
                submit_active: '--submit-active',
                gradient_start: '--gradient-start',
                gradient_end: '--gradient-end',
            };

            Object.entries(themeMap).forEach(([key, cssVar]) => {
                if (theme[key]) {
                    document.documentElement.style.setProperty(cssVar, theme[key]);
                }
            });
        } catch (error) {
            console.error('Failed to parse login theme data:', error);
        }
    }

    var loginTitleButton = document.querySelector(".login-title-btn");
    if (loginTitleButton) {
        loginTitleButton.style.display = "none";
    }

    // Autofocus on username field
    var usernameField = document.getElementById("username");
    if (usernameField) {
        usernameField.focus();
    }

    // Creative Touch: Trigger shake animation if errors are present
    const shakeTrigger = document.querySelector('.shake-trigger') || document.querySelector('.is-invalid');
    if (shakeTrigger) {
        const loginCard = document.querySelector('.left');
        if (loginCard) {
            loginCard.classList.add('ms-shake');
            // Remove class after animation ends so it can be re-triggered if needed
            loginCard.addEventListener('animationend', () => {
                loginCard.classList.remove('ms-shake');
            }, { once: true });
        }
    }

    // Submit button "thinking" state
    const loginForm = document.querySelector('form');
    const submitBtn = document.getElementById('submit');
    if (loginForm && submitBtn) {
        loginForm.addEventListener('submit', function() {
            if (loginForm.checkValidity()) {
                const originalText = submitBtn.innerHTML;
                submitBtn.disabled = true;
                submitBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> ${originalText}`;
            }
        });
    }
});
