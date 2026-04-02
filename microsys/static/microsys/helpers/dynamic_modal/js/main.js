/**
 * Microsys Universal Dynamic Modals
 * Handles loading combined tables and forms into a generic bootstrap modal.
 */

document.addEventListener('DOMContentLoaded', function() {
    if (window.__microDynamicModalsInitialized) return;
    window.__microDynamicModalsInitialized = true;

    const modalEl = document.getElementById('universalDynamicModal');
    if (!modalEl) return;

    const modalBody = document.getElementById('universalDynamicModalBody');
    const titleText = document.getElementById('dynamicModalTitleText');
    const footer = document.getElementById('universalDynamicModalFooter');
    
    // Hide footer since the form includes its own submit button
    if (footer) footer.style.display = 'none';

    let currentBaseUrl = '';

    // Initialize modal instance safely
    const dynamicModal = bootstrap.Modal.getOrCreateInstance(modalEl);

    // Explicitly handle all close buttons within this modal to ensure backdrop cleanup
    modalEl.addEventListener('click', function(e) {
        if (e.target.closest('[data-bs-dismiss="modal"]')) {
            e.preventDefault();
            dynamicModal.hide();
        }
    });

    // Cleanup backdrop and body classes on hide just in case
    modalEl.addEventListener('hide.bs.modal', function() {
        // Fix for "Blocked aria-hidden on an element because its descendant retained focus"
        // If the active element is inside the modal, blur it before the modal hides.
        if (modalEl.contains(document.activeElement)) {
            document.activeElement.blur();
        }
    });

    modalEl.addEventListener('hidden.bs.modal', function () {
        // Remove any lingering backdrops
        document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
        // Ensure body scrolling is restored
        document.body.classList.remove('modal-open');
        document.body.style.overflow = '';
        document.body.style.paddingRight = '';
    });

    // 1. Listen for clicks on buttons with data-dynamic-modal attribute
    document.body.addEventListener('click', function(e) {
        const trigger = e.target.closest('[data-dynamic-modal]');
        if (!trigger) return;

        e.preventDefault();
        
        const url = trigger.getAttribute('data-dynamic-modal');
        const title = trigger.getAttribute('data-modal-title') || 'Manage Records';
        
        currentBaseUrl = url;
        if (titleText) titleText.textContent = title;
        
        openModalAndLoad(url, trigger);
    });

    // Programmatic trigger (Context Menu / external integrations)
    document.body.addEventListener('micro:dynamic_modal:open', function(e) {
        const url = e.detail.data?.url || e.detail.action?.url;
        const title = e.detail.data?.title || e.detail.action?.title || 'تفاصيل';
        const trigger = e.detail.trigger || null;
        
        if (!url) return;
        currentBaseUrl = url;
        if (titleText) titleText.textContent = title;
        
        openModalAndLoad(url, trigger);
    });

    // 2. Load Content via AJAX
    function openModalAndLoad(url, trigger = null) {
        
        // Show loading state without changing size
        let existingOverlay = modalBody.querySelector('.dynamic-modal-overlay');
        if (!existingOverlay) {
            // If there's content, add an overlay to keep the size. If empty, just show simple loading.
            if (modalBody.innerHTML.trim() && !modalBody.innerHTML.includes('spinner-border')) {
                const overlay = document.createElement('div');
                overlay.className = 'dynamic-modal-overlay position-absolute top-0 start-0 w-100 h-100 bg-white d-flex align-items-center justify-content-center';
                overlay.style.zIndex = '1055';
                overlay.style.opacity = '0.7';
                
                // Spinner inside overlay
                overlay.innerHTML = `
                    <div class="spinner-border text-primary" role="status" style="width: 3rem; height: 3rem;">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                `;
                // Make sure modal body is positioned relative so overlay covers it
                modalBody.style.position = 'relative';
                modalBody.appendChild(overlay);
            } else {
                // Initial load, no content yet. Show simple spinner.
                modalBody.innerHTML = `
                    <div class="d-flex align-items-center justify-content-center w-100 p-5" style="min-height: 200px;">
                        <div class="spinner-border text-primary" role="status" style="width: 3rem; height: 3rem;">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                    </div>`;
            }
        }
        
        dynamicModal.show(trigger);

        fetch(url, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        })
        .then(data => {
            if (data.html) {
                modalBody.innerHTML = data.html;
                attachListeners();
                
                // Execute any inline scripts returned in the HTML payload
                const scripts = modalBody.querySelectorAll('script');
                scripts.forEach(oldScript => {
                    // Prevent re-executing core scripts that bind global events
                    if (oldScript.src && (
                        oldScript.src.includes('dynamic_modals.js') || 
                        oldScript.src.includes('context_menu/js/main.js') ||
                        oldScript.src.includes('context_menu/js/section_manager.js')
                    )) {
                        return;
                    }

                    const newScript = document.createElement('script');
                    // Copy attributes (especially `nonce` for CSP)
                    Array.from(oldScript.attributes).forEach(attr => newScript.setAttribute(attr.name, attr.value));
                    
                    if (oldScript.src) {
                        newScript.src = oldScript.src;
                    } else {
                        newScript.textContent = oldScript.textContent;
                    }
                    oldScript.parentNode.replaceChild(newScript, oldScript);
                });
            } else if (data.error) {
                showError(data.error);
            }
        })
        .catch(err => {
            console.error('Error loading modal content:', err);
            showError('Failed to load content. Please try again.');
        });
    }

    // 3. Attach Listeners to Table Rows (Edit & Delete) and Form Submit
    function attachListeners() {
        // Form interceptor
        const form = modalBody.querySelector('form');
        if (form) {
            form.addEventListener('submit', function(e) {
                e.preventDefault();
                submitForm(form);
            });
        }

        // Edit buttons
        const editBtns = modalBody.querySelectorAll('.dynamic-edit-btn');
        editBtns.forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                const pk = this.getAttribute('data-pk');
                if (pk) {
                    const editUrl = currentBaseUrl.endsWith('/') ? 
                        currentBaseUrl + pk + '/' : 
                        currentBaseUrl + '/' + pk + '/';
                    openModalAndLoad(editUrl);
                }
            });
        });

        // Delete buttons
        const delBtns = modalBody.querySelectorAll('.dynamic-delete-btn');
        delBtns.forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                const pk = this.getAttribute('data-pk');
                if (pk && confirm('Are you sure you want to delete this record?')) {
                    deleteRecord(pk);
                }
            });
        });

        // Back buttons (View Mode)
        const backBtns = modalBody.querySelectorAll('.dynamic-back-btn');
        backBtns.forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                openModalAndLoad(currentBaseUrl);
            });
        });

        // Initialize plugins if they exist
        if (window.flatpickr) {
            flatpickr(modalBody.querySelectorAll('.flatpickr'), {
                locale: 'ar',
                dateFormat: 'Y-m-d',
                allowInput: true,
            });
        }
    }

    // 4. Form Submission Logic
    function submitForm(form) {
        const submitBtn = form.querySelector('[type="submit"]');
        if (submitBtn) submitBtn.disabled = true;

        const formData = new FormData(form);
        const actionUrl = form.getAttribute('action') || currentBaseUrl;

        // Resolve absolute URL for action
        const fetchUrl = new URL(actionUrl, window.location.origin);

        fetch(fetchUrl, {
            method: 'POST',
            body: formData,
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                if (data.refresh_parent) {
                    window.location.reload();
                    return;
                }
                // Refresh the list and clear the form by reloading the base URL
                openModalAndLoad(currentBaseUrl);
            } else if (data.html) {
                // Form validation failed, render new HTML form with errors
                modalBody.innerHTML = data.html;
                attachListeners();
            } else {
                if (submitBtn) submitBtn.disabled = false;
                showError(data.error || 'Failed to save record.');
            }
        })
        .catch(err => {
            if (submitBtn) submitBtn.disabled = false;
            console.error('Error saving form:', err);
            showError('A network error occurred.');
        });
    }
    
    // 5. Delete Logic
    function deleteRecord(pk) {
        const deleteUrl = currentBaseUrl.endsWith('/') ? 
            currentBaseUrl + 'delete/' + pk + '/' : 
            currentBaseUrl + '/delete/' + pk + '/';
            
        // Must send CSRF token!
        let csrfToken = '';
        const csrfInput = modalBody.querySelector('input[name="csrfmiddlewaretoken"]');
        if (csrfInput) {
            csrfToken = csrfInput.value;
        } else {
            // Fallback to meta tag if present
            const metaCsrf = document.querySelector('meta[name="csrf-token"]');
            if (metaCsrf) csrfToken = metaCsrf.getAttribute('content');
            // Or try document cookie
            else {
                const name = 'csrftoken=';
                const decodedCookie = decodeURIComponent(document.cookie);
                const ca = decodedCookie.split(';');
                for(let i = 0; i <ca.length; i++) {
                    let c = ca[i];
                    while (c.charAt(0) == ' ') { c = c.substring(1); }
                    if (c.indexOf(name) == 0) { csrfToken = c.substring(name.length, c.length); break; }
                }
            }
        }

        fetch(deleteUrl, {
            method: 'POST',
            headers: { 
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken
            }
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                openModalAndLoad(currentBaseUrl);
            } else {
                alert(data.error || 'Failed to delete record.');
            }
        })
        .catch(err => {
            console.error('Error deleting record:', err);
            alert('A network error occurred.');
        });
    }

    function showError(msg) {
        modalBody.innerHTML = `
            <div class="text-center p-5 text-danger">
                <i class="bi bi-exclamation-circle display-1 mb-3"></i>
                <p>${msg}</p>
            </div>`;
    }

    // 6. Context Menu Integration (Catch events fired by auto-generated tables)
    modalEl.addEventListener('micro:record:edit', function(e) {
        if (!modalEl.classList.contains('show')) return;
        e.stopPropagation();
        
        const data = e.detail.data;
        if (!data || !data.id) return;
        
        const editUrl = currentBaseUrl.endsWith('/') ? 
            currentBaseUrl + data.id + '/' : 
            currentBaseUrl + '/' + data.id + '/';
        openModalAndLoad(editUrl);
    });

    modalEl.addEventListener('micro:record:delete', function(e) {
        if (!modalEl.classList.contains('show')) return;
        e.stopPropagation();
        
        const data = e.detail.data;
        if (!data || !data.id) return;
        
        if (confirm('Are you sure you want to delete this record (ID: ' + data.id + ')?')) {
            deleteRecord(data.id);
        }
    });

    modalEl.addEventListener('micro:record:view', function(e) {
        if (!modalEl.classList.contains('show')) return;
        e.stopPropagation();
        
        const data = e.detail.data;
        if (!data || !data.id) return;
        
        const viewUrl = currentBaseUrl.endsWith('/') ? 
            currentBaseUrl + data.id + '/?action=view' : 
            currentBaseUrl + '/' + data.id + '/?action=view';
        openModalAndLoad(viewUrl);
    });

});
