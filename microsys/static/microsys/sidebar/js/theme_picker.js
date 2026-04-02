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
            // Update the main indicator circle's color class
            indicator.className = 'current-theme-indicator theme-circle-' + (theme || 'light');
            
            // Highlight active option in popup
            options.forEach(opt => {
                opt.classList.remove('active');
                if (opt.getAttribute('data-theme') === (theme || 'light')) {
                    opt.classList.add('active');
                }
            });
        }

        // Initialize indicator color
        const savedTheme = window.USER_PREFS?.theme || localStorage.getItem('appTheme') || 'light';
        updateCurrentThemeIndicator(savedTheme);
    });
})();

