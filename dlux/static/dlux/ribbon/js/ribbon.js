document.addEventListener('change', function (event) {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) {
        return;
    }

    const form = target.closest('form.dlux-ribbon[data-dlux-ribbon-autosubmit="true"]');
    if (!form) {
        return;
    }
    if (target.multiple || target.disabled || target.dataset.dluxNoAutosubmit === 'true') {
        return;
    }

    form.submit();
});

// The advanced panel remembers whether it was left open, per list page, so
// paginating or re-applying a filter does not collapse it again.
(function () {
    const STORAGE_PREFIX = 'dluxRibbonAdvanced:';

    function storageKey(panel) {
        return `${STORAGE_PREFIX}${window.location.pathname}#${panel.id}`;
    }

    function read(key) {
        try {
            return localStorage.getItem(key);
        } catch (_error) {
            return null;
        }
    }

    function write(key, value) {
        try {
            localStorage.setItem(key, value);
        } catch (_error) {
            // Private-browsing quota failures must not break the ribbon.
        }
    }

    function syncToggles(panel, expanded) {
        const selector = `[data-bs-toggle="collapse"][data-bs-target="#${CSS.escape(panel.id)}"]`;
        document.querySelectorAll(selector).forEach(function (toggle) {
            toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        });
    }

    function init() {
        const panels = new Set();
        document.querySelectorAll('button.dlux-ribbon-toggle[data-bs-target]').forEach(function (toggle) {
            const panel = document.querySelector(toggle.getAttribute('data-bs-target'));
            if (panel && panel.id) {
                panels.add(panel);
            }
        });

        panels.forEach(function (panel) {
            // A server-rendered `show` means an advanced field is actually
            // filtering; that outranks a stored "collapsed", which would
            // otherwise hide a filter that is in effect. The stored preference
            // is left untouched so it still applies once the filter is cleared.
            if (!panel.classList.contains('show') && read(storageKey(panel)) === 'true') {
                panel.classList.add('show');
                syncToggles(panel, true);
            }

            panel.addEventListener('shown.bs.collapse', function () {
                write(storageKey(panel), 'true');
                syncToggles(panel, true);
            });
            panel.addEventListener('hidden.bs.collapse', function () {
                write(storageKey(panel), 'false');
                syncToggles(panel, false);
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
