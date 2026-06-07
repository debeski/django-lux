// Lightweight inline markdown → HTML (no dependencies)
function msLoginMarkdown(text) {
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

    // Render hero message markdown (fullpage style)
    const heroEl = document.querySelector('[data-ms-login-hero]');
    if (heroEl) {
        const raw = heroEl.getAttribute('data-ms-login-hero') || '';
        // The attribute lives on the body element itself; render into it directly.
        const bodyEl = heroEl.classList.contains('ms-login-hero__body')
            ? heroEl
            : heroEl.querySelector('.ms-login-hero__body');
        if (bodyEl && raw.trim()) {
            bodyEl.innerHTML = msLoginMarkdown(raw);
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
