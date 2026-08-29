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

    function findFirstLink(selector) {
        const link = document.querySelector(selector);
        return link && link.href ? link : null;
    }

    // Ctrl/Cmd-J opens Options and Ctrl/Cmd-H opens Home.
    // Navigate via rendered links so gating/URLs stay server-driven.
    document.addEventListener('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && (e.key === 'j' || e.key === 'J')) {
            const link = findFirstLink('[data-dlux-options-link], [data-titlebar-action-key="settings"]');
            if (link) {
                e.preventDefault();
                window.location.href = link.href;
            }
        } else if ((e.ctrlKey || e.metaKey) && (e.key === 'h' || e.key === 'H')) {
            const link = findFirstLink('[data-titlebar-home]');
            if (link) {
                e.preventDefault();
                window.location.href = link.href;
            }
        }
    });

});
