document.addEventListener('DOMContentLoaded', function() {
    // 1. Manage Scopes Button (Main page)
    const btnManageScopes = document.getElementById('btn-manage-scopes');
    if (btnManageScopes) {
        btnManageScopes.addEventListener('click', loadScopeManager);
    }

    // 2. Toggle Scopes Switch (Main page)
    const toggleScopes = document.getElementById('toggleScopes');
    if (toggleScopes) {
        toggleScopes.addEventListener('change', handleToggleScopes);
    }

    // Event Delegation for Scope Modal content (loaded via AJAX)
    const scopeModalBody = document.getElementById('scopeModalBody');
    if (scopeModalBody) {
        scopeModalBody.addEventListener('click', function(e) {
            // Load Scope Form Buttons (including Back, Add, Edit)
            const loadBtn = e.target.closest('.js-load-scope-form');
            if (loadBtn) {
                e.preventDefault();
                const url = loadBtn.dataset.url;
                if (url) loadScopeForm(url);
                return;
            }

            // Delete Scope Buttons (if any)
            const deleteBtn = e.target.closest('.js-delete-scope');
            if (deleteBtn) {
                e.preventDefault();
                const url = deleteBtn.dataset.url;
                if (url) deleteScope(url);
                return;
            }
        });
    }
});

// Handle Scope Form Submission (delegated to document for dynamic forms)
document.addEventListener('submit', function(e) {
    if (e.target.matches('#scopeForm')) {
        e.preventDefault();
        const url = e.target.dataset.url;
        if (url) submitScopeForm(e.target, url);
    }
});

function loadScopeManager() {
    const modalEl = document.getElementById('scopeModal');
    if (modalEl) {
        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        modal.show();
        
        const btn = document.getElementById('btn-manage-scopes');
        const url = btn.dataset.url; // URL provided in data-url attribute
        if (url) loadScopeForm(url);
    }
}

function loadScopeForm(url) {
    if (!url) return;
    
    fetch(url, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
    .then(response => response.json())
    .then(data => {
        const body = document.getElementById('scopeModalBody');
        if (body) {
            body.innerHTML = data.html;
        }
    })
    .catch(err => console.error('Error loading content:', err));
}

function submitScopeForm(form, url) {
    const formData = new FormData(form);

    fetch(url, {
        method: 'POST',
        body: formData,
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
        }
    })
    .then(response => response.json())
    .then(data => {
        const body = document.getElementById('scopeModalBody');
        if (body) {
            body.innerHTML = data.html;
        }
    })
    .catch(err => console.error('Error submitting form:', err));
}

function deleteScope(url) {
    if (!confirm('هل أنت متأكد من الحذف؟')) return; // Basic confirmation

    fetch(url, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const body = document.getElementById('scopeModalBody');
            if (body) {
                body.innerHTML = data.html;
            }
        }
    })
    .catch(err => console.error('Error deleting scope:', err));
}

function handleToggleScopes(e) {
    const checkbox = e.target;
    const url = checkbox.dataset.url; 
    const csrfToken = checkbox.dataset.csrf; 

    if (!url || !csrfToken) {
        console.error('Missing URL or CSRF token for toggle scopes');
        return;
    }

    // If Activating (checking the box)
    if (checkbox.checked) {
        e.preventDefault(); // Stop immediate change
        checkbox.checked = false; // Revert visually
        
        const warningModal = bootstrap.Modal.getOrCreateInstance(document.getElementById('scopeWarningModal'));
        warningModal.show();

        // Handle Confirmation
        const confirmBtn = document.getElementById('confirmScopeActivation');
        // Remove previous listeners to avoid duplicates if opened multiple times
        const newConfirmBtn = confirmBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
        
        newConfirmBtn.addEventListener('click', function() {
            warningModal.hide();
            performScopeToggle(url, csrfToken, checkbox, true);
        });

    } else {
        // Deactivating - proceed normally (or add another warning if needed, but per request only activation)
        performScopeToggle(url, csrfToken, checkbox, false);
    }
}

function performScopeToggle(url, csrfToken, checkbox, targetState) {
    fetch(url, {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ target_enabled: targetState })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            location.reload(); 
        } else {
            alert(data.error || 'فشل في تبديل حالة النطاقات.');
            checkbox.checked = !targetState; // Revert to original state on failure
        }
    })
    .catch(err => {
        console.error('Error:', err);
        alert('حدث خطأ في الاتصال بالخادم. يرجى المحاولة مرة أخرى.');
        checkbox.checked = !targetState; // Revert
    });
}
