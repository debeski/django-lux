document.addEventListener('DOMContentLoaded', function() {
    const root = document.documentElement;
    const themes = ['light', 'blue', 'gold', 'green', 'red', 'dark'];

    // Load saved theme
    const savedTheme = (window.USER_PREFS && window.USER_PREFS.theme) || localStorage.getItem('appTheme');
    if (savedTheme && themes.includes(savedTheme)) {
        root.classList.add(`theme-${savedTheme}`);
    }

    // Global function to set theme
    window.setTheme = function(theme) {
        // Remove all current theme classes
        themes.forEach(t => root.classList.remove(`theme-${t}`));

        if (theme && themes.includes(theme)) {
            root.classList.add(`theme-${theme}`);
            localStorage.setItem('appTheme', theme);
        } else {
            localStorage.removeItem('appTheme');
        }
        
        // Visual Update: Highlight active theme circle
        updateActiveThemeUI(theme || 'light');

        // Dispatch event for components that might need resizing (like Plotly)
        window.dispatchEvent(new Event('resize'));
    };

    function updateActiveThemeUI(activeTheme) {
        document.querySelectorAll('.theme-preview').forEach(el => {
            el.classList.remove('active');
            if (el.getAttribute('data-theme') === activeTheme) {
                el.classList.add('active');
            }
        });
    }

    // Initialize UI on load
    updateActiveThemeUI(savedTheme || 'light');
});
