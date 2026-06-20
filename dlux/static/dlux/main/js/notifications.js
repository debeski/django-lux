(function () {
    'use strict';

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
        const base = (root.dataset.listUrl || '/sys/api/notifications/').replace(/\/$/, '');
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
        button.appendChild(body);
        return button;
    }

    function emptyText(root) {
        return root.dataset.emptyText || 'No notifications';
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
        if (!url) {
            return Promise.resolve();
        }
        return fetch(url, {
            credentials: 'same-origin',
            headers: {'X-Requested-With': 'XMLHttpRequest'},
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('Request failed');
            }
            return response.json();
        }).then(function (payload) {
            renderList(root, payload.items || []);
            updateBadge(root, payload.unread_count || 0, payload.unread_level || 'info');
        }).catch(function () {});
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
            refresh(root);
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

        if (item.dataset.readUrl && item.classList.contains('dlux-notifications__item--unread')) {
            postJSON(item.dataset.readUrl).then(function () {
                item.classList.remove('dlux-notifications__item--unread');
                refresh(root);
            }).catch(function () {});
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        const roots = Array.from(document.querySelectorAll('[data-dlux-notifications]'));
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
                        refresh(root);
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
                        refresh(root);
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
                        refresh(root);
                    }).catch(function () {});
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
