/*
 * Global confirm-password prompt (DSRP-1: external asset, no inline JS).
 *
 * window.dluxConfirmPassword({
 *   title, description|message,   // dynamic heading + body copy
 *   confirmLabel,                 // confirm button text
 *   requirePassword,              // show + require the current-password field
 *   danger,                       // red icon + danger confirm button (destructive)
 *   icon,                         // bootstrap icon class override
 *   onConfirm(password, { showError, showSuccess })  // may return a Promise;
 *                                 //   resolve false to keep the modal open
 * })
 *
 * Drives the single #dluxConfirmModal partial rendered in base.html. Reused by
 * the profile security actions (via showConfirmation) and the admin panel
 * force-password command, so every "confirm with your password" prompt shares
 * one design and behaviour.
 */
(function () {
    'use strict';

    function q(root, sel) { return root ? root.querySelector(sel) : null; }

    function dluxConfirmPassword(config) {
        config = config || {};
        var modalEl = document.querySelector('[data-dlux-confirm-modal]');
        if (!modalEl || !window.bootstrap) { return; }

        var titleEl = q(modalEl, '[data-dlux-confirm-title]');
        var descEl = q(modalEl, '[data-dlux-confirm-description]');
        var alertEl = q(modalEl, '[data-dlux-confirm-alert]');
        var iconEl = q(modalEl, '[data-dlux-confirm-icon]');
        var wrapEl = q(modalEl, '[data-dlux-confirm-password-wrap]');
        var passwordEl = q(modalEl, '[data-dlux-confirm-password]');
        var errorEl = q(modalEl, '[data-dlux-confirm-error]');
        var successEl = q(modalEl, '[data-dlux-confirm-success]');

        var requirePassword = !!config.requirePassword;
        var danger = !!config.danger;
        var description = config.description != null ? config.description : (config.message || '');

        if (titleEl && config.title != null) { titleEl.textContent = config.title; }
        if (descEl) { descEl.textContent = description; }
        if (alertEl) {
            alertEl.classList.toggle('alert-danger', danger);
            alertEl.classList.toggle('alert-warning', !danger);
        }
        if (iconEl) {
            iconEl.className = 'bi flex-shrink-0 mt-1 ' + (config.icon
                || (danger ? 'bi-exclamation-triangle-fill' : 'bi-exclamation-triangle-fill'));
        }
        if (wrapEl) { wrapEl.classList.toggle('d-none', !requirePassword); }
        if (passwordEl) {
            passwordEl.value = '';
            passwordEl.required = requirePassword;
            passwordEl.classList.remove('is-invalid');
        }

        function hide(el) { if (el) { el.textContent = ''; el.classList.add('d-none'); } }
        function showError(msg) {
            hide(successEl);
            if (errorEl) { errorEl.textContent = msg || ''; errorEl.classList.toggle('d-none', !msg); }
            if (requirePassword && passwordEl) { passwordEl.classList.add('is-invalid'); passwordEl.focus(); }
        }
        function showSuccess(msg) {
            hide(errorEl);
            if (successEl) { successEl.textContent = msg || ''; successEl.classList.toggle('d-none', !msg); }
        }
        hide(errorEl);
        hide(successEl);

        // Fresh submit button each open so listeners never stack.
        var oldSubmit = q(modalEl, '[data-dlux-confirm-submit]');
        var submitEl = oldSubmit.cloneNode(true);
        oldSubmit.parentNode.replaceChild(submitEl, oldSubmit);
        submitEl.textContent = config.confirmLabel || submitEl.textContent;
        submitEl.classList.toggle('btn-danger', danger);
        submitEl.classList.toggle('btn-primary', !danger);

        var modal = window.bootstrap.Modal.getInstance(modalEl) || new window.bootstrap.Modal(modalEl);

        function setBusy(busy) {
            submitEl.disabled = busy;
            if (passwordEl) { passwordEl.disabled = busy; }
            if (busy) {
                submitEl.dataset.originalHtml = submitEl.innerHTML;
                submitEl.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>' + submitEl.textContent.trim();
            } else if (submitEl.dataset.originalHtml) {
                submitEl.innerHTML = submitEl.dataset.originalHtml;
                delete submitEl.dataset.originalHtml;
            }
        }

        function attempt() {
            var password = passwordEl ? passwordEl.value.trim() : '';
            if (requirePassword && !password) {
                showError((passwordEl && passwordEl.dataset.requiredMsg) || 'Please enter your current password.');
                return;
            }
            hide(errorEl);
            if (typeof config.onConfirm !== 'function') { modal.hide(); return; }

            var result = config.onConfirm(password, { showError: showError, showSuccess: showSuccess });
            if (!result || typeof result.then !== 'function') {
                if (result !== false) { modal.hide(); }
                return;
            }
            setBusy(true);
            result
                .then(function (shouldClose) { if (shouldClose !== false) { modal.hide(); } })
                .catch(function (err) { showError(err && err.message); })
                .finally(function () { setBusy(false); });
        }

        submitEl.addEventListener('click', attempt);
        if (requirePassword && passwordEl) {
            function onKey(e) { if (e.key === 'Enter') { e.preventDefault(); attempt(); } }
            function onInput() { passwordEl.classList.remove('is-invalid'); hide(errorEl); }
            passwordEl.addEventListener('keydown', onKey);
            passwordEl.addEventListener('input', onInput);
            modalEl.addEventListener('hidden.bs.modal', function cleanup() {
                passwordEl.removeEventListener('keydown', onKey);
                passwordEl.removeEventListener('input', onInput);
                modalEl.removeEventListener('hidden.bs.modal', cleanup);
            });
        }

        modal.show();
        if (requirePassword && passwordEl) {
            window.setTimeout(function () { passwordEl.focus(); }, 150);
        }
        return modal;
    }

    window.dluxConfirmPassword = dluxConfirmPassword;
})();
