document.addEventListener('DOMContentLoaded', function() {
    const userDetailModalBody = document.getElementById('userDetailModalBody');

    document.addEventListener('micro:view-user-details', function(e) {
        const detail = e.detail;
        const data = detail.data || detail.actionData?.data || detail.action?.data;
        const url = data?.url;

        if (!url) {
            return;
        }

        const modalEl = document.getElementById('userDetailModal');
        const modalBody = document.getElementById('userDetailModalBody');
        if (!modalEl || !modalBody) {
            return;
        }

        modalBody.innerHTML = `
            <div class="text-center p-5">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">${modalBody.dataset.loadingText || 'Loading...'}</span>
                </div>
            </div>`;

        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        modal.show();

        fetch(url, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(response => response.text())
        .then(html => {
            modalBody.innerHTML = html;
        })
        .catch(err => {
            console.error('Error loading user details:', err);
            modalBody.innerHTML = `
                <div class="text-center p-5 text-danger">
                    <i class="bi bi-exclamation-circle display-1 mb-3"></i>
                    <p>${modalBody.dataset.errorText || 'Error loading details.'}</p>
                </div>`;
        });
    });

    document.addEventListener('micro:reset-password', function(e) {
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

    document.addEventListener('micro:soft-delete', function(e) {
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

    document.addEventListener('click', function(e) {
        const printButton = e.target.closest('[data-ms-user-report-print]');
        if (!printButton) return;
        e.preventDefault();
        window.print();
    });

    function updateUserReportActivityPager(report, requestedPage) {
        const timeline = report.querySelector('[data-ms-user-report-activity]');
        const pager = report.querySelector('[data-ms-user-report-activity-pagination]');
        if (!timeline || !pager) {
            return;
        }

        const items = Array.from(timeline.querySelectorAll('[data-ms-user-report-activity-item]'));
        const pageSize = Math.max(parseInt(timeline.dataset.msUserReportPageSize || '8', 10), 1);
        const totalPages = Math.max(Math.ceil(items.length / pageSize), 1);
        const currentPage = Math.min(Math.max(requestedPage || parseInt(timeline.dataset.currentPage || '1', 10), 1), totalPages);

        timeline.dataset.currentPage = String(currentPage);
        items.forEach((item, index) => {
            const itemPage = Math.floor(index / pageSize) + 1;
            item.classList.toggle('d-none', itemPage !== currentPage);
        });

        const state = pager.querySelector('[data-ms-user-report-page-state]');
        if (state) {
            const pageLabel = state.dataset.pageLabel || '';
            const ofLabel = state.dataset.ofLabel || '';
            state.textContent = `${pageLabel} ${currentPage} ${ofLabel} ${totalPages}`.trim();
        }

        const previous = pager.querySelector('[data-ms-user-report-page-prev]');
        const next = pager.querySelector('[data-ms-user-report-page-next]');
        if (previous) previous.disabled = currentPage <= 1;
        if (next) next.disabled = currentPage >= totalPages;
    }

    function initUserReportActivityPagers(root) {
        root.querySelectorAll('[data-ms-user-report]').forEach(report => {
            if (report.dataset.activityPagerReady === 'true') {
                return;
            }
            report.dataset.activityPagerReady = 'true';
            updateUserReportActivityPager(report, 1);
        });
    }

    document.addEventListener('click', function(e) {
        const previous = e.target.closest('[data-ms-user-report-page-prev]');
        const next = e.target.closest('[data-ms-user-report-page-next]');
        if (!previous && !next) {
            return;
        }

        const report = e.target.closest('[data-ms-user-report]');
        const timeline = report?.querySelector('[data-ms-user-report-activity]');
        if (!report || !timeline) {
            return;
        }

        e.preventDefault();
        const currentPage = parseInt(timeline.dataset.currentPage || '1', 10);
        updateUserReportActivityPager(report, currentPage + (next ? 1 : -1));
    });

    initUserReportActivityPagers(document);
    const universalModalBody = document.getElementById('universalDynamicModalBody');
    if (universalModalBody) {
        new MutationObserver(() => initUserReportActivityPagers(universalModalBody)).observe(
            universalModalBody,
            { childList: true, subtree: true }
        );
    }

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
