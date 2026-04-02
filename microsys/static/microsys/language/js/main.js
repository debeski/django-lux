/**
 * microsys/static/main/js/language.js
 * ====================================
 * Client-side language switcher for the microsys framework.
 * 
 * Handles:
 *   1. Immediate <html lang> and <html dir> attribute swap
 *   2. Hot-swap of Bootstrap CSS between LTR and RTL variants
 *   3. Saving preference to Profile.preferences via the existing API
 *   4. localStorage fallback (matching theme/accessibility pattern)
 *   5. Page reload for server-side string refresh
 *
 * Global function: window.setLanguage(langCode)
 */
(function() {
    'use strict';

    // Read server-resolved language from the injected USER_PREFS object
    const currentLang = (window.USER_PREFS && window.USER_PREFS._lang) || 'ar';
    const currentDir  = (window.USER_PREFS && window.USER_PREFS._dir)  || 'rtl';

    /**
     * Set the active language.
     * @param {string} langCode - The language code to switch to (e.g. 'en', 'ar', 'fr')
     */
    window.setLanguage = function(langCode) {
        if (!langCode || langCode === currentLang) return;

        // 1. Immediately update HTML attributes for visual feedback
        document.documentElement.setAttribute('lang', langCode);

        // 2. Determine direction — check USER_PREFS for config, else guess from known RTL codes
        const rtlCodes = ['ar', 'he', 'fa', 'ur', 'ps', 'ku', 'sd', 'yi'];
        // Try to get direction from the languages config embedded in the page
        let newDir = rtlCodes.includes(langCode) ? 'rtl' : 'ltr';
        
        // Check if the options page has data-lang elements with direction info
        const langEl = document.querySelector(`[data-lang="${langCode}"]`);
        if (langEl && langEl.dataset.dir) {
            newDir = langEl.dataset.dir;
        }

        document.documentElement.setAttribute('dir', newDir);

        // 3. Hot-swap Bootstrap CSS if direction changed
        const bootstrapLink = document.getElementById('bootstrap-css');
        if (bootstrapLink && newDir !== currentDir) {
            const href = bootstrapLink.getAttribute('href');
            if (newDir === 'ltr') {
                bootstrapLink.setAttribute('href', href.replace('bootstrap.rtl.min.css', 'bootstrap.min.css'));
            } else {
                bootstrapLink.setAttribute('href', href.replace('bootstrap.min.css', 'bootstrap.rtl.min.css'));
            }
        }

        // 4. Save to localStorage as immediate fallback
        localStorage.setItem('appLanguage', langCode);

        // 5. Save to server via existing preferences API
        const csrfMeta = document.querySelector('meta[name="csrf-token"]');
        const csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';

        fetch('/sys/api/preferences/update/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            body: JSON.stringify({ language: langCode }),
        })
        .then(() => {
            // 6. Reload page for server-side string refresh
            window.location.reload();
        })
        .catch((err) => {
            console.error('Failed to save language preference:', err);
            // Still reload — localStorage will persist the choice
            window.location.reload();
        });
    };

    // Update active language indicator on options page (if present)
    function updateLanguageUI() {
        document.querySelectorAll('.lang-option').forEach(el => {
            el.classList.remove('lang-active');
            if (el.getAttribute('data-lang') === currentLang) {
                el.classList.add('lang-active');
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', updateLanguageUI);
    } else {
        updateLanguageUI();
    }
})();
