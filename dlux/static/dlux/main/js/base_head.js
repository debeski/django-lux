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
    window.DLUX_STRINGS = parseJsonScript('dlux-strings-data', {});

    // Path prefix dlux is mounted under ("/" at root, e.g. "/en/" behind an
    // i18n language prefix or a sub-path mount). dlux JS uses root-relative
    // paths like "/sys/api/preferences/update/"; those 404 under a prefix, so
    // dluxUrl() rewrites a root-relative path onto the real mount prefix.
    var rawPrefix = parseJsonScript('dlux-url-prefix', '/');
    var rawUrls = parseJsonScript('dlux-url-data', {});
    if (typeof rawPrefix !== 'string' || !rawPrefix) {
        rawPrefix = '/';
    }
    if (!rawUrls || typeof rawUrls !== 'object' || Array.isArray(rawUrls)) {
        rawUrls = {};
    }
    if (rawPrefix.charAt(0) !== '/') { rawPrefix = '/' + rawPrefix; }
    if (rawPrefix.charAt(rawPrefix.length - 1) !== '/') { rawPrefix += '/'; }
    window.DLUX_URL_PREFIX = rawPrefix;
    window.DLUX_URLS = rawUrls;
    window.dluxUrl = function (path) {
        if (!path || typeof path !== 'string') { return path; }
        // Leave absolute URLs (http(s)://, //host) and already-prefixed paths alone.
        if (/^(https?:)?\/\//.test(path)) { return path; }
        var prefix = window.DLUX_URL_PREFIX || '/';
        if (prefix !== '/' && path.indexOf(prefix) === 0) { return path; }
        return prefix + path.replace(/^\/+/, '');
    };
    window.dluxEndpoint = function (name, params, fallbackPath) {
        var path = (window.DLUX_URLS && window.DLUX_URLS[name]) || fallbackPath || '';
        if (!path || typeof path !== 'string') { return path; }
        Object.keys(params || {}).forEach(function (key) {
            path = path.split('__' + key + '__').join(encodeURIComponent(String(params[key])));
        });
        return window.dluxUrl(path);
    };
    window.DLUX_THEME_NAMES = parseJsonScript('dlux-theme-names', ['light']);
    window.DLUX_CONFIG = parseJsonScript('dlux-config-data', {});
    window.DLUX_FONT_FAMILIES = parseJsonScript('dlux-font-families', {});

    window.USER_PREFS._lang = document.documentElement.getAttribute('lang') || 'en';
    window.USER_PREFS._dir = document.documentElement.getAttribute('dir') || 'ltr';

    const allowedThemes = Array.isArray(window.DLUX_THEME_NAMES) && window.DLUX_THEME_NAMES.length
        ? window.DLUX_THEME_NAMES
        : ['light'];
    const defaultTheme = window.DLUX_CONFIG.default_theme || allowedThemes[0] || 'light';
    const savedTheme = window.USER_PREFS.theme || localStorage.getItem('appTheme') || defaultTheme;
    const themeToApply = allowedThemes.includes(savedTheme) ? savedTheme : defaultTheme;
    const savedAccessibility = window.USER_PREFS.accessibility || localStorage.getItem('accessibilityMode');

    document.documentElement.classList.add(`theme-${themeToApply}`);

    const allowedFonts = window.DLUX_CONFIG.allowed_fonts || [];
    const savedFont = window.USER_PREFS.font || localStorage.getItem('appFont');
    if (savedFont && (allowedFonts.length === 0 || allowedFonts.includes(savedFont))) {
        const familyName = window.DLUX_FONT_FAMILIES[savedFont];
        if (familyName) {
        document.documentElement.style.setProperty('--dlux-main-font', `'${familyName}', sans-serif`);
        }
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
