// Permission-preset ("Groups") management modal — mirrors the Scope-manager
// pattern (bespoke #groupModal + #groupModalBody, AJAX list<->form<->members
// navigation) but re-executes injected <script> tags the same way the dynamic
// modal does, so the grouped-permission and card-selector widgets initialise.
(function () {
    'use strict';

    var MODAL_ID = 'groupModal';
    var BODY_ID = 'groupModalBody';

    function modalBody() {
        return document.getElementById(BODY_ID);
    }

    // Set innerHTML then re-run any <script> tags it carried (innerHTML never
    // executes scripts on its own). Attributes (incl. src + CSP nonce) are copied.
    function setBody(html) {
        var body = modalBody();
        if (!body) return;
        body.innerHTML = html;
        body.querySelectorAll('script').forEach(function (oldScript) {
            var newScript = document.createElement('script');
            Array.prototype.forEach.call(oldScript.attributes, function (attr) {
                newScript.setAttribute(attr.name, attr.value);
            });
            newScript.textContent = oldScript.textContent;
            oldScript.parentNode.replaceChild(newScript, oldScript);
        });
    }

    function loadView(url) {
        if (!url) return;
        fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (r) { return r.json(); })
            .then(function (d) { if (d && typeof d.html === 'string') setBody(d.html); })
            .catch(function (err) { console.error('dlux groups: load error', err); });
    }

    function submitForm(form) {
        var url = form.dataset.url;
        if (!url) return;
        fetch(url, {
            method: 'POST',
            body: new FormData(form),
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(function (r) { return r.json(); })
            .then(function (d) { if (d && typeof d.html === 'string') setBody(d.html); })
            .catch(function (err) { console.error('dlux groups: submit error', err); });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var openBtn = document.getElementById('btn-manage-groups');
        if (openBtn) {
            openBtn.addEventListener('click', function () {
                var modalEl = document.getElementById(MODAL_ID);
                if (!modalEl) return;
                bootstrap.Modal.getOrCreateInstance(modalEl).show();
                loadView(openBtn.dataset.url);
            });
        }

        // Delegate in-modal navigation (add / edit / members / back) to the body.
        var body = modalBody();
        if (body) {
            body.addEventListener('click', function (e) {
                var nav = e.target.closest('.js-group-nav');
                if (nav) {
                    e.preventDefault();
                    loadView(nav.dataset.url);
                }
            });
        }
    });

    // Delegated form submission for the preset + members forms.
    document.addEventListener('submit', function (e) {
        if (e.target.matches && e.target.matches('.js-group-form')) {
            e.preventDefault();
            submitForm(e.target);
        }
    });
})();
