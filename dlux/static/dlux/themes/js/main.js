document.addEventListener('DOMContentLoaded', function() {
    const root = document.documentElement;
    const themes = Array.isArray(window.DLUX_THEME_NAMES) && window.DLUX_THEME_NAMES.length
        ? window.DLUX_THEME_NAMES
        : ['light'];
    const defaultTheme = (window.DLUX_CONFIG && window.DLUX_CONFIG.default_theme) || themes[0] || 'light';
    const themeCssUrls = {};
    const themeStylesheets = new Map();
    const previewThemes = new Set();
    const themeSwitchFade = {
        swapTimer: null,
        cleanupTimer: null,
        revision: 0,
    };
    let themeRequest = 0;

    document.getElementById('dlux-theme-stylesheets')?.content
        .querySelectorAll('link[data-dlux-theme-css]')
        .forEach((link) => {
            themeCssUrls[link.dataset.dluxThemeCss] = link.getAttribute('href');
        });

    // Load saved theme
    const savedTheme = ((window.USER_PREFS && window.USER_PREFS.theme) || localStorage.getItem('appTheme') || defaultTheme);
    const initialTheme = themes.includes(savedTheme) ? savedTheme : defaultTheme;
    themes.forEach(t => root.classList.remove(`theme-${t}`));
    root.classList.add(`theme-${initialTheme}`);
    loadThemeStylesheet(initialTheme);

    // The page ships only the active theme's stylesheet. Another theme's sheet
    // is inserted beside it, keeping its place in the cascade, and resolves once
    // it has loaded so a switch never paints the page unstyled.
    function loadThemeStylesheet(theme, url) {
        if (!theme) {
            return Promise.resolve(false);
        }
        if (themeStylesheets.has(theme)) {
            return themeStylesheets.get(theme);
        }

        let stylesheet = document.querySelector(`link[data-dlux-theme-css="${CSS.escape(theme)}"]`);
        if (stylesheet && stylesheet.sheet) {
            const loaded = Promise.resolve(true);
            themeStylesheets.set(theme, loaded);
            return loaded;
        }
        if (stylesheet) {
            // A server-rendered sheet without a CSSOM sheet by now failed to load.
            stylesheet.remove();
        }

        const href = themeCssUrls[theme] || url;
        if (!href) {
            return Promise.resolve(false);
        }
        const anchors = document.querySelectorAll('link[data-dlux-theme-css]');
        stylesheet = document.createElement('link');
        stylesheet.rel = 'stylesheet';
        stylesheet.href = href;
        stylesheet.dataset.dluxThemeCss = theme;

        const loading = new Promise((resolve) => {
            stylesheet.addEventListener('load', () => resolve(true), { once: true });
            stylesheet.addEventListener('error', () => {
                themeStylesheets.delete(theme);
                stylesheet.remove();
                resolve(false);
            }, { once: true });
        });
        themeStylesheets.set(theme, loading);
        if (anchors.length) {
            anchors[anchors.length - 1].after(stylesheet);
        } else {
            document.head.appendChild(stylesheet);
        }
        return loading;
    }

    window.dluxLoadThemeStylesheet = loadThemeStylesheet;

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
        const request = ++themeRequest;

        if (allowPreviewTheme && !themes.includes(resolvedTheme)) {
            previewThemes.add(resolvedTheme);
        }

        loadThemeStylesheet(resolvedTheme, options && options.cssUrl).then(() => {
            if (request === themeRequest) {
                fadeThemeSwitch(resolvedTheme);
            }
        });
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

        const url = window.dluxEndpoint
            ? window.dluxEndpoint('preferencesUpdate', null, '/sys/api/preferences/update/')
            : (window.dluxUrl ? window.dluxUrl('/sys/api/preferences/update/') : '/sys/api/preferences/update/');
        return fetch(url, {
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
