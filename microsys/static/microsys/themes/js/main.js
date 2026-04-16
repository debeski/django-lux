document.addEventListener('DOMContentLoaded', function() {
    const root = document.documentElement;
    const themes = Array.isArray(window.MICROSYS_THEME_NAMES) && window.MICROSYS_THEME_NAMES.length
        ? window.MICROSYS_THEME_NAMES
        : ['light'];

    // Load saved theme
    const savedTheme = ((window.USER_PREFS && window.USER_PREFS.theme) || localStorage.getItem('appTheme') || 'light');
    themes.forEach(t => root.classList.remove(`theme-${t}`));
    root.classList.add(`theme-${themes.includes(savedTheme) ? savedTheme : 'light'}`);

    // Global function to set theme
    window.setTheme = function(theme) {
        const resolvedTheme = theme && themes.includes(theme) ? theme : 'light';

        // Remove all current theme classes
        themes.forEach(t => root.classList.remove(`theme-${t}`));

        root.classList.add(`theme-${resolvedTheme}`);
        localStorage.setItem('appTheme', resolvedTheme);
        if (window.USER_PREFS) window.USER_PREFS.theme = resolvedTheme;
        
        // Visual Update: Highlight active theme circle
        updateActiveThemeUI(resolvedTheme);

        window.dispatchEvent(new CustomEvent('microsys:theme-changed', {
            detail: { theme: resolvedTheme }
        }));

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
