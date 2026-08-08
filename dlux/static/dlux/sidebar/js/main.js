// API Helper - Exposed Globally
window.updatePreferences = function(data) {
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';

    if (!csrfToken) {
        console.error("CSRF token not found, cannot save preferences.");
        return Promise.resolve();
    }

    const url = window.dluxEndpoint
        ? window.dluxEndpoint('preferencesUpdate', null, '/sys/api/preferences/update/')
        : (window.dluxUrl ? window.dluxUrl('/sys/api/preferences/update/') : '/sys/api/preferences/update/');
    return fetch(url, {
        method: "POST",
        headers: {
            "X-CSRFToken": csrfToken,
            "Content-Type": "application/json",
        },
        body: JSON.stringify(data)
    }).then(response => {
        if (!response.ok) {
            console.error("Failed to save preferences:", response.statusText);
        } else if (window.USER_PREFS) {
            Object.assign(window.USER_PREFS, data);
        }
    }).catch(error => {
        console.error("Error updating preferences:", error);
    });
};

// App-owned preferences helpers ------------------------------------------------
// Downstream projects persist their own per-user state under the reserved `app`
// namespace so it survives across browsers/devices, cleanly isolated from
// Dlux's own preference keys.
//
//   window.updateAppPreference('myproject.dashboard.v1', { order: [...] })
//   const layout = window.getAppPreference('myproject.dashboard.v1', {})
//
// updateAppPreference does a targeted, concurrent-safe write (only that one
// namespace is touched) and returns the fetch Promise so callers can react to
// a 413 (payload too large). Pass `null` as the value to clear the namespace.
window.getAppPreference = function (namespace, fallback) {
    const bag = (window.USER_PREFS && window.USER_PREFS.app) || {};
    return Object.prototype.hasOwnProperty.call(bag, namespace) ? bag[namespace] : fallback;
};

window.updateAppPreference = function (namespace, value) {
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';
    if (!csrfToken) {
        console.error("CSRF token not found, cannot save app preference.");
        return Promise.reject(new Error('missing-csrf'));
    }

    const url = window.dluxEndpoint
        ? window.dluxEndpoint('appPreference', { namespace: namespace }, '/sys/api/preferences/app/__namespace__/')
        : (window.dluxUrl ? window.dluxUrl('/sys/api/preferences/app/') : '/sys/api/preferences/app/') + encodeURIComponent(namespace) + '/';
    return fetch(url, {
        method: "POST",
        headers: {
            "X-CSRFToken": csrfToken,
            "Content-Type": "application/json",
        },
        body: JSON.stringify(value === undefined ? null : value)
    }).then(response => {
        if (!response.ok) {
            console.error("Failed to save app preference:", response.statusText);
            return response;
        }
        // Mirror the write into the in-page cache so getAppPreference is fresh.
        if (window.USER_PREFS) {
            if (!window.USER_PREFS.app || typeof window.USER_PREFS.app !== 'object') {
                window.USER_PREFS.app = {};
            }
            if (value === null || value === undefined) {
                delete window.USER_PREFS.app[namespace];
            } else {
                window.USER_PREFS.app[namespace] = value;
            }
        }
        return response;
    }).catch(error => {
        console.error("Error updating app preference:", error);
        throw error;
    });
};

// Declarative auto-persist: any control marked `data-dlux-app-pref="<namespace>"`
// writes its value to that app-pref namespace on change — no per-card JS needed.
//   <select data-dlux-app-pref="sales.catalog_layout"> ...        // scalar value
//   <input type="checkbox" data-dlux-app-pref="myapp.flags"
//          data-dlux-app-pref-field="compact">                     // merge one field
// After persisting, a `dlux:app-pref-changed` event fires on document
// (detail: {namespace, field, value}) so the app can apply the change live.
window.bindAppPrefControls = function (root) {
    root = root || document;
    const controls = root.querySelectorAll('[data-dlux-app-pref]');
    controls.forEach(function (el) {
        if (el.__dluxAppPrefBound) { return; }
        el.__dluxAppPrefBound = true;
        el.addEventListener('change', function () {
            const ns = el.getAttribute('data-dlux-app-pref');
            if (!ns) { return; }
            const field = el.getAttribute('data-dlux-app-pref-field') || null;
            let raw = (el.type === 'checkbox') ? el.checked : el.value;

            let payload;
            let changedValue;
            if (field) {
                const current = window.getAppPreference(ns, {});
                const obj = (current && typeof current === 'object' && !Array.isArray(current))
                    ? Object.assign({}, current) : {};
                obj[field] = raw;
                payload = obj;
                changedValue = raw;
            } else {
                payload = raw;
                changedValue = raw;
            }

            window.updateAppPreference(ns, payload);
            document.dispatchEvent(new CustomEvent('dlux:app-pref-changed', {
                detail: { namespace: ns, field: field, value: changedValue }
            }));
        });
    });
};

document.addEventListener('DOMContentLoaded', function () {
    window.bindAppPrefControls(document);
});

document.addEventListener("DOMContentLoaded", function () {
    const sidebar = document.getElementById("sidebar");
    const sidebarToggle = document.getElementById("sidebarToggle");
    const densityIndicator = document.getElementById("sidebarDensityIndicator");
    const densityPopup = document.getElementById("sidebarDensityPopup");
    const densityOptions = densityPopup ? Array.from(densityPopup.querySelectorAll('[data-sidebar-density-choice]')) : [];

    if (!sidebar) {
        return;
    }

    document.documentElement.classList.remove('dlux-sidebar-precollapse');

    const mobileBreakpoint = 1100;
    const collapseMode = sidebar.dataset.sidebarCollapseMode || 'icons';
    const allowUserDensity = sidebar.dataset.sidebarAllowUserDensity === 'true';

    let isCollapsed = window.USER_PREFS?.sidebar_collapsed;
    if (isCollapsed === undefined) {
        isCollapsed = sidebar.dataset.sessionCollapsed === "true";
    }
    isCollapsed = Boolean(isCollapsed);

    function isMobileViewport() {
        return window.innerWidth < mobileBreakpoint;
    }

    function canShowIconRail() {
        return collapseMode === 'icons' && sidebar.dataset.sidebarShowIcons === 'true';
    }

    function applySidebarDensity(density) {
        const resolvedDensity = density || sidebar.dataset.sidebarDefaultDensity || 'balanced';
        sidebar.setAttribute('data-sidebar-density', resolvedDensity);
        densityOptions.forEach((option) => {
            option.classList.toggle('is-active', option.getAttribute('data-sidebar-density-choice') === resolvedDensity);
        });
    }

    function initializeTooltips() {
        if (!sidebar.classList.contains('collapsed') || !canShowIconRail() || isMobileViewport()) {
            deinitializeTooltips();
            return;
        }

        const sidebarItems = document.querySelectorAll(".sidebar.collapsed .list-group-item, .sidebar.collapsed .accordion-button");
        sidebarItems.forEach(item => {
            const label = item.querySelector("span");
            const tooltipText = label ? label.textContent.trim() : '';
            if (tooltipText) {
                item.setAttribute('data-dlux-sidebar-tooltip', tooltipText);
                item.setAttribute('data-dlux-sidebar-tooltip-placement', 'right');
            }
        });
    }

    function deinitializeTooltips() {
        const sidebarItems = document.querySelectorAll(".sidebar .list-group-item, .sidebar .accordion-button");
        sidebarItems.forEach(item => {
            item.removeAttribute('data-dlux-sidebar-tooltip');
            item.removeAttribute('data-dlux-sidebar-tooltip-placement');
        });
    }

    // The toggle reports the sidebar it controls: `aria-expanded` for assistive
    // tech, `is-collapsed` for the icon's facing direction. Read back off the
    // sidebar's own class rather than the requested value, because the branches
    // below can override the request (mobile, locked_expanded).
    function syncToggleState() {
        if (!sidebarToggle) {
            return;
        }
        const collapsed = sidebar.classList.contains('collapsed');
        sidebarToggle.classList.toggle('is-collapsed', collapsed);
        sidebarToggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        sidebarToggle.classList.add('is-ready');
    }

    function applyCollapsedState(collapsed) {
        applySidebarCollapsedClass(collapsed);
        syncToggleState();
    }

    function applySidebarCollapsedClass(collapsed) {
        if (isMobileViewport()) {
            sidebar.classList.toggle('collapsed', collapsed);
            deinitializeTooltips();
            return;
        }

        if (collapseMode === 'locked_expanded') {
            sidebar.classList.remove('collapsed');
            deinitializeTooltips();
            return;
        }

        sidebar.classList.toggle('collapsed', collapsed);
        initializeTooltips();
        if (!collapsed) {
            deinitializeTooltips();
        }
    }

    function adjustSidebarForWindowSize() {
        applyCollapsedState(isMobileViewport() ? true : isCollapsed);
    }

    adjustSidebarForWindowSize();
    applySidebarDensity((window.USER_PREFS && window.USER_PREFS.sidebar_density) || sidebar.dataset.sidebarDensity || 'balanced');
    window.addEventListener("resize", adjustSidebarForWindowSize);

    if (sidebarToggle) {
        sidebarToggle.addEventListener("click", function () {
            if (!isMobileViewport() && collapseMode === 'locked_expanded') {
                return;
            }

            if (isMobileViewport()) {
                sidebar.classList.toggle("collapsed");
                syncToggleState();
                return;
            }

            isCollapsed = !sidebar.classList.contains('collapsed');
            applyCollapsedState(isCollapsed);
            window.updatePreferences({ sidebar_collapsed: isCollapsed });
            if (window.USER_PREFS) {
                window.USER_PREFS.sidebar_collapsed = isCollapsed;
            }
        });
    }

    const themePopup = document.getElementById('sidebarThemePopup');
    const themeIndicator = document.getElementById('sidebarThemeIndicator');
    const themeArrow = document.getElementById('sidebarThemeArrow');

    function closeThemePopup() {
        if (themePopup) themePopup.classList.remove('show');
        if (themeIndicator) themeIndicator.classList.remove('open');
        if (themeArrow) themeArrow.classList.remove('visible');
    }

    if (densityIndicator && densityPopup) {
        densityIndicator.addEventListener('click', function(event) {
            event.stopPropagation();
            const isOpening = !densityPopup.classList.contains('show');
            densityPopup.classList.toggle('show');
            if (isOpening) closeThemePopup();
        });

        document.addEventListener('click', function(event) {
            if (!densityPopup.contains(event.target) && event.target !== densityIndicator) {
                densityPopup.classList.remove('show');
            }
        });
    }

    densityOptions.forEach((option) => {
        option.addEventListener('click', function() {
            const density = option.getAttribute('data-sidebar-density-choice') || 'balanced';
            applySidebarDensity(density);
            densityPopup.classList.remove('show');
            if (allowUserDensity) {
                window.updatePreferences({ sidebar_density: density });
                if (window.USER_PREFS) {
                    window.USER_PREFS.sidebar_density = density;
                }
            }
        });
    });

    const accordions = document.querySelectorAll('.sidebar .accordion-collapse');
    const openAccordions = window.USER_PREFS?.open_accordions || [];
    openAccordions.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.classList.add('show');
            const btn = document.querySelector(`[data-bs-target="#${id}"]`);
            if (btn) {
                btn.classList.remove('collapsed');
                btn.setAttribute('aria-expanded', 'true');
            }
        }
    });

    function handleSidebarOverflow(event) {
        const scrollContainer = document.querySelector('.sidebar-items-wrapper');
        if (!scrollContainer || sidebar.classList.contains('collapsed')) return;
        if (event && event.type === 'hidden.bs.collapse') return;

        const isOverflowing = scrollContainer.scrollHeight > (scrollContainer.clientHeight + 10);
        if (!isOverflowing) return;

        let priorityAcc = null;
        if (event && event.type === 'shown.bs.collapse') {
            priorityAcc = event.target;
        }
        if (!priorityAcc) {
            priorityAcc = document.querySelector('.sidebar .accordion-collapse.show .list-group-item.active')?.closest('.accordion-collapse');
        }
        if (!priorityAcc) {
            priorityAcc = document.querySelector('.sidebar .accordion-collapse.show');
        }
        if (!priorityAcc) return;

        const openSidebarAccordions = document.querySelectorAll('.sidebar .accordion-collapse.show');
        openSidebarAccordions.forEach(acc => {
            if (acc !== priorityAcc) {
                const bsCollapse = bootstrap.Collapse.getInstance(acc) || new bootstrap.Collapse(acc, { toggle: false });
                bsCollapse.hide();
            }
        });
    }

    function saveAccordionState(event) {
        const openItems = Array.from(document.querySelectorAll('.sidebar .accordion-collapse.show'))
            .map(el => el.id)
            .filter(id => id);

        window.updatePreferences({ open_accordions: openItems });
        if (window.USER_PREFS) {
            window.USER_PREFS.open_accordions = openItems;
        }
        handleSidebarOverflow(event);
    }

    accordions.forEach(acc => {
        acc.addEventListener('shown.bs.collapse', saveAccordionState);
        acc.addEventListener('hidden.bs.collapse', saveAccordionState);
    });

    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(handleSidebarOverflow, 250);
    });

    document.addEventListener("click", function (event) {
        if (!isMobileViewport() || !sidebarToggle) {
            return;
        }

        if (!sidebar.contains(event.target) && !sidebarToggle.contains(event.target) && !sidebar.classList.contains("collapsed")) {
            sidebar.classList.add("collapsed");
            syncToggleState();
        }
    });
});
