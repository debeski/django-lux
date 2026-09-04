(function () {
    'use strict';

    // Grouping the titlebar's optional actions behind one caret.
    //
    // The end side carries two groups that do not share a flex context — the loose
    // search / theme / language buttons and the actions group — and nothing inside
    // either shrinks, so past a certain width they overlap instead of compressing,
    // and the brand is squeezed out long before that. Grouped, every optional action
    // moves into the rail under the bar and only the constants stay: Home, the
    // caret, and the user hub trigger.
    //
    // The nodes are moved, never duplicated, so each toggle keeps the panel nested
    // inside it — the notification panel, the search box and its results — along with
    // the JS that wired them.

    const MIN_TITLE_WIDTH = 150;
    const RAIL_GAP = 10;
    const MOBILE_QUERY = '(max-width: 575.98px)';

    // What never groups. Home is the one constant action, and the caret and the hub
    // trigger are the controls that would be grouping things away.
    const CONSTANTS = [
        '.dlux-titlebar-home',
        '[data-titlebar-home]',
        '[data-titlebar-action-key="home"]',
        '.dlux-user-trigger',
        '.dlux-titlebar-rail-toggle',
        '.titlebar__constants',
    ].join(', ');

    // The button styles are written against these attributes on the titlebar, and the
    // rail is not inside it — mirror the ones that decide how a grouped action looks
    // and whether it shows at all, so a hidden Home stays hidden once grouped.
    const MIRRORED_ATTRIBUTES = [
        'data-titlebar-buttons-shape',
        'data-titlebar-home-shape',
        'data-titlebar-show-home',
        'data-titlebar-show-language-switcher',
    ];

    // Both action groups are always rendered and CSS hides the one the user-hub
    // style does not use — including a second notification bell. Grouping lifts
    // children out of their group, which would take that hidden copy with them and
    // show it, so only the active group's children are ever collected.
    function groupable(end, activeGroup) {
        const found = [];
        Array.prototype.forEach.call(end.children, function (child) {
            if (child.matches(CONSTANTS)) {
                return;
            }
            if (child.classList.contains('titlebar__actions')) {
                if (child.dataset.titlebarActionsGroup !== activeGroup) {
                    return;
                }
                Array.prototype.forEach.call(child.children, function (action) {
                    if (!action.matches(CONSTANTS)) {
                        found.push(action);
                    }
                });
                return;
            }
            found.push(child);
        });
        return found;
    }

    function anchor(node) {
        if (!node.__dluxRailAnchor) {
            const placeholder = document.createComment('dlux-titlebar-action');
            node.parentNode.insertBefore(placeholder, node);
            node.__dluxRailAnchor = placeholder;
        }
        return node.__dluxRailAnchor;
    }

    function create(titlebar, rail) {
        const end = titlebar.querySelector('.titlebar__side--end');
        const activeGroup = titlebar.dataset.titlebarUserHubStyle === 'titlebar_actions'
            ? 'titlebar_actions'
            : 'dropdown';
        const items = end ? groupable(end, activeGroup) : [];
        if (!items.length) {
            return null;
        }

        const start = titlebar.querySelector('.titlebar__side--start');
        const logo = titlebar.querySelector('.titlebar__logo');
        const toggle = titlebar.querySelector('[data-dlux-titlebar-rail-toggle]');
        const mobile = window.matchMedia(MOBILE_QUERY);
        let grouped = false;
        let open = false;

        function mirror() {
            MIRRORED_ATTRIBUTES.forEach(function (name) {
                const value = titlebar.getAttribute(name);
                if (value !== null) {
                    rail.setAttribute(name, value);
                }
            });
        }

        mirror();
        // System Settings previews titlebar appearance by rewriting these on the live
        // titlebar, so the rail has to follow rather than keep its load-time copy.
        new MutationObserver(mirror).observe(titlebar, {
            attributes: true,
            attributeFilter: MIRRORED_ATTRIBUTES,
        });

        // Measured only while the node sits in the titlebar: inside a closed rail it
        // is display:none and reports 0, which would read as "it fits" and ungroup it.
        function naturalWidth(node) {
            if (!grouped) {
                const width = node.offsetWidth;
                if (width > 0) {
                    node.__dluxNaturalWidth = width;
                }
            }
            return node.__dluxNaturalWidth || 0;
        }

        // Measure the end side as leaves: a wrapper holding a groupable action reports
        // a different width depending on whether it is currently grouped, which would
        // make the decision depend on its own outcome and flap. Descending past those
        // wrappers keeps every input stable.
        const statics = [];
        (function collect(node) {
            if (items.indexOf(node) !== -1) {
                return;
            }
            if (!items.some(function (item) { return node.contains(item); })) {
                statics.push(node);
                return;
            }
            Array.prototype.forEach.call(node.children, collect);
        }(end));

        function scatteredFits() {
            let needed = 0;
            items.forEach(function (node) {
                needed += naturalWidth(node) + RAIL_GAP;
            });
            statics.forEach(function (node) {
                const own = node.offsetWidth;
                needed += own ? own + RAIL_GAP : 0;
            });
            const available = titlebar.clientWidth
                - (start ? start.offsetWidth : 0)
                - (logo ? logo.offsetWidth : 0)
                - needed;
            return available >= MIN_TITLE_WIDTH;
        }

        // Grouped when the setting asks for it, when the screen is too narrow to do
        // anything else, or when the scattered row can no longer leave the title a
        // readable minimum.
        function shouldGroup() {
            return titlebar.dataset.titlebarActionsLayout === 'grouped'
                || mobile.matches
                || !scatteredFits();
        }

        // The rail is laid out (opacity 0) even while closed, so it can be measured
        // either way. Scrolling is only right once the actions stop fitting: while
        // they fit they are spread evenly, and space-evenly in a scroll container
        // parks the leading action before the scrollable start, out of reach.
        function measure() {
            rail.classList.toggle('is-scrollable', rail.scrollWidth > rail.clientWidth + 1);
            // A scroll container clips the panels, so they anchor to the viewport
            // under the rail instead of hanging off it.
            rail.style.setProperty(
                '--dlux-titlebar-rail-panel-top',
                Math.round(rail.getBoundingClientRect().bottom + 8) + 'px'
            );
        }

        function setOpen(next) {
            open = grouped && next;
            rail.classList.toggle('show', open);
            if (toggle) {
                toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            }
            if (open) {
                measure();
            }
        }

        function applyGrouping(next) {
            if (next === grouped) {
                return;
            }
            if (next) {
                items.forEach(function (node) {
                    anchor(node);
                    rail.appendChild(node);
                });
            } else {
                // Reverse order: each node goes back after its own placeholder, so
                // restoring the last one first cannot land it inside a sibling that is
                // still away.
                items.slice().reverse().forEach(function (node) {
                    const placeholder = node.__dluxRailAnchor;
                    if (placeholder && placeholder.parentNode) {
                        placeholder.parentNode.insertBefore(node, placeholder.nextSibling);
                    }
                });
            }
            grouped = next;
            titlebar.setAttribute('data-titlebar-actions-grouped', next ? 'true' : 'false');
            rail.classList.toggle('is-grouped', next);
            if (!next) {
                setOpen(false);
            }
            if (typeof window.__dluxSyncTitlebar === 'function') {
                window.__dluxSyncTitlebar();
            }
        }

        let badge = null;
        items.some(function (node) {
            badge = node.matches('[data-dlux-notifications-badge]')
                ? node
                : node.querySelector('[data-dlux-notifications-badge]');
            return !!badge;
        });

        return {
            toggle: toggle,
            badge: badge,
            isGrouped: function () { return grouped; },
            isOpen: function () { return open; },
            setOpen: setOpen,
            sync: function () {
                applyGrouping(shouldGroup());
                if (grouped) {
                    measure();
                }
            },
        };
    }

    // The bell's unread badge is out of sight while the rail is closed, so mirror the
    // unread state onto the caret that now stands in for it.
    function watchUnread(rail) {
        const badge = rail.badge;
        if (!rail.toggle || !badge) {
            return function () {};
        }
        function sync() {
            const unread = rail.isGrouped()
                && !badge.classList.contains('d-none')
                && badge.textContent.trim() !== '';
            rail.toggle.setAttribute('data-dlux-rail-alert', unread ? 'true' : 'false');
        }
        new MutationObserver(sync).observe(badge, {
            attributes: true,
            attributeFilter: ['class'],
            childList: true,
            characterData: true,
            subtree: true,
        });
        return sync;
    }

    function start() {
        const titlebar = document.querySelector('.titlebar');
        const element = document.querySelector('[data-dlux-titlebar-rail]');
        if (!titlebar || !element) {
            return;
        }
        const rail = create(titlebar, element);
        if (!rail) {
            return;
        }
        const syncUnread = watchUnread(rail);

        function syncAll() {
            rail.sync();
            syncUnread();
        }

        let frame = 0;
        function schedule() {
            window.cancelAnimationFrame(frame);
            frame = window.requestAnimationFrame(syncAll);
        }

        if (rail.toggle) {
            rail.toggle.addEventListener('click', function (event) {
                event.stopPropagation();
                rail.setOpen(!rail.isOpen());
            });
        }

        // Anything inside the rail counts as inside: the notification panel and the
        // search box live there, and closing the rail would unmount them mid-use.
        document.addEventListener('click', function (event) {
            if (!rail.isOpen() || element.contains(event.target)) {
                return;
            }
            if (rail.toggle && rail.toggle.contains(event.target)) {
                return;
            }
            // The tour drives the page from its own overlay while the rail is held
            // open for it; those clicks are not "outside".
            if (event.target.closest('#tutorial-controls, .driver-popover, .driver-overlay')) {
                return;
            }
            rail.setOpen(false);
        });

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && rail.isOpen()) {
                rail.setOpen(false);
            }
        });

        // The rail and the user hub both hang off the same corner of the titlebar,
        // so opening one closes the other.
        document.addEventListener('dlux:user-hub-toggled', function (event) {
            if (event.detail && event.detail.open) {
                rail.setOpen(false);
            }
        });

        syncAll();
        // System Settings previews the layout selector by rewriting the attribute on
        // the live titlebar.
        new MutationObserver(schedule).observe(titlebar, {
            attributes: true,
            attributeFilter: ['data-titlebar-actions-layout'],
        });
        window.addEventListener('resize', schedule);
        window.addEventListener('load', schedule);
        if (document.fonts && typeof document.fonts.ready === 'object') {
            document.fonts.ready.then(schedule).catch(function () {});
        }

        // The tutorial walks the individual actions, which are unreachable while the
        // rail is closed, so it opens the rail for the duration of the tour.
        window.__dluxTitlebarRail = {
            isGrouped: rail.isGrouped,
            isOpen: rail.isOpen,
            open: function () { rail.setOpen(true); },
            close: function () { rail.setOpen(false); },
            sync: syncAll,
        };
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
}());
