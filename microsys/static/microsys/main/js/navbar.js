(function () {
    'use strict';

    const HISTORY_KEY = 'microsys.navbar.history.v1';
    const HISTORY_LIMIT = 6;

    function parseJson(text, fallback) {
        try {
            return JSON.parse(text || '');
        } catch (error) {
            return fallback;
        }
    }

    function normalizedPath(value) {
        try {
            const path = new URL(value || window.location.href, window.location.origin).pathname || '/';
            return path === '/' ? path : path.replace(/\/+$/, '');
        } catch (error) {
            return '';
        }
    }

    function currentLanguage() {
        return String(document.documentElement.getAttribute('lang') || 'en')
            .trim()
            .toLowerCase()
            .replace(/_/g, '-')
            .replace(/[^a-z0-9-]/g, '') || 'en';
    }

    function readHistory() {
        try {
            const entries = parseJson(sessionStorage.getItem(HISTORY_KEY), []);
            return Array.isArray(entries) ? entries : [];
        } catch (error) {
            return [];
        }
    }

    function writeHistory(entries) {
        try {
            sessionStorage.setItem(HISTORY_KEY, JSON.stringify(entries.slice(-HISTORY_LIMIT)));
        } catch (error) {
            return;
        }
    }

    function trackCurrentPage(navbar) {
        const path = normalizedPath(navbar.dataset.navbarPath);
        const label = String(navbar.dataset.navbarLabel || '').trim();
        if (!path || path === '/' || !label) {
            return readHistory();
        }
        const language = currentLanguage();
        const existing = readHistory().find((entry) => normalizedPath(entry.path) === path) || {};
        const labels = { ...(existing.labels || {}) };
        labels[language] = label;
        const entries = readHistory().filter((entry) => normalizedPath(entry.path) !== path);
        entries.push({ path, label, labels });
        writeHistory(entries);
        return entries.slice(-HISTORY_LIMIT);
    }

    function routeLabels(navbar) {
        const labelsData = navbar.querySelector('#ms-navbar-route-labels-data');
        const labels = parseJson(labelsData ? labelsData.textContent : '{}', {});
        return labels && typeof labels === 'object' && !Array.isArray(labels) ? labels : {};
    }

    function makeCrumbElement(crumb, isCurrent) {
        const item = document.createElement('li');
        item.className = `ms-navbar__crumb${isCurrent ? ' is-current' : ''}`;
        item.dataset.navbarCrumb = 'true';

        if (crumb.clickable && crumb.url) {
            const link = document.createElement('a');
            link.href = crumb.url;
            link.textContent = crumb.label;
            if (isCurrent) {
                link.setAttribute('aria-current', 'page');
            }
            item.appendChild(link);
            return item;
        }

        const label = document.createElement('span');
        label.textContent = crumb.label;
        if (isCurrent) {
            label.setAttribute('aria-current', 'page');
        }
        item.appendChild(label);
        return item;
    }

    function renderTrail(navbar, crumbs) {
        const trail = navbar.querySelector('[data-navbar-trail]');
        if (!trail) {
            return;
        }
        const fragment = document.createDocumentFragment();
        crumbs.forEach((crumb, index) => {
            fragment.appendChild(makeCrumbElement(crumb, index === crumbs.length - 1));
        });
        trail.replaceChildren(fragment);
    }

    function initNavbar(navbar) {
        if (navbar.dataset.navbarBound === 'true') {
            return;
        }
        navbar.dataset.navbarBound = 'true';

        const hierarchyData = navbar.querySelector('#ms-navbar-hierarchy-data');
        const hierarchy = parseJson(hierarchyData ? hierarchyData.textContent : '[]', []);
        const labelsByPath = routeLabels(navbar);
        const root = hierarchy.find((crumb) => crumb && crumb.kind === 'root') || {
            label: '',
            clickable: false,
            url: '',
            kind: 'root',
        };

        function historyCrumbs() {
            const language = currentLanguage();
            return [
                root,
                ...trackCurrentPage(navbar).map((entry) => ({
                    label: labelsByPath[normalizedPath(entry.path)] || (entry.labels && entry.labels[language]) || entry.label || entry.path,
                    url: entry.path,
                    clickable: true,
                    kind: 'history',
                })),
            ];
        }

        function renderMode(mode) {
            const normalizedMode = mode === 'history' ? 'history' : 'hierarchy';
            navbar.dataset.navbarMode = normalizedMode;
            renderTrail(navbar, normalizedMode === 'history' ? historyCrumbs() : hierarchy);
        }

        navbar.__msRenderMode = renderMode;
        renderMode(navbar.dataset.navbarMode);
    }

    function setNavbarMode(mode) {
        document.querySelectorAll('[data-ms-navbar]').forEach((navbar) => {
            initNavbar(navbar);
            navbar.__msRenderMode(mode);
        });
    }

    window.setNavbarMode = setNavbarMode;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            document.querySelectorAll('[data-ms-navbar]').forEach(initNavbar);
        });
    } else {
        document.querySelectorAll('[data-ms-navbar]').forEach(initNavbar);
    }
})();
