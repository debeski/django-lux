(function() {
    document.addEventListener('DOMContentLoaded', () => {
        const indicator = document.getElementById('sidebarThemeIndicator');
        const popup = document.getElementById('sidebarThemePopup');
        const options = document.querySelectorAll('.theme-option-circle');
        const arrow = document.getElementById('sidebarThemeArrow');

        if (!indicator || !popup) return;

        // Toggle Popup
        indicator.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = popup.classList.toggle('show');
            indicator.classList.toggle('open', isOpen);
            if (arrow) arrow.classList.toggle('visible', isOpen);
            if (isOpen) {
                const densityPopup = document.getElementById('sidebarDensityPopup');
                if (densityPopup) densityPopup.classList.remove('show');
            }
        });

        // Close when clicking outside
        document.addEventListener('click', (e) => {
            if (!popup.contains(e.target) && e.target !== indicator) {
                popup.classList.remove('show');
                indicator.classList.remove('open');
                if (arrow) arrow.classList.remove('visible');
            }
        });

        // Theme selection
        options.forEach(opt => {
            opt.addEventListener('click', () => {
                const theme = opt.getAttribute('data-theme');
                if (window.setTheme) {
                    window.setTheme(theme);
                    updateCurrentThemeIndicator(theme);
                    popup.classList.remove('show');
                    indicator.classList.remove('open');
                    if (arrow) arrow.classList.remove('visible');
                    
                    // Save to API
                    if (window.updatePreferences) {
                        window.updatePreferences({ theme: theme });
                        if (window.USER_PREFS) window.USER_PREFS.theme = theme;
                    }
                }
            });
        });

        function updateCurrentThemeIndicator(theme) {
            const resolvedTheme = theme || (window.DLUX_CONFIG && window.DLUX_CONFIG.default_theme) || 'light';
            const activeOption = Array.from(options).find(
                (opt) => opt.getAttribute('data-theme') === resolvedTheme
            );

            indicator.className = 'current-theme-indicator';
            if (activeOption) {
                indicator.style.background = window.getComputedStyle(activeOption).background;
            } else {
                indicator.style.background = '';
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
        const savedTheme = window.USER_PREFS?.theme || localStorage.getItem('appTheme') || (window.DLUX_CONFIG && window.DLUX_CONFIG.default_theme) || 'light';
        updateCurrentThemeIndicator(savedTheme);
    });
})();
