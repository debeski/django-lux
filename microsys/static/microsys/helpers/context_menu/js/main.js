/**
 * Micro Context Menu
 * A generic, data-driven context menu for the MicroSys ecosystem.
 */

(function() {
    'use strict';

    // Namespace
    window.MicroContextMenu = window.MicroContextMenu || {};

    // Internal State
    const LONG_PRESS_DURATION = 500; // ms
    let pressTimer = null;
    let currentTarget = null;
    let menuElement = null;
    let activeActions = [];

    // Initialize
    document.addEventListener('DOMContentLoaded', init);

    function init() {
        if (window.__microContextMenuInitialized) return;
        window.__microContextMenuInitialized = true;

        // Create Menu DOM if not exists
        if (!document.getElementById('microContextMenu')) {
            createMenuDOM();
        }
        menuElement = document.getElementById('microContextMenu');

        // Global Event Delegation for Context Menu
        document.addEventListener('contextmenu', handleGlobalContextMenu);
        
        // Mobile Long Press Delegation
        document.addEventListener('touchstart', handleGlobalTouchStart, { passive: false });
        document.addEventListener('touchend', handleGlobalTouchEnd);
        document.addEventListener('touchcancel', handleGlobalTouchEnd);
        document.addEventListener('touchmove', handleGlobalTouchEnd);

        // Close menu on interaction
        document.addEventListener('click', hideMenu);
        document.addEventListener('scroll', hideMenu, { passive: true });
        
        // Handle Menu Action Clicks
        menuElement.addEventListener('click', handleActionClick);

        // Global Double Click for "Quick Actions" (View)
        document.addEventListener('dblclick', handleGlobalDoubleClick);

        // Initialize Subsection Logic (Legacy/Specific Support)
        initSubsectionLogic();
    }

    function createMenuDOM() {
        const div = document.createElement('div');
        div.id = 'microContextMenu';
        div.className = 'context-menu'; // Uses existing CSS class
        div.style.display = 'none';
        document.body.appendChild(div);
    }

    // ============================================================
    // Event Handlers
    // ============================================================

    function handleGlobalContextMenu(e) {
        const target = e.target.closest('[data-micro-context]');
        if (!target) return;

        e.preventDefault();
        e.stopPropagation();
        
        currentTarget = target;
        openMenu(target, e.clientX, e.clientY);
    }

    function handleGlobalDoubleClick(e) {
        const target = e.target.closest('[data-micro-context]');
        if (!target) return;

        const actions = getActionsForTarget(target);
        // Constraint: Only execute if action explicitly has dblclick: true
        const quickAction = actions.find(a => a.dblclick === true);

        if (quickAction) {
            e.preventDefault();
            // Execute the action
            if (quickAction.url) {
                window.location.href = quickAction.url;
            } else if (quickAction.action || quickAction.event) {
                 // Dispatch event if it's an event-based action
                 const eventName = quickAction.action || quickAction.event;
                 const event = new CustomEvent(eventName, {
                    bubbles: true,
                    detail: { 
                        originalTarget: target, 
                        action: quickAction,
                        data: quickAction.data 
                    }
                });
                document.body.dispatchEvent(event);
            }
        }
    }

    function handleGlobalTouchStart(e) {
        const target = e.target.closest('[data-micro-context]');
        if (!target) return;

        currentTarget = target;
        // Visual feedback
        target.classList.add('context-pressing');

        pressTimer = setTimeout(() => {
            if (navigator.vibrate) navigator.vibrate(50);
            const touch = e.touches[0];
            openMenu(target, touch.clientX, touch.clientY);
        }, LONG_PRESS_DURATION);
    }

    function handleGlobalTouchEnd(e) {
        if (pressTimer) {
            clearTimeout(pressTimer);
            pressTimer = null;
        }
        if (currentTarget) {
            currentTarget.classList.remove('context-pressing');
        }
    }

    // ============================================================
    // Menu Logic
    // ============================================================

    function openMenu(target, x, y) {
        // 1. Get Actions
        activeActions = getActionsForTarget(target);
        if (!activeActions || activeActions.length === 0) return;

        // 2. Render Actions
        renderMenu(activeActions);

        // 3. Position and Show
        menuElement.style.display = 'block';
        menuElement.classList.add('show');
        
        // Position logic
        menuElement.style.left = `${x}px`;
        menuElement.style.top = `${y}px`;

        // Boundary check
        const rect = menuElement.getBoundingClientRect();
        if (rect.right > window.innerWidth) {
            menuElement.style.left = `${window.innerWidth - rect.width - 10}px`;
        }
        if (rect.bottom > window.innerHeight) {
            menuElement.style.top = `${window.innerHeight - rect.height - 10}px`;
        }
    }

    function hideMenu() {
        if (menuElement) {
            menuElement.classList.remove('show');
            menuElement.style.display = 'none';
        }
    }

    function getActionsForTarget(target) {
        // Option 1: Inline JSON
        if (target.dataset.microActions) {
            try {
                return JSON.parse(target.dataset.microActions);
            } catch (e) {
                console.warn('MicroContextMenu: Invalid JSON in data-micro-actions', e);
                return [];
            }
        }
        // Option 2: ID Reference to Script Tag (for large menus)
        if (target.dataset.microActionsId) {
            const el = document.getElementById(target.dataset.microActionsId);
            if (el) {
                try {
                    return JSON.parse(el.textContent);
                } catch (e) {
                    console.warn('MicroContextMenu: Invalid JSON in script block', e);
                }
            }
        }
        // Option 3: Legacy/Fallback (Subsections)
        if (target.classList.contains('subsection-checkbox-label')) {
            return getSubsectionActions(target);
        }
        
        return [];
    }

    function renderMenu(actions) {
        menuElement.innerHTML = '';

        actions.forEach(action => {
            if (action.type === 'divider') {
                const div = document.createElement('div');
                div.className = 'context-menu-divider';
                menuElement.appendChild(div);
                return;
            }

            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = `context-menu-item ${action.cls || ''}`;
            if (action.textClass) btn.classList.add(action.textClass);
            
            // Icon
            let iconHtml = '';
            if (action.icon) {
                iconHtml = `<i class="${action.icon}"></i> `;
            }

            btn.innerHTML = `${iconHtml}${action.label}`;
            
            // Store action data on button for click handler
            btn.dataset.actionIndex = actions.indexOf(action);
            
            menuElement.appendChild(btn);
        });
    }

    function handleActionClick(e) {
        const btn = e.target.closest('.context-menu-item');
        if (!btn) return;

        const index = btn.dataset.actionIndex;
        const action = activeActions[index];
        
        if (!action) return;

        executeAction(action, currentTarget);
        hideMenu();
    }

    function executeAction(action, target) {
        // 1. URL Navigation
        if (action.type === 'url' || action.url) {
            if (action.confirm && !confirm(action.confirm)) return;
            window.location.href = action.url;
        }
        // 2. Form Submission (POST)
        else if (action.type === 'form') {
            if (action.confirm && !confirm(action.confirm)) return;
            submitForm(action.url, action.data);
        }
        // 3. Event Dispatch (for custom JS handling)
        else if (action.type === 'event' || action.event) {
            const eventName = action.event;
            const event = new CustomEvent(eventName, {
                bubbles: true,
                detail: {
                    originalTarget: target,
                    action: action,
                    data: action.data
                }
            });
            target.dispatchEvent(event);
        }
        // 4. Function Call (via name)
        else if (action.type === 'function') {
            // Need to parse function name "MyObj.func"
            // This is unsafe if not careful, better use events.
            // Skipping for now unless requested.
        }
    }

    function submitForm(url, data) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = url;
        
        // Add CSRF
        const csrf = getCookie('csrftoken') || document.querySelector('[name=csrfmiddlewaretoken]')?.value;
         if (csrf) {
            const inp = document.createElement('input');
            inp.type = 'hidden';
            inp.name = 'csrfmiddlewaretoken';
            inp.value = csrf;
            form.appendChild(inp);
        }

        if (data) {
            for (const [key, value] of Object.entries(data)) {
                const inp = document.createElement('input');
                inp.type = 'hidden';
                inp.name = key;
                inp.value = value;
                form.appendChild(inp);
            }
        }
        
        document.body.appendChild(form);
        form.submit();
        document.body.removeChild(form);
    }
    
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                // Does this cookie string begin with the name we want?
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // ============================================================
    // Legacy / Specific Logic (Subsections)
    // ============================================================
    
    // Helper to generate actions for the old subsection system
    function getSubsectionActions(target) {
        const isLocked = target.dataset.locked === 'true';
        // Check if there is specific logic in translations for "Edit" etc
        // For now hardcoding or using what was there.
        // We can check if a translation object exists globally.
        const ms_trans = window.MS_TRANS || {}; 
        
        const actions = [
            {
                label: ms_trans.edit_label || 'تعديل',
                icon: 'bi bi-pencil',
                type: 'event',
                event: 'micro:subsection:edit'
            },
            { type: 'divider' },
            {
                label: ms_trans.delete_label || 'حذف',
                icon: 'bi bi-trash',
                textClass: 'text-danger',
                type: 'event',
                event: 'micro:subsection:delete',
                disabled: isLocked
            }
        ];
        return actions;
    }

    // Initialize the specific logic for Subsections (Inline Editing)
    function initSubsectionLogic() {
        // Listen for the events we dispatch
        document.body.addEventListener('micro:subsection:edit', function(e) {
            const target = e.detail.originalTarget;
            handleSubsectionEdit(target);
        });

        document.body.addEventListener('micro:subsection:delete', function(e) {
            const target = e.detail.originalTarget;
            handleSubsectionDelete(target);
        });

        // Inline Add Button Helper (Keep existing logic)
        document.body.addEventListener('click', function(e) {
            const btn = e.target.closest('.add-subsection-btn');
            if (btn) {
                handleInlineAdd(e, btn);
            }
        });
    }

    // Ported Logic for Subsection Inline Edit
    function handleSubsectionEdit(currentTarget) {
        const subId = currentTarget.dataset.subId;
        const subName = currentTarget.dataset.subName;
        
        // Find CSRF from add button
        const container = currentTarget.closest('.d-flex');
        const addBtn = container ? container.querySelector('.add-subsection-btn') : document.querySelector('.add-subsection-btn');
        const csrfToken = addBtn ? addBtn.dataset.csrf : '';

        // UI Transformation
        const label = currentTarget;
        const checkboxId = label.getAttribute('for');
        const checkbox = document.getElementById(checkboxId);
        
        label.style.display = 'none';
        checkbox.style.display = 'none';

        const input = document.createElement('input');
        input.type = 'text';
        input.value = subName;
        input.className = 'form-control textinput pt-1 d-inline-block';
        input.style.width = Math.max(subName.length * 10 + 50, 150) + 'px';
        input.dir = 'rtl';
        input.dataset.originalName = subName;

        label.parentNode.insertBefore(input, label.nextSibling);
        input.focus();

        const finishEdit = (save) => {
            if (input.parentNode) {
                if (save) {
                    saveEditSubsection(input, subId, csrfToken, label, checkbox, addBtn);
                } else {
                    input.remove();
                    label.style.display = '';
                    checkbox.style.display = '';
                }
            }
        };

        input.addEventListener('keydown', function(ev) {
            if (ev.key === 'Enter') {
                ev.preventDefault();
                finishEdit(true);
            } else if (ev.key === 'Escape') {
                finishEdit(false);
            }
        });

         input.addEventListener('blur', function() {
            if (input.value.trim() && input.value.trim() !== subName) {
                finishEdit(true);
            } else {
                finishEdit(false);
            }
        });
    }

    function saveEditSubsection(input, subId, csrfToken, label, checkbox, addBtn) {
       if (input.dataset.saving) return;
       const newName = input.value.trim();
       if (!newName || newName === input.dataset.originalName) {
           input.remove();
           label.style.display = '';
           checkbox.style.display = '';
           return;
       }

       input.dataset.saving = 'true';
       input.disabled = true;

       const formData = new FormData();
       formData.append('name', newName);
       formData.append('csrfmiddlewaretoken', csrfToken);

       // Build Query
       let queryParams = '';
       if (addBtn) {
           const queryParts = [
               `model=${addBtn.dataset.childModel}`,
               `parent=${addBtn.dataset.parentModel}`,
           ];
           if (addBtn.dataset.parentId) queryParts.push(`parent_id=${addBtn.dataset.parentId}`);
           if (addBtn.dataset.parentField) queryParts.push(`parent_field=${addBtn.dataset.parentField}`);
           queryParams = `?${queryParts.join('&')}`;
       }
       
       const editUrlTemplate = addBtn ? addBtn.dataset.editUrlTemplate : '';
       const editUrl = editUrlTemplate ? editUrlTemplate.replace('{id}', subId) : '';

       if (!editUrl) {
           alert('Error: Edit URL not found');
           input.remove();
           label.style.display = '';
           checkbox.style.display = '';
           return;
       }

       fetch(`${editUrl}${queryParams}`, {
           method: 'POST',
           body: formData,
           headers: {'X-Requested-With': 'XMLHttpRequest'}
       })
       .then(r => r.json())
       .then(data => {
           if (data.success) {
               input.remove();
               label.style.display = '';
               checkbox.style.display = '';
               
               const lockIcon = label.querySelector('i.bi-lock-fill');
               label.textContent = data.name + ' ';
               if (lockIcon) label.appendChild(lockIcon);
               label.dataset.subName = data.name;
           } else {
               alert(data.error || 'Error saving');
               input.disabled = false;
               delete input.dataset.saving;
               input.focus();
           }
       })
       .catch(e => {
           console.error(e);
           alert('Connection error');
           input.disabled = false;
           delete input.dataset.saving;
       });
    }

    function handleSubsectionDelete(currentTarget) {
         const subId = currentTarget.dataset.subId;
         const subName = currentTarget.dataset.subName;
         const isLocked = currentTarget.dataset.locked === 'true';

         if (isLocked) {
             alert('Cannot delete this item as it is linked.');
             return;
         }

         if (!confirm(`Are you sure you want to delete "${subName}"?`)) return;

         // Find delete form or create one
         const container = currentTarget.closest('.d-flex');
         const addBtn = container ? container.querySelector('.add-subsection-btn') : document.querySelector('.add-subsection-btn');
         
         const deleteUrlTemplate = addBtn ? addBtn.dataset.deleteUrlTemplate : '';
         const deleteUrl = deleteUrlTemplate ? deleteUrlTemplate.replace('{id}', subId) : '';
         
         if (!deleteUrl) {
             alert('Delete URL not found');
             return;
         }

         let queryParams = '';
         if (addBtn) {
             const queryParts = [
                `model=${addBtn.dataset.childModel}`,
                `parent=${addBtn.dataset.parentModel}`,
             ];
             if (addBtn.dataset.parentId) queryParts.push(`parent_id=${addBtn.dataset.parentId}`);
             if (addBtn.dataset.parentField) queryParts.push(`parent_field=${addBtn.dataset.parentField}`);
             queryParams = `?${queryParts.join('&')}`;
         }

         // Submit via standard form to handle redirect or page reload
         let form = document.getElementById('deleteSubsectionForm');
         if (!form) {
             form = document.createElement('form');
             form.method = 'POST';
             form.style.display = 'none';
             const csrf = getCookie('csrftoken') || document.querySelector('[name=csrfmiddlewaretoken]')?.value;
             if (csrf) {
                 const inp = document.createElement('input');
                 inp.type = 'hidden'; name='csrfmiddlewaretoken'; inp.value=csrf;
                 form.appendChild(inp);
             }
             document.body.appendChild(form);
         }
         
         form.action = `${deleteUrl}${queryParams}`;
         form.submit();
    }

    function handleInlineAdd(e, btn) {
        // ... (Keep existing inline add logic mostly as is for simplicity, or refactor later)
        // For brevity, assuming the existing logic is copied here.
        // It's quite long, so I will paste the previous implementation but wrapped.
        
        const container = btn.closest('.d-flex');
        const csrfToken = btn.dataset.csrf; 
        const fieldName = btn.dataset.fieldName || 'sub_affiliates';
        const addUrl = btn.dataset.addUrl;
        const parentModel = btn.dataset.parentModel;
        const parentId = btn.dataset.parentId;
        const parentField = btn.dataset.parentField;
        const childModel = btn.dataset.childModel;
        
        const inputWrapper = document.createElement('div');
        inputWrapper.className = 'position-relative d-inline-block';
        
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'form-control textinput h-100';
        input.placeholder = '...';
        input.style.width = '150px';
        input.dir = 'rtl';
        
        inputWrapper.appendChild(input);
        container.insertBefore(inputWrapper, btn);
        input.focus();
        
        const save = () => {
             saveNewSubsection(input, parentModel, childModel, csrfToken, fieldName, addUrl, parentId, parentField);
        };

        input.addEventListener('keydown', function(ev) {
            if (ev.key === 'Enter') { ev.preventDefault(); save(); }
            else if (ev.key === 'Escape') inputWrapper.remove();
        });
        
        input.addEventListener('blur', function() {
            if (input.value.trim()) save();
            else inputWrapper.remove();
        });
    }

    function saveNewSubsection(input, parentModel, childModel, csrfToken, fieldName, addUrl, parentId, parentField) {
        if (input.dataset.saving) return; 
        const name = input.value.trim();
        if (!name) return;
        
        input.dataset.saving = 'true';
        input.disabled = true;
        
        const formData = new FormData();
        formData.append('name', name);
        formData.append('csrfmiddlewaretoken', csrfToken);
        
        const queryParts = [`model=${childModel}`, `parent=${parentModel}`];
        if (parentId) queryParts.push(`parent_id=${parentId}`);
        if (parentField) queryParts.push(`parent_field=${parentField}`);
        const query = `?${queryParts.join('&')}`;
        
        fetch(`${addUrl}${query}`, {
            method: 'POST', body: formData, headers: {'X-Requested-With': 'XMLHttpRequest'}
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                const wrapper = input.parentElement;
                const container = wrapper.parentElement;
                const emptyMsg = container.querySelector('.subsection-empty');
                if (emptyMsg) emptyMsg.remove();
                
                const checkboxId = `id_${fieldName}_new_${data.id}`;
                const checkboxHTML = `
                    <input type="checkbox" name="${fieldName}" value="${data.id}" class="btn-check" id="${checkboxId}" checked>
                    <label class="btn btn-outline-secondary subsection-checkbox-label" 
                           for="${checkboxId}" style="font-size: 1.1rem;"
                           data-sub-id="${data.id}" data-sub-name="${name}"
                           data-micro-context="true"
                           data-locked="false">
                      ${name}
                    </label>
                `;
                wrapper.outerHTML = checkboxHTML;
            } else {
                alert(data.error || 'Error');
                input.disabled = false;
                delete input.dataset.saving;
                input.focus();
            }
        })
        .catch(err => {
            console.error(err);
            alert('Connection Error');
            input.disabled = false;
             delete input.dataset.saving;
        });
    }

})();
