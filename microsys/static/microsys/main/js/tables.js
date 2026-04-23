(function () {
    'use strict';

    const DENSITY_VALUES = new Set(['dense', 'balanced', 'roomy']);

    function syncDensityOptions(activeDensity) {
        document.querySelectorAll('[data-ms-table-density-inline]').forEach((group) => {
            group.querySelectorAll('[data-ms-table-density-option]').forEach((option) => {
                const isActive = option.getAttribute('data-ms-table-density-option') === activeDensity;
                option.classList.toggle('is-active', isActive);
                option.setAttribute('aria-pressed', isActive ? 'true' : 'false');
            });
        });
    }

    function syncTableShells(activeDensity) {
        document.querySelectorAll('.ms-table-shell[data-ms-table-density]').forEach((shell) => {
            if (shell.hasAttribute('data-ms-table-density-locked')) {
                return;
            }
            shell.setAttribute('data-ms-table-density', activeDensity);
        });
    }

    function persistDensity(activeDensity) {
        if (typeof window.updatePreferences === 'function') {
            window.updatePreferences({ table_density: activeDensity });
            return;
        }

        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
        if (!csrfToken) {
            return;
        }

        fetch('/sys/api/preferences/update/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            body: JSON.stringify({ table_density: activeDensity }),
        }).catch((error) => {
            console.error('Failed to save table density preference:', error);
        });
    }

    function applyDensity(activeDensity, persistPreference) {
        if (!DENSITY_VALUES.has(activeDensity)) {
            return;
        }

        syncDensityOptions(activeDensity);
        syncTableShells(activeDensity);

        if (window.USER_PREFS) {
            window.USER_PREFS.table_density = activeDensity;
        }

        if (persistPreference) {
            persistDensity(activeDensity);
        }
    }

    window.applyMicrosysTableDensityPreview = function(activeDensity) {
        applyDensity(activeDensity, false);
    };

    document.addEventListener('click', (event) => {
        const option = event.target.closest('[data-ms-table-density-option]');
        if (!option) {
            return;
        }

        const activeDensity = option.getAttribute('data-ms-table-density-option');
        applyDensity(activeDensity, true);
    });

    document.addEventListener('DOMContentLoaded', () => {
        const initialDensity = (window.USER_PREFS && window.USER_PREFS.table_density) || null;
        if (DENSITY_VALUES.has(initialDensity)) {
            applyDensity(initialDensity, false);
        }
    });
})();
