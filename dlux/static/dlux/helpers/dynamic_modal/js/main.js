/**
 * Dlux Universal Dynamic Modals
 * Handles loading combined tables and forms into a generic bootstrap modal.
 */

document.addEventListener('DOMContentLoaded', function() {
    if (window.__dluxDynamicModalsInitialized) return;
    window.__dluxDynamicModalsInitialized = true;

    const MODAL_STATE_KEY = 'dlux.dynamicModalState';
    const modalEl = document.getElementById('universalDynamicModal');
    if (!modalEl) return;

    const modalBody = document.getElementById('universalDynamicModalBody');
    const titleText = document.getElementById('dynamicModalTitleText');
    const footer = document.getElementById('universalDynamicModalFooter');
    const DEFAULT_LOADING_MIN_HEIGHT = 320;
    const RELOCATED_FORM_ID = 'universalDynamicModalForm';

    function directModalChild(className) {
        return Array.from(modalBody.children).find(child => child.classList.contains(className)) || null;
    }

    // Custom/legacy AJAX fragments may still return their own Bootstrap modal
    // header, body, and footer. Fold that chrome into the universal shell so the
    // viewer sees one title, one scrolling body, and one persistent action footer.
    function normalizeModalChrome() {
        modalBody.removeAttribute('data-dlux-wizard-bound');
        const embeddedHeader = directModalChild('modal-header');
        const embeddedBody = directModalChild('modal-body');
        const embeddedFooter = directModalChild('modal-footer');

        if (embeddedHeader) {
            const embeddedTitle = embeddedHeader.querySelector('.modal-title');
            const normalizedTitle = embeddedTitle
                ? embeddedTitle.textContent.replace(/\s+/g, ' ').trim()
                : '';
            if (normalizedTitle && titleText) {
                titleText.textContent = normalizedTitle;
            }
            if (embeddedTitle) embeddedTitle.remove();
            embeddedHeader.querySelectorAll('.btn-close, [data-bs-dismiss="modal"]').forEach(control => {
                control.remove();
            });

            const hasContext = embeddedHeader.textContent.trim()
                || embeddedHeader.querySelector('img, svg, .badge');
            if (hasContext) {
                embeddedHeader.classList.remove('modal-header', 'border-0', 'pb-0');
                embeddedHeader.classList.add('dlux-modal-header-context', 'mb-3');
                if (embeddedBody) embeddedBody.prepend(embeddedHeader);
            } else {
                embeddedHeader.remove();
            }
        }

        if (embeddedFooter) {
            embeddedFooter.setAttribute('data-dlux-modal-footer', '');
        }

        if (embeddedBody) {
            embeddedBody.replaceWith(...Array.from(embeddedBody.childNodes));
        }
    }

    // Footer starts hidden; syncModalFooter() reveals it only when the loaded
    // content has a standard action bar to pin.
    function resetModalFooter() {
        if (!footer) return;
        footer.innerHTML = '';
        footer.style.display = 'none';
    }

    // Built-in action bars auto-detected for relocation:
    //  - .dlux-form-actions  → auto-form template + crispy auto-helper
    //  - .dlux-setup-wizard-actions → System Settings wizard FormActions
    //  - .dlux-modal-form-actions   → _build_submit_actions / _build_wizard_actions
    const BUILTIN_ACTION_SELECTOR =
        '.dlux-form-actions, .dlux-setup-wizard-actions, .dlux-modal-form-actions';

    // Dev opt-in: put `data-dlux-modal-footer` on ANY container in a custom modal
    // template / options view to have it pinned into the sticky footer. It takes
    // priority over the built-in bars. For custom buttons that need their own JS,
    // bind via document-level delegation (the element is moved out of the modal body)
    // or rely on the `form=` association added below for submit buttons.
    const DEV_FOOTER_SELECTOR = '[data-dlux-modal-footer]';

    // Relocate an action bar into the sticky modal footer so it stays on screen while
    // the body scrolls. Buttons keep working: submit buttons are re-associated to the
    // form via the `form=` attribute (which still fires the form's submit event the JS
    // intercepts), and the cancel/back button keeps the click listener attached earlier
    // in attachListeners() (moving a node preserves its listeners).
    //
    // Resolution order:
    //  1. an explicit [data-dlux-modal-footer] container (dev opt-in), else
    //  2. the first built-in action bar.
    // If nothing matches (tables / detail / dev-custom with no marker), the
    // footer stays hidden.
    function syncModalFooter() {
        if (!footer) return;
        resetModalFooter();

        const actions = modalBody.querySelector(DEV_FOOTER_SELECTOR)
            || modalBody.querySelector(BUILTIN_ACTION_SELECTOR);
        if (!actions) return;

        const form = actions.closest('form') || modalBody.querySelector('form');
        if (form) {
            if (!form.id) form.id = RELOCATED_FORM_ID;
            actions.querySelectorAll('button').forEach(btn => {
                if (!btn.hasAttribute('form')) btn.setAttribute('form', form.id);
            });
        }

        if (actions.classList.contains('modal-footer')) {
            footer.append(...Array.from(actions.childNodes));
            actions.remove();
        } else {
            footer.appendChild(actions);
        }
        footer.style.display = '';
    }

    resetModalFooter();

    let currentBaseUrl = '';
    let activeLoadToken = 0;

    function persistModalState() {
        if (!currentBaseUrl) {
            return;
        }
        try {
            sessionStorage.setItem(MODAL_STATE_KEY, JSON.stringify({
                url: currentBaseUrl,
                title: titleText ? titleText.textContent : '',
            }));
        } catch (error) {
            console.warn('Failed to persist dynamic modal state:', error);
        }
    }

    function clearModalState() {
        try {
            sessionStorage.removeItem(MODAL_STATE_KEY);
        } catch (error) {
            console.warn('Failed to clear dynamic modal state:', error);
        }
    }

    window.persistCurrentDynamicModalState = function() {
        persistModalState();
    };

    function hasUsablePreviousFallback() {
        return Array.from(modalBody.childNodes).some(node => {
            if (node.nodeType === Node.TEXT_NODE) {
                return node.textContent.trim().length > 0;
            }
            if (node.nodeType !== Node.ELEMENT_NODE) {
                return false;
            }
            return !node.classList.contains('dynamic-modal-overlay')
                && !node.classList.contains('dynamic-modal-loading-shell');
        });
    }

    function skeletonBlock(width, height = '1rem') {
        return `<span aria-hidden="true" class="d-block rounded" style="width: ${width}; height: ${height}; background: rgba(108, 117, 125, 0.22);"></span>`;
    }

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
        activeLoadToken += 1;
        // Remove any lingering backdrops
        document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
        // Ensure body scrolling is restored
        document.body.classList.remove('modal-open');
        document.body.style.overflow = '';
        document.body.style.paddingRight = '';
        modalBody.style.minHeight = '';
        resetModalFooter();
        clearModalState();
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

    // Programmatic trigger (Context Menu / global search / external integrations).
    // Bound to `document`, not `document.body`: an event dispatched directly on
    // `document` never reaches body (bubbling only travels child → parent), so a
    // body-bound listener silently ignored those callers. Element-dispatched
    // bubbling events still arrive here, so this is strictly more permissive.
    document.addEventListener('dlux:dynamic_modal:open', function(e) {
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
        const loadToken = activeLoadToken + 1;
        activeLoadToken = loadToken;

        // New content is coming — clear any pinned footer from the previous view.
        resetModalFooter();

        const hasPreviousFallback = hasUsablePreviousFallback();

        if (hasPreviousFallback) {
            const overlay = document.createElement('div');
            overlay.className = 'dynamic-modal-overlay position-absolute top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center';
            overlay.style.zIndex = '1055';
            overlay.style.background = 'var(--bs-body-bg, #fff)';
            overlay.style.opacity = '0.96';
            overlay.innerHTML = `
                <div class="spinner-border text-primary" role="status" style="width: 3rem; height: 3rem;">
                    <span class="visually-hidden">Loading...</span>
                </div>
            `;
            modalBody.style.position = 'relative';
            modalBody.appendChild(overlay);
        } else {
            modalBody.style.position = '';
            modalBody.style.minHeight = `${DEFAULT_LOADING_MIN_HEIGHT}px`;
            modalBody.innerHTML = `
                <div class="dynamic-modal-loading-shell w-100 p-4" style="min-height: ${DEFAULT_LOADING_MIN_HEIGHT}px;">
                    <div class="d-flex justify-content-between align-items-center mb-4">
                        ${skeletonBlock('42%', '1.4rem')}
                        ${skeletonBlock('18%', '1.1rem')}
                    </div>
                    <div class="row g-3">
                        <div class="col-12 col-md-6 d-grid gap-2">${skeletonBlock('34%', '0.75rem')}${skeletonBlock('100%', '2.4rem')}</div>
                        <div class="col-12 col-md-6 d-grid gap-2">${skeletonBlock('36%', '0.75rem')}${skeletonBlock('100%', '2.4rem')}</div>
                        <div class="col-12 col-md-6 d-grid gap-2">${skeletonBlock('28%', '0.75rem')}${skeletonBlock('86%', '2.4rem')}</div>
                        <div class="col-12 col-md-6 d-grid gap-2">${skeletonBlock('26%', '0.75rem')}${skeletonBlock('72%', '2.4rem')}</div>
                    </div>
                    <div class="d-flex align-items-center justify-content-center mt-4">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                    </div>
                </div>
            `;
        }
        
        // Open at the viewer's active modal-size preference so the dialog is the
        // correct width from the first frame — never inheriting a stale
        // `data-dlux-modal-size` left on <body> by a settings-form live preview or
        // a previously opened modal. Width is driven by the body attribute + CSS.
        if (window.USER_PREFS && window.USER_PREFS.modal_size) {
            document.body.dataset.dluxModalSize = window.USER_PREFS.modal_size;
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
            if (loadToken !== activeLoadToken) return;
            if (data.html) {
                modalBody.style.minHeight = '';
                modalBody.innerHTML = data.html;
                normalizeModalChrome();
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
            if (loadToken !== activeLoadToken) return;
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
        if (window.Datepicker) {
            if (typeof window.initDluxDatepickers === 'function') {
                window.initDluxDatepickers(modalBody);
            } else {
                modalBody.querySelectorAll('.dlux-datepicker, .flatpickr').forEach(input => {
                    if (input.dataset.dluxDatepickerReady === 'true') {
                        return;
                    }
                    input.dataset.dluxDatepickerReady = 'true';
                    new Datepicker(input, {
                        format: 'yyyy-mm-dd',
                        autohide: true,
                        buttonClass: 'btn',
                    });
                });
            }
        }

        // Pin the standard action bar to the sticky footer (must run last, after the
        // back/edit/delete listeners are attached so moving the bar keeps them).
        syncModalFooter();
    }

    // 4. Form Submission Logic
    function submitForm(form) {
        // The submit button may have been relocated into the sticky footer
        // (associated back via the form= attribute), so look there too.
        const submitBtn = form.querySelector('[type="submit"]')
            || (footer && footer.querySelector('[type="submit"]'));
        // Shared loading-button spinner for the lifetime of the POST. Falls back
        // to a plain disable if the helper somehow isn't loaded.
        const loadingButton = window.DluxLoadingButton;
        const submitHandle = (submitBtn && loadingButton)
            ? loadingButton.start(submitBtn, { keepText: true })
            : null;
        if (submitBtn && !submitHandle) submitBtn.disabled = true;
        const releaseSubmit = () => {
            if (submitHandle) submitHandle.stop();
            else if (submitBtn) submitBtn.disabled = false;
        };

        const formData = new FormData(form);
        const actionUrl = form.getAttribute('action') || currentBaseUrl;

        // Resolve absolute URL for action
        const fetchUrl = new URL(actionUrl, window.location.origin);

        fetch(fetchUrl, {
            method: 'POST',
            body: formData,
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(res => res.text().then(text => {
            let data = null;
            try {
                data = text ? JSON.parse(text) : {};
            } catch (err) {
                data = {
                    success: false,
                    error: res.ok ? 'Invalid server response.' : `Request failed with HTTP ${res.status}.`
                };
            }
            if (!res.ok && data && !data.error) {
                data.error = `Request failed with HTTP ${res.status}.`;
            }
            return data;
        }))
        .then(data => {
            if (data.success) {
                if (data.add_more) {
                    // "Save and add more": reload the page so the parent table reflects
                    // the new record (preserving the current URL/query), then reopen this
                    // modal with a fresh form via the persisted modal state.
                    persistModalState();
                    window.location.reload();
                    return;
                }
                if (data.refresh_parent) {
                    clearModalState();
                    window.location.reload();
                    return;
                }
                // Refresh the list and clear the form by reloading the base URL
                openModalAndLoad(currentBaseUrl);
            } else if (data.html) {
                // Form validation failed: render the new HTML form with errors.
                // syncModalFooter()/resetModalFooter() rebuild the footer from the
                // fresh markup, discarding this (busy) button — no restore needed.
                modalBody.innerHTML = data.html;
                normalizeModalChrome();
                attachListeners();
            } else {
                releaseSubmit();
                showError(data.error || 'Failed to save record.');
            }
        })
        .catch(err => {
            releaseSubmit();
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
        modalBody.style.minHeight = '';
        modalBody.innerHTML = `
            <div class="text-center p-5 text-danger">
                <i class="bi bi-exclamation-circle display-1 mb-3"></i>
                <p>${msg}</p>
            </div>`;
    }

    // 6. Context Menu Integration (Catch events fired by auto-generated tables)
    modalEl.addEventListener('dlux:record:edit', function(e) {
        if (!modalEl.classList.contains('show')) return;
        e.stopPropagation();
        
        const data = e.detail.data;
        if (!data || !data.id) return;
        
        const editUrl = currentBaseUrl.endsWith('/') ? 
            currentBaseUrl + data.id + '/' : 
            currentBaseUrl + '/' + data.id + '/';
        openModalAndLoad(editUrl);
    });

    modalEl.addEventListener('dlux:record:delete', function(e) {
        if (!modalEl.classList.contains('show')) return;
        e.stopPropagation();
        
        const data = e.detail.data;
        if (!data || !data.id) return;
        
        if (confirm('Are you sure you want to delete this record (ID: ' + data.id + ')?')) {
            deleteRecord(data.id);
        }
    });

    modalEl.addEventListener('dlux:record:view', function(e) {
        if (!modalEl.classList.contains('show')) return;
        e.stopPropagation();
        
        const data = e.detail.data;
        if (!data || !data.id) return;
        
        const viewUrl = currentBaseUrl.endsWith('/') ? 
            currentBaseUrl + data.id + '/?action=view' : 
            currentBaseUrl + '/' + data.id + '/?action=view';
        openModalAndLoad(viewUrl);
    });

    try {
        const savedState = JSON.parse(sessionStorage.getItem(MODAL_STATE_KEY) || 'null');
        if (savedState && savedState.url) {
            currentBaseUrl = savedState.url;
            if (titleText && savedState.title) {
                titleText.textContent = savedState.title;
            }
            openModalAndLoad(savedState.url);
        }
    } catch (error) {
        clearModalState();
    }

    // First-login Initial User Setup: auto-open its dynamic modal once (unless another
    // modal is being restored from saved state).
    try {
        const autoTrigger = document.querySelector('[data-dynamic-modal][data-dlux-auto-open]');
        let hasSavedModal = false;
        try {
            const st = JSON.parse(sessionStorage.getItem(MODAL_STATE_KEY) || 'null');
            hasSavedModal = !!(st && st.url);
        } catch (e) { hasSavedModal = false; }
        if (autoTrigger && !hasSavedModal) {
            autoTrigger.click();
        }
    } catch (e) { /* no-op */ }

    // Initial User Setup "Skip for now": POST skip=1 to mark the profile configured, then reload.
    document.body.addEventListener('click', function(e) {
        const skipBtn = e.target.closest('[data-dlux-skip-setup]');
        if (!skipBtn) return;
        e.preventDefault();
        const url = skipBtn.getAttribute('data-url');
        const form = skipBtn.closest('form');
        const csrf = form ? form.querySelector('[name=csrfmiddlewaretoken]') : null;
        const body = new FormData();
        body.append('skip', '1');
        if (csrf) body.append('csrfmiddlewaretoken', csrf.value);
        skipBtn.disabled = true;
        fetch(url, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' }, body: body })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Skip request failed (HTTP ' + response.status + ').');
                }
                // The profile is now marked configured server-side. Clear any persisted
                // modal state so the reloaded page does not re-open onboarding.
                clearModalState();
                window.location.reload();
            })
            .catch(function () {
                // Never blindly reload on failure: the profile was not marked configured,
                // so a reload would re-open this modal in a loop. Re-enable the button so
                // the user can retry (or use Save) instead.
                skipBtn.disabled = false;
            });
    });

});
