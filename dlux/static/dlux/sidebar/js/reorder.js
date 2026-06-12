(function() {
    'use strict';

    let isReorderMode = false;
    let draggedNode = null;
    let itemMap = new Map();
    let groupMap = new Map();

    function parseTreeState() {
        const script = document.getElementById('sidebarTreeData');
        if (!script) return [];
        try {
            const parsed = JSON.parse(script.textContent || '[]');
            return Array.isArray(parsed) ? parsed : [];
        } catch (err) {
            console.warn('Could not parse sidebar tree state:', err);
            return [];
        }
    }

    function indexTreeState(entries) {
        itemMap = new Map();
        groupMap = new Map();

        function walk(nodes) {
            (nodes || []).forEach((entry) => {
                if (!entry || typeof entry !== 'object') return;
                const entryId = entry.id || entry.url_name || entry.url;
                if (!entryId) return;

                if (entry.kind === 'group') {
                    groupMap.set(entryId, {
                        kind: 'group',
                        id: entryId,
                        label: entry.label || 'Group',
                        icon: entry.icon || 'bi-folder2-open',
                        url_name: entry.url_name || '',
                        url: entry.url || '',
                    });
                    walk(entry.items || []);
                    return;
                }

                itemMap.set(entryId, {
                    kind: 'item',
                    id: entryId,
                    url_name: entry.url_name || entryId,
                    label: entry.label || entry.url_name || entryId,
                    icon: entry.icon || 'bi-link-45deg',
                    permissions: Array.isArray(entry.permissions) ? entry.permissions : [],
                    group_key: entry.group_key || '',
                    group_label: entry.group_label || '',
                });
            });
        }

        walk(entries);
    }

    function getTreeRoot() {
        return document.getElementById('sidebarTreeRoot');
    }

    function getGroupContainer(groupNode) {
        return groupNode ? groupNode.querySelector('[data-group-dropzone]') : null;
    }

    function getNodeContainer(node) {
        if (!node) return null;
        const parent = node.parentElement;
        if (!parent) return null;
        if (parent.id === 'sidebarTreeRoot' || parent.hasAttribute('data-group-dropzone')) {
            return parent;
        }
        return null;
    }

    function clearDropClasses(root) {
        (root || document).querySelectorAll('.sidebar-drop-target').forEach((el) => el.classList.remove('sidebar-drop-target'));
        (root || document).querySelectorAll('.sidebar-drop-before').forEach((el) => el.classList.remove('sidebar-drop-before'));
        (root || document).querySelectorAll('.sidebar-drop-after').forEach((el) => el.classList.remove('sidebar-drop-after'));
    }

    function setDraggingState(node, active) {
        if (!node) return;
        node.classList.toggle('dragging', active);
        if (node.dataset.entryKind === 'group') {
            const button = node.querySelector('.accordion-button');
            if (button) {
                button.classList.toggle('dragging', active);
            }
        }
    }

    function canDropOnNode(targetNode) {
        if (!draggedNode || !targetNode || draggedNode === targetNode) return false;
        if (draggedNode.dataset.entryKind === 'group') {
            return getNodeContainer(targetNode) === getTreeRoot();
        }
        return true;
    }

    function syncDraggableHandles(root) {
        const nodes = root.querySelectorAll('[data-entry-kind][data-entry-id]');
        nodes.forEach((node) => {
            if (node.dataset.reorderBound === 'true') {
                const handle = node.dataset.entryKind === 'group' ? node.querySelector('.accordion-button') : node;
                if (handle) {
                    if (isReorderMode) {
                        handle.setAttribute('draggable', 'true');
                    } else {
                        handle.removeAttribute('draggable');
                    }
                }
                return;
            }

            node.dataset.reorderBound = 'true';
            const handle = node.dataset.entryKind === 'group' ? node.querySelector('.accordion-button') : node;
            if (!handle) return;

            handle.addEventListener('dragstart', (event) => {
                if (!isReorderMode) {
                    event.preventDefault();
                    return;
                }
                draggedNode = node;
                setDraggingState(node, true);
                event.dataTransfer.effectAllowed = 'move';
                event.dataTransfer.setData('text/plain', node.dataset.entryId || '');
            });

            handle.addEventListener('dragend', () => {
                setDraggingState(node, false);
                draggedNode = null;
                clearDropClasses(root);
            });

            handle.addEventListener('click', (event) => {
                if (isReorderMode) {
                    event.preventDefault();
                    event.stopPropagation();
                }
            });

            node.addEventListener('dragover', (event) => {
                if (!isReorderMode || !canDropOnNode(node)) return;
                event.preventDefault();
                event.stopPropagation();
                const rect = node.getBoundingClientRect();
                const before = event.clientY < rect.top + rect.height / 2;
                node.classList.toggle('sidebar-drop-before', before);
                node.classList.toggle('sidebar-drop-after', !before);
            });

            node.addEventListener('dragleave', () => {
                node.classList.remove('sidebar-drop-before', 'sidebar-drop-after');
            });

            node.addEventListener('drop', (event) => {
                if (!isReorderMode || !canDropOnNode(node) || !draggedNode) return;
                event.preventDefault();
                event.stopPropagation();

                const container = getNodeContainer(node);
                if (!container) return;

                const rect = node.getBoundingClientRect();
                const before = event.clientY < rect.top + rect.height / 2;
                container.insertBefore(draggedNode, before ? node : node.nextSibling);
                node.classList.remove('sidebar-drop-before', 'sidebar-drop-after');
                saveSidebarTree(root);
            });

            if (node.dataset.entryKind === 'group') {
                const groupContainer = getGroupContainer(node);
                if (groupContainer) {
                    groupContainer.addEventListener('dragover', (event) => {
                        if (!isReorderMode || !draggedNode || draggedNode.dataset.entryKind !== 'item') return;
                        event.preventDefault();
                        event.stopPropagation();
                        groupContainer.classList.add('sidebar-drop-target');
                    });

                    groupContainer.addEventListener('dragleave', () => {
                        groupContainer.classList.remove('sidebar-drop-target');
                    });

                    groupContainer.addEventListener('drop', (event) => {
                        if (!isReorderMode || !draggedNode || draggedNode.dataset.entryKind !== 'item') return;
                        event.preventDefault();
                        event.stopPropagation();
                        groupContainer.appendChild(draggedNode);
                        groupContainer.classList.remove('sidebar-drop-target');
                        saveSidebarTree(root);
                    });
                }
            }
        });
    }

    function fallbackItemFromNode(node) {
        return {
            kind: 'item',
            id: node.dataset.entryId,
            url_name: node.dataset.urlName || node.dataset.entryId,
            label: node.querySelector('span') ? node.querySelector('span').textContent.trim() : (node.dataset.urlName || node.dataset.entryId),
            icon: Array.from(node.querySelector('i')?.classList || []).find((cls) => cls.startsWith('bi-')) || 'bi-link-45deg',
            permissions: [],
            group_key: '',
            group_label: '',
        };
    }

    function fallbackGroupFromNode(node) {
        return {
            kind: 'group',
            id: node.dataset.entryId,
            label: node.querySelector('.accordion-button span') ? node.querySelector('.accordion-button span').textContent.trim() : 'Group',
            icon: Array.from(node.querySelector('.accordion-button i')?.classList || []).find((cls) => cls.startsWith('bi-')) || 'bi-folder2-open',
            url_name: '',
            url: '',
        };
    }

    function serializeItems(container) {
        return Array.from(container.children)
            .filter((node) => node.nodeType === 1 && node.matches('[data-entry-kind="item"][data-entry-id]'))
            .map((node) => {
                const itemId = node.dataset.entryId;
                return { ...(itemMap.get(itemId) || fallbackItemFromNode(node)), id: itemId, kind: 'item' };
            });
    }

    function serializeSidebarTree(root) {
        return Array.from(root.children)
            .filter((node) => node.nodeType === 1 && node.matches('[data-entry-kind][data-entry-id]'))
            .map((node) => {
                const entryId = node.dataset.entryId;
                if (node.dataset.entryKind === 'group') {
                    const group = { ...(groupMap.get(entryId) || fallbackGroupFromNode(node)), id: entryId, kind: 'group' };
                    const groupContainer = getGroupContainer(node);
                    group.items = groupContainer ? serializeItems(groupContainer) : [];
                    return group;
                }
                return { ...(itemMap.get(entryId) || fallbackItemFromNode(node)), id: entryId, kind: 'item' };
            });
    }

    function saveSidebarTree(root) {
        const entries = serializeSidebarTree(root);
        const payload = { entries };

        const script = document.getElementById('sidebarTreeData');
        if (script) {
            script.textContent = JSON.stringify(entries);
        }

        indexTreeState(entries);

        if (window.updatePreferences) {
            window.updatePreferences({ sidebar_tree: payload });
        }
        if (window.USER_PREFS) {
            window.USER_PREFS.sidebar_tree = payload;
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const sidebar = document.getElementById('sidebar');
        const treeRoot = getTreeRoot();
        const reorderToggle = document.getElementById('sidebarReorderToggle');

        if (!sidebar || !treeRoot || !reorderToggle) return;

        indexTreeState(parseTreeState());
        syncDraggableHandles(treeRoot);

        reorderToggle.addEventListener('click', (event) => {
            event.stopPropagation();
            isReorderMode = !isReorderMode;
            reorderToggle.classList.toggle('active', isReorderMode);
            sidebar.classList.toggle('reorder-mode', isReorderMode);
            syncDraggableHandles(treeRoot);
            if (!isReorderMode) {
                clearDropClasses(treeRoot);
                setDraggingState(draggedNode, false);
                draggedNode = null;
            }
        });

        document.addEventListener('click', (event) => {
            if (isReorderMode && !sidebar.contains(event.target)) {
                isReorderMode = false;
                reorderToggle.classList.remove('active');
                sidebar.classList.remove('reorder-mode');
                syncDraggableHandles(treeRoot);
                clearDropClasses(treeRoot);
                setDraggingState(draggedNode, false);
                draggedNode = null;
            }
        });

        treeRoot.addEventListener('dragover', (event) => {
            if (!isReorderMode || !draggedNode) return;
            event.preventDefault();
            treeRoot.classList.add('sidebar-drop-target');
        });

        treeRoot.addEventListener('dragleave', () => {
            treeRoot.classList.remove('sidebar-drop-target');
        });

        treeRoot.addEventListener('drop', (event) => {
            if (!isReorderMode || !draggedNode) return;
            event.preventDefault();
            event.stopPropagation();
            treeRoot.appendChild(draggedNode);
            treeRoot.classList.remove('sidebar-drop-target');
            saveSidebarTree(treeRoot);
        });
    });
})();
