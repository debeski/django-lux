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
        // Tooltip Manager
        const tooltip = document.createElement('div');
        tooltip.className = 'ms-tooltip';
        document.body.appendChild(tooltip);

        function showTooltip(e) {
            const target = e.currentTarget;
            const text = target.getAttribute('data-ms-tooltip');
            if (!text) return;

            tooltip.innerText = text;
            const rect = target.getBoundingClientRect();
            
            tooltip.style.left = (rect.left + rect.width / 2) + 'px';
            tooltip.style.top = (rect.top - 10 - tooltip.offsetHeight) + 'px';
            
            // Adjust for positioning after text is set
            requestAnimationFrame(() => {
                tooltip.style.top = (rect.top - 8 - tooltip.offsetHeight) + 'px';
                tooltip.classList.add('show');
            });
        }

        function hideTooltip() {
            tooltip.classList.remove('show');
        }

        document.querySelectorAll('[data-ms-tooltip]').forEach(el => {
            el.addEventListener('mouseenter', showTooltip);
            el.addEventListener('mouseleave', hideTooltip);
            el.addEventListener('click', hideTooltip);
        });
    }
});
