// Weather widgets: the titlebar action, the user-hub and floating indicators,
// and the dashboard card. The panel is placed by CSS the way the notifications
// panel is (under its trigger, or fixed under the header on phones), so this
// only fetches readings, fills them in, and opens and closes the panel.
(function () {
    'use strict';
    if (window.dluxWeatherLoaded) return;
    window.dluxWeatherLoaded = true;
    const pending = new Map();
    // A 202 means a worker is fetching the first reading; ask again shortly.
    const PENDING_RETRY_MS = 3000;
    const PENDING_RETRIES = 6;
    const t = (key, fallback) => (window.DLUX_STRINGS || {})[key] || fallback;

    function text(root, selector, value) {
        root.querySelectorAll(selector).forEach((node) => { node.textContent = value; });
    }

    async function refresh(widget) {
        if (!widget.isConnected || widget.dataset.weatherDisabled) return;
        const selected = widget.dataset.weatherLocation;
        // The base URL may already carry a settings-preview token.
        const address = new URL(widget.dataset.weatherUrl, window.location.origin);
        address.searchParams.set('location', selected);
        const url = address.pathname + address.search;
        let entry = pending.get(url);
        if (!entry || Date.now() - entry.at > 60000) {
            entry = {
                at: Date.now(),
                promise: fetch(url, { headers: { Accept: 'application/json' } }).then(async (response) => {
                    if (response.status === 202) throw new Error('pending');
                    if (!response.ok) throw new Error(response.status === 404 ? 'disabled' : 'unavailable');
                    return response.json();
                }),
            };
            pending.set(url, entry);
        }
        try {
            const data = await entry.promise;
            if (widget.dataset.weatherLocation !== selected) return;
            delete widget.dataset.weatherPendingTries;
            text(widget, '[data-weather-temperature]', data.temperature + data.unit);
            text(widget, '[data-weather-feels]', data.feels_like + data.unit);
            text(widget, '[data-weather-description]', data.description);
            widget.querySelectorAll('[data-weather-icon]').forEach((node) => { node.className = 'bi bi-' + data.icon; });
            const label = `${data.location}: ${data.description}, ${data.temperature}${data.unit}`;
            const button = widget.querySelector('[data-weather-toggle]');
            if (button) {
                button.setAttribute('aria-label', label);
                button.setAttribute('data-dlux-tooltip', label);
            }
            const when = new Date(data.observed_at * 1000).toLocaleString(document.documentElement.lang || undefined);
            text(widget, '[data-weather-status]',
                (data.stale ? t('weather_stale', 'Last available reading') : t('weather_updated', 'Updated')) + ': ' + when);
        } catch (error) {
            if (widget.dataset.weatherLocation !== selected) return;
            if (error.message === 'pending') {
                pending.delete(url);
                const tries = Number(widget.dataset.weatherPendingTries || 0) + 1;
                widget.dataset.weatherPendingTries = String(tries);
                if (tries <= PENDING_RETRIES) {
                    text(widget, '[data-weather-status]', t('weather_loading', 'Loading weather…'));
                    window.setTimeout(() => refresh(widget), PENDING_RETRY_MS);
                    return;
                }
            }
            if (error.message === 'disabled') {
                widget.dataset.weatherDisabled = 'true';
                widget.hidden = true;
                return;
            }
            text(widget, '[data-weather-status]', t('weather_unavailable', 'Weather is temporarily unavailable.'));
            text(widget, '[data-weather-description]', t('weather_unavailable_short', 'Unavailable'));
            const button = widget.querySelector('[data-weather-toggle]');
            if (button) button.setAttribute('aria-label', t('weather_unavailable', 'Weather is temporarily unavailable.'));
        }
    }

    // ── The floating bubble ───────────────────────────────────────────────
    // Dragged like an assistant launcher: it snaps to the nearer side, the
    // position is kept per user (a preference, so it follows them), and the
    // panel opens away from the edges the bubble sits against.
    const FLOAT_MARGIN = 12;
    const DRAG_THRESHOLD = 6;
    const FLOAT_PREFERENCE = 'weather_float_position';

    function clamp(value, low, high) {
        return Math.min(Math.max(value, low), Math.max(low, high));
    }

    function orient(widget) {
        const rect = widget.getBoundingClientRect();
        widget.dataset.weatherDock = rect.left + rect.width / 2 < window.innerWidth / 2 ? 'left' : 'right';
        widget.dataset.weatherRise = rect.top + rect.height / 2 > window.innerHeight / 2 ? 'up' : 'down';
    }

    function place(widget, left, top) {
        const size = widget.offsetWidth;
        widget.classList.add('is-placed');
        widget.style.left = clamp(left, FLOAT_MARGIN, window.innerWidth - size - FLOAT_MARGIN) + 'px';
        widget.style.top = clamp(top, FLOAT_MARGIN, window.innerHeight - size - FLOAT_MARGIN) + 'px';
        orient(widget);
    }

    function placeSaved(widget) {
        const saved = (window.USER_PREFS || {})[FLOAT_PREFERENCE];
        if (!saved || (saved.side !== 'left' && saved.side !== 'right') || !Number.isFinite(saved.y)) {
            orient(widget);
            return;
        }
        const size = widget.offsetWidth;
        const left = saved.side === 'left' ? FLOAT_MARGIN : window.innerWidth - size - FLOAT_MARGIN;
        place(widget, left, clamp(saved.y, 0, 1) * (window.innerHeight - size));
    }

    function savePosition(widget) {
        const rect = widget.getBoundingClientRect();
        const value = {
            side: rect.left + rect.width / 2 < window.innerWidth / 2 ? 'left' : 'right',
            y: Math.round((rect.top / Math.max(1, window.innerHeight - rect.height)) * 1000) / 1000,
        };
        window.USER_PREFS = Object.assign({}, window.USER_PREFS || {}, { [FLOAT_PREFERENCE]: value });
        if (typeof window.updatePreferences === 'function') {
            window.updatePreferences({ [FLOAT_PREFERENCE]: value });
        }
    }

    function setupFloating(widget, button) {
        let start = null;
        let dragging = false;
        if (button.dataset.weatherDragHint) button.title = button.dataset.weatherDragHint;
        placeSaved(widget);
        button.addEventListener('pointerdown', (event) => {
            if (event.button !== 0) return;
            const rect = widget.getBoundingClientRect();
            start = { x: event.clientX, y: event.clientY, left: rect.left, top: rect.top };
            dragging = false;
            button.setPointerCapture(event.pointerId);
        });
        button.addEventListener('pointermove', (event) => {
            if (!start) return;
            const dx = event.clientX - start.x;
            const dy = event.clientY - start.y;
            if (!dragging && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
            if (!dragging) {
                dragging = true;
                widget.classList.add('is-dragging');
                close(widget);
            }
            place(widget, start.left + dx, start.top + dy);
        });
        const finish = () => {
            if (!start) return;
            start = null;
            if (!dragging) return;
            widget.classList.remove('is-dragging');
            const rect = widget.getBoundingClientRect();
            const toLeft = rect.left + rect.width / 2 < window.innerWidth / 2;
            place(widget, toLeft ? FLOAT_MARGIN : window.innerWidth - rect.width - FLOAT_MARGIN, rect.top);
            savePosition(widget);
            // The click that ends a drag must not also open the panel.
            widget.dataset.weatherJustDragged = 'true';
            window.setTimeout(() => { delete widget.dataset.weatherJustDragged; }, 0);
        };
        button.addEventListener('pointerup', finish);
        button.addEventListener('pointercancel', finish);
        button.addEventListener('click', (event) => {
            if (!widget.dataset.weatherJustDragged) return;
            event.stopImmediatePropagation();
            event.preventDefault();
        }, true);
        window.addEventListener('resize', () => {
            if (widget.classList.contains('is-placed')) placeSaved(widget);
            else orient(widget);
        });
    }

    function close(widget) {
        const button = widget.querySelector('[data-weather-toggle]');
        if (!button) return;
        button.setAttribute('aria-expanded', 'false');
        widget.querySelector('[data-weather-panel]').hidden = true;
    }

    function init() {
        document.querySelectorAll('[data-weather-widget]').forEach((widget) => {
            if (widget.dataset.weatherReady) return;
            widget.dataset.weatherReady = 'true';
            const button = widget.querySelector('[data-weather-toggle]');
            if (button && button.hasAttribute('data-weather-draggable')) setupFloating(widget, button);
            if (button) {
                button.addEventListener('click', () => {
                    const panel = widget.querySelector('[data-weather-panel]');
                    const opening = panel.hidden;
                    // Where the bubble sits now decides which way its panel opens.
                    if (opening && button.hasAttribute('data-weather-draggable')) orient(widget);
                    document.querySelectorAll('[data-weather-widget]').forEach(close);
                    panel.hidden = !opening;
                    button.setAttribute('aria-expanded', String(opening));
                });
            }
            // The location picker is a Dlux selector: one radio per location.
            widget.querySelector('[data-weather-select]').addEventListener('change', (event) => {
                if (!event.target.matches('input[type="radio"]') || !event.target.checked) return;
                widget.dataset.weatherLocation = event.target.value;
                text(widget, '[data-weather-temperature], [data-weather-feels]', '—');
                text(widget, '[data-weather-description], [data-weather-status]', t('weather_loading', 'Loading weather…'));
                refresh(widget);
            });
            refresh(widget);
        });
    }

    document.addEventListener('click', (event) => {
        document.querySelectorAll('[data-weather-widget]').forEach((widget) => {
            if (!widget.contains(event.target)) close(widget);
        });
    });
    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape') return;
        document.querySelectorAll('[data-weather-widget]').forEach((widget) => {
            const button = widget.querySelector('[data-weather-toggle][aria-expanded="true"]');
            if (button) {
                close(widget);
                button.focus();
            }
        });
    });
    setInterval(() => {
        if (!document.hidden) document.querySelectorAll('[data-weather-widget]').forEach(refresh);
    }, 900000);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) document.querySelectorAll('[data-weather-widget]').forEach(refresh);
    });
    new MutationObserver(init).observe(document.documentElement, { childList: true, subtree: true });
    init();
}());
