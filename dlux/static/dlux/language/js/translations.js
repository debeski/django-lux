/**
 * Dlux Frontend Translation Utility
 * Allows zero-boilerplate localization within Vanilla JS scripts.
 * Depends on window.DLUX_STRINGS injected by the backend in base.html.
 */

const dluxString = (key, fallback) => {
    // If fallback is not provided, return the key itself
    const defaultVal = fallback !== undefined ? fallback : key;

    // Check if the backend injected the translation dictionary
    if (window.DLUX_STRINGS && typeof window.DLUX_STRINGS === 'object') {
        const value = window.DLUX_STRINGS[key];
        // If the key exists (even if empty string), return it
        if (value !== undefined && value !== null) {
            return value;
        }
    }

    return defaultVal;
};

// Expose globally
window.dluxString = dluxString;
