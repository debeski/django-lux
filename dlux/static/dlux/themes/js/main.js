document.addEventListener('DOMContentLoaded', function() {
    const root = document.documentElement;
    const themes = Array.isArray(window.DLUX_THEME_NAMES) && window.DLUX_THEME_NAMES.length
        ? window.DLUX_THEME_NAMES
        : ['light'];
    const defaultTheme = (window.DLUX_CONFIG && window.DLUX_CONFIG.default_theme) || themes[0] || 'light';
    const previewThemes = new Set();
    const themeSwitchFade = {
        swapTimer: null,
        cleanupTimer: null,
        revision: 0,
    };

    // Load saved theme
    const savedTheme = ((window.USER_PREFS && window.USER_PREFS.theme) || localStorage.getItem('appTheme') || defaultTheme);
    themes.forEach(t => root.classList.remove(`theme-${t}`));
    root.classList.add(`theme-${themes.includes(savedTheme) ? savedTheme : defaultTheme}`);

    function loadPreviewStylesheet(theme, url) {
        if (!theme || !url || document.querySelector(`[data-dlux-preview-theme-css="${theme}"]`)) {
            return;
        }

        const stylesheet = document.createElement('link');
        stylesheet.rel = 'stylesheet';
        stylesheet.href = url;
        stylesheet.dataset.dluxPreviewThemeCss = theme;
        document.head.appendChild(stylesheet);
    }

    function applyTheme(resolvedTheme) {
        // Remove all current theme classes
        themes.forEach(t => root.classList.remove(`theme-${t}`));
        previewThemes.forEach(t => root.classList.remove(`theme-${t}`));

        root.classList.add(`theme-${resolvedTheme}`);
        localStorage.setItem('appTheme', resolvedTheme);
        if (window.USER_PREFS) window.USER_PREFS.theme = resolvedTheme;
        
        // Visual Update: Highlight active theme circle
        updateActiveThemeUI(resolvedTheme);

        window.dispatchEvent(new CustomEvent('dlux:theme-changed', {
            detail: { theme: resolvedTheme }
        }));

        // Dispatch event for components that might need resizing (like Plotly)
        window.dispatchEvent(new Event('resize'));
    }

    function clearThemeSwitchFade() {
        themeSwitchFade.revision += 1;
        window.clearTimeout(themeSwitchFade.swapTimer);
        window.clearTimeout(themeSwitchFade.cleanupTimer);
        themeSwitchFade.swapTimer = null;
        themeSwitchFade.cleanupTimer = null;
        root.classList.remove('dlux-theme-switching', 'dlux-theme-switching-covered');
        root.style.removeProperty('--dlux-theme-switch-surface');
    }

    function shouldFadeThemeSwitch() {
        return Boolean(
            document.body
            && !root.classList.contains('accessibility-no-animations')
            && !(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches)
        );
    }

    function fadeThemeSwitch(resolvedTheme) {
        if (!shouldFadeThemeSwitch()) {
            clearThemeSwitchFade();
            applyTheme(resolvedTheme);
            return;
        }

        clearThemeSwitchFade();
        const revision = themeSwitchFade.revision;
        root.style.setProperty(
            '--dlux-theme-switch-surface',
            window.getComputedStyle(document.body).backgroundColor || 'var(--body)'
        );
        root.classList.add('dlux-theme-switching');

        window.requestAnimationFrame(() => {
            if (revision !== themeSwitchFade.revision) {
                return;
            }
            root.classList.add('dlux-theme-switching-covered');
            themeSwitchFade.swapTimer = window.setTimeout(() => {
                if (revision !== themeSwitchFade.revision) {
                    return;
                }
                applyTheme(resolvedTheme);
                root.classList.remove('dlux-theme-switching-covered');
                themeSwitchFade.cleanupTimer = window.setTimeout(clearThemeSwitchFade, 220);
            }, 110);
        });
    }

    // Global function to set theme
    window.setTheme = function(theme, options) {
        const allowPreviewTheme = Boolean(options && options.preview && theme);
        const resolvedTheme = theme && (themes.includes(theme) || allowPreviewTheme) ? theme : defaultTheme;

        if (allowPreviewTheme && !themes.includes(resolvedTheme)) {
            previewThemes.add(resolvedTheme);
            loadPreviewStylesheet(resolvedTheme, options.cssUrl);
        }

        fadeThemeSwitch(resolvedTheme);
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
