// Layout decides some of the other ribbon settings, so the Settings step greys
// out the ones the chosen layout has already answered: compact is a single row,
// so it has no title to show.
// Disabled inputs are not submitted, so the stored value is left untouched and
// comes back when a layout that uses it is chosen again.
(function () {
    const LAYOUT = 'ribbon_layout';
    const DECIDED_BY_LAYOUT = {
        compact: ['ribbon_title'],
        stacked: [],
        default: [],
    };

    function currentLayout(root) {
        const checked = root.querySelector(`input[name="${LAYOUT}"]:checked`);
        return checked ? checked.value : 'default';
    }

    function apply(root) {
        const decided = DECIDED_BY_LAYOUT[currentLayout(root)] || [];
        root.querySelectorAll('[data-dlux-ribbon-dependent]').forEach(function (row) {
            const name = row.getAttribute('data-dlux-ribbon-dependent');
            const off = decided.includes(name);
            row.classList.toggle('dlux-ribbon-setting-disabled', off);
            row.querySelectorAll('input, select, button').forEach(function (control) {
                control.disabled = off;
            });
        });
    }

    function init(root) {
        if (!root || !root.querySelector(`input[name="${LAYOUT}"]`)) {
            return;
        }
        apply(root);
    }

    document.addEventListener('change', function (event) {
        if (event.target && event.target.name === LAYOUT) {
            const root = event.target.closest('form') || document;
            apply(root);
        }
    });

    // The settings form arrives in a dynamic modal, so it is not in the DOM at
    // load; re-run whenever one is inserted. `shown.bs.modal` is the dialog
    // opening, which usually beats the fetch that fills it — the content event is
    // the one that means the form is actually there.
    document.addEventListener('shown.bs.modal', function (event) {
        init(event.target);
    });
    document.addEventListener('dlux:modal-content-loaded', function (event) {
        init(event.target);
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { init(document); });
    } else {
        init(document);
    }
})();
