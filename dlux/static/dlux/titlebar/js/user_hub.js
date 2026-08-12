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

    // Ctrl/Cmd-J opens the Options view (mirrors Ctrl/Cmd-K for global search).
    // Navigate via the rendered options link so gating/URL stay server-driven:
    // no link (unavailable) means the shortcut is a no-op.
    document.addEventListener('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && (e.key === 'j' || e.key === 'J')) {
            const link = document.querySelector('[data-dlux-options-link], [data-titlebar-action-key="settings"]');
            if (link && link.href) {
                e.preventDefault();
                window.location.href = link.href;
            }
        }
    });

});
