(function() {
    document.addEventListener('DOMContentLoaded', () => {
        const indicator = document.getElementById('sidebarThemeIndicator');
        const popup = document.getElementById('sidebarThemePopup');
        const options = popup ? popup.querySelectorAll('.theme-option-circle') : [];
        const swatches = indicator ? indicator.querySelectorAll('[data-theme-swatch]') : [];
        const arrow = document.getElementById('sidebarThemeArrow');
        const isDirectToggle = Boolean(indicator?.hasAttribute('data-sidebar-theme-toggle'));
        const themeNames = ((indicator?.dataset.themeCycle || '').split(',')
            .map((theme) => theme.trim()).filter(Boolean));

        if (!indicator) return;

        function selectTheme(theme) {
            if (!theme || !window.setTheme) return;
            window.setTheme(theme);
            updateCurrentThemeIndicator(theme);
            if (window.updatePreferences) {
                window.updatePreferences({ theme: theme });
            }
            if (window.USER_PREFS) window.USER_PREFS.theme = theme;
        }

        function currentTheme() {
            return window.USER_PREFS?.theme
                || localStorage.getItem('appTheme')
                || (window.DLUX_CONFIG && window.DLUX_CONFIG.default_theme)
                || themeNames[0]
                || 'light';
        }

        indicator.addEventListener('click', (e) => {
            e.stopPropagation();
            if (isDirectToggle) {
                if (themeNames.length !== 2) return;
                const active = currentTheme();
                const index = themeNames.indexOf(active);
                const next = themeNames[index === 0 ? 1 : 0];
                if (next && next !== active) selectTheme(next);
                return;
            }
            if (!popup) return;
            const isOpen = popup.classList.toggle('show');
            indicator.classList.toggle('open', isOpen);
            indicator.setAttribute('aria-expanded', String(isOpen));
            if (arrow) arrow.classList.toggle('visible', isOpen);
            if (isOpen) {
                const densityPopup = document.getElementById('sidebarDensityPopup');
                if (densityPopup) densityPopup.classList.remove('show');
            }
        });

        // Close when clicking outside
        document.addEventListener('click', (e) => {
            if (popup && !popup.contains(e.target) && e.target !== indicator) {
                popup.classList.remove('show');
                indicator.classList.remove('open');
                indicator.setAttribute('aria-expanded', 'false');
                if (arrow) arrow.classList.remove('visible');
            }
        });

        // Theme selection
        options.forEach(opt => {
            opt.addEventListener('click', () => {
                const theme = opt.getAttribute('data-theme');
                selectTheme(theme);
                if (popup) {
                    popup.classList.remove('show');
                    indicator.classList.remove('open');
                    indicator.setAttribute('aria-expanded', 'false');
                    if (arrow) arrow.classList.remove('visible');
                }
            });
        });

        function updateCurrentThemeIndicator(theme) {
            const resolvedTheme = theme || (window.DLUX_CONFIG && window.DLUX_CONFIG.default_theme) || 'light';
            const activeOption = Array.from(options).find(
                (opt) => opt.getAttribute('data-theme') === resolvedTheme
            );
            const activeSwatch = Array.from(swatches).find(
                (swatch) => swatch.getAttribute('data-theme') === resolvedTheme
            );
            const preview = activeOption || activeSwatch;

            if (preview?.dataset.themeColor) {
                indicator.style.background = preview.dataset.themeColor;
            } else if (preview) {
                indicator.style.background = window.getComputedStyle(preview).background;
            } else {
                indicator.style.background = '';
            }

            if (isDirectToggle && themeNames.length === 2) {
                const nextTheme = themeNames[themeNames.indexOf(resolvedTheme) === 0 ? 1 : 0];
                const nextSwatch = Array.from(swatches).find(
                    (swatch) => swatch.getAttribute('data-theme') === nextTheme
                );
                const label = indicator.dataset.themeToggleLabel || 'Change theme';
                const nextLabel = nextSwatch?.dataset.themeLabel || nextTheme;
                const actionLabel = nextLabel ? `${label}: ${nextLabel}` : label;
                indicator.title = actionLabel;
                indicator.setAttribute('aria-label', actionLabel);
            }
            
            // Highlight active option in popup
            options.forEach(opt => {
                opt.classList.remove('active');
                if (opt.getAttribute('data-theme') === resolvedTheme) {
                    opt.classList.add('active');
                }
            });
        }

        window.addEventListener('dlux:theme-changed', (event) => {
            const theme = event?.detail?.theme || window.USER_PREFS?.theme || localStorage.getItem('appTheme') || (window.DLUX_CONFIG && window.DLUX_CONFIG.default_theme) || 'light';
            updateCurrentThemeIndicator(theme);
        });

        // Initialize indicator color
        updateCurrentThemeIndicator(currentTheme());
    });
})();
