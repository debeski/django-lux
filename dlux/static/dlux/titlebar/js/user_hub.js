/* user_dropdown.js */
document.addEventListener('DOMContentLoaded', function() {
    const trigger = document.getElementById('dlux-user-dropdown-trigger');
    const card = document.getElementById('dlux-user-dropdown-card');

    if (trigger && card) {
        trigger.addEventListener('click', function(e) {
            e.stopPropagation();
            card.classList.toggle('show');
            
            // Log interaction if needed
            if (card.classList.contains('show')) {
                trigger.classList.add('active');
            } else {
                trigger.classList.remove('active');
            }
        });

        // Close on outside click
        document.addEventListener('click', function(e) {
            if (
                !card.contains(e.target) && 
                !trigger.contains(e.target) && 
                !e.target.closest('#tutorial-controls') && 
                !e.target.closest('.driver-popover') && 
                !e.target.closest('.driver-overlay') && 
                !e.target.closest('#sidebarThemePopup') && 
                !e.target.closest('#sidebarThemeIndicator')
            ) {
                card.classList.remove('show');
                trigger.classList.remove('active');
            }
        });

        // Close on Escape key
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && card.classList.contains('show')) {
                card.classList.remove('show');
                trigger.classList.remove('active');
            }
        });
    }

    // The first *navigable* match: a key can also land on a wrapper slot, which
    // matches the selector and has no href of its own.
    function findFirstLink(selector) {
        return Array.from(document.querySelectorAll(selector)).find(node => node.href) || null;
    }

    // Ctrl/Cmd-J opens Options, Ctrl/Cmd-H opens Home, Ctrl/Cmd-U opens User
    // Management. Navigate via rendered links so gating/URLs stay server-driven:
    // a reader who may not manage users has no link, and the key does nothing.
    const NAVIGATION_KEYS = {
        j: '[data-dlux-options-link], [data-titlebar-action-key="settings"]',
        h: '[data-titlebar-home]',
        u: '[data-dlux-users-link], [data-titlebar-action-key="users"]',
    };

    document.addEventListener('keydown', function(e) {
        if (!e.ctrlKey && !e.metaKey) return;
        const selector = NAVIGATION_KEYS[(e.key || '').toLowerCase()];
        if (!selector) return;
        const link = findFirstLink(selector);
        if (!link) return;
        e.preventDefault();
        window.location.href = link.href;
    });

});
