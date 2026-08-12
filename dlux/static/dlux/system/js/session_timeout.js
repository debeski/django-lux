/*
 * Dlux inactivity timeout (DSRP-1: external asset, no inline JS, reads config
 * from window globals seeded by base_head.js).
 *
 * Driven by the admin auth_config toggle:
 *   window.DLUX_CONFIG.inactivity_timeout_enabled  (bool)
 *   window.DLUX_CONFIG.inactivity_timeout_minutes  (int, minutes)
 *
 * Real user input resets a client-side idle clock. A countdown modal appears
 * ~30s before expiry with a "Stay signed in" dismiss button that clears the
 * timer AND pings the keepalive endpoint so the server-side backstop
 * (DluxMiddleware) stays in sync. On expiry the user is signed out (POST to the
 * logout view) and routed to the idle session-ended interstitial.
 */
(function () {
    'use strict';

    var config = window.DLUX_CONFIG || {};
    if (!config.inactivity_timeout_enabled) {
        return;
    }

    var minutes = parseInt(config.inactivity_timeout_minutes, 10);
    if (!minutes || minutes < 1) { minutes = 10; }

    var TIMEOUT_MS = minutes * 60 * 1000;
    // Warn 30s before expiry (or halfway for very short windows — the field
    // minimum is 1 minute, so this is normally a flat 30s).
    var WARN_MS = Math.min(30 * 1000, Math.floor(TIMEOUT_MS / 2));
    // Throttle server keepalive pings so active single-page use keeps the
    // server clock fresh without a request per keystroke.
    var PING_MS = Math.max(30 * 1000, Math.floor(TIMEOUT_MS / 2));
    var _u = window.dluxEndpoint || function (_name, _params, fallbackPath) {
        return window.dluxUrl ? window.dluxUrl(fallbackPath) : fallbackPath;
    };
    var KEEPALIVE_URL = _u('sessionKeepalive', null, '/accounts/session-keepalive/');
    var LOGOUT_URL = _u('logout', null, '/accounts/logout/');
    var ENDED_URL = _u('sessionEnded', null, '/accounts/session-ended/') + '?reason=idle_timeout';

    var strings = window.DLUX_STRINGS || {};
    function s(key, fallback) {
        var value = strings[key];
        return (typeof value === 'string' && value.length) ? value : fallback;
    }

    var lastActivity = Date.now();
    var lastPing = Date.now();
    var expiring = false;
    var tickTimer = null;
    var modal = null;
    var countdownEl = null;
    var messageTemplate = s('session_timeout_warning_message', 'You will be signed out due to inactivity in {seconds} seconds.');

    function readCookie(name) {
        var match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
        return match ? decodeURIComponent(match[1]) : '';
    }

    function pingKeepalive() {
        lastPing = Date.now();
        try {
            fetch(KEEPALIVE_URL, {
                method: 'GET',
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                cache: 'no-store',
            }).catch(function () {});
        } catch (_e) { /* offline / blocked — the client clock still governs UX */ }
    }

    function signOut() {
        if (expiring) { return; }
        expiring = true;
        stopModal();
        // Definitive sign-out via POST (Django requires POST for logout), landing
        // on the idle interstitial regardless of any background request that may
        // have refreshed the server clock.
        var form = document.createElement('form');
        form.method = 'POST';
        form.action = LOGOUT_URL;
        form.style.display = 'none';
        var token = readCookie('csrftoken');
        if (!token) {
            var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
            token = input ? input.value : '';
        }
        form.innerHTML =
            '<input type="hidden" name="csrfmiddlewaretoken">' +
            '<input type="hidden" name="next">';
        form.children[0].value = token;
        form.children[1].value = ENDED_URL;
        document.body.appendChild(form);
        if (token) {
            form.submit();
        } else {
            // No CSRF token available — fall back to the interstitial; the server
            // middleware backstop finishes the sign-out.
            window.location.href = ENDED_URL;
        }
    }

    function buildModal() {
        if (modal) { return; }
        modal = document.createElement('div');
        modal.className = 'dlux-idle-modal';
        modal.setAttribute('role', 'alertdialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-labelledby', 'dlux-idle-title');
        modal.setAttribute('aria-describedby', 'dlux-idle-message');

        var dialog = document.createElement('div');
        dialog.className = 'dlux-idle-modal__dialog';

        var title = document.createElement('h2');
        title.className = 'dlux-idle-modal__title';
        title.id = 'dlux-idle-title';
        title.textContent = s('session_timeout_warning_title', 'Still there?');

        var message = document.createElement('p');
        message.className = 'dlux-idle-modal__message';
        message.id = 'dlux-idle-message';

        countdownEl = document.createElement('span');
        countdownEl.className = 'dlux-idle-modal__count';
        message.appendChild(countdownEl);

        var actions = document.createElement('div');
        actions.className = 'dlux-idle-modal__actions';

        // Reuse the app's theme-skinned Bootstrap button classes so the modal
        // follows every theme (light/dark/mono/…) without bespoke colour rules.
        var stayBtn = document.createElement('button');
        stayBtn.type = 'button';
        stayBtn.className = 'dlux-idle-modal__btn btn btn-primary';
        stayBtn.textContent = s('session_timeout_stay_button', 'Stay signed in');
        stayBtn.addEventListener('click', dismiss);

        var outBtn = document.createElement('button');
        outBtn.type = 'button';
        outBtn.className = 'dlux-idle-modal__btn btn btn-secondary';
        outBtn.textContent = s('session_timeout_signout_button', 'Sign out now');
        outBtn.addEventListener('click', signOut);

        actions.appendChild(stayBtn);
        actions.appendChild(outBtn);
        dialog.appendChild(title);
        dialog.appendChild(message);
        dialog.appendChild(actions);
        modal.appendChild(dialog);
        document.body.appendChild(modal);
        stayBtn.focus();
    }

    function renderCountdown(secondsLeft) {
        if (!modal) { buildModal(); }
        modal.classList.add('dlux-idle-modal--open');
        if (countdownEl) {
            countdownEl.textContent = String(Math.max(0, secondsLeft));
        }
        // Rebuild the message so the {seconds} placeholder wraps the live count.
        var message = document.getElementById('dlux-idle-message');
        if (message && message.dataset.built !== 'true') {
            var parts = messageTemplate.split('{seconds}');
            message.textContent = parts[0] || '';
            message.appendChild(countdownEl);
            if (parts.length > 1) {
                message.appendChild(document.createTextNode(parts[1]));
            }
            message.dataset.built = 'true';
        }
    }

    function stopModal() {
        if (modal) {
            modal.classList.remove('dlux-idle-modal--open');
        }
    }

    function dismiss() {
        registerActivity(true);
        stopModal();
    }

    function registerActivity(force) {
        lastActivity = Date.now();
        if (expiring) { return; }
        stopModal();
        if (force || (Date.now() - lastPing) > PING_MS) {
            pingKeepalive();
        }
    }

    function tick() {
        if (expiring) { return; }
        var idle = Date.now() - lastActivity;
        var remaining = TIMEOUT_MS - idle;
        if (remaining <= 0) {
            signOut();
            return;
        }
        if (remaining <= WARN_MS) {
            renderCountdown(Math.ceil(remaining / 1000));
        }
    }

    var ACTIVITY_EVENTS = ['mousedown', 'keydown', 'touchstart', 'scroll', 'mousemove'];
    var lastActivityTick = 0;
    function onActivity() {
        // Throttle hard: scroll/mousemove fire dozens of times per second, but the
        // idle window is minutes — doing anything per-event just janks scrolling.
        // A single timestamp compare per event is all these listeners cost now.
        var now = Date.now();
        if (now - lastActivityTick < 1000) {
            return;
        }
        lastActivityTick = now;
        // Ignore activity while the warning modal is open so clicking its own
        // buttons doesn't silently reset the clock; the buttons handle intent.
        if (modal && modal.classList.contains('dlux-idle-modal--open')) {
            return;
        }
        registerActivity(false);
    }

    function start() {
        ACTIVITY_EVENTS.forEach(function (evt) {
            window.addEventListener(evt, onActivity, { passive: true });
        });
        tickTimer = window.setInterval(tick, 1000);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
