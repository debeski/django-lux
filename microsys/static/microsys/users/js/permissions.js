(function() {
    function initPermissionWidget() {
        // Master Checkbox Logic: App Level
        // Using event delegation on document body for dynamic content
    }

    // Attach to document for event delegation
    document.body.addEventListener('change', function(e) {
        // App Level Master
        if (e.target.matches('.app-master-checkbox')) {
            const isChecked = e.target.checked;
            const card = e.target.closest('.permissions-card');
            card.querySelectorAll('.permission-checkbox, .model-master-checkbox').forEach(cb => {
                if (cb.disabled) return;
                cb.checked = isChecked;
                cb.indeterminate = false;
            });
        }

        // Model Level Master
        if (e.target.matches('.model-master-checkbox')) {
            const isChecked = e.target.checked;
            const modelGroup = e.target.closest('.model-group');
            modelGroup.querySelectorAll('.permission-checkbox').forEach(cb => {
                if (cb.disabled) return;
                cb.checked = isChecked;
            });
            updateAppMasterStatus(e.target.closest('.permissions-card'));
        }

        // Individual Permission Checkbox
        if (e.target.matches('.permission-checkbox')) {
            updateModelMasterStatus(e.target.closest('.model-group'));
            updateAppMasterStatus(e.target.closest('.permissions-card'));
        }
    });

    // Delegate Click for toggling
    document.body.addEventListener('click', function(e) {
        const header = e.target.closest('.permissions-card-header');
        if (header) {
            if (e.target.closest('.prevent-toggle')) return;
            
            const targetId = header.getAttribute('data-bs-target');
            const target = document.querySelector(targetId);
            if (target) {
                const isCollapsed = !target.classList.contains('show');
                if (!isCollapsed) {
                    header.classList.add('collapsed');
                    bootstrap.Collapse.getOrCreateInstance(target).hide();
                } else {
                    header.classList.remove('collapsed');
                    bootstrap.Collapse.getOrCreateInstance(target).show();
                }
            }
        }
    });

    function updateModelMasterStatus(modelGroup) {
        if (!modelGroup) return;
        const master = modelGroup.querySelector('.model-master-checkbox');
        if (!master) return;
        const children = Array.from(modelGroup.querySelectorAll('.permission-checkbox')).filter(c => !c.disabled);
        const checkedCount = children.filter(c => c.checked).length;

        master.checked = checkedCount === children.length && children.length > 0;
        master.indeterminate = checkedCount > 0 && checkedCount < children.length;
    }

    function updateAppMasterStatus(card) {
        if (!card) return;
        const master = card.querySelector('.app-master-checkbox');
        if (!master) return;
        const children = Array.from(card.querySelectorAll('.permission-checkbox')).filter(c => !c.checked);
        const allChildren = Array.from(card.querySelectorAll('.permission-checkbox')).filter(c => !c.disabled);
        const checkedCount = allChildren.length - children.length;

        master.checked = checkedCount === allChildren.length && allChildren.length > 0;
        master.indeterminate = checkedCount > 0 && checkedCount < allChildren.length;
    }

    // Export sync functions to window just in case
    window.syncPermissionsStatus = function(container) {
        const root = container || document;
        root.querySelectorAll('.model-group').forEach(group => updateModelMasterStatus(group));
        root.querySelectorAll('.permissions-card').forEach(card => updateAppMasterStatus(card));
    };

    // Initial sync for whatever is present
    setTimeout(window.syncPermissionsStatus, 100);

})();

