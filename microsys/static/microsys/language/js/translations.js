/**
 * Microsys Frontend Translation Utility
 * Allows zero-boilerplate localization within Vanilla JS scripts.
 * Depends on window.__MS_TRANS injected by the backend in base.html.
 */

const ms_trans = (key, fallback) => {
    // If fallback is not provided, return the key itself
    const defaultVal = fallback !== undefined ? fallback : key;
    
    // Check if the backend injected the translation dictionary
    if (window.__MS_TRANS && typeof window.__MS_TRANS === 'object') {
        const value = window.__MS_TRANS[key];
        // If the key exists (even if empty string), return it
        if (value !== undefined && value !== null) {
            return value;
        }
    }
    
    return defaultVal;
};

// Expose globally
window.ms_trans = ms_trans;
