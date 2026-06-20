/*!
 * DjangoLux — The Lux Signature (attribution easter egg)
 * "Let there be light."  MIT License · (c) 2026 DeBeski (micro)
 * https://github.com/debeski/django-lux
 *
 * Purely client-side. No network calls, no telemetry, no tracking — just a
 * quiet, discoverable credit. Safe to remove; nothing depends on it.
 */
(function () {
    'use strict';

    var REPO = 'https://github.com/debeski/django-lux';

    // DSRP-1 data bridge: read the credit from <html data-dlux="..."> — no inline JS.
    var bridge = '';
    try { bridge = document.documentElement.dataset.dlux || ''; } catch (_e) { bridge = ''; }

    // bridge looks like: "DjangoLux 1.0.3 · github.com/debeski/django-lux"
    var version = '';
    var match = /DjangoLux\s+([^\s·]+)/.exec(bridge);
    if (match) { version = match[1]; }
    var label = 'DjangoLux' + (version ? (' v' + version) : '');

    // ── Layer 1: one quiet styled console line on load ──
    try {
        if (window.console && typeof console.log === 'function') {
            console.log(
                '%c✦ ' + label + ' %c— let there be light.  %c' + REPO,
                'color:#ff4055;font-weight:700',
                'color:#172127;font-weight:400',
                'color:#8a939b;font-weight:400'
            );
        }
    } catch (_e) { /* a signature must never throw */ }

    // ── Layer 2: window.lux / window.dlux — type it in the console for the full credit ──
    function burst() {
        try {
            var card =
                '\n  ✦  D J A N G O L U X  ✦\n' +
                '  ──────────────────────────────\n' +
                '  ' + label + '\n' +
                '  Author : DeBeski (micro)\n' +
                '  License: MIT · (c) 2026\n' +
                '  Repo   : ' + REPO + '\n' +
                '  ──────────────────────────────\n' +
                '  Let there be light.\n';
            if (window.console && typeof console.log === 'function') {
                console.log('%c' + card, 'color:#ff4055;font-family:monospace;line-height:1.4');
            }
        } catch (_e) { /* never throw */ }
        // Return a tidy one-liner so the REPL echoes something clean, not `undefined`.
        return '✦ ' + label + ' — let there be light. ' + REPO;
    }

    function isTypingTarget(target) {
        if (!target || target === document.body || target === document.documentElement) {
            return false;
        }
        var tag = (target.tagName || '').toLowerCase();
        return tag === 'input' ||
            tag === 'textarea' ||
            tag === 'select' ||
            target.isContentEditable;
    }

    function showSignatureToast() {
        try {
            burst();

            var previous = document.querySelector('[data-dlux-signature-pop]');
            if (previous) {
                previous.remove();
            }

            var toast = document.createElement('div');
            toast.className = 'dlux-signature-pop';
            toast.setAttribute('data-dlux-signature-pop', 'true');
            toast.setAttribute('role', 'status');
            toast.setAttribute('aria-live', 'polite');

            var mark = document.createElement('span');
            mark.className = 'dlux-signature-pop__mark';
            mark.textContent = '✦';

            var body = document.createElement('span');
            body.className = 'dlux-signature-pop__body';

            var title = document.createElement('strong');
            title.textContent = label;

            var detail = document.createElement('span');
            detail.textContent = 'Let there be light.';

            body.appendChild(title);
            body.appendChild(detail);
            toast.appendChild(mark);
            toast.appendChild(body);
            document.body.appendChild(toast);

            window.setTimeout(function () {
                toast.classList.add('dlux-signature-pop--visible');
            }, 20);

            window.setTimeout(function () {
                toast.classList.remove('dlux-signature-pop--visible');
                window.setTimeout(function () {
                    if (toast.isConnected) {
                        toast.remove();
                    }
                }, 260);
            }, 3200);
        } catch (_e) { /* never throw */ }
    }

    try {
        // enumerable:false → never fires when expanding `window` / Object.keys in DevTools;
        // only when a curious dev explicitly types `lux` (discoverable via autocomplete).
        var descriptor = { get: burst, configurable: true, enumerable: false };
        if (!('lux' in window)) { Object.defineProperty(window, 'lux', descriptor); }
        if (!('dlux' in window)) { Object.defineProperty(window, 'dlux', descriptor); }
    } catch (_e) { /* defineProperty unavailable; the load line already printed */ }

    // ── Layer 7: page key sequence. Typing "dlux" outside inputs reveals a small visual credit. ──
    try {
        var typed = '';
        document.addEventListener('keydown', function (event) {
            if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) {
                return;
            }
            if (isTypingTarget(event.target) || typeof event.key !== 'string' || event.key.length !== 1) {
                return;
            }

            typed = (typed + event.key.toLowerCase()).slice(-4);
            if (typed === 'dlux') {
                typed = '';
                showSignatureToast();
            }
        });
    } catch (_e) { /* never throw */ }
})();
