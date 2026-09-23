// A reveal toggle on every password field, added by the page rather than by
// each template.
//
// Password inputs come from templates, from crispy-rendered forms and from
// Django widgets (`forms.PasswordInput`), and they arrive in dynamic modals long
// after load. Asking each of those to opt in would mean finding them all now and
// remembering them for ever, so this attaches to `input[type="password"]`
// wherever it appears — including nodes added later — and a field that must not
// offer it opts OUT with `data-dlux-no-reveal`.
//
// The input keeps its own classes and validation: only its `type` changes, which
// is what password managers and autofill already expect.
(function () {
    'use strict';

    const ATTACHED = 'dluxRevealAttached';

    function labels() {
        const data = document.body ? document.body.dataset : {};
        return {
            show: data.dluxRevealShow || 'Show password',
            hide: data.dluxRevealHide || 'Hide password',
        };
    }

    function setState(input, button, revealed) {
        const text = labels();
        input.type = revealed ? 'text' : 'password';
        button.setAttribute('aria-pressed', revealed ? 'true' : 'false');
        button.setAttribute('aria-label', revealed ? text.hide : text.show);
        button.title = revealed ? text.hide : text.show;
        const icon = button.firstElementChild;
        if (icon) { icon.className = revealed ? 'bi bi-eye-slash' : 'bi bi-eye'; }
    }

    function attach(input) {
        if (!input || input.dataset[ATTACHED] === 'true') { return; }
        if (input.type !== 'password' || 'dluxNoReveal' in input.dataset) { return; }
        input.dataset[ATTACHED] = 'true';

        // Wrap rather than restyle: the input keeps whatever layout its form
        // gives it, and the button is positioned against this wrapper alone.
        const wrapper = document.createElement('span');
        wrapper.className = 'dlux-reveal';
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);

        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'dlux-reveal__toggle';
        // Not a tab stop: it sits between the password field and the submit
        // button, and a keyboard user typing a password should reach submit next.
        button.tabIndex = -1;
        button.appendChild(document.createElement('i'));
        wrapper.appendChild(button);
        setState(input, button, false);

        button.addEventListener('click', function (event) {
            event.preventDefault();
            const revealed = input.type === 'password';
            // Restore the caret: changing `type` moves it to the end in some
            // browsers, which is maddening mid-correction.
            const start = input.selectionStart;
            const end = input.selectionEnd;
            setState(input, button, revealed);
            input.focus();
            try { input.setSelectionRange(start, end); } catch (_error) { /* not all types allow it */ }
        });

        // Never leave a password on screen once the field is done with: a form
        // that fails validation re-renders, but a revealed value would otherwise
        // stay visible behind the error.
        input.form?.addEventListener('submit', function () {
            if (input.type === 'text') { setState(input, button, false); }
        });
    }

    function scan(root) {
        const scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('input[type="password"]').forEach(attach);
    }

    function watch() {
        if (typeof MutationObserver !== 'function') { return; }
        new MutationObserver(function (records) {
            records.forEach(function (record) {
                record.addedNodes.forEach(function (node) {
                    if (node.nodeType !== 1) { return; }
                    if (node.matches && node.matches('input[type="password"]')) { attach(node); }
                    scan(node);
                });
            });
        }).observe(document.documentElement, { childList: true, subtree: true });
    }

    function boot() {
        scan(document);
        watch();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
}());
