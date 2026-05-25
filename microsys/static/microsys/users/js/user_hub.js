/* user_dropdown.js */
document.addEventListener('DOMContentLoaded', function() {
    const trigger = document.getElementById('ms-user-dropdown-trigger');
    const card = document.getElementById('ms-user-dropdown-card');

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

});
