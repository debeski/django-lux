// Weather widgets: the titlebar action, the user-hub and floating indicators,
// and the dashboard card. The panel is placed by CSS the way the notifications
// panel is (under its trigger, or fixed under the header on phones), so this
// only fetches readings, fills them in, and opens and closes the panel.
(function () {
    'use strict';
    if (window.dluxWeatherLoaded) return;
    window.dluxWeatherLoaded = true;
    const pending = new Map();
    const t = (key, fallback) => (window.DLUX_STRINGS || {})[key] || fallback;

    function text(root, selector, value) {
        root.querySelectorAll(selector).forEach((node) => { node.textContent = value; });
    }

    async function refresh(widget) {
        if (!widget.isConnected || widget.dataset.weatherDisabled) return;
        const selected = widget.dataset.weatherLocation;
        const url = widget.dataset.weatherUrl + '?location=' + encodeURIComponent(selected);
        let entry = pending.get(url);
        if (!entry || Date.now() - entry.at > 60000) {
            entry = {
                at: Date.now(),
                promise: fetch(url, { headers: { Accept: 'application/json' } }).then(async (response) => {
                    if (!response.ok) throw new Error(response.status === 404 ? 'disabled' : 'unavailable');
                    return response.json();
                }),
            };
            pending.set(url, entry);
        }
        try {
            const data = await entry.promise;
            if (widget.dataset.weatherLocation !== selected) return;
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
            if (button) {
                button.addEventListener('click', () => {
                    const panel = widget.querySelector('[data-weather-panel]');
                    const opening = panel.hidden;
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
