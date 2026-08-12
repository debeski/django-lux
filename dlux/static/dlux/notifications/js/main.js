(function () {
    'use strict';

    const PROGRESS_REFRESH_MS = 3000;

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function postJSON(url) {
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': csrfToken(),
                'X-Requested-With': 'XMLHttpRequest',
            },
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('Request failed');
            }
            return response.json();
        });
    }

    function endpoint(root, id, action) {
        const fallback = window.dluxEndpoint
            ? window.dluxEndpoint('notificationsList', null, '/sys/api/notifications/')
            : (window.dluxUrl ? window.dluxUrl('/sys/api/notifications/') : '/sys/api/notifications/');
        const base = (root.dataset.listUrl || fallback).replace(/\/$/, '');
        return base + '/' + encodeURIComponent(id) + '/' + action + '/';
    }

    function updateBadge(root, count, level) {
        const badge = root.querySelector('[data-dlux-notifications-badge]');
        if (!badge) {
            return;
        }
        if (root.dataset.badgeEnabled !== 'true' || !count) {
            badge.classList.add('d-none');
            badge.textContent = '';
            return;
        }
        badge.className = 'dlux-notifications__badge dlux-notifications__badge--' + (level || 'info');
        badge.textContent = count > 99 ? '99+' : String(count);
    }

    function updateSidebarSectionBadges(sectionCounts) {
        const counts = sectionCounts && typeof sectionCounts === 'object' ? sectionCounts : {};
        document.querySelectorAll('[data-dlux-sidebar-notification-keys]').forEach(function (entry) {
            const keys = Array.from(new Set(
                (entry.dataset.dluxSidebarNotificationKeys || '').split(/\s+/).filter(Boolean)
            ));
            const count = keys.reduce(function (total, key) {
                return total + Math.max(0, Number(counts[key]) || 0);
            }, 0);
            const badge = entry.querySelector(':scope > [data-dlux-sidebar-notification-badge], :scope > h2 button [data-dlux-sidebar-notification-badge]');
            if (!badge) {
                return;
            }
            const root = entry.closest('#sidebarTreeRoot');
            const enabled = !root || root.dataset.dluxSidebarNotificationBadgesEnabled === 'true';
            badge.classList.toggle('d-none', !enabled || !count);
            badge.textContent = count > 99 ? '99+' : (count ? String(count) : '');
            const label = root ? root.dataset.dluxSidebarUnreadLabel : 'unread notifications';
            const accessibleLabel = count + ' ' + (label || 'unread notifications');
            badge.setAttribute('aria-label', accessibleLabel);
            badge.title = accessibleLabel;
        });
    }

    function itemMeta(item) {
        const parts = [];
        if (item.source_model || item.category) {
            parts.push(item.source_model || item.category);
        }
        if (item.action) {
            parts.push(item.action);
        }
        return parts.join(' · ');
    }

    function createItem(root, item) {
        const metadata = item.metadata || {};
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'dlux-notifications__item' + (item.read ? '' : ' dlux-notifications__item--unread');
        button.dataset.dluxNotificationItem = 'true';
        button.dataset.id = item.id;
        button.dataset.readUrl = endpoint(root, item.id, 'read');
        button.dataset.dismissUrl = endpoint(root, item.id, 'dismiss');
        button.dataset.title = item.title || '';
        button.dataset.message = item.message || '';
        button.dataset.level = item.level || 'info';
        button.dataset.source = item.source || '';
        button.dataset.action = item.action || '';
        button.dataset.origin = item.source_model || item.source_label || item.category || '';
        button.dataset.targetUrl = item.target_url || '';
        button.dataset.locked = metadata.locked ? 'true' : 'false';
        button.dataset.progress = String(metadata.progress || 0);
        button.dataset.progressMessage = metadata.progress_message || '';
        button.dataset.backupProgress = metadata.backup_progress ? 'true' : 'false';

        const dot = document.createElement('span');
        dot.className = 'dlux-notifications__dot dlux-notifications__dot--' + (item.level || 'info');
        button.appendChild(dot);

        const body = document.createElement('span');
        body.className = 'dlux-notifications__item-body';
        const title = document.createElement('span');
        title.className = 'dlux-notifications__item-title';
        title.textContent = item.title || item.message || '';
        const meta = document.createElement('span');
        meta.className = 'dlux-notifications__item-meta';
        meta.textContent = itemMeta(item);
        body.appendChild(title);
        body.appendChild(meta);
        if (metadata.backup_progress) {
            const progress = document.createElement('progress');
            progress.className = 'dlux-notifications__progress';
            progress.max = 100;
            progress.value = Math.max(0, Math.min(Number(metadata.progress) || 0, 100));
            const label = document.createElement('small');
            label.className = 'dlux-notifications__progress-label';
            label.textContent = (metadata.progress || 0) + '%';
            body.appendChild(progress);
            body.appendChild(label);
        }
        button.appendChild(body);
        return button;
    }

    function emptyText(root) {
        return root.dataset.emptyText || 'No notifications';
    }

    function notificationsEnabled(root) {
        return root && root.dataset.dluxNotificationsEnabled === 'true';
    }

    function applyPayload(root, payload) {
        renderList(root, payload.items || []);
        updateBadge(root, payload.unread_count || 0, payload.unread_level || 'info');
        updateSidebarSectionBadges(payload.section_counts || {});
    }

    function hasActiveProgress(payload) {
        return Boolean(payload && (payload.items || []).some(function (item) {
            return item.metadata && item.metadata.backup_progress && item.metadata.locked;
        }));
    }

    function rootHasActiveProgress(root) {
        return Boolean(root && root.querySelector(
            '[data-dlux-notification-item][data-backup-progress="true"][data-locked="true"]'
        ));
    }

    function renderList(root, items) {
        const list = root.querySelector('[data-dlux-notifications-list]');
        if (!list) {
            return;
        }
        list.textContent = '';
        if (!items.length) {
            const empty = document.createElement('div');
            empty.className = 'dlux-notifications__empty';
            empty.dataset.dluxNotificationsEmpty = 'true';
            empty.textContent = emptyText(root);
            list.appendChild(empty);
            return;
        }
        items.forEach(function (item) {
            list.appendChild(createItem(root, item));
        });
    }

    function refresh(root) {
        const url = root.dataset.listUrl;
        if (!url || !notificationsEnabled(root)) {
            return Promise.resolve();
        }
        return fetch(url, {
            cache: 'no-store',
            credentials: 'same-origin',
            headers: {'X-Requested-With': 'XMLHttpRequest'},
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('Request failed');
            }
            return response.json();
        }).then(function (payload) {
            applyPayload(root, payload);
            return payload;
        }).catch(function () { return null; });
    }

    function refreshRoot(root) {
        if (root && typeof root.__dluxNotificationsRefresh === 'function') {
            return root.__dluxNotificationsRefresh();
        }
        return refresh(root);
    }

    function setOpen(root, open) {
        const panel = root.querySelector('[data-dlux-notifications-panel]');
        const trigger = root.querySelector('[data-dlux-notifications-toggle]');
        if (!panel || !trigger) {
            return;
        }
        panel.hidden = !open;
        trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open) {
            refreshRoot(root);
        }
    }

    function showList(root) {
        const detail = root.querySelector('[data-dlux-notifications-detail]');
        const list = root.querySelector('[data-dlux-notifications-list]');
        if (detail) {
            detail.hidden = true;
        }
        if (list) {
            list.hidden = false;
        }
    }

    function showDetail(root, item) {
        const detail = root.querySelector('[data-dlux-notifications-detail]');
        const list = root.querySelector('[data-dlux-notifications-list]');
        if (!detail || !list) {
            return;
        }
        list.hidden = true;
        detail.hidden = false;
        detail.dataset.currentId = item.dataset.id || '';
        detail.dataset.dismissUrl = item.dataset.dismissUrl || '';

        const title = detail.querySelector('[data-dlux-notifications-detail-title]');
        const message = detail.querySelector('[data-dlux-notifications-detail-message]');
        const origin = detail.querySelector('[data-dlux-notifications-detail-origin]');
        const link = detail.querySelector('[data-dlux-notifications-detail-link]');
        const dismiss = detail.querySelector('[data-dlux-notifications-dismiss]');
        const progress = detail.querySelector('[data-dlux-notifications-detail-progress]');
        if (title) {
            title.textContent = item.dataset.title || item.querySelector('.dlux-notifications__item-title')?.textContent || '';
        }
        if (message) {
            message.textContent = item.dataset.message || '';
        }
        if (origin) {
            origin.textContent = [item.dataset.origin, item.dataset.action].filter(Boolean).join(' · ');
        }
        if (link) {
            if (item.dataset.targetUrl) {
                link.hidden = false;
                link.href = item.dataset.targetUrl;
            } else {
                link.hidden = true;
                link.removeAttribute('href');
            }
        }
        if (dismiss) {
            dismiss.hidden = item.dataset.locked === 'true';
        }
        if (progress) {
            const value = Math.max(0, Math.min(parseInt(item.dataset.progress || '0', 10) || 0, 100));
            progress.hidden = item.dataset.backupProgress !== 'true';
            const bar = progress.querySelector('[data-dlux-notifications-detail-progress-bar]');
            const label = progress.querySelector('[data-dlux-notifications-detail-progress-label]');
            if (bar) bar.value = value;
            if (label) label.textContent = (item.dataset.progressMessage || '') + (item.dataset.progressMessage ? ' · ' : '') + value + '%';
        }

        if (item.dataset.readUrl && item.classList.contains('dlux-notifications__item--unread')) {
            postJSON(item.dataset.readUrl).then(function () {
                item.classList.remove('dlux-notifications__item--unread');
                refreshRoot(root);
            }).catch(function () {});
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        const roots = Array.from(document.querySelectorAll('[data-dlux-notifications]'));
        const groupsByUrl = new Map();
        roots.forEach(function (root) {
            const url = root.dataset.listUrl || '';
            if (!url) {
                return;
            }
            if (!groupsByUrl.has(url)) {
                groupsByUrl.set(url, { url: url, roots: [] });
            }
            groupsByUrl.get(url).roots.push(root);
        });
        const refreshGroups = Array.from(groupsByUrl.values());
        const refreshTimers = new Map();

        function groupEnabled(group) {
            return group.roots.some(notificationsEnabled);
        }

        function groupHasActiveProgress(group) {
            return group.roots.some(function (root) {
                return notificationsEnabled(root) && rootHasActiveProgress(root);
            });
        }

        function clearRefresh(group) {
            const current = refreshTimers.get(group);
            if (current) window.clearTimeout(current);
            refreshTimers.delete(group);
        }

        function refreshGroup(group) {
            const enabledRoots = group.roots.filter(notificationsEnabled);
            if (!group.url || !enabledRoots.length || document.hidden) {
                return Promise.resolve(null);
            }
            return fetch(group.url, {
                cache: 'no-store',
                credentials: 'same-origin',
                headers: {'X-Requested-With': 'XMLHttpRequest'},
            }).then(function (response) {
                if (!response.ok) {
                    throw new Error('Request failed');
                }
                return response.json();
            }).then(function (payload) {
                enabledRoots.forEach(function (root) {
                    applyPayload(root, payload);
                });
                return payload;
            }).catch(function () { return null; });
        }

        function scheduleProgressRefresh(group, delay) {
            clearRefresh(group);
            if (!groupEnabled(group) || !groupHasActiveProgress(group) || document.hidden) {
                return;
            }
            refreshTimers.set(group, window.setTimeout(function () {
                if (document.hidden) {
                    clearRefresh(group);
                    return;
                }
                refreshGroup(group).then(function (payload) {
                    if (hasActiveProgress(payload) || (payload === null && groupHasActiveProgress(group))) {
                        scheduleProgressRefresh(group, PROGRESS_REFRESH_MS);
                    } else {
                        clearRefresh(group);
                    }
                });
            }, delay));
        }

        function startGroupProgressRefresh(group, delay) {
            if (!groupEnabled(group) || !groupHasActiveProgress(group) || document.hidden || refreshTimers.get(group)) {
                return;
            }
            scheduleProgressRefresh(group, delay);
        }

        function refreshGroupAndMaybePoll(group) {
            return refreshGroup(group).then(function (payload) {
                if (hasActiveProgress(payload)) {
                    scheduleProgressRefresh(group, PROGRESS_REFRESH_MS);
                } else if (!groupHasActiveProgress(group)) {
                    clearRefresh(group);
                }
                return payload;
            });
        }

        refreshGroups.forEach(function (group) {
            group.roots.forEach(function (root) {
                root.__dluxNotificationsRefresh = function () {
                    return refreshGroupAndMaybePoll(group);
                };
            });
        });

        roots.forEach(function (root) {
            const trigger = root.querySelector('[data-dlux-notifications-toggle]');
            const readAll = root.querySelector('[data-dlux-notifications-read-all]');
            const clearAll = root.querySelector('[data-dlux-notifications-clear-all]');
            const back = root.querySelector('[data-dlux-notifications-back]');
            const dismiss = root.querySelector('[data-dlux-notifications-dismiss]');

            if (trigger) {
                trigger.addEventListener('click', function (event) {
                    event.stopPropagation();
                    const panel = root.querySelector('[data-dlux-notifications-panel]');
                    setOpen(root, panel ? panel.hidden : true);
                });
            }

            root.addEventListener('click', function (event) {
                const item = event.target.closest('[data-dlux-notification-item]');
                if (item && root.contains(item)) {
                    showDetail(root, item);
                }
                event.stopPropagation();
            });

            if (readAll) {
                readAll.addEventListener('click', function (event) {
                    event.stopPropagation();
                    if (!root.dataset.readAllUrl) {
                        return;
                    }
                    postJSON(root.dataset.readAllUrl).then(function () {
                        refreshRoot(root);
                        showList(root);
                    }).catch(function () {});
                });
            }

            if (clearAll) {
                clearAll.addEventListener('click', function (event) {
                    event.stopPropagation();
                    if (!root.dataset.clearAllUrl) {
                        return;
                    }
                    postJSON(root.dataset.clearAllUrl).then(function () {
                        refreshRoot(root);
                        showList(root);
                    }).catch(function () {});
                });
            }

            if (back) {
                back.addEventListener('click', function () {
                    showList(root);
                });
            }

            if (dismiss) {
                dismiss.addEventListener('click', function () {
                    const detail = root.querySelector('[data-dlux-notifications-detail]');
                    const url = detail ? detail.dataset.dismissUrl : '';
                    if (!url) {
                        return;
                    }
                    postJSON(url).then(function () {
                        showList(root);
                        refreshRoot(root);
                    }).catch(function () {});
                });
            }
        });

        refreshGroups.forEach(function (group) {
            startGroupProgressRefresh(group, 0);
        });

        document.addEventListener('visibilitychange', function () {
            if (document.hidden) {
                refreshGroups.forEach(clearRefresh);
            } else {
                refreshGroups.forEach(function (group) {
                    startGroupProgressRefresh(group, 0);
                });
            }
        });

        document.addEventListener('click', function () {
            roots.forEach(function (root) {
                setOpen(root, false);
            });
        });

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                roots.forEach(function (root) {
                    setOpen(root, false);
                });
            }
        });
    });
})();
