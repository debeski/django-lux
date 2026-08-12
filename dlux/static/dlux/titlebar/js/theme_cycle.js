(function () {
    'use strict';

    // The titlebar theme action, next to the language cycle it mirrors: one
    // button that steps through the allowed themes. The sidebar toolbar's picker
    // (sidebar/js/theme_picker.js) is a different surface and stays independent.
    function initThemeCycle(button) {
        if (!button || button.dataset.dluxThemeCycleReady === 'true') {
            return;
        }
        button.dataset.dluxThemeCycleReady = 'true';

        const themes = String(button.dataset.themeCodes || '')
            .split(',')
            .map((theme) => theme.trim())
            .filter(Boolean);
        if (themes.length < 2) {
            return;
        }

        const dot = button.querySelector('[data-dlux-theme-cycle-dot]');
        const swatches = Array.from(button.querySelectorAll('[data-theme-swatch]'));

        function currentTheme() {
            return (window.USER_PREFS && window.USER_PREFS.theme)
                || localStorage.getItem('appTheme')
                || (window.DLUX_CONFIG && window.DLUX_CONFIG.default_theme)
                || themes[0];
        }

        function paint(theme) {
            const swatch = swatches.find((item) => item.dataset.theme === theme);
            if (dot && swatch) {
                dot.style.background = swatch.dataset.themeColor || '';
            }
            if (swatch && swatch.dataset.themeLabel) {
                button.setAttribute('data-dlux-tooltip', swatch.dataset.themeLabel);
                button.setAttribute('aria-label', swatch.dataset.themeLabel);
            }
        }

        button.addEventListener('click', function (event) {
            event.stopPropagation();
            const active = currentTheme();
            const index = themes.indexOf(active);
            const next = themes[(index + 1) % themes.length];
            if (!next || next === active || typeof window.setTheme !== 'function') {
                return;
            }
            window.setTheme(next);
            if (window.USER_PREFS) {
                window.USER_PREFS.theme = next;
            }
            if (typeof window.updatePreferences === 'function') {
                window.updatePreferences({ theme: next });
            }
            paint(next);
        });

        paint(currentTheme());
    }

    function scan(root) {
        (root || document).querySelectorAll('[data-dlux-theme-cycle]').forEach(initThemeCycle);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { scan(document); });
    } else {
        scan(document);
    }
}());
