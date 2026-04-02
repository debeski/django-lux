(function() {
    const root = document.documentElement;
    const modes = ['high-contrast', 'grayscale', 'invert', 'large-text', 'no-animations'];

    // Load saved preference (Now supports multiple modes)
    let savedModes = [];
    try {
        const stored = localStorage.getItem('accessibilityMode');
        // Handle legacy string format or new JSON array
        if (stored) {
            savedModes = stored.startsWith('[') ? JSON.parse(stored) : [stored];
        }
    } catch (e) {
        console.error("Error parsing accessibility modes", e);
        savedModes = [];
    }

    // Apply saved modes immediately
    savedModes.forEach(mode => {
        if (modes.includes(mode)) {
            root.classList.add(`accessibility-${mode}`);
        }
    });

    function updateAccessibilityUI(activeModes) {
        document.querySelectorAll('.accessibility-switch').forEach(toggle => {
            const mode = toggle.getAttribute('data-accessibility');
            toggle.checked = activeModes.includes(mode);
        });
    }

    function initAccessibilityUI() {
        updateAccessibilityUI(savedModes);
    }

    // Function to toggle mode
    window.setAccessibilityMode = function(mode) {
        if (!mode || !modes.includes(mode)) return;

        if (savedModes.includes(mode)) {
            // Remove mode
            savedModes = savedModes.filter(m => m !== mode);
            root.classList.remove(`accessibility-${mode}`);
        } else {
            // Add mode
            savedModes.push(mode);
            root.classList.add(`accessibility-${mode}`);
        }

        // Save updated list
        if (savedModes.length > 0) {
            localStorage.setItem('accessibilityMode', JSON.stringify(savedModes));
        } else {
            localStorage.removeItem('accessibilityMode');
        }

        // Visual Update
        updateAccessibilityUI(savedModes);
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAccessibilityUI);
    } else {
        initAccessibilityUI();
    }
})();
