document.addEventListener('DOMContentLoaded', function() {


    document.addEventListener('dlux:reset-password', function(e) {
        const eventData = e.detail.data;
        if (!eventData || !eventData.url) {
            return;
        }

        const modalEl = document.getElementById('resetPasswordModal');
        const form = document.getElementById('resetPasswordForm');

        if (modalEl && form) {
            const usernameInput = form.querySelector('input[name$="username"]');
            form.action = eventData.url;
            if (usernameInput && eventData.username) {
                usernameInput.value = eventData.username;
            }
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            modal.show();
        }
    });

    document.addEventListener('dlux:soft-delete', function(e) {
        const eventData = e.detail.data;
        if (!eventData || !eventData.url) {
            return;
        }

        const modalEl = document.getElementById('deleteModal');
        const form = document.getElementById('deleteForm');
        const nameSpan = document.getElementById('userName');

        if (modalEl && form) {
            form.action = eventData.url;
            if (nameSpan && eventData.name) {
                nameSpan.textContent = eventData.name;
            }
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            modal.show();
        }
    });

    // 1. Manage Scopes Button (Main page)
    const btnManageScopes = document.getElementById('btn-manage-scopes');
    if (btnManageScopes) {
        btnManageScopes.addEventListener('click', loadScopeManager);
    }

    // 2. Toggle Auto Scopes Switch
    const toggleAutoScopes = document.getElementById('toggleAutoScopes');
    if (toggleAutoScopes) {
        toggleAutoScopes.addEventListener('change', function(e) {
            const checkbox = e.target;
            const url = checkbox.dataset.url;
            const csrfToken = checkbox.dataset.csrf;
            if (!url || !csrfToken) return;
            
            fetch(url, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ target_enabled: checkbox.checked })
            })
            .then(response => response.json())
            .then(data => {
                if (!data.success) {
                    alert('فشل في تبديل الخاصية.');
                    checkbox.checked = !checkbox.checked;
                }
            })
            .catch(err => {
                console.error('Error:', err);
                checkbox.checked = !checkbox.checked;
            });
        });
    }

    // 3. Toggle Scopes Switch (Main page)
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

        scopeModalBody.addEventListener('dlux:scope:edit', function(e) {
            const url = e.detail?.data?.url || e.detail?.action?.data?.url;
            if (url) loadScopeForm(url);
        });

        scopeModalBody.addEventListener('dlux:scope:detail', function(e) {
            const url = e.detail?.data?.url || e.detail?.action?.data?.url;
            if (url) loadScopeForm(url);
        });

        scopeModalBody.addEventListener('dlux:scope:toggle-public-default', function(e) {
            const url = e.detail?.data?.url || e.detail?.action?.data?.url;
            if (url) postScopeAction(url);
        });

        scopeModalBody.addEventListener('dlux:scope:delete', function(e) {
            const url = e.detail?.data?.url || e.detail?.action?.data?.url;
            if (url) deleteScope(url);
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
        method: 'POST',
        headers: {
            'X-CSRFToken': getScopeCsrfToken(),
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const body = document.getElementById('scopeModalBody');
            if (body) {
                body.innerHTML = data.html;
            }
        } else {
            alert(formatScopeDeleteError(data));
        }
    })
    .catch(err => console.error('Error deleting scope:', err));
}

function formatScopeDeleteError(data) {
    let message = data?.error || 'Cannot delete this item.';
    const related = data?.related || {};
    const lines = [];
    Object.keys(related).forEach(function (label) {
        const items = related[label] || [];
        if (items.length) lines.push(`${label}: ${items.join(', ')}`);
    });
    if (lines.length) message += `\n\n${lines.join('\n')}`;
    return message;
}

function getScopeCsrfToken() {
    const token = document.querySelector('[name=csrfmiddlewaretoken]');
    if (token && token.value) return token.value;
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
}

function postScopeAction(url) {
    fetch(url, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getScopeCsrfToken(),
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        const body = document.getElementById('scopeModalBody');
        if (body && data.html) {
            body.innerHTML = data.html;
        }
    })
    .catch(err => console.error('Error applying scope action:', err));
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
