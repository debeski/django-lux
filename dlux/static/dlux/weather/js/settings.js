(function () {
    'use strict';
    const t = (key, fallback) => (window.DLUX_STRINGS || {})[key] || fallback;
    function init() {
        document.querySelectorAll('[data-weather-settings]').forEach(root => {
            if (root.dataset.weatherReady) return;
            root.dataset.weatherReady = 'true';
            const form = root.closest('form');
            const field = name => form.querySelector(`[name="weather_${name}"]`);
            const hidden = field('locations');
            const defaultField = field('default_location');
            const builder = root.querySelector('[data-weather-location-builder]');
            const status = root.querySelector('[data-weather-search-status]');
            const chosen = root.querySelector('[data-weather-chosen]');
            const results = root.querySelector('[data-weather-results]');
            const helpers = window.DluxSetupDom;
            const read = () => { try { return JSON.parse(hidden.value || '[]'); } catch (_) { return []; } };
            function sync() {
                const enabled = field('enabled').checked;
                helpers.setDependentFieldEnabled(root.querySelector('[data-weather-dependent]'), enabled, t('weather_disabled_reason', 'Enable weather to configure these settings.'));
                const floating = helpers.getNamedFieldValue(form, 'weather_placement') === 'floating';
                helpers.setDependentFieldEnabled(root.querySelector('[data-weather-corner]'), enabled && floating,
                    enabled ? t('weather_corner_reason', 'Choose Floating placement to change the corner.') : t('weather_disabled_reason', 'Enable weather to configure these settings.'));
            }
            function write(locations) {
                hidden.value = JSON.stringify(locations);
                if (!locations.some(item => item.id === defaultField.value)) defaultField.value = locations[0]?.id || '';
                hidden.dispatchEvent(new Event('change', { bubbles: true }));
                defaultField.dispatchEvent(new Event('change', { bubbles: true }));
            }
            function button(label, callback) {
                const node = document.createElement('button');
                node.type = 'button'; node.className = 'btn btn-sm btn-outline-secondary'; node.textContent = label;
                node.addEventListener('click', callback);
                return node;
            }
            function render() {
                chosen.replaceChildren();
                read().forEach(location => {
                    const row = document.createElement('div');
                    row.className = 'list-group-item d-flex flex-wrap align-items-center gap-2';
                    const name = document.createElement('span'); name.className = 'me-auto'; name.textContent = location.name; row.append(name);
                    if (defaultField.value === location.id) {
                        const badge = document.createElement('span'); badge.className = 'badge text-bg-secondary'; badge.textContent = t('weather_default', 'Default'); row.append(badge);
                    } else row.append(button(t('weather_set_default', 'Set as default'), () => { defaultField.value = location.id; write(read()); }));
                    row.append(button(t('weather_remove', 'Remove'), () => write(read().filter(item => item.id !== location.id))));
                    chosen.append(row);
                });
                sync();
            }
            async function search() {
                if (!field('enabled').checked) return;
                const query = root.querySelector('[data-weather-query]').value.trim();
                if (query.length < 2) return;
                root.querySelector('[data-weather-search]').disabled = true;
                status.textContent = t('weather_loading', 'Loading…'); results.replaceChildren();
                try {
                    const csrf = form.querySelector('[name="csrfmiddlewaretoken"]')?.value || document.querySelector('meta[name="csrf-token"]')?.content || '';
                    const response = await fetch(builder.dataset.weatherSearchUrl, {
                        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
                        body: JSON.stringify({ query, api_key: field('api_key').value, enabled: true }),
                    });
                    if (!response.ok) throw new Error('search');
                    const data = await response.json();
                    if (!field('enabled').checked) { status.textContent = ''; return; }
                    status.textContent = data.locations.length ? '' : t('weather_empty_search', 'No matching cities.');
                    data.locations.forEach(location => {
                        const add = button(t('weather_add', 'Add') + ': ' + location.name, () => {
                            const locations = read();
                            if (locations.some(item => item.id === location.id)) return;
                            if (locations.length >= 10) { status.textContent = t('weather_choose_location', 'Choose up to ten locations.'); return; }
                            write([...locations, location]); add.disabled = true;
                        });
                        add.className = 'list-group-item list-group-item-action'; results.append(add);
                    });
                } catch (_) { status.textContent = t('weather_search_error', 'Could not search. Check the API key and try again.'); }
                finally { sync(); }
            }
            root.querySelector('[data-weather-search]').addEventListener('click', search);
            root.querySelector('[data-weather-query]').addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); search(); } });
            field('enabled').addEventListener('change', sync);
            form.querySelectorAll('[name="weather_placement"]').forEach(input => input.addEventListener('change', sync));
            hidden.addEventListener('change', render);
            render();
        });
    }
    new MutationObserver(init).observe(document.documentElement, { childList: true, subtree: true });
    init();
}());
