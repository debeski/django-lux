/*
 * Dlux global search (titlebar). DSRP-1: external asset, no inline JS, reads its
 * config from data-* attributes on the [data-global-search] root.
 *
 * Modes (data-global-search-mode): 'always' (field shown), 'icon' (icon expands
 * to a field on focus), 'disabled' (the root is not rendered server-side).
 * Debounced fetch to the JSON endpoint, grouped dropdown, full keyboard nav,
 * RTL/theme aware. Component results (pages/settings/actions) resolve to a link
 * or a dynamic-modal deep-link; data results navigate to the record when a URL
 * is known. Ctrl/Cmd-K focuses the box from anywhere.
 */
(function () {
    'use strict';

    var DEBOUNCE_MS = 200;
    var MIN_LEN = 2;

    function strings() { return window.DLUX_STRINGS || {}; }
    function s(key, fallback) {
        var v = strings()[key];
        return (typeof v === 'string' && v.length) ? v : fallback;
    }

    var GROUP_LABELS = {
        page: function () { return s('search_group_pages', 'Pages'); },
        setting: function () { return s('search_group_settings', 'Settings'); },
        option: function () { return s('search_group_options', 'Options'); },
        action: function () { return s('search_group_actions', 'Actions'); },
        data: function () { return s('search_group_data', 'Data'); },
    };

    function init(root) {
        if (root.dataset.globalSearchBound === 'true') { return; }
        root.dataset.globalSearchBound = 'true';

        var mode = root.getAttribute('data-global-search-mode') || 'icon';
        var endpoint = root.getAttribute('data-global-search-url') || (
            window.dluxEndpoint
                ? window.dluxEndpoint('globalSearch', null, '/search/')
                : (window.dluxUrl ? window.dluxUrl('/search/') : '/search/')
        );
        var includeData = root.getAttribute('data-global-search-include-data') === '1';
        var input = root.querySelector('[data-global-search-input]');
        var results = root.querySelector('[data-global-search-results]');
        var toggle = root.querySelector('[data-global-search-toggle]');
        if (!input || !results) { return; }

        var flatItems = [];      // flattened, in render order, for keyboard nav
        var activeIndex = -1;
        var debounceTimer = null;
        var lastQuery = '';
        var seq = 0;             // guards out-of-order responses

        function openBox() {
            root.classList.add('dlux-global-search--open');
        }
        function collapseIfEmpty() {
            if (mode === 'icon' && !input.value.trim()) {
                root.classList.remove('dlux-global-search--open');
                closeResults();
            }
        }
        function closeResults() {
            results.hidden = true;
            results.innerHTML = '';
            flatItems = [];
            activeIndex = -1;
            input.setAttribute('aria-expanded', 'false');
        }

        function activate(item) {
            if (!item) { return; }
            var url = item.url;
            var modeAttr = item.mode;
            if (modeAttr === 'modal' && url) {
                // Dispatch on document.body with bubbles:true so this reaches a
                // listener bound to either body or document — the modal helper is
                // a separately cached asset and may be an older copy.
                if (document.getElementById('universalDynamicModal')) {
                    document.body.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', {
                        bubbles: true,
                        detail: { data: { url: url, title: item.label } },
                    }));
                    clear();
                } else if (item.fallback_url) {
                    // No modal host on this page (a bare or non-dlux layout).
                    // Land on the page that owns the setting instead of doing
                    // nothing at all, which is indistinguishable from a dead UI.
                    window.location.href = item.fallback_url;
                }
            } else if (modeAttr === 'link' && url) {
                window.location.href = url;
            }
            // mode 'none' (unresolved data URL) is intentionally inert.
        }

        function clear() {
            input.value = '';
            closeResults();
            collapseIfEmpty();
        }

        function setActive(next) {
            var nodes = results.querySelectorAll('[data-search-item]');
            if (!nodes.length) { return; }
            if (activeIndex >= 0 && nodes[activeIndex]) {
                nodes[activeIndex].classList.remove('is-active');
            }
            activeIndex = (next + nodes.length) % nodes.length;
            var node = nodes[activeIndex];
            node.classList.add('is-active');
            node.scrollIntoView({ block: 'nearest' });
            input.setAttribute('aria-activedescendant', node.id);
        }

        function render(groups, query) {
            results.innerHTML = '';
            flatItems = [];
            activeIndex = -1;

            if (!groups || !groups.length) {
                var empty = document.createElement('div');
                empty.className = 'dlux-global-search__empty';
                empty.textContent = s('search_no_results', 'No matches found.');
                results.appendChild(empty);
                results.hidden = false;
                input.setAttribute('aria-expanded', 'true');
                return;
            }

            groups.forEach(function (group) {
                var heading = document.createElement('div');
                heading.className = 'dlux-global-search__group';
                heading.textContent = (GROUP_LABELS[group.type] ? GROUP_LABELS[group.type]() : group.type);
                results.appendChild(heading);

                group.items.forEach(function (item) {
                    var idx = flatItems.length;
                    flatItems.push(item);
                    var row = document.createElement(item.url && item.mode === 'link' ? 'a' : 'div');
                    row.className = 'dlux-global-search__item';
                    if (item.mode === 'none' || !item.url) { row.classList.add('is-inert'); }
                    row.id = 'dlux-search-item-' + idx;
                    row.setAttribute('data-search-item', '');
                    row.setAttribute('role', 'option');
                    if (row.tagName === 'A') { row.href = item.url; }

                    var icon = document.createElement('i');
                    icon.className = 'bi ' + (item.icon || 'bi-dot') + ' dlux-global-search__item-icon';
                    row.appendChild(icon);

                    var text = document.createElement('span');
                    text.className = 'dlux-global-search__item-text';
                    var label = document.createElement('span');
                    label.className = 'dlux-global-search__item-label';
                    label.textContent = item.label;
                    label.setAttribute('dir', 'auto');
                    text.appendChild(label);
                    if (item.sublabel) {
                        var sub = document.createElement('span');
                        sub.className = 'dlux-global-search__item-sub';
                        sub.textContent = item.sublabel;
                        sub.setAttribute('dir', 'auto');
                        text.appendChild(sub);
                    }
                    row.appendChild(text);

                    row.addEventListener('mouseenter', function () { setActive(idx); });
                    row.addEventListener('click', function (e) {
                        e.preventDefault();
                        activate(item);
                    });
                    results.appendChild(row);
                });
            });

            results.hidden = false;
            input.setAttribute('aria-expanded', 'true');
        }

        function fetchResults(query) {
            var mySeq = ++seq;
            var url = endpoint + '?q=' + encodeURIComponent(query) + (includeData ? '&data=1' : '');
            fetch(url, {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            }).then(function (r) { return r.ok ? r.json() : { groups: [] }; })
              .then(function (payload) {
                  if (mySeq !== seq) { return; }        // a newer request superseded this
                  if (input.value.trim() !== query) { return; }
                  render(payload.groups || [], query);
              }).catch(function () {
                  if (mySeq === seq) { closeResults(); }
              });
        }

        function onInput() {
            var query = input.value.trim();
            window.clearTimeout(debounceTimer);
            if (query.length < MIN_LEN) {
                lastQuery = '';
                closeResults();
                return;
            }
            if (query === lastQuery) { return; }
            lastQuery = query;
            debounceTimer = window.setTimeout(function () { fetchResults(query); }, DEBOUNCE_MS);
        }

        input.addEventListener('input', onInput);
        input.addEventListener('focus', function () {
            openBox();
            if (input.value.trim().length >= MIN_LEN && results.hidden) { onInput(); }
        });
        input.addEventListener('keydown', function (e) {
            if (e.key === 'ArrowDown') { e.preventDefault(); setActive(activeIndex + 1); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(activeIndex - 1); }
            else if (e.key === 'Enter') {
                if (activeIndex >= 0 && flatItems[activeIndex]) { e.preventDefault(); activate(flatItems[activeIndex]); }
            } else if (e.key === 'Escape') {
                if (!results.hidden) { closeResults(); } else { input.blur(); collapseIfEmpty(); }
            }
        });

        if (toggle) {
            toggle.addEventListener('click', function () { openBox(); input.focus(); });
        }

        document.addEventListener('click', function (e) {
            if (!root.contains(e.target)) { closeResults(); collapseIfEmpty(); }
        });

        // Ctrl/Cmd-K focuses the search from anywhere.
        document.addEventListener('keydown', function (e) {
            if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
                e.preventDefault();
                openBox();
                input.focus();
                input.select();
            }
        });
    }

    function boot() {
        document.querySelectorAll('[data-global-search]').forEach(init);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
