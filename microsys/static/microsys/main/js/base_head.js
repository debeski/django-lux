(function () {
    'use strict';

    function parseJsonScript(id, fallback) {
        const element = document.getElementById(id);
        if (!element) {
            return fallback;
        }

        try {
            return JSON.parse(element.textContent) || fallback;
        } catch (_error) {
            return fallback;
        }
    }

    window.USER_PREFS = parseJsonScript('user-prefs-data', {});
    window.__MS_TRANS = parseJsonScript('ms-trans-data', {});
    window.MICROSYS_THEME_NAMES = parseJsonScript('microsys-theme-names', ['light']);
    window.MICROSYS_CONFIG = parseJsonScript('microsys-config-data', {});

    window.USER_PREFS._lang = document.documentElement.getAttribute('lang') || 'en';
    window.USER_PREFS._dir = document.documentElement.getAttribute('dir') || 'ltr';

    const allowedThemes = Array.isArray(window.MICROSYS_THEME_NAMES) && window.MICROSYS_THEME_NAMES.length
        ? window.MICROSYS_THEME_NAMES
        : ['light'];
    const defaultTheme = window.MICROSYS_CONFIG.default_theme || allowedThemes[0] || 'light';
    const savedTheme = window.USER_PREFS.theme || localStorage.getItem('appTheme') || defaultTheme;
    const themeToApply = allowedThemes.includes(savedTheme) ? savedTheme : defaultTheme;
    const savedAccessibility = window.USER_PREFS.accessibility || localStorage.getItem('accessibilityMode');

    document.documentElement.classList.add(`theme-${themeToApply}`);

    const allowedFonts = window.MICROSYS_CONFIG.allowed_fonts || [];
    const savedFont = window.USER_PREFS.font || localStorage.getItem('appFont');
    if (savedFont && (allowedFonts.length === 0 || allowedFonts.includes(savedFont))) {
        const familyName = savedFont.charAt(0).toUpperCase() + savedFont.slice(1);
        document.documentElement.style.setProperty('--ms-main-font', `'${familyName}', sans-serif`);
    }

    if (savedAccessibility) {
        let modes = [];
        try {
            modes = Array.isArray(savedAccessibility)
                ? savedAccessibility
                : (savedAccessibility.trim().startsWith('[') ? JSON.parse(savedAccessibility) : [savedAccessibility]);
        } catch (_error) {
            modes = [savedAccessibility];
        }

        modes.forEach((mode) => {
            if (mode) {
                document.documentElement.classList.add(`accessibility-${mode}`);
            }
        });
    }

    for (let index = 0; index < localStorage.length; index += 1) {
        const key = localStorage.key(index);
        if (!key || !key.endsWith('Collapsed') || localStorage.getItem(key) !== 'true') {
            continue;
        }

        const storageKeyBase = key.replace('Collapsed', '');
        const style = document.createElement('style');
        style.id = `fouc-${storageKeyBase}`;
        style.textContent = `#${storageKeyBase}Body { display: none !important; }`;
        document.head.appendChild(style);
    }
})();
