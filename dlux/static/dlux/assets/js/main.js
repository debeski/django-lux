(function () {
    function initialize(form) {
        if (form.dataset.managedAssetReady === 'true') return;
        const kind = form.querySelector('[name="kind"]');
        const fields = form.querySelector('[data-managed-font-fields]');
        if (!kind || !fields) return;
        form.dataset.managedAssetReady = 'true';
        const sync = function () {
            fields.hidden = kind.value !== 'font';
        };
        kind.addEventListener('change', sync);
        sync();
    }

    function initializeAll(root) {
        if (root.matches && root.matches('[data-managed-asset-form]')) initialize(root);
        if (root.querySelectorAll) root.querySelectorAll('[data-managed-asset-form]').forEach(initialize);
    }

    initializeAll(document);
    if (window.dluxManagedAssetObserver) return;
    window.dluxManagedAssetObserver = new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            mutation.addedNodes.forEach(initializeAll);
        });
    });
    window.dluxManagedAssetObserver.observe(document.body, { childList: true, subtree: true });
}());
