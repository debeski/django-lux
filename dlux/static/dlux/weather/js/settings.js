// Weather's location builder in Extra Features.
//
// Built from the same parts as the Sidebar builder: two panes of
// `dlux-builder-item` rows (chosen locations, search results) and a
// DluxInspectorShell whose action row adds, orders, defaults and removes the
// selected row, and whose field panel renames it. The locations and the default
// still live in the form's hidden `weather_locations` / `weather_default_location`
// fields, so the settings form saves them like any other field.
(function () {
    'use strict';

    const MAX_LOCATIONS = 10;

    function init() {
        document.querySelectorAll('[data-weather-settings]').forEach(setup);
    }

    function setup(root) {
        if (root.dataset.weatherReady) return;
        const form = root.closest('form');
        const builder = root.querySelector('[data-weather-location-builder]');
        if (!form || !builder) return;
        root.dataset.weatherReady = 'true';

        const labels = builder.dataset;
        const helpers = window.DluxSetupDom;
        const field = (name) => form.querySelector(`[name="weather_${name}"]`);
        const hidden = field('locations');
        const defaultField = field('default_location');
        const refs = {
            chosen: builder.querySelector('[data-weather-chosen]'),
            results: builder.querySelector('[data-weather-results]'),
            status: builder.querySelector('[data-weather-search-status]'),
            query: builder.querySelector('[data-weather-query]'),
            searchButton: builder.querySelector('[data-weather-search]'),
            shellHost: builder.querySelector('[data-weather-inspector-shell]'),
        };
        const state = { results: [], selected: null };

        const enabled = () => Boolean(field('enabled') && field('enabled').checked);

        function read() {
            try {
                const value = JSON.parse(hidden.value || '[]');
                return Array.isArray(value) ? value : [];
            } catch (_) {
                return [];
            }
        }

        // The hidden field's change listener re-renders, so an import that
        // rewrites the field redraws the builder the same way an edit does.
        function write(locations) {
            hidden.value = JSON.stringify(locations);
            if (!locations.some((item) => item.id === defaultField.value)) {
                defaultField.value = locations[0] ? locations[0].id : '';
            }
            defaultField.dispatchEvent(new Event('change', { bubbles: true }));
            hidden.dispatchEvent(new Event('change', { bubbles: true }));
        }

        function selected() {
            if (!state.selected) return null;
            const list = state.selected.pane === 'chosen' ? read() : state.results;
            return list.find((item) => item.id === state.selected.id) || null;
        }

        function setStatus(text, isError) {
            refs.status.textContent = text || '';
            refs.status.hidden = !text;
            refs.status.classList.toggle('text-danger', Boolean(isError));
            refs.status.classList.toggle('text-muted', !isError);
        }

        function select(pane, id) {
            state.selected = { pane, id };
            render();
        }

        function add() {
            const location = state.selected && state.selected.pane === 'results' ? selected() : null;
            if (!location) return;
            const locations = read();
            if (locations.some((item) => item.id === location.id)) return;
            if (locations.length >= MAX_LOCATIONS) {
                setStatus(labels.labelTooMany, true);
                return;
            }
            state.selected = { pane: 'chosen', id: location.id };
            write([...locations, location]);
        }

        function setDefault() {
            const location = state.selected && state.selected.pane === 'chosen' ? selected() : null;
            if (!location) return;
            defaultField.value = location.id;
            write(read());
        }

        function move(offset) {
            const locations = read();
            const index = locations.findIndex((item) => state.selected && item.id === state.selected.id);
            const target = index + offset;
            if (index < 0 || target < 0 || target >= locations.length) return;
            [locations[index], locations[target]] = [locations[target], locations[index]];
            write(locations);
        }

        function remove() {
            if (!state.selected || state.selected.pane !== 'chosen') return;
            const id = state.selected.id;
            state.selected = null;
            write(read().filter((item) => item.id !== id));
        }

        function rename(value) {
            const name = String(value || '').trim().slice(0, 120);
            if (!name || !state.selected || state.selected.pane !== 'chosen') return;
            write(read().map((item) => (item.id === state.selected.id ? { ...item, name } : item)));
        }

        function row(location, pane, badgeText) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'dlux-builder-item available-item';
            button.dataset.pane = pane;
            button.dataset.weatherLocationId = location.id;
            if (state.selected && state.selected.pane === pane && state.selected.id === location.id) {
                button.classList.add('is-active');
            }
            const main = document.createElement('span');
            main.className = 'dlux-builder-item-main';
            const icon = document.createElement('i');
            icon.className = 'bi bi-geo-alt';
            icon.setAttribute('aria-hidden', 'true');
            const copy = document.createElement('span');
            copy.className = 'dlux-builder-item-copy';
            const label = document.createElement('span');
            label.className = 'dlux-builder-item-label';
            label.textContent = location.name;
            const meta = document.createElement('span');
            meta.className = 'dlux-builder-item-meta';
            meta.textContent = `${location.lat}, ${location.lon}`;
            copy.append(label, meta);
            main.append(icon, copy);
            button.append(main);
            if (badgeText) {
                const badge = document.createElement('span');
                badge.className = 'badge text-bg-light';
                badge.textContent = badgeText;
                button.append(badge);
            }
            button.addEventListener('click', () => select(pane, location.id));
            if (pane === 'results') {
                button.addEventListener('dblclick', () => { select(pane, location.id); add(); });
            }
            return button;
        }

        function emptyNote(text) {
            const note = document.createElement('p');
            note.className = 'text-muted small p-2 mb-0';
            note.textContent = text;
            return note;
        }

        function renderRows() {
            const locations = read();
            refs.chosen.replaceChildren(...(locations.length
                ? locations.map((location) => row(
                    location, 'chosen', location.id === defaultField.value ? labels.labelDefault : '',
                ))
                : [emptyNote(labels.labelEmpty)]));
            refs.results.replaceChildren(...state.results.map((location) => row(location, 'results', '')));
        }

        const shell = window.DluxInspectorShell && refs.shellHost
            ? window.DluxInspectorShell.create(refs.shellHost, {
                strings: { clearSelection: labels.labelClear },
                adapter: {
                    getSelection: () => state.selected,
                    clearSelection: () => {
                        state.selected = null;
                        renderRows();
                    },
                    getActions: () => {
                        const on = enabled();
                        const pane = state.selected && state.selected.pane;
                        const locations = read();
                        const index = pane === 'chosen'
                            ? locations.findIndex((item) => item.id === state.selected.id)
                            : -1;
                        const current = selected();
                        return [
                            {
                                id: 'weather-add',
                                label: labels.labelAdd,
                                icon: 'bi bi-plus-square',
                                variant: 'primary',
                                disabled: !on || pane !== 'results' || !current
                                    || locations.some((item) => item.id === current.id),
                                onClick: add,
                            },
                            {
                                id: 'weather-default',
                                label: labels.labelSetDefault,
                                icon: 'bi bi-star',
                                variant: 'outline-primary',
                                disabled: !on || index < 0 || locations[index].id === defaultField.value,
                                onClick: setDefault,
                            },
                            {
                                id: 'weather-up',
                                label: labels.labelMoveUp,
                                icon: 'bi bi-arrow-up',
                                disabled: !on || index <= 0,
                                onClick: () => move(-1),
                            },
                            {
                                id: 'weather-down',
                                label: labels.labelMoveDown,
                                icon: 'bi bi-arrow-down',
                                disabled: !on || index < 0 || index >= locations.length - 1,
                                onClick: () => move(1),
                            },
                            {
                                id: 'weather-remove',
                                label: labels.labelRemove,
                                icon: 'bi bi-trash3',
                                variant: 'outline-danger',
                                disabled: !on || index < 0,
                                onClick: remove,
                            },
                        ];
                    },
                    getTitle: () => (selected() || {}).name || '',
                    getSubtitle: () => {
                        const current = selected();
                        return current ? `${current.lat}, ${current.lon}` : '';
                    },
                    getBadge: () => {
                        const current = selected();
                        if (!current) return '';
                        if (state.selected.pane === 'results') return labels.labelResult;
                        return current.id === defaultField.value ? labels.labelDefault : '';
                    },
                    getFields: () => {
                        const current = selected();
                        if (!enabled() || !current || state.selected.pane !== 'chosen') return [];
                        return [{
                            id: 'weather-display-name',
                            type: 'text',
                            label: labels.labelDisplayName,
                            value: current.name,
                            onChange: ({ value }) => rename(value),
                        }];
                    },
                },
            })
            : null;

        // The dependent helper enables every control it finds, including actions
        // that must stay disabled, so the shell re-renders after it.
        function sync() {
            const on = enabled();
            helpers.setDependentFieldEnabled(root.querySelector('[data-weather-dependent]'), on, labels.labelDisabled);
            const floating = helpers.getNamedFieldValue(form, 'weather_placement') === 'floating';
            helpers.setDependentFieldEnabled(
                root.querySelector('[data-weather-corner]'), on && floating,
                on ? labels.labelCorner : labels.labelDisabled,
            );
            if (shell) shell.render();
        }

        function render() {
            renderRows();
            sync();
        }

        async function search() {
            if (!enabled()) return;
            const query = refs.query.value.trim();
            if (query.length < 2) return;
            const run = async () => {
                setStatus('', false);
                try {
                    const csrf = (form.querySelector('[name="csrfmiddlewaretoken"]') || {}).value
                        || (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
                    const response = await fetch(builder.dataset.weatherSearchUrl, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
                        body: JSON.stringify({ query, api_key: field('api_key').value, enabled: true }),
                    });
                    if (!response.ok) {
                        let code = '';
                        try { code = (await response.json()).error || ''; } catch (_) { /* not JSON */ }
                        throw new Error(code || 'search');
                    }
                    const data = await response.json();
                    if (!enabled()) return;
                    state.results = Array.isArray(data.locations) ? data.locations : [];
                    if (state.selected && state.selected.pane === 'results') state.selected = null;
                    setStatus(state.results.length ? '' : labels.labelNoResults, false);
                } catch (error) {
                    // A refused key and an unreachable provider need different fixes.
                    const reason = error && error.message;
                    setStatus(reason === 'credentials' ? labels.labelErrorKey
                        : (reason === 'provider' || reason === 'worker') ? labels.labelErrorNetwork
                            : labels.labelSearchError, true);
                }
                render();
            };
            if (window.DluxLoadingButton) {
                await window.DluxLoadingButton.run(refs.searchButton, run);
            } else {
                await run();
            }
        }

        refs.searchButton.addEventListener('click', search);
        refs.query.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                search();
            }
        });
        field('enabled').addEventListener('change', sync);
        form.querySelectorAll('[name="weather_placement"]').forEach((input) => input.addEventListener('change', sync));
        hidden.addEventListener('change', render);
        render();
    }

    new MutationObserver(init).observe(document.documentElement, { childList: true, subtree: true });
    init();
}());
