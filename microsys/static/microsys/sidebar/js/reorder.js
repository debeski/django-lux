(function() {
    'use strict';

    const STORAGE_KEY_AUTO = 'sidebar_auto_order';
    const STORAGE_KEY_PREFIX_EXTRA = 'sidebar_extra_';
    const STORAGE_KEY_GROUPS = 'sidebar_groups_order';

    let isReorderMode = false;
    let draggedElement = null;
    let dropIndicator = null;

    // Expose restore function globally for immediate FOUC fix
    window.restoreSidebarOrder = restoreOrder;

    document.addEventListener('DOMContentLoaded', () => {
        const sidebar = document.getElementById('sidebar');
        const reorderToggle = document.getElementById('sidebarReorderToggle');
        
        if (!sidebar || !reorderToggle) return;

        // Create drop indicator element
        dropIndicator = document.createElement('div');
        dropIndicator.className = 'drop-indicator';
        dropIndicator.style.display = 'none';

        // Restore is now called immediately via inline script for FOUC prevention
        // But call again here as fallback if inline script didn't run
        if (!window._sidebarOrderRestored) {
            restoreOrder();
        }

        // Toggle reorder mode
        reorderToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            isReorderMode = !isReorderMode;
            reorderToggle.classList.toggle('active', isReorderMode);
            sidebar.classList.toggle('reorder-mode', isReorderMode);
            
            if (isReorderMode) {
                enableDragAndDrop();
            } else {
                disableDragAndDrop();
            }
        });

        // Close reorder mode when clicking outside
        document.addEventListener('click', (e) => {
            if (isReorderMode && !sidebar.contains(e.target)) {
                isReorderMode = false;
                reorderToggle.classList.remove('active');
                sidebar.classList.remove('reorder-mode');
                disableDragAndDrop();
            }
        });
    });

    function enableDragAndDrop() {
        // 1. Auto items in .sidebar-auto-items
        const autoContainer = document.getElementById('sidebarAutoItems');
        if (autoContainer) {
            setupDraggableContainer(autoContainer, ':scope > .list-group-item', STORAGE_KEY_AUTO, 'urlName');
        }

        // 2. Extra group items in accordion bodies
        const accordionBodies = document.querySelectorAll('.sidebar .accordion-body');
        accordionBodies.forEach(body => {
            const groupName = body.dataset.groupName || body.closest('.accordion-item')?.querySelector('.accordion-button span')?.textContent?.trim();
            if (groupName) {
                const key = STORAGE_KEY_PREFIX_EXTRA + slugify(groupName);
                setupDraggableContainer(body, ':scope > .list-group-item', key, 'urlName');
            }
        });

        // 3. Accordion groups themselves
        const groupsContainer = document.getElementById('sidebarExtraAccordion');
        if (groupsContainer) {
            setupDraggableContainer(groupsContainer, ':scope > .accordion-item', STORAGE_KEY_GROUPS, 'groupId');
        }
    }

    function disableDragAndDrop() {
        const items = document.querySelectorAll('.sidebar [draggable="true"]');
        items.forEach(item => {
            item.removeAttribute('draggable');
            item.removeEventListener('dragstart', handleDragStart);
            item.removeEventListener('dragend', handleDragEnd);
            item.removeEventListener('dragover', handleDragOver);
            item.removeEventListener('drop', handleDrop);
        });
        
        // Hide drop indicator
        if (dropIndicator) {
            dropIndicator.style.display = 'none';
            if (dropIndicator.parentNode) {
                dropIndicator.parentNode.removeChild(dropIndicator);
            }
        }
    }

    function setupDraggableContainer(container, selector, storageKey, idAttribute) {
        const items = container.querySelectorAll(selector);
        
        items.forEach(item => {
            item.setAttribute('draggable', 'true');
            item.dataset.storageKey = storageKey;
            item.dataset.idAttribute = idAttribute;
            
            item.addEventListener('dragstart', handleDragStart);
            item.addEventListener('dragend', handleDragEnd);
            item.addEventListener('dragover', handleDragOver);
            item.addEventListener('drop', handleDrop);
        });

        // Add event listeners to container for drag events
        container.addEventListener('dragover', handleContainerDragOver);
        container.addEventListener('drop', handleContainerDrop);
    }

    function handleDragStart(e) {
        draggedElement = this;
        this.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', ''); // Required for Firefox
        
        // Add drop indicator to DOM
        if (dropIndicator && this.parentNode) {
            this.parentNode.appendChild(dropIndicator);
        }
    }

    function handleDragEnd(e) {
        this.classList.remove('dragging');
        
        // Hide drop indicator
        if (dropIndicator) {
            dropIndicator.style.display = 'none';
        }
        
        // Save new order
        if (draggedElement) {
            saveOrder(draggedElement.parentNode, draggedElement.dataset.storageKey, draggedElement.dataset.idAttribute);
        }
        
        draggedElement = null;
    }

    function handleDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        
        if (!draggedElement || draggedElement === this) return;
        if (draggedElement.dataset.storageKey !== this.dataset.storageKey) return;
        
        const rect = this.getBoundingClientRect();
        const midY = rect.top + rect.height / 2;
        
        // Show drop indicator
        if (dropIndicator) {
            dropIndicator.style.display = 'block';
            if (e.clientY < midY) {
                this.parentNode.insertBefore(dropIndicator, this);
            } else {
                this.parentNode.insertBefore(dropIndicator, this.nextSibling);
            }
        }
    }

    function handleContainerDragOver(e) {
        e.preventDefault();
    }

    function handleDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        
        if (!draggedElement || draggedElement === this) return;
        if (draggedElement.dataset.storageKey !== this.dataset.storageKey) return;
        
        const rect = this.getBoundingClientRect();
        const midY = rect.top + rect.height / 2;
        
        if (e.clientY < midY) {
            this.parentNode.insertBefore(draggedElement, this);
        } else {
            this.parentNode.insertBefore(draggedElement, this.nextSibling);
        }
    }

    function handleContainerDrop(e) {
        e.preventDefault();
        // Item drops are handled by individual items
    }

    function saveOrder(container, storageKey, idAttribute) {
        if (!container || !storageKey || !idAttribute) return;
        
        const items = container.querySelectorAll(`:scope > [data-${slugifyAttr(idAttribute)}]`);
        const order = Array.from(items).map(item => item.dataset[idAttribute]);
        
        // 1. Update local storage (individual key for backward compat/local speed)
        try {
            localStorage.setItem(storageKey, JSON.stringify(order));
        } catch (e) {
            console.warn('Could not save sidebar order (localStorage):', e);
        }

        // 2. Update DB via consolidated sidebar_layout
        if (window.updatePreferences) {
            const currentPrefs = window.USER_PREFS || {};
            const currentLayout = currentPrefs.sidebar_layout || {};
            
            // Reconstruct the specific part of the layout
            if (storageKey === STORAGE_KEY_AUTO) {
                currentLayout.auto_items = order;
            } else if (storageKey === STORAGE_KEY_GROUPS) {
                currentLayout.accordion_groups_order = order;
            } else if (storageKey.startsWith(STORAGE_KEY_PREFIX_EXTRA)) {
                if (!currentLayout.group_items) currentLayout.group_items = {};
                currentLayout.group_items[storageKey] = order;
            }
            
            window.updatePreferences({ 
                sidebar_layout: currentLayout 
            });
            
            // Sync local USER_PREFS
            if (window.USER_PREFS) {
                window.USER_PREFS.sidebar_layout = currentLayout;
            }
        }
    }

    function restoreOrder() {
        // 1. Restore auto items order
        const autoContainer = document.getElementById('sidebarAutoItems');
        if (autoContainer) {
            restoreContainerOrder(autoContainer, STORAGE_KEY_AUTO, 'urlName');
        }

        // 2. Restore extra group items order
        const accordionBodies = document.querySelectorAll('.sidebar .accordion-body');
        accordionBodies.forEach(body => {
            const groupName = body.dataset.groupName || body.closest('.accordion-item')?.querySelector('.accordion-button span')?.textContent?.trim();
            if (groupName) {
                const key = STORAGE_KEY_PREFIX_EXTRA + slugify(groupName);
                restoreContainerOrder(body, key, 'urlName');
            }
        });

        // 3. Restore parent groups order
        const groupsContainer = document.getElementById('sidebarExtraAccordion');
        if (groupsContainer) {
            restoreContainerOrder(groupsContainer, STORAGE_KEY_GROUPS, 'groupId');
        }
        
        // Mark as restored
        window._sidebarOrderRestored = true;
    }

    function restoreContainerOrder(container, storageKey, idAttribute) {
        let savedOrder;
        try {
            const layout = window.USER_PREFS?.sidebar_layout || {};
            
            // Try structured layout first
            if (storageKey === STORAGE_KEY_AUTO && layout.auto_items) {
                savedOrder = layout.auto_items;
            } else if (storageKey === STORAGE_KEY_GROUPS && layout.accordion_groups_order) {
                savedOrder = layout.accordion_groups_order;
            } else if (storageKey.startsWith(STORAGE_KEY_PREFIX_EXTRA) && layout.group_items?.[storageKey]) {
                savedOrder = layout.group_items[storageKey];
            } else {
                // Fallback to legacy sidebar_order if it exists (for transition)
                if (window.USER_PREFS?.sidebar_order?.[storageKey]) {
                    savedOrder = window.USER_PREFS.sidebar_order[storageKey];
                } else {
                    // Final fallback to localStorage
                    const saved = localStorage.getItem(storageKey);
                    if (saved) savedOrder = JSON.parse(saved);
                }
            }
        } catch (e) {
            return; // Invalid, use default
        }
        
        if (!Array.isArray(savedOrder) || savedOrder.length === 0) return;
        
        const items = container.querySelectorAll(`:scope > [data-${slugifyAttr(idAttribute)}]`);
        const itemMap = new Map();
        items.forEach(item => {
            itemMap.set(item.dataset[idAttribute], item);
        });
        
        // Reorder based on saved order
        savedOrder.forEach(idValue => {
            const item = itemMap.get(idValue);
            if (item) {
                container.appendChild(item);
                itemMap.delete(idValue);
            }
        });
        
        // Append any remaining items (new items not in saved order)
        itemMap.forEach(item => {
            container.appendChild(item);
        });
    }

    function slugify(text) {
        return text
            .toString()
            .toLowerCase()
            .trim()
            .replace(/\s+/g, '-')
            .replace(/[^\w\-]+/g, '')
            .replace(/\-\-+/g, '-');
    }

    function slugifyAttr(text) {
        return text.replace(/([a-z])([A-Z])/g, '$1-$2').toLowerCase();
    }
})();
