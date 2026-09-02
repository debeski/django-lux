(function () {
    'use strict';

    const ICON_SUGGESTIONS = [
        // ── Home & Dashboard ──
        'bi-house',
        'bi-house-fill',
        'bi-house-door',
        'bi-house-door-fill',
        'bi-house-heart',
        'bi-house-heart-fill',
        'bi-house-gear',
        'bi-house-gear-fill',
        'bi-house-lock',
        'bi-houses',
        'bi-speedometer2',
        'bi-speedometer',

        // ── Sidebar toggle & panels ──
        'bi-list',
        'bi-list-nested',
        'bi-text-indent-left',
        'bi-text-indent-right',
        'bi-arrow-bar-left',
        'bi-arrow-bar-right',
        'bi-chevron-bar-left',
        'bi-chevron-bar-right',
        'bi-chevron-double-left',
        'bi-chevron-double-right',
        'bi-menu-app',
        'bi-menu-button',
        'bi-menu-button-wide',
        'bi-layout-sidebar-reverse',
        'bi-layout-sidebar-inset-reverse',
        'bi-layout-text-sidebar-reverse',

        // ── Grid & Layout ──
        'bi-grid',
        'bi-grid-3x2',
        'bi-grid-3x2-gap',
        'bi-grid-3x3-gap',
        'bi-grid-fill',
        'bi-grid-1x2',
        'bi-layout-sidebar',
        'bi-layout-text-sidebar',
        'bi-layout-sidebar-inset',
        'bi-layout-three-columns',
        'bi-columns',
        'bi-columns-gap',
        'bi-window',
        'bi-window-sidebar',
        'bi-window-stack',
        'bi-window-fullscreen',
        'bi-window-split',

        // ── Boxes & Containers ──
        'bi-box',
        'bi-box-fill',
        'bi-box-seam',
        'bi-box-seam-fill',
        'bi-box2',
        'bi-boxes',
        'bi-inbox',
        'bi-inbox-fill',
        'bi-inboxes',
        'bi-inboxes-fill',
        'bi-archive',
        'bi-archive-fill',
        'bi-collection',
        'bi-collection-fill',

        // ── Folders ──
        'bi-folder',
        'bi-folder-fill',
        'bi-folder-plus',
        'bi-folder-check',
        'bi-folder-minus',
        'bi-folder-x',
        'bi-folder-symlink',
        'bi-folder-symlink-fill',
        'bi-folder2',
        'bi-folder2-open',

        // ── Files (Generic) ──
        'bi-file',
        'bi-file-fill',
        'bi-file-text',
        'bi-file-text-fill',
        'bi-file-richtext',
        'bi-file-richtext-fill',
        'bi-file-code',
        'bi-file-code-fill',
        'bi-file-binary',
        'bi-file-binary-fill',
        'bi-file-diff',
        'bi-file-diff-fill',
        'bi-file-ruled',
        'bi-file-ruled-fill',
        'bi-file-check',
        'bi-file-check-fill',
        'bi-file-x',
        'bi-file-x-fill',
        'bi-file-plus',
        'bi-file-plus-fill',
        'bi-file-minus',
        'bi-file-minus-fill',
        'bi-file-lock',
        'bi-file-lock-fill',
        'bi-file-lock2',
        'bi-file-lock2-fill',
        'bi-file-break',
        'bi-file-break-fill',
        'bi-file-bar-graph',
        'bi-file-bar-graph-fill',
        'bi-file-post',
        'bi-file-post-fill',
        'bi-file-medical',
        'bi-file-medical-fill',
        'bi-file-person',
        'bi-file-person-fill',

        // // ── Files (Earmark Variants) ──
        // 'bi-file-earmark',
        // 'bi-file-earmark-fill',
        // 'bi-file-earmark-text',
        // 'bi-file-earmark-text-fill',
        // 'bi-file-earmark-richtext',
        // 'bi-file-earmark-richtext-fill',
        // 'bi-file-earmark-code',
        // 'bi-file-earmark-code-fill',
        // 'bi-file-earmark-binary',
        // 'bi-file-earmark-binary-fill',
        // 'bi-file-earmark-diff',
        // 'bi-file-earmark-diff-fill',
        // 'bi-file-earmark-ruled',
        // 'bi-file-earmark-ruled-fill',
        // 'bi-file-earmark-check',
        // 'bi-file-earmark-check-fill',
        // 'bi-file-earmark-x',
        // 'bi-file-earmark-x-fill',
        // 'bi-file-earmark-plus',
        // 'bi-file-earmark-plus-fill',
        // 'bi-file-earmark-minus',
        // 'bi-file-earmark-minus-fill',
        // 'bi-file-earmark-lock',
        // 'bi-file-earmark-lock-fill',
        // 'bi-file-earmark-lock2',
        // 'bi-file-earmark-lock2-fill',
        // 'bi-file-earmark-break',
        // 'bi-file-earmark-break-fill',
        // 'bi-file-earmark-bar-graph',
        // 'bi-file-earmark-bar-graph-fill',
        // 'bi-file-earmark-spreadsheet',
        // 'bi-file-earmark-spreadsheet-fill',
        // 'bi-file-earmark-person',
        // 'bi-file-earmark-person-fill',
        // 'bi-file-earmark-medical',
        // 'bi-file-earmark-medical-fill',
        // 'bi-file-earmark-post',
        // 'bi-file-earmark-post-fill',
        // 'bi-file-earmark-arrow-up',
        // 'bi-file-earmark-arrow-up-fill',
        // 'bi-file-earmark-arrow-down',
        // 'bi-file-earmark-arrow-down-fill',
        // 'bi-file-earmark-image',
        // 'bi-file-earmark-image-fill',
        // 'bi-file-earmark-music',
        // 'bi-file-earmark-music-fill',
        // 'bi-file-earmark-play',
        // 'bi-file-earmark-play-fill',
        // 'bi-file-earmark-slides',
        // 'bi-file-earmark-slides-fill',
        // 'bi-file-earmark-font',
        // 'bi-file-earmark-font-fill',
        // 'bi-file-earmark-zip',
        // 'bi-file-earmark-zip-fill',
        // 'bi-file-earmark-pdf',
        // 'bi-file-earmark-pdf-fill',
        // 'bi-file-earmark-word',
        // 'bi-file-earmark-word-fill',
        // 'bi-file-earmark-excel',
        // 'bi-file-earmark-excel-fill',
        // 'bi-file-earmark-ppt',
        // 'bi-file-earmark-ppt-fill',

        // ── File Stacks ──
        'bi-files',
        'bi-files-alt',
        'bi-file-zip',
        'bi-file-zip-fill',
        'bi-file-pdf',
        'bi-file-pdf-fill',
        'bi-file-word',
        'bi-file-word-fill',
        'bi-file-excel',
        'bi-file-excel-fill',
        'bi-file-ppt',
        'bi-file-ppt-fill',
        'bi-file-image',
        'bi-file-image-fill',
        'bi-file-music',
        'bi-file-music-fill',
        'bi-file-play',
        'bi-file-play-fill',
        'bi-file-slides',
        'bi-file-slides-fill',
        'bi-file-font',
        'bi-file-font-fill',
        'bi-file-spreadsheet',
        'bi-file-spreadsheet-fill',
        'bi-file-arrow-up',
        'bi-file-arrow-up-fill',
        'bi-file-arrow-down',
        'bi-file-arrow-down-fill',

        // ── Clipboard & Journals ──
        'bi-clipboard',
        'bi-clipboard-fill',
        'bi-clipboard-data',
        'bi-clipboard-data-fill',
        'bi-clipboard-check',
        'bi-clipboard-check-fill',
        'bi-clipboard-plus',
        'bi-clipboard-plus-fill',
        'bi-clipboard-minus',
        'bi-clipboard-minus-fill',
        'bi-clipboard-x',
        'bi-clipboard-x-fill',
        'bi-clipboard-heart',
        'bi-clipboard-heart-fill',
        'bi-clipboard-pulse',
        'bi-clipboard2',
        'bi-clipboard2-data',
        'bi-clipboard2-check',
        'bi-clipboard2-plus',
        'bi-journal',
        'bi-journal-text',
        'bi-journal-check',
        'bi-journal-richtext',
        'bi-journal-album',
        'bi-journal-bookmark',
        'bi-journal-bookmark-fill',
        'bi-journal-medical',
        'bi-journals',

        // ── Books & Reading ──
        'bi-book',
        'bi-book-fill',
        'bi-book-half',
        'bi-bookmark',
        'bi-bookmark-fill',
        'bi-bookmark-star',
        'bi-bookmark-star-fill',
        'bi-bookmark-check',
        'bi-bookmark-check-fill',
        'bi-bookmark-heart',
        'bi-bookmark-heart-fill',
        'bi-bookmarks',
        'bi-bookmarks-fill',
        'bi-bookshelf',

        // ── Finance & Commerce ──
        'bi-wallet',
        'bi-wallet-fill',
        'bi-wallet2',
        'bi-cash',
        'bi-cash-coin',
        'bi-cash-stack',
        'bi-currency-dollar',
        'bi-currency-euro',
        'bi-currency-exchange',
        'bi-bank',
        'bi-bank2',
        'bi-piggy-bank',
        'bi-piggy-bank-fill',
        'bi-credit-card',
        'bi-credit-card-fill',
        'bi-credit-card-2-front',
        'bi-credit-card-2-front-fill',
        'bi-receipt',
        'bi-receipt-cutoff',
        'bi-safe',
        'bi-safe-fill',
        'bi-safe2',
        'bi-safe2-fill',
        'bi-coin',
        'bi-tags',
        'bi-tags-fill',
        'bi-tag',
        'bi-tag-fill',

        // ── Security & Privacy ──
        'bi-shield',
        'bi-shield-check',
        'bi-shield-lock',
        'bi-shield-lock-fill',
        'bi-shield-fill-check',
        'bi-shield-exclamation',
        'bi-shield-fill-exclamation',
        'bi-shield-slash',
        'bi-lock',
        'bi-lock-fill',
        'bi-unlock',
        'bi-unlock-fill',
        'bi-key',
        'bi-key-fill',
        'bi-fingerprint',
        'bi-incognito',
        'bi-eye',
        'bi-eye-fill',
        'bi-eye-slash',
        'bi-eye-slash-fill',

        // ── People & Users ──
        'bi-person',
        'bi-person-fill',
        'bi-person-circle',
        'bi-person-badge',
        'bi-person-badge-fill',
        'bi-person-lines-fill',
        'bi-person-vcard',
        'bi-person-vcard-fill',
        'bi-person-gear',
        'bi-person-check',
        'bi-person-check-fill',
        'bi-person-dash',
        'bi-person-plus',
        'bi-person-plus-fill',
        'bi-person-lock',
        'bi-person-workspace',
        'bi-people',
        'bi-people-fill',
        'bi-person-rolodex',

        // ── Settings & Tools ──
        'bi-gear',
        'bi-gear-fill',
        'bi-gear-wide',
        'bi-gear-wide-connected',
        'bi-sliders',
        'bi-sliders2',
        'bi-sliders2-vertical',
        'bi-wrench',
        'bi-wrench-adjustable',
        'bi-wrench-adjustable-circle',
        'bi-tools',
        'bi-hammer',
        'bi-nut',
        'bi-nut-fill',
        'bi-screwdriver',
        'bi-funnel',
        'bi-funnel-fill',
        'bi-filter',
        'bi-toggles',
        'bi-toggles2',

        // ── Business & Buildings ──
        'bi-briefcase',
        'bi-briefcase-fill',
        'bi-building',
        'bi-building-fill',
        'bi-building-gear',
        'bi-buildings',
        'bi-buildings-fill',
        'bi-shop',
        'bi-shop-window',
        'bi-hospital',
        'bi-hospital-fill',

        // ── Tables, Lists & Data ──
        'bi-table',
        'bi-list-ul',
        'bi-list-ol',
        'bi-list-check',
        'bi-list-task',
        'bi-list-nested',
        'bi-list-stars',
        'bi-kanban',
        'bi-kanban-fill',
        'bi-view-list',
        'bi-view-stacked',
        'bi-ui-checks',
        'bi-ui-checks-grid',
        'bi-ui-radios',

        // ── Charts & Analytics ──
        'bi-pie-chart',
        'bi-pie-chart-fill',
        'bi-bar-chart',
        'bi-bar-chart-fill',
        'bi-bar-chart-line',
        'bi-bar-chart-line-fill',
        'bi-bar-chart-steps',
        'bi-graph-up',
        'bi-graph-up-arrow',
        'bi-graph-down',
        'bi-graph-down-arrow',
        'bi-activity',
        'bi-diagram-3',
        'bi-diagram-3-fill',
        'bi-diagram-2',
        'bi-diagram-2-fill',

        // ── Shipping & Commerce ──
        'bi-truck',
        'bi-truck-front',
        'bi-truck-front-fill',
        'bi-truck-flatbed',
        'bi-cart',
        'bi-cart-fill',
        'bi-cart-check',
        'bi-cart-check-fill',
        'bi-cart-plus',
        'bi-cart-plus-fill',
        'bi-cart3',
        'bi-bag',
        'bi-bag-fill',
        'bi-bag-check',
        'bi-bag-check-fill',
        'bi-bag-heart',
        'bi-bag-heart-fill',
        'bi-basket',
        'bi-basket-fill',
        'bi-basket2',
        'bi-basket2-fill',
        'bi-basket3',
        'bi-basket3-fill',

        // ── Communication ──
        'bi-envelope',
        'bi-envelope-fill',
        'bi-envelope-open',
        'bi-envelope-open-fill',
        'bi-envelope-paper',
        'bi-envelope-paper-fill',
        'bi-chat-square-text',
        'bi-chat-square-text-fill',
        'bi-chat-left-text',
        'bi-chat-left-text-fill',
        'bi-chat-dots',
        'bi-chat-dots-fill',
        'bi-chat-quote',
        'bi-chat-quote-fill',
        'bi-send',
        'bi-send-fill',
        'bi-send-check',
        'bi-send-check-fill',
        'bi-mailbox',
        'bi-mailbox2',
        'bi-megaphone',
        'bi-megaphone-fill',
        'bi-telephone',
        'bi-telephone-fill',
        'bi-telephone-inbound',
        'bi-telephone-inbound-fill',
        'bi-telephone-outbound',
        'bi-telephone-outbound-fill',
        'bi-telephone-forward',
        'bi-telephone-forward-fill',
        'bi-headset',

        // ── Globe & Web ──
        'bi-globe',
        'bi-globe2',
        'bi-globe-americas',
        'bi-globe-europe-africa',
        'bi-translate',
        'bi-link',
        'bi-link-45deg',
        'bi-share',
        'bi-share-fill',
        'bi-rss',
        'bi-rss-fill',
        'bi-wifi',
        'bi-broadcast',

        // ── Time & Calendar ──
        'bi-calendar',
        'bi-calendar-fill',
        'bi-calendar-event',
        'bi-calendar-event-fill',
        'bi-calendar-check',
        'bi-calendar-check-fill',
        'bi-calendar-plus',
        'bi-calendar-plus-fill',
        'bi-calendar-minus',
        'bi-calendar-minus-fill',
        'bi-calendar-week',
        'bi-calendar-week-fill',
        'bi-calendar-range',
        'bi-calendar-range-fill',
        'bi-calendar-date',
        'bi-calendar-date-fill',
        'bi-clock',
        'bi-clock-fill',
        'bi-clock-history',
        'bi-hourglass',
        'bi-hourglass-split',
        'bi-stopwatch',
        'bi-stopwatch-fill',
        'bi-alarm',
        'bi-alarm-fill',

        // ── Notifications & Status ──
        'bi-bell',
        'bi-bell-fill',
        'bi-bell-slash',
        'bi-bell-slash-fill',
        'bi-star',
        'bi-star-fill',
        'bi-star-half',
        'bi-heart',
        'bi-heart-fill',
        'bi-check-circle',
        'bi-check-circle-fill',
        'bi-check-square',
        'bi-check-square-fill',
        'bi-x-circle',
        'bi-x-circle-fill',
        'bi-exclamation-triangle',
        'bi-exclamation-triangle-fill',
        'bi-exclamation-circle',
        'bi-exclamation-circle-fill',
        'bi-info-circle',
        'bi-info-circle-fill',
        'bi-question-circle',
        'bi-question-circle-fill',
        'bi-flag',
        'bi-flag-fill',
        'bi-patch-check',
        'bi-patch-check-fill',

        // ── Arrows & Navigation ──
        'bi-arrow-left-right',
        'bi-arrow-repeat',
        'bi-arrow-clockwise',
        'bi-arrow-counterclockwise',
        'bi-arrow-up-right-square',
        'bi-box-arrow-up-right',
        'bi-box-arrow-in-right',
        'bi-signpost',
        'bi-signpost-fill',
        'bi-signpost-split',
        'bi-signpost-split-fill',
        'bi-sign-turn-right',
        'bi-compass',
        'bi-compass-fill',

        // ── Database & Server ──
        'bi-database',
        'bi-database-fill',
        'bi-database-gear',
        'bi-database-check',
        'bi-database-add',
        'bi-database-lock',
        'bi-database-up',
        'bi-database-down',
        'bi-server',
        'bi-hdd',
        'bi-hdd-fill',
        'bi-hdd-stack',
        'bi-hdd-stack-fill',
        'bi-hdd-network',
        'bi-hdd-network-fill',

        // ── Devices ──
        'bi-pc-display',
        'bi-pc-display-horizontal',
        'bi-laptop',
        'bi-laptop-fill',
        'bi-phone',
        'bi-phone-fill',
        'bi-tablet',
        'bi-tablet-fill',
        'bi-printer',
        'bi-printer-fill',
        'bi-projector',
        'bi-projector-fill',
        'bi-cpu',
        'bi-cpu-fill',
        'bi-gpu-card',
        'bi-motherboard',
        'bi-motherboard-fill',
        'bi-usb-drive',
        'bi-usb-drive-fill',
        'bi-disc',
        'bi-disc-fill',

        // ── Media & Images ──
        'bi-image',
        'bi-image-fill',
        'bi-images',
        'bi-camera',
        'bi-camera-fill',
        'bi-camera-video',
        'bi-camera-video-fill',
        'bi-film',
        'bi-play-circle',
        'bi-play-circle-fill',
        'bi-music-note',
        'bi-music-note-beamed',
        'bi-music-note-list',
        'bi-mic',
        'bi-mic-fill',
        'bi-volume-up',
        'bi-volume-up-fill',
        'bi-easel',
        'bi-easel-fill',
        'bi-palette',
        'bi-palette-fill',
        'bi-brush',
        'bi-brush-fill',
        'bi-pen',
        'bi-pen-fill',
        'bi-pencil-square',
        'bi-vector-pen',

        // ── Map & Location ──
        'bi-geo',
        'bi-geo-alt',
        'bi-geo-alt-fill',
        'bi-geo-fill',
        'bi-pin',
        'bi-pin-fill',
        'bi-pin-map',
        'bi-pin-map-fill',
        'bi-map',
        'bi-map-fill',

        // ── Weather & Nature ──
        'bi-sun',
        'bi-sun-fill',
        'bi-moon',
        'bi-moon-fill',
        'bi-cloud',
        'bi-cloud-fill',
        'bi-cloud-sun',
        'bi-cloud-sun-fill',
        'bi-tree',
        'bi-tree-fill',
        'bi-flower1',
        'bi-flower2',
        'bi-water',
        'bi-droplet',
        'bi-droplet-fill',

        // ── Health & Science ──
        'bi-heart-pulse',
        'bi-heart-pulse-fill',
        'bi-bandaid',
        'bi-bandaid-fill',
        'bi-capsule',
        'bi-prescription2',
        'bi-virus',
        'bi-virus2',
        'bi-lungs',
        'bi-lungs-fill',
        'bi-radioactive',
        'bi-binoculars',
        'bi-binoculars-fill',
        'bi-search',
        'bi-search-heart',
        'bi-zoom-in',
        'bi-zoom-out',

        // ── Misc & Math ──
        'bi-calculator',
        'bi-calculator-fill',
        'bi-percent',
        'bi-hash',
        'bi-puzzle',
        'bi-puzzle-fill',
        'bi-trophy',
        'bi-trophy-fill',
        'bi-award',
        'bi-award-fill',
        'bi-lightning',
        'bi-lightning-fill',
        'bi-lightning-charge',
        'bi-lightning-charge-fill',
        'bi-magic',
        'bi-rocket',
        'bi-rocket-fill',
        'bi-rocket-takeoff',
        'bi-rocket-takeoff-fill',
        'bi-hand-thumbs-up',
        'bi-hand-thumbs-up-fill',
        'bi-emoji-smile',
        'bi-emoji-smile-fill',
        'bi-cup-hot',
        'bi-cup-hot-fill',
        'bi-bullseye',
        'bi-clipboard2-pulse',
        'bi-clipboard2-pulse-fill',
        'bi-qr-code',
        'bi-qr-code-scan',
        'bi-upc-scan',
        'bi-bug',
        'bi-bug-fill',
        'bi-code-slash',
        'bi-braces',
        'bi-terminal',
        'bi-terminal-fill',
        'bi-plugin',
        'bi-plug',
        'bi-plug-fill',
        'bi-power',
        'bi-recycle',
        'bi-trash',
        'bi-trash3',
        'bi-trash3-fill',
    ];

    // Self-contained copies of the two setup helpers the picker needs, so the
    // component works on any page that renders `dlux/includes/icon_picker.html`
    // without depending on setup/js/main.js load order.
    function t(key, fallback) {
        if (window.DLUX_STRINGS && typeof window.DLUX_STRINGS[key] === 'string' && window.DLUX_STRINGS[key]) {
            return window.DLUX_STRINGS[key];
        }
        return fallback;
    }

    function namedFieldSelector(name) {
        return `[name="${String(name || '').replace(/"/g, '\\"')}"]`;
    }

    function setNamedFieldValue(form, name, value) {
        const inputs = Array.from(form.querySelectorAll(namedFieldSelector(name)));
        if (!inputs.length) {
            return;
        }

        if (inputs[0].type === 'radio') {
            inputs.forEach((input) => {
                input.checked = String(input.value) === String(value);
            });
            // Choice-selector widgets track their highlighted option from a 'change'
            // event on the checked input; without this they keep the previously-selected
            // option visually marked (two options appearing selected at once).
            const checked = inputs.find((input) => input.checked) || inputs[0];
            checked.dispatchEvent(new Event('change', { bubbles: true }));
            return;
        }

        inputs[0].value = value;
        inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
        inputs[0].dispatchEvent(new Event('change', { bubbles: true }));
    }

    // Standalone icon picker for a plain form field, sharing ICON_SUGGESTIONS with
    // the sidebar builder's inspector. The visible input and the grid both write
    // to the posted hidden field, so a value can be typed or clicked.
    function initIconPickers(root) {
        root.querySelectorAll('[data-dlux-icon-picker]').forEach((picker) => {
            if (picker.dataset.dluxIconPickerReady === 'true') {
                return;
            }
            picker.dataset.dluxIconPickerReady = 'true';

            const form = picker.closest('form');
            const fieldName = picker.getAttribute('data-icon-field') || '';
            const defaultIcon = picker.getAttribute('data-icon-default') || 'bi-list';
            const input = picker.querySelector('[data-icon-input]');
            const preview = picker.querySelector('[data-icon-preview]');
            const search = picker.querySelector('[data-icon-search]');
            const suggestions = picker.querySelector('[data-icon-suggestions]');
            const reset = picker.querySelector('[data-icon-reset]');
            const toggle = picker.querySelector('[data-icon-toggle]');
            const body = picker.querySelector('[data-icon-picker-body]');
            const isPopover = picker.getAttribute('data-icon-popover') === 'true';
            // Where "no icon" is a real answer — a ribbon tab falls back to the icon
            // the page already gives it — clearing the box has to mean cleared. Without
            // this, emptying it and Reset both wrote the default straight back, and the
            // only way to drop an icon was to type a name that did not exist.
            const allowEmpty = picker.getAttribute('data-icon-allow-empty') === 'true';
            if (!form || !fieldName || !input || !suggestions) {
                return;
            }

            // A popover floats over the fields below it, so it needs a way out
            // that an in-flow disclosure does not: clicking off it. The toggle
            // lives inside `picker`, so the click that opened it never closes it.
            function onOutsideClick(event) {
                if (!picker.contains(event.target)) {
                    close();
                }
            }

            // The grid is ~600 buttons. Building it on init cost that on every
            // render of the step, so it is built when opened and thrown away on
            // close — a closed picker is just an input.
            function isOpen() {
                return Boolean(body) && !body.classList.contains('d-none');
            }

            function currentValue() {
                const raw = String(input.value || '').trim().toLowerCase();
                return raw || (allowEmpty ? '' : defaultIcon);
            }

            function apply(icon, { rerender = true } = {}) {
                const raw = String(icon || '').trim().toLowerCase();
                const value = raw || (allowEmpty ? '' : defaultIcon);
                input.value = value;
                if (preview) {
                    // Nothing chosen still needs something to show on the trigger.
                    preview.className = `bi ${value || defaultIcon}`;
                    preview.classList.toggle('dlux-icon-picker-preview--empty', !value);
                }
                setNamedFieldValue(form, fieldName, value);
                if (rerender && isOpen()) {
                    renderSuggestions();
                }
            }

            function renderSuggestions() {
                const needle = String(search ? search.value : '').trim().toLowerCase().replace(/\s+/g, '-');
                const matches = needle
                    ? ICON_SUGGESTIONS.filter((icon) => icon.includes(needle))
                    : ICON_SUGGESTIONS;
                const active = currentValue();
                const fragment = document.createDocumentFragment();
                matches.forEach((icon) => {
                    const button = document.createElement('button');
                    button.type = 'button';
                    button.className = `btn btn-sm dlux-builder-icon-choice ${icon === active ? 'is-active' : ''}`;
                    button.setAttribute('title', icon);
                    button.setAttribute('aria-label', icon);
                    button.innerHTML = `<i class="bi ${icon}"></i>`;
                    // Picking is a completed choice, so the grid folds away again.
                    button.addEventListener('click', () => {
                        apply(icon, { rerender: false });
                        close({ focusTrigger: true });
                    });
                    fragment.appendChild(button);
                });
                suggestions.innerHTML = '';
                if (!matches.length) {
                    suggestions.innerHTML = `<div class="text-muted small p-2">${t('sidebar_no_icons_found', 'No icons match your search.')}</div>`;
                    return;
                }
                suggestions.appendChild(fragment);
            }

            // The grid drops below the field, or rises above it when there is no room
            // below. "Room" is the box that actually clips it — every scrolling or
            // `overflow: hidden` ancestor, narrowed to the viewport — not the viewport
            // alone: inside a scrollable modal there is usually screen below the modal
            // and none inside it, and a grid opened into that gap can be neither
            // clicked nor scrolled to.
            function visibleBounds(element) {
                const doc = element.ownerDocument;
                const view = doc && doc.defaultView;
                let top = 0;
                let bottom = (view && view.innerHeight)
                    || (doc && doc.documentElement && doc.documentElement.clientHeight)
                    || 0;
                if (!view || typeof view.getComputedStyle !== 'function') return { top, bottom };
                let node = element.parentElement;
                while (node && node !== doc.body) {
                    const overflowY = view.getComputedStyle(node).overflowY;
                    if (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'hidden') {
                        const rect = node.getBoundingClientRect();
                        top = Math.max(top, rect.top);
                        bottom = Math.min(bottom, rect.bottom);
                    }
                    node = node.parentElement;
                }
                return { top, bottom };
            }

            function placeBody() {
                if (!isPopover || !body) return;
                body.classList.remove('dlux-builder-icon-picker--above');
                const bounds = visibleBounds(picker);
                const fieldRect = picker.getBoundingClientRect();
                const needed = body.offsetHeight + 8;
                const roomBelow = bounds.bottom - fieldRect.bottom;
                const roomAbove = fieldRect.top - bounds.top;
                if (needed > roomBelow && roomAbove > roomBelow) {
                    body.classList.add('dlux-builder-icon-picker--above');
                }
            }

            function open() {
                if (!body || isOpen()) {
                    return;
                }
                body.classList.remove('d-none');
                if (toggle) {
                    toggle.setAttribute('aria-expanded', 'true');
                }
                if (isPopover) {
                    document.addEventListener('click', onOutsideClick);
                }
                renderSuggestions();
                // After the grid exists, so its height is the one being placed.
                placeBody();
                if (search) {
                    search.focus();
                }
            }

            function close({ focusTrigger = false } = {}) {
                if (body) body.classList.remove('dlux-builder-icon-picker--above');
                if (!body || !isOpen()) {
                    return;
                }
                body.classList.add('d-none');
                if (toggle) {
                    toggle.setAttribute('aria-expanded', 'false');
                }
                document.removeEventListener('click', onOutsideClick);
                // Drop the grid so a closed picker costs nothing to keep around.
                suggestions.innerHTML = '';
                if (search) {
                    search.value = '';
                }
                if (focusTrigger && toggle) {
                    toggle.focus();
                }
            }

            input.addEventListener('input', () => apply(input.value, { rerender: false }));
            input.addEventListener('change', () => apply(input.value));
            if (search) {
                search.addEventListener('input', renderSuggestions);
            }
            if (reset) {
                // Reset means "back to no choice" where empty is allowed, and "back to
                // the default" where it is not.
                reset.addEventListener('click', () => apply(allowEmpty ? '' : defaultIcon));
            }
            if (toggle) {
                toggle.addEventListener('click', () => (isOpen() ? close() : open()));
            }
            picker.addEventListener('keydown', (event) => {
                if (event.key === 'Escape' && isOpen()) {
                    event.stopPropagation();
                    close({ focusTrigger: true });
                }
            });

            apply(currentValue(), { rerender: false });
        });
    }

    window.DluxIconPicker = {
        suggestions: ICON_SUGGESTIONS,
        init: initIconPickers,
    };
    window.initIconPickers = initIconPickers;

    function scan(root) {
        initIconPickers(root || document);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => scan(document));
    } else {
        scan(document);
    }

    new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            for (const node of mutation.addedNodes) {
                if (node.nodeType !== 1) {
                    continue;
                }
                if (node.matches('[data-dlux-icon-picker]') || node.querySelector('[data-dlux-icon-picker]')) {
                    scan(node.matches('[data-dlux-icon-picker]') ? node.parentNode || document : node);
                    return;
                }
            }
        }
    }).observe(document.documentElement, { childList: true, subtree: true });
})();
