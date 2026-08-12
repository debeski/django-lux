(function () {
    var root = document.querySelector('[data-control-link]');
    if (!root) return;
    var statusUrl = root.getAttribute('data-status-url');
    var wasPending = root.querySelector('[data-control-link-pending]') !== null;
    if (!wasPending || !statusUrl) return;

    function poll() {
        fetch(statusUrl, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (data) {
                if (!data || !data.link) return;
                if (!data.link.pending) { window.location.reload(); }
            })
            .catch(function () {});
    }

    setInterval(poll, 3000);
})();
