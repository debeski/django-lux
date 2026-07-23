(function () {
    var root = document.querySelector('[data-control-link]');
    if (!root) return;
    var statusUrl = root.getAttribute('data-status-url');
    // A pending pairing renders a warning alert with a Cancel control.
    var wasPending = root.querySelector('.alert-warning form') !== null;
    if (!wasPending || !statusUrl) return;

    function poll() {
        fetch(statusUrl, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (data) {
                if (!data || !data.link) return;
                // Once the pairing reaches a terminal state, reload so the full
                // server-rendered status card (or error) is accurate.
                if (!data.link.pending) { window.location.reload(); }
            })
            .catch(function () {});
    }

    setInterval(poll, 3000);
})();
