document.addEventListener('DOMContentLoaded', function() {
    const root = document.documentElement;
    const themes = Array.isArray(window.MICROSYS_THEME_NAMES) && window.MICROSYS_THEME_NAMES.length
        ? window.MICROSYS_THEME_NAMES
        : ['light'];
    const defaultTheme = (window.MICROSYS_CONFIG && window.MICROSYS_CONFIG.default_theme) || themes[0] || 'light';

    // Load saved theme
    const savedTheme = ((window.USER_PREFS && window.USER_PREFS.theme) || localStorage.getItem('appTheme') || defaultTheme);
    themes.forEach(t => root.classList.remove(`theme-${t}`));
    root.classList.add(`theme-${themes.includes(savedTheme) ? savedTheme : defaultTheme}`);

    // Global function to set theme
    window.setTheme = function(theme) {
        const resolvedTheme = theme && themes.includes(theme) ? theme : defaultTheme;

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
    updateActiveThemeUI(themes.includes(savedTheme) ? savedTheme : defaultTheme);
});

if (typeof window.updatePreferences !== 'function') {
    window.updatePreferences = function(data) {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
        if (!csrfToken) {
            console.error("CSRF token not found, cannot save preferences.");
            return Promise.resolve();
        }

        return fetch('/sys/api/preferences/update/', {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken,
                "Content-Type": "application/json",
            },
            body: JSON.stringify(data || {})
        }).then(response => {
            if (!response.ok) {
                console.error("Failed to save preferences:", response.statusText);
                return null;
            }
            return response.json().catch(() => null);
        }).then(payload => {
            if (payload && payload.preferences && window.USER_PREFS) {
                Object.assign(window.USER_PREFS, payload.preferences);
            } else if (window.USER_PREFS && data) {
                Object.assign(window.USER_PREFS, data);
            }
            return payload;
        }).catch(error => {
            console.error("Error updating preferences:", error);
            return null;
        });
    };
}
