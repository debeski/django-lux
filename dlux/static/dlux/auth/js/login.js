// Lightweight inline markdown → HTML (no dependencies)
function dluxLoginMarkdown(text) {
    if (!text) return '';
    let html = text
        // Escape existing HTML
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        // Headings (must come before inline patterns)
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        // Inline code (before bold/italic so asterisks inside code are safe)
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        // Strikethrough ~~text~~
        .replace(/~~(.+?)~~/g, '<s>$1</s>')
        // Bold+italic: *** and ___
        .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
        .replace(/___(.+?)___/g, '<strong><em>$1</em></strong>')
        // Bold: ** and __
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/__(.+?)__/g, '<strong>$1</strong>')
        // Italic: * and _ (single; avoid matching inside words for _)
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/(?<![a-zA-Z0-9])_([^_]+?)_(?![a-zA-Z0-9])/g, '<em>$1</em>')
        // Links [text](url)
        .replace(/\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
        // Unordered lists (- or * followed by a space)
        .replace(/^[*] (.+)$/gm, '<li>$1</li>')
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        // Ordered lists
        .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
        // Wrap consecutive <li> blocks
        .replace(/(<li>.*<\/li>\n?)+/g, function(m) { return '<ul>' + m + '</ul>'; })
        // Horizontal rules (3+ dashes/asterisks on their own line)
        .replace(/^(\*{3,}|-{3,})$/gm, '<hr>')
        // Blank lines → paragraph break
        .replace(/\n\n+/g, '\n<p>\n')
        // Remaining newlines → line break
        .replace(/\n(?!<)/g, '<br>');
    return html;
}

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

    // Apply the admin-configured banner colour via a data-* bridge (no inline style; DSRP-1).
    document.querySelectorAll('[data-login-banner-color]').forEach(function (panel) {
        const bannerColor = panel.getAttribute('data-login-banner-color');
        if (bannerColor) {
            panel.style.setProperty('--login-banner-color', bannerColor);
        }
    });

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
            loginCard.classList.add('dlux-shake');
            // Remove class after animation ends so it can be re-triggered if needed
            loginCard.addEventListener('animationend', () => {
                loginCard.classList.remove('dlux-shake');
            }, { once: true });
        }
    }

    // Render hero message markdown (fullpage style)
    const heroEl = document.querySelector('[data-dlux-login-hero]');
    if (heroEl) {
        const raw = heroEl.getAttribute('data-dlux-login-hero') || '';
        // The attribute lives on the body element itself; render into it directly.
        const bodyEl = heroEl.classList.contains('dlux-login-hero__body')
            ? heroEl
            : heroEl.querySelector('.dlux-login-hero__body');
        if (bodyEl && raw.trim()) {
            bodyEl.innerHTML = dluxLoginMarkdown(raw);
        }
    }

    // Lockout countdown — when the server rejects a locked-out attempt it emits
    // a block carrying the exact remaining seconds; tick it down live and keep
    // the submit button disabled until the lock clears.
    const lockoutEl = document.querySelector('[data-dlux-lockout-remaining]');
    if (lockoutEl) {
        const messageEl = lockoutEl.querySelector('[data-dlux-lockout-message]');
        const template = lockoutEl.getAttribute('data-dlux-lockout-template') || 'Try again in {time}.';
        const expiredText = lockoutEl.getAttribute('data-dlux-lockout-expired') || '';
        const submitBtn = document.getElementById('submit');
        let remaining = parseInt(lockoutEl.getAttribute('data-dlux-lockout-remaining'), 10);
        if (!Number.isFinite(remaining) || remaining < 0) { remaining = 0; }

        const fmt = function (secs) {
            const m = Math.floor(secs / 60);
            const s = secs % 60;
            return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
        };

        const lockFields = [
            submitBtn,
            document.getElementById('username'),
            document.getElementById('password'),
        ].filter(Boolean);

        const setDisabled = function (disabled) {
            lockFields.forEach(function (el) {
                el.disabled = disabled;
                el.classList.toggle('disabled', disabled);
                el.setAttribute('aria-disabled', disabled ? 'true' : 'false');
            });
        };

        const render = function () {
            if (remaining > 0) {
                if (messageEl) { messageEl.textContent = template.replace('{time}', fmt(remaining)); }
            } else {
                if (messageEl) { messageEl.textContent = expiredText; }
                lockoutEl.classList.add('dlux-login-lockout--cleared');
                // Flip the notice from a warning to an all-clear tone.
                const alertEl = lockoutEl.querySelector('.alert');
                if (alertEl) {
                    alertEl.classList.remove('alert-warning');
                    alertEl.classList.add('alert-success');
                }
                const iconEl = lockoutEl.querySelector('.bi');
                if (iconEl) {
                    iconEl.classList.remove('bi-hourglass-split');
                    iconEl.classList.add('bi-check-circle');
                }
                setDisabled(false);
            }
        };

        if (remaining > 0) {
            setDisabled(true);
            render();
            const timer = setInterval(function () {
                remaining -= 1;
                if (remaining <= 0) {
                    remaining = 0;
                    clearInterval(timer);
                }
                render();
            }, 1000);
        } else {
            render();
        }
    }

    // Submit "thinking" state is now handled by the shared loading-button helper
    // (dlux/helpers/loading_button/js/main.js): the login and register submit
    // buttons carry `data-dlux-loading`, so the global helper shows the spinner
    // on a valid submit. No page-specific spinner code is needed here.
});
document.querySelectorAll('[data-login-background-url]').forEach(function (page) {
    const backgroundUrl = page.dataset.loginBackgroundUrl;
    if (backgroundUrl) page.style.setProperty('--dlux-login-background-image', `url(${JSON.stringify(backgroundUrl)})`);
});
