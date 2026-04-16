(function() {
    'use strict';

    // Configuration
    const STORAGE_PREFIX = 'microsys_autofill_';
    const TOGGLE_KEY = 'enable_prefill';
    const DEBUG = false; // Set to true for development

    function debugLog(...args) {
        if (DEBUG) console.log(...args);
    }

    /**
     * Initialize Autofill System
     */
    function initAutofill() {
        // 1. Check for autofillable context
        // Case A: Form with data-model-name (Sticky/Clone feature)
        const stickyForm = document.querySelector('form[data-model-name]');
        // Case B: Inputs with data-autofill-source (FK Autofill feature)
        const fkInputs = document.querySelectorAll('[data-autofill-source]');

        const hasAutofill = stickyForm || fkInputs.length > 0;

        if (!hasAutofill) return;

        // 2. Inject Toggle into Titlebar (if not present)
        injectToggle();

        const toggle = document.getElementById('autofillToggle');
        if (!toggle) return;

        // 3. Load State
        const isEnabled = localStorage.getItem(TOGGLE_KEY) === 'true';
        toggle.checked = isEnabled;

        // 4. Bind Toggle Events
        toggle.addEventListener('change', async function() {
            const enabled = this.checked;
            localStorage.setItem(TOGGLE_KEY, enabled);
            
            if (!enabled) {
                 // User requested: "disabling autofill toggle... should clear the fields".
                 debugLog("Autofill: Toggle OFF. Clearing all related fields.");
                 for (const input of fkInputs) {
                     const source = input.dataset.autofillSource;
                     if (source) {
                         const [app, model] = source.split('.');
                         try {
                             const data = await fetchModelDetails(app, model, 'empty_schema');
                             const form = input.closest('form');
                             if (data && form) populateForm(form, data);
                         } catch (e) {
                             console.error("Autofill: Error clearing fields on toggle off", e);
                         }
                     }
                 }
            } else {
                // Optional: Re-fill fields based on current selection
                fkInputs.forEach(input => {
                    if (input.value) {
                         // Dispatch event to trigger refill? 
                         // Or manually call handler? 
                         // Since delegation handles bubbling, dispatching event on input works.
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                });
            }
        });

        // 5. Initialize Features
        // We still support sticky form if it exists, check was done at start.
        if (stickyForm) initStickyForm(stickyForm, isEnabled);
        
        // Initialize FK Delegation
        // We pass inputs just for logic, but delegation is global.
        initFKAutofill(fkInputs, isEnabled);
    }

    /**
     * Inject Toggle Switch into Titlebar
     */
    function injectToggle() {
        if (document.getElementById('autofillToggle')) return;

        const titlebarContainer = document.querySelector('.titlebar .pe-2.d-flex.align-items-center');
        if (!titlebarContainer) return;

        // Bootstrap 5 Switch Markup
        const toggleHtml = `
            <div class="form-check form-switch d-flex align-items-center me-3 animate__animated animate__fadeIn" title="التعبئة التلقائية">
                <input class="form-check-input" type="checkbox" id="autofillToggle" style="cursor: pointer;">
                <label class="form-check-label ms-1 d-none d-md-inline small text-muted" for="autofillToggle" style="cursor: pointer;">تعبئة تلقائية</label>
            </div>
        `;

        // Prepend to the container (before Help/User buttons)
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = toggleHtml;
        titlebarContainer.insertBefore(tempDiv.firstElementChild, titlebarContainer.firstChild);
    }

    /**
     * Sticky Form Logic (Original Feature)
     */
    function initStickyForm(form, isEnabled) {
        const appLabel = form.dataset.appLabel;
        const modelName = form.dataset.modelName;

        if (!appLabel || !modelName) return;

        // Handle Submit
        form.addEventListener('submit', function() {
            if (localStorage.getItem(TOGGLE_KEY) === 'true') {
                 sessionStorage.setItem('microsys_last_submit_autofill', 'true');
            } else {
                 sessionStorage.removeItem('microsys_last_submit_autofill');
            }
        });

        // Run autofill if enabled
        if (isEnabled) {
            handleStickyAutofill(form);
        }
    }

    async function handleStickyAutofill(form) {
        const appLabel = form.dataset.appLabel;
        const modelName = form.dataset.modelName;
        const storageKey = `${STORAGE_PREFIX}${appLabel}_${modelName}`;
        
        // 1. Check for "Create & Add Another" flow via sessionStorage
        if (sessionStorage.getItem('microsys_last_submit_autofill') === 'true') {
            try {
                const lastEntry = await fetchLastEntry(appLabel, modelName);
                if (lastEntry && lastEntry._pk) {
                    // Update header/status to show we found something?
                    localStorage.setItem(storageKey, lastEntry._pk); // Save for future
                    populateForm(form, lastEntry);
                }
                sessionStorage.removeItem('microsys_last_submit_autofill');
            } catch (e) {
                console.error("Autofill: Failed to fetch last entry", e);
            }
            return;
        }

        // 2. Check localStorage (Sticky ID)
        const targetId = localStorage.getItem(storageKey);
        if (targetId) {
             try {
                const data = await fetchModelDetails(appLabel, modelName, targetId);
                populateForm(form, data);
            } catch (e) {
                console.warn("Autofill: ID invalid or not found:", targetId);
            }
        }
    }

    /**
     * FK Autofill Logic (New Feature)
     */
    function initFKAutofill(inputs, isEnabled) {
        // We use event delegation on document.body to handle:
        // 1. Elements dynamically added after load
        // 2. Event bubbling issues
        // 3. Simplifying listener logic
        
        debugLog("Autofill: Initializing Event Delegation for FK inputs.");

        const handleEvent = async function(e) {
            // Find the relevant element (self or parent)
            const target = e.target;
            
            // DEBUG: catch-all log
            // debugLog("Autofill: Global event", e.type, "on", target.tagName, target.name, target.className);

            const sourceEl = target.closest ? target.closest('[data-autofill-source]') : null;
            
            if (!sourceEl) return;

            // Check Toggle
            if (localStorage.getItem(TOGGLE_KEY) !== 'true') {
                return;
            }

            // debugLog(`Autofill: Delegated '${e.type}' captured on`, sourceEl.name || sourceEl.id, "Value:", sourceEl.value);

            const val = sourceEl.value;
            const source = sourceEl.dataset.autofillSource; 
            if (!source) return;
            
            const [app, model] = source.split('.');
            const form = sourceEl.closest('form');

            // Case: Clear fields if value is empty
            if (!val) {
                 debugLog("Autofill: Value cleared. Fetching empty schema.", sourceEl.name);
                 try {
                     // UI Feedback
                    if (sourceEl.parentElement) sourceEl.parentElement.classList.add('opacity-50');
                    
                    const data = await fetchModelDetails(app, model, 'empty_schema');
                    
                    if (data && form) {
                        populateForm(form, data);
                    }
                 } catch (err) {
                    console.error("Autofill error clearing fields:", err);
                 } finally {
                    if (sourceEl.parentElement) sourceEl.parentElement.classList.remove('opacity-50');
                 }
                 return; 
            }

            debugLog("Autofill: Fetching details for", source, "ID:", val);
            
            try {
                // UI Feedback
                if (sourceEl.parentElement) sourceEl.parentElement.classList.add('opacity-50');
                
                const data = await fetchModelDetails(app, model, val);
                debugLog("Autofill: Data received:", data);
                
                if (data && form) {
                    populateForm(form, data);
                }
            } catch (err) {
                console.error("Autofill: Error fetching details:", err);
            } finally {
                if (sourceEl.parentElement) sourceEl.parentElement.classList.remove('opacity-50');
            }
        };


        // Attach to Body
        document.body.addEventListener('change', handleEvent);
        document.body.addEventListener('input', handleEvent);
        
        // jQuery specific handling
        if (window.jQuery) {
            window.jQuery(document.body).on('select2:select', function(e) {
                handleEvent(e.originalEvent || e);
            });
        }
    }
    
    // ... rest of code without debug logs ...


    /**
     * API Helpers
     */
    async function fetchLastEntry(app, model) {
        const response = await fetch(`/sys/api/last-entry/${app}/${model}/`);
        if (!response.ok) throw new Error(response.statusText);
        return await response.json();
    }
    
    async function fetchModelDetails(app, model, pk) {
        const url = `/sys/api/details/${app}/${model}/${pk}/`;
        debugLog("Autofill: Calling API:", url);
        const response = await fetch(url);
        if (!response.ok) throw new Error(`API Error ${response.status}: ${response.statusText}`);
        return await response.json();
    }

    /**
     * Population Logic
     */
    function populateForm(form, data) {
        if (!data) return;

        debugLog("Autofill: Attempting to populate form with keys:", Object.keys(data));
        
        // Iterate over data and fill inputs
        for (const [key, value] of Object.entries(data)) {
            if (key.startsWith('_')) continue; // Skip metadata
            
            const input = form.querySelector(`[name="${key}"]`);
            if (input) {
                debugLog("Autofill: Match found! Setting", key, "to", value);
                
                // Determine field type
                if (input.type === 'checkbox') {
                    input.checked = !!value;
                } else if (input.type === 'radio') {
                    // Start logic for radio if needed
                } else {
                    input.value = value;
                }
                
                // Trigger change for dependencies (but avoid loops with simple checks if needed)
                // input.dispatchEvent(new Event('change', { bubbles: true }));
            } else {
                // Debug: Log missing matches to help user diagnose
                // debugLog("Autofill: No input found for key:", key);
            }
        }
    }

    // Run
    // Use DOMContentLoaded or run immediately if deferred
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAutofill);
    } else {
        initAutofill();
    }

})();
