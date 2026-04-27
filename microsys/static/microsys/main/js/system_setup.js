(function () {
    'use strict';

    const SETUP_STATE_KEY = `microsys.systemSetupState:${window.location.pathname}`;
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

        // ── Files (Earmark Variants) ──
        'bi-file-earmark',
        'bi-file-earmark-fill',
        'bi-file-earmark-text',
        'bi-file-earmark-text-fill',
        'bi-file-earmark-richtext',
        'bi-file-earmark-richtext-fill',
        'bi-file-earmark-code',
        'bi-file-earmark-code-fill',
        'bi-file-earmark-binary',
        'bi-file-earmark-binary-fill',
        'bi-file-earmark-diff',
        'bi-file-earmark-diff-fill',
        'bi-file-earmark-ruled',
        'bi-file-earmark-ruled-fill',
        'bi-file-earmark-check',
        'bi-file-earmark-check-fill',
        'bi-file-earmark-x',
        'bi-file-earmark-x-fill',
        'bi-file-earmark-plus',
        'bi-file-earmark-plus-fill',
        'bi-file-earmark-minus',
        'bi-file-earmark-minus-fill',
        'bi-file-earmark-lock',
        'bi-file-earmark-lock-fill',
        'bi-file-earmark-lock2',
        'bi-file-earmark-lock2-fill',
        'bi-file-earmark-break',
        'bi-file-earmark-break-fill',
        'bi-file-earmark-bar-graph',
        'bi-file-earmark-bar-graph-fill',
        'bi-file-earmark-spreadsheet',
        'bi-file-earmark-spreadsheet-fill',
        'bi-file-earmark-person',
        'bi-file-earmark-person-fill',
        'bi-file-earmark-medical',
        'bi-file-earmark-medical-fill',
        'bi-file-earmark-post',
        'bi-file-earmark-post-fill',
        'bi-file-earmark-arrow-up',
        'bi-file-earmark-arrow-up-fill',
        'bi-file-earmark-arrow-down',
        'bi-file-earmark-arrow-down-fill',
        'bi-file-earmark-image',
        'bi-file-earmark-image-fill',
        'bi-file-earmark-music',
        'bi-file-earmark-music-fill',
        'bi-file-earmark-play',
        'bi-file-earmark-play-fill',
        'bi-file-earmark-slides',
        'bi-file-earmark-slides-fill',
        'bi-file-earmark-font',
        'bi-file-earmark-font-fill',
        'bi-file-earmark-zip',
        'bi-file-earmark-zip-fill',
        'bi-file-earmark-pdf',
        'bi-file-earmark-pdf-fill',
        'bi-file-earmark-word',
        'bi-file-earmark-word-fill',
        'bi-file-earmark-excel',
        'bi-file-earmark-excel-fill',
        'bi-file-earmark-ppt',
        'bi-file-earmark-ppt-fill',

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

    function t(key, fallback) {
        if (window.__MS_TRANS && typeof window.__MS_TRANS[key] === 'string' && window.__MS_TRANS[key]) {
            return window.__MS_TRANS[key];
        }
        return fallback;
    }

    function parseJson(text, fallback) {
        try {
            return JSON.parse(text || '');
        } catch (err) {
            return fallback;
        }
    }

    function readSetupState() {
        try {
            return parseJson(sessionStorage.getItem(SETUP_STATE_KEY), null);
        } catch (err) {
            return null;
        }
    }

    function persistSetupFormState(form) {
        if (!form || !form.classList.contains('ms-system-setup-form')) {
            return;
        }

        const state = {
            path: window.location.pathname,
            values: {},
            currentStep: 0,
        };

        const steps = Array.from(form.querySelectorAll('.wizard-step'));
        const visibleStepIndex = steps.findIndex((step) => window.getComputedStyle(step).display !== 'none');
        if (visibleStepIndex >= 0) {
            state.currentStep = visibleStepIndex;
        }

        form.querySelectorAll('input[name], select[name], textarea[name]').forEach((field) => {
            if (!field.name || field.name === 'csrfmiddlewaretoken' || field.disabled || field.type === 'file') {
                return;
            }

            if (field.type === 'radio') {
                if (field.checked) {
                    state.values[field.name] = field.value;
                }
                return;
            }

            if (field.type === 'checkbox') {
                state.values[field.name] = Boolean(field.checked);
                return;
            }

            state.values[field.name] = field.value;
        });

        sessionStorage.setItem(SETUP_STATE_KEY, JSON.stringify(state));
    }

    function restoreSetupFormState(root) {
        root.querySelectorAll('form.ms-system-setup-form').forEach((form) => {
            if (form.dataset.setupStateRestored === 'true') {
                return;
            }
            form.dataset.setupStateRestored = 'true';

            const state = readSetupState();
            if (!state || state.path !== window.location.pathname || !state.values || typeof state.values !== 'object') {
                return;
            }

            Object.entries(state.values).forEach(([name, value]) => {
                const safeName = String(name).replace(/"/g, '\\"');
                const fields = Array.from(form.querySelectorAll(`[name="${safeName}"]`));
                if (!fields.length) {
                    return;
                }

                if (fields[0].type === 'radio') {
                    fields.forEach((field) => {
                        field.checked = field.value === value;
                    });
                    return;
                }

                fields.forEach((field) => {
                    if (field.type === 'checkbox') {
                        field.checked = Boolean(value);
                    } else if (field.type !== 'file') {
                        field.value = value;
                    }
                });
            });

            if (Number.isInteger(state.currentStep) && state.currentStep >= 0) {
                form.dataset.msWizardInitialStep = String(state.currentStep);
            }

            sessionStorage.removeItem(SETUP_STATE_KEY);
        });
    }

    window.__msGetWizardInitialStep = function (container) {
        const form = container && (container.matches && container.matches('form') ? container : container.closest && container.closest('form'));
        if (!form || !form.classList.contains('ms-system-setup-form')) {
            return null;
        }
        const state = readSetupState();
        if (!state || state.path !== window.location.pathname) {
            return null;
        }
        return Number.isInteger(state.currentStep) ? state.currentStep : null;
    };

    function humanizeKey(value) {
        return String(value || '')
            .split(':')
            .pop()
            .replace(/[_-]+/g, ' ')
            .replace(/\b\w/g, (char) => char.toUpperCase())
            .trim();
    }

    function namedFieldSelector(name) {
        return `[name="${String(name || '').replace(/"/g, '\\"')}"]`;
    }

    function getNamedFieldInputs(form, name) {
        return Array.from(form.querySelectorAll(namedFieldSelector(name)));
    }

    function getNamedFieldValue(form, name) {
        const inputs = getNamedFieldInputs(form, name);
        if (!inputs.length) {
            return '';
        }

        if (inputs[0].type === 'radio') {
            const checked = inputs.find((input) => input.checked);
            return checked ? checked.value : '';
        }

        return inputs[0].value;
    }

    function setNamedFieldValue(form, name, value) {
        const inputs = getNamedFieldInputs(form, name);
        if (!inputs.length) {
            return;
        }

        if (inputs[0].type === 'radio') {
            inputs.forEach((input) => {
                input.checked = String(input.value) === String(value);
            });
            return;
        }

        inputs[0].value = value;
    }

    function setNamedFieldReadonly(form, name, isReadonly) {
        const inputs = getNamedFieldInputs(form, name);
        if (!inputs.length) {
            return;
        }

        const selectorRoot = inputs[0].closest('[data-ms-selector]');
        if (selectorRoot) {
            selectorRoot.classList.toggle('is-readonly', Boolean(isReadonly));
        }

        inputs.forEach((input) => {
            if (isReadonly) {
                input.setAttribute('tabindex', '-1');
                input.setAttribute('aria-disabled', 'true');
            } else {
                input.removeAttribute('tabindex');
                input.removeAttribute('aria-disabled');
            }
        });
    }

    function setPreviewVisibility(element, isVisible) {
        if (!element) {
            return;
        }
        element.classList.toggle('d-none', !isVisible);
        element.style.display = isVisible ? '' : 'none';
    }

    function readBooleanField(form, selector, fallback) {
        const field = form.querySelector(selector);
        if (!field) {
            return Boolean(fallback);
        }
        return Boolean(field.checked);
    }

    function readTrimmedValue(form, selector, fallback) {
        const field = form.querySelector(selector);
        if (!field) {
            return fallback || '';
        }
        return String(field.value || fallback || '').trim();
    }

    function getSetupAllowedThemeCount(form) {
        return Array.from(form.querySelectorAll('[data-setup-theme-allowed]')).filter((checkbox) => checkbox.checked).length;
    }

    function applyTitlebarPreview(form) {
        const titlebar = document.querySelector('.titlebar');
        if (!titlebar) {
            return;
        }

        const showTitle = readBooleanField(form, '#id_titlebar_show_title', true);
        const showLogo = readBooleanField(form, '#id_titlebar_show_logo', true);
        const showHome = readBooleanField(form, '#id_titlebar_show_home_button', true);
        const titleAlign = getNamedFieldValue(form, 'titlebar_title_align') || 'start';
        const titleSize = getNamedFieldValue(form, 'titlebar_title_size') || 'md';
        const height = getNamedFieldValue(form, 'titlebar_height') || 'balanced';
        const surface = getNamedFieldValue(form, 'titlebar_surface') || 'default';
        const homeShape = getNamedFieldValue(form, 'titlebar_home_shape') || 'circle';
        const homeUrl = readTrimmedValue(form, '#id_home_url', titlebar.querySelector('[data-titlebar-home]')?.getAttribute('href') || '/');
        const scopeName = String(titlebar.dataset.titlebarScopeName || '').trim();
        const htmlLang = (document.documentElement.getAttribute('lang') || (window.USER_PREFS && window.USER_PREFS._lang) || 'en').split('-')[0];
        let systemNames = {};
        try {
            systemNames = JSON.parse(getNamedFieldValue(form, 'system_names') || '{}') || {};
        } catch (e) {
            systemNames = {};
        }
        const defaultLanguage = getNamedFieldValue(form, 'default_language') || 'en';
        const resolvedName = systemNames[htmlLang] || systemNames[defaultLanguage] || Object.values(systemNames).find(Boolean) || 'microSYS';
        const resolvedTitle = scopeName ? `${resolvedName} - ${scopeName}` : resolvedName;

        titlebar.dataset.titleAlign = titleAlign;
        titlebar.dataset.titleSize = titleSize;
        titlebar.dataset.titlebarHeight = height;
        titlebar.dataset.titlebarSurface = surface;
        titlebar.dataset.titlebarHomeShape = homeShape;
        titlebar.dataset.titlebarShowTitle = showTitle ? 'true' : 'false';
        titlebar.dataset.titlebarShowLogo = showLogo ? 'true' : 'false';
        titlebar.dataset.titlebarShowHome = showHome ? 'true' : 'false';

        const homeButton = titlebar.querySelector('[data-titlebar-home]');
        if (homeButton && homeUrl) {
            homeButton.setAttribute('href', homeUrl);
        }

        const titleTarget = titlebar.querySelector('[data-titlebar-title-text]');
        if (titleTarget) {
            titleTarget.textContent = resolvedTitle;
        }
    }

    function applyBrandingFilePreviews(form) {
        const logoInput = form.querySelector('#id_logo');
        const faviconInput = form.querySelector('#id_favicon');

        if (logoInput && logoInput.files && logoInput.files[0]) {
            const reader = new FileReader();
            reader.onload = () => {
                document.querySelectorAll('.titlebar__logo, .ms-setup-page-logo').forEach((image) => {
                    image.setAttribute('src', reader.result);
                });
            };
            reader.readAsDataURL(logoInput.files[0]);
        }

        if (faviconInput && faviconInput.files && faviconInput.files[0]) {
            const reader = new FileReader();
            reader.onload = () => {
                document.querySelectorAll('link[rel="icon"]').forEach((favicon) => {
                    favicon.setAttribute('href', reader.result);
                });
            };
            reader.readAsDataURL(faviconInput.files[0]);
        }
    }

    function applySidebarPreview(form) {
        const sidebar = document.getElementById('sidebar');
        if (!sidebar) {
            return;
        }

        const showIcons = readBooleanField(form, '#id_sidebar_show_icons', true);
        const collapseMode = getNamedFieldValue(form, 'sidebar_collapse_mode') || 'icons';
        const density = getNamedFieldValue(form, 'sidebar_density') || 'balanced';
        const allowUserDensity = readBooleanField(form, '#id_sidebar_allow_user_density', true);
        const enableToolbar = readBooleanField(form, '#id_sidebar_enable_toolbar', true);
        const enableReorder = readBooleanField(form, '#id_sidebar_enable_reorder', true);
        const allowThemeOverride = readBooleanField(form, '#id_allow_user_theme_override', true);
        const allowUserLanguage = readBooleanField(form, '#id_allow_user_language_override', true);
        const allowedThemeCount = getSetupAllowedThemeCount(form);
        const languageCount = form.querySelectorAll('[data-language-row]').length || form.querySelectorAll('[data-setup-language-choice]').length;
        const themeToolVisible = allowThemeOverride && allowedThemeCount > 1;
        const densityToolVisible = allowUserDensity;
        const reorderToolVisible = enableReorder;

        sidebar.dataset.sidebarShowIcons = showIcons ? 'true' : 'false';
        sidebar.dataset.sidebarCollapseMode = collapseMode;
        sidebar.dataset.sidebarDensity = density;
        sidebar.dataset.sidebarDefaultDensity = density;
        sidebar.dataset.sidebarAllowUserDensity = allowUserDensity ? 'true' : 'false';

        if (collapseMode === 'locked_expanded') {
            sidebar.classList.remove('collapsed');
        }

        const titlebar = document.querySelector('.titlebar');
        if (titlebar) {
            titlebar.dataset.sidebarCollapseMode = collapseMode;
        }

        const toolbar = sidebar.querySelector('.sidebar-toolbar');
        const themeArrow = document.getElementById('sidebarThemeArrow');
        const themeIndicator = document.getElementById('sidebarThemeIndicator');
        const themePopup = document.getElementById('sidebarThemePopup');
        const densityControl = sidebar.querySelector('.sidebar-density-control');
        const reorderToggle = document.getElementById('sidebarReorderToggle') || sidebar.querySelector('.reorder-toggle');
        const sectionsManagerLink = sidebar.querySelector('.sidebar-toolbar-link');
        const toolbarVisible = enableToolbar && Boolean(themeToolVisible || densityToolVisible || reorderToolVisible || sectionsManagerLink);

        setPreviewVisibility(themeArrow, themeToolVisible);
        setPreviewVisibility(themeIndicator, themeToolVisible);
        setPreviewVisibility(densityControl, densityToolVisible);
        setPreviewVisibility(reorderToggle, reorderToolVisible);
        setPreviewVisibility(toolbar, toolbarVisible);

        if (!themeToolVisible && themePopup) {
            themePopup.classList.remove('show');
        }

        if (!densityToolVisible) {
            const densityPopup = document.getElementById('sidebarDensityPopup');
            if (densityPopup) {
                densityPopup.classList.remove('show');
            }
        }

        sidebar.querySelectorAll('[data-sidebar-density-choice]').forEach((option) => {
            option.classList.toggle('is-active', option.getAttribute('data-sidebar-density-choice') === density);
        });

        const themeCard = document.querySelector('[data-options-card="theme"]');
        const languageCard = document.querySelector('[data-options-card="language"]');
        const sidebarDensityCard = document.querySelector('[data-options-card="sidebar-density"]');

        setPreviewVisibility(themeCard, themeToolVisible);
        setPreviewVisibility(languageCard, allowUserLanguage && languageCount > 1);
        setPreviewVisibility(sidebarDensityCard, allowUserDensity);
    }

    function applyTableDensityPreview(form) {
        const density = getNamedFieldValue(form, 'default_table_density') || 'balanced';
        if (typeof window.applyMicrosysTableDensityPreview === 'function') {
            window.applyMicrosysTableDensityPreview(density);
        }
    }

    function applyImmediateSystemSettingsPreview(form) {
        if (!form || !form.classList.contains('ms-system-setup-form')) {
            return;
        }
        applyTitlebarPreview(form);
        applyBrandingFilePreviews(form);
        applySidebarPreview(form);
        applyTableDensityPreview(form);
        window.dispatchEvent(new Event('resize'));
    }

    function initImmediateSystemSettingsPreview(root) {
        root.querySelectorAll('form.ms-system-setup-form').forEach((form) => {
            if (form.dataset.immediatePreviewBound === 'true') {
                applyImmediateSystemSettingsPreview(form);
                return;
            }

            form.dataset.immediatePreviewBound = 'true';

            form.querySelectorAll('input[name], select[name], textarea[name]').forEach((field) => {
                const eventName = field.type === 'text' || field.tagName === 'TEXTAREA' ? 'input' : 'change';
                field.addEventListener(eventName, () => {
                    applyImmediateSystemSettingsPreview(form);
                });
                if (eventName !== 'change') {
                    field.addEventListener('change', () => {
                        applyImmediateSystemSettingsPreview(form);
                    });
                }
            });

            applyImmediateSystemSettingsPreview(form);
        });
    }

    function availableItemDisplayLabel(item) {
        const label = String(item && item.label ? item.label : '').trim();
        const groupLabel = String(item && item.group_label ? item.group_label : '').trim();
        const urlName = String(item && item.url_name ? item.url_name : item && item.id ? item.id : '').trim();
        const leaf = urlName.split(':').pop();

        if (label && label !== groupLabel) {
            return label;
        }
        if (leaf === 'dashboard' && groupLabel) {
            return `${groupLabel} Dashboard`;
        }
        return humanizeKey(urlName) || groupLabel || t('sidebar_group_label', 'Item');
    }

    function normalizeCatalog(catalog) {
        if (!Array.isArray(catalog)) {
            return [];
        }
        return catalog
            .filter(entry => entry && entry.id && entry.url_name)
            .map(entry => ({
                kind: 'item',
                id: entry.id,
                url_name: entry.url_name,
                label: entry.label || entry.id,
                icon: entry.icon || 'bi-link-45deg',
                permissions: Array.isArray(entry.permissions) ? entry.permissions : [],
                group_key: entry.group_key || 'general',
                group_label: entry.group_label || entry.group_key || 'General',
                group_icon: entry.group_icon || 'bi-folder2-open',
                is_system: Boolean(entry.is_system),
            }));
    }

    function buildCatalogLookup(catalog) {
        const lookup = new Map();
        (catalog || []).forEach((entry) => {
            if (!entry || typeof entry !== 'object') {
                return;
            }
            const id = String(entry.id || '').trim();
            const urlName = String(entry.url_name || '').trim();
            if (id) {
                lookup.set(id, entry);
            }
            if (urlName) {
                lookup.set(urlName, entry);
            }
        });
        return lookup;
    }

    function findCatalogEntry(entry, catalogLookup) {
        if (!entry || typeof entry !== 'object' || !catalogLookup) {
            return null;
        }
        const id = String(entry.id || '').trim();
        const urlName = String(entry.url_name || '').trim();
        return catalogLookup.get(id) || catalogLookup.get(urlName) || null;
    }

    function frameworkDefaultLabels(entry, discovered) {
        const labels = new Set();
        const candidates = [
            entry && entry.id,
            entry && entry.url_name,
            discovered && discovered.label,
            discovered && discovered.group_label,
            discovered && discovered.id,
            discovered && discovered.url_name,
        ];

        candidates.forEach((candidate) => {
            const value = String(candidate || '').trim();
            if (value) {
                labels.add(value);
            }
        });

        const humanized = humanizeKey((entry && (entry.url_name || entry.id)) || (discovered && (discovered.url_name || discovered.id)) || '');
        if (humanized) {
            labels.add(humanized);
        }

        if (discovered) {
            const displayLabel = availableItemDisplayLabel(discovered);
            if (displayLabel) {
                labels.add(displayLabel);
            }
        }

        return labels;
    }

    function resolveBuilderItemLabel(entry, currentDiscovered, fallbackDiscovered) {
        const savedLabel = String(entry && entry.label ? entry.label : '').trim();
        const localizedLabel = currentDiscovered ? availableItemDisplayLabel(currentDiscovered) : '';
        const defaultLabels = new Set([
            ...frameworkDefaultLabels(entry, currentDiscovered),
            ...frameworkDefaultLabels(entry, fallbackDiscovered),
        ]);

        if (!savedLabel || defaultLabels.has(savedLabel)) {
            return localizedLabel || savedLabel || String(entry && (entry.url_name || entry.id) ? (entry.url_name || entry.id) : '').trim();
        }

        return savedLabel;
    }

    function resolveBuilderGroupLabel(entry, items, fallbackCatalogLookup) {
        const savedLabel = String(entry && entry.label ? entry.label : '').trim();
        const localizedLabel = String(
            (items || []).find((item) => String(item && item.group_label ? item.group_label : '').trim())?.group_label || ''
        ).trim();
        const fallbackReference = findCatalogEntry(((entry && entry.items) || []).find((item) => item && (item.id || item.url_name)), fallbackCatalogLookup);
        const fallbackGroupLabel = String(fallbackReference && fallbackReference.group_label ? fallbackReference.group_label : '').trim();
        const defaultLabels = new Set([
            fallbackGroupLabel,
            t('sidebar_group_label', 'Group'),
            'Group',
        ]);

        if (!savedLabel || (localizedLabel && defaultLabels.has(savedLabel))) {
            return localizedLabel || savedLabel || t('sidebar_group_label', 'Group');
        }

        return savedLabel;
    }

    function normalizeSidebarConfig(config, catalogLookup, fallbackCatalogLookup) {
        if (!config || typeof config !== 'object') {
            return { home_url_name: null, entries: [] };
        }

        const entries = Array.isArray(config.entries) ? config.entries : [];
        return {
            home_url_name: config.home_url_name || null,
            entries: entries.map(entry => normalizeEntry(entry, catalogLookup, fallbackCatalogLookup)).filter(Boolean),
        };
    }

    function normalizeEntry(entry, catalogLookup, fallbackCatalogLookup) {
        if (!entry || typeof entry !== 'object') {
            return null;
        }
        if ((entry.kind || 'item') === 'group') {
            const items = Array.isArray(entry.items)
                ? entry.items.map(item => normalizeEntry(item, catalogLookup, fallbackCatalogLookup)).filter(Boolean)
                : [];
            return {
                kind: 'group',
                id: entry.id || `group-${Date.now()}`,
                label: resolveBuilderGroupLabel(entry, items, fallbackCatalogLookup),
                icon: entry.icon || 'bi-folder2-open',
                items,
            };
        }
        if (!entry.id && !entry.url_name) {
            return null;
        }
        const currentDiscovered = findCatalogEntry(entry, catalogLookup);
        const fallbackDiscovered = findCatalogEntry(entry, fallbackCatalogLookup);
        return {
            kind: 'item',
            id: entry.id || entry.url_name,
            url_name: entry.url_name || entry.id,
            label: resolveBuilderItemLabel(entry, currentDiscovered, fallbackDiscovered),
            icon: entry.icon || (currentDiscovered && currentDiscovered.icon) || 'bi-link-45deg',
            permissions: Array.isArray(entry.permissions) ? entry.permissions : ((currentDiscovered && currentDiscovered.permissions) || []),
            group_key: entry.group_key || (currentDiscovered && currentDiscovered.group_key) || '',
            group_label: entry.group_label || (currentDiscovered && currentDiscovered.group_label) || '',
        };
    }

    function cloneEntry(entry) {
        return JSON.parse(JSON.stringify(entry));
    }

    function cloneGroupEntry(group) {
        const items = Array.isArray(group && group.items) ? group.items.map(cloneEntry) : [];
        const label = String(group && group.label ? group.label : '').trim() || t('sidebar_group_label', 'Group');
        return {
            kind: 'group',
            id: makeGroupId(group && (group.id || group.group_key || label || 'group')),
            label,
            icon: group && group.icon ? group.icon : 'bi-folder2-open',
            items,
        };
    }

    function makeGroupId(label) {
        const safeLabel = (label || 'group').toLowerCase().replace(/\s+/g, '-').replace(/[^\w-]+/g, '').replace(/-+/g, '-');
        return `${safeLabel || 'group'}-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    }

    function collectSelectedItemIds(entries, acc) {
        acc = acc || new Set();
        (entries || []).forEach(entry => {
            if (entry.kind === 'group') {
                collectSelectedItemIds(entry.items || [], acc);
                return;
            }
            if (entry.id) {
                acc.add(entry.id);
            }
        });
        return acc;
    }

    function availableItems(state) {
        const selectedIds = collectSelectedItemIds(state.config.entries);
        return state.catalog.filter(item => !selectedIds.has(item.id) && (state.showSystemItems || !item.is_system));
    }

    function groupedAvailableItems(state) {
        const grouped = {};
        availableItems(state)
            .filter(item => {
                if (!state.search) return true;
                const haystack = `${item.label} ${item.group_label} ${item.url_name}`.toLowerCase();
                return haystack.includes(state.search.toLowerCase());
            })
            .forEach(item => {
                const key = item.group_key || item.group_label || 'general';
                if (!grouped[key]) {
                    grouped[key] = {
                        kind: 'group',
                        id: key,
                        label: item.group_label || key,
                        icon: item.group_icon || 'bi-folder2-open',
                        items: [],
                    };
                }
                grouped[key].items.push(item);
            });

        return Object.values(grouped).sort((left, right) => left.label.localeCompare(right.label));
    }

    function findEntryLocation(entries, id, kind) {
        for (let index = 0; index < entries.length; index += 1) {
            const entry = entries[index];
            if (entry.kind === kind && entry.id === id) {
                return { parent: entries, index, entry, container: 'root' };
            }
            if (entry.kind === 'group') {
                if (kind === 'group' && entry.id === id) {
                    return { parent: entries, index, entry, container: 'root' };
                }
                const childIndex = (entry.items || []).findIndex(item => item.id === id && item.kind === kind);
                if (childIndex !== -1) {
                    return { parent: entry.items, index: childIndex, entry: entry.items[childIndex], container: 'group', group: entry };
                }
            }
        }
        return null;
    }

    function insertEntryIntoConfig(configEntries, entry, target) {
        if (target.type === 'root-container') {
            configEntries.push(entry);
            return;
        }

        if (target.type === 'group-container') {
            const groupLocation = findEntryLocation(configEntries, target.groupId, 'group');
            if (groupLocation && groupLocation.entry.kind === 'group') {
                groupLocation.entry.items.push(entry);
            } else {
                configEntries.push(entry);
            }
            return;
        }

        if (target.type === 'root-node') {
            const targetLocation = findEntryLocation(configEntries, target.targetId, target.targetKind);
            if (!targetLocation) {
                configEntries.push(entry);
            } else {
                const insertIndex = target.before ? targetLocation.index : targetLocation.index + 1;
                configEntries.splice(insertIndex, 0, entry);
            }
            return;
        }

        if (target.type === 'group-node') {
            const groupLocation = findEntryLocation(configEntries, target.parentGroupId, 'group');
            if (!groupLocation || groupLocation.entry.kind !== 'group') {
                configEntries.push(entry);
                return;
            }
            const targetLocation = findEntryLocation(groupLocation.entry.items, target.targetId, target.targetKind);
            if (!targetLocation) {
                groupLocation.entry.items.push(entry);
            } else {
                const insertIndex = target.before ? targetLocation.index : targetLocation.index + 1;
                groupLocation.entry.items.splice(insertIndex, 0, entry);
            }
        }
    }

    function topLevelItems(entries) {
        return (entries || []).filter(entry => entry.kind === 'item' && entry.url_name);
    }

    function initBuilder(builder) {
        if (!builder || builder.dataset.builderBound === 'true') {
            return;
        }
        builder.dataset.builderBound = 'true';

        const form = builder.closest('form');
        const hiddenInput = form ? form.querySelector('input[name="sidebar_config"]') : null;
        if (!hiddenInput) {
            return;
        }

        const catalogData = builder.querySelector('.ms-sidebar-catalog-data');
        const fallbackCatalogData = builder.querySelector('.ms-sidebar-catalog-fallback-data');
        const configData = builder.querySelector('.ms-sidebar-config-data');
        const catalog = normalizeCatalog(parseJson(catalogData ? catalogData.value : '[]', []));
        const fallbackCatalog = normalizeCatalog(parseJson(fallbackCatalogData ? fallbackCatalogData.value : '[]', []));
        const catalogLookup = buildCatalogLookup(catalog);
        const fallbackCatalogLookup = buildCatalogLookup(fallbackCatalog);
        const state = {
            catalog,
            config: normalizeSidebarConfig(
                parseJson(hiddenInput.value || (configData ? configData.value : '{}'), {}),
                catalogLookup,
                fallbackCatalogLookup
            ),
            selected: null,
            selectedTargetGroup: null,
            search: '',
            dragging: null,
            showSystemItems: false,
            iconSearch: '',
        };

        const refs = {
            selectedTree: builder.querySelector('[data-builder-selected-tree]'),
            availableList: builder.querySelector('[data-builder-available-list]'),
            search: builder.querySelector('[data-builder-search]'),
            systemToggle: builder.querySelector('[data-builder-system-toggle]'),
            inspector: builder.querySelector('[data-builder-inspector]'),
            inspectorEmpty: builder.querySelector('[data-builder-empty-inspector]'),
            labelInput: builder.querySelector('[data-builder-label-input]'),
            iconInput: builder.querySelector('[data-builder-icon-input]'),
            iconPreview: builder.querySelector('[data-builder-icon-preview]'),
            iconSuggestions: builder.querySelector('[data-builder-icon-suggestions]'),
            iconSearch: builder.querySelector('[data-builder-icon-search]'),
        };

        function clearDragFeedback() {
            builder.querySelectorAll('.ms-builder-drop-target').forEach(el => el.classList.remove('ms-builder-drop-target'));
            builder.querySelectorAll('.ms-builder-drop-before').forEach(el => el.classList.remove('ms-builder-drop-before'));
            builder.querySelectorAll('.ms-builder-drop-after').forEach(el => el.classList.remove('ms-builder-drop-after'));
            builder.querySelectorAll('.is-dragging').forEach(el => el.classList.remove('is-dragging'));
        }

        function serialize() {
            hiddenInput.value = JSON.stringify(state.config);
        }

        function renderAvailable() {
            refs.availableList.innerHTML = '';

            groupedAvailableItems(state).forEach(group => {
                const section = document.createElement('div');
                section.className = 'ms-builder-available-group';
                const groupButton = document.createElement('button');
                groupButton.type = 'button';
                groupButton.className = 'ms-builder-item available-item fw-semibold';
                groupButton.dataset.pane = 'available';
                groupButton.dataset.entryId = group.id;
                groupButton.dataset.entryKind = 'group';
                if (state.selected && state.selected.pane === 'available' && state.selected.kind === 'group' && state.selected.id === group.id) {
                    groupButton.classList.add('is-active');
                }
                groupButton.innerHTML = `
                    <span class="ms-builder-item-main">
                        <i class="bi ${group.icon}"></i>
                        <span>${group.label}</span>
                    </span>
                    <span class="badge text-bg-light">${group.items.length}</span>
                `;
                groupButton.addEventListener('click', () => {
                    state.selected = { pane: 'available', id: group.id, kind: 'group' };
                    state.selectedTargetGroup = null;
                    renderAll();
                });
                groupButton.addEventListener('dblclick', () => {
                    addSelectedAvailableItem();
                });
                groupButton.draggable = true;
                groupButton.addEventListener('dragstart', () => {
                    state.dragging = { pane: 'available', id: group.id, kind: 'group' };
                    groupButton.classList.add('is-dragging');
                });
                groupButton.addEventListener('dragend', () => {
                    state.dragging = null;
                    clearDragFeedback();
                });
                section.appendChild(groupButton);

                const children = document.createElement('div');
                children.className = 'ms-builder-available-items';

                group.items.forEach(item => {
                    const button = document.createElement('button');
                    button.type = 'button';
                    button.className = 'ms-builder-item available-item is-child';
                    button.dataset.pane = 'available';
                    button.dataset.entryId = item.id;
                    button.dataset.entryKind = 'item';
                    if (state.selected && state.selected.pane === 'available' && state.selected.kind === 'item' && state.selected.id === item.id) {
                        button.classList.add('is-active');
                    }
                    button.innerHTML = `
                        <span class="ms-builder-item-main">
                            <i class="bi ${item.icon}"></i>
                            <span class="ms-builder-item-copy">
                                <span class="ms-builder-item-label">${availableItemDisplayLabel(item)}</span>
                                <span class="ms-builder-item-meta">${item.url_name || item.id}</span>
                            </span>
                        </span>
                    `;
                    button.addEventListener('click', () => {
                        state.selected = { pane: 'available', id: item.id, kind: 'item' };
                        state.selectedTargetGroup = null;
                        renderAll();
                    });
                    button.addEventListener('dblclick', () => {
                        addSelectedAvailableItem();
                    });
                    button.draggable = true;
                    button.addEventListener('dragstart', () => {
                        state.dragging = { pane: 'available', id: item.id, kind: 'item' };
                        button.classList.add('is-dragging');
                    });
                    button.addEventListener('dragend', () => {
                        state.dragging = null;
                        clearDragFeedback();
                    });
                    children.appendChild(button);
                });

                section.appendChild(children);

                refs.availableList.appendChild(section);
            });

            if (!refs.availableList.children.length) {
                refs.availableList.innerHTML = `<div class="text-muted small">${t('sidebar_no_available', 'No available entries match the current selection.')}</div>`;
            }
        }

        function makeNode(entry, parentGroupId) {
            const wrapper = document.createElement('div');
            wrapper.className = `ms-builder-node ${entry.kind === 'group' ? 'is-group' : 'is-item'}`;
            wrapper.dataset.entryId = entry.id;
            wrapper.dataset.entryKind = entry.kind;
            wrapper.draggable = true;

            if (state.selected && state.selected.pane === 'selected' && state.selected.id === entry.id && state.selected.kind === entry.kind) {
                wrapper.classList.add('is-active');
            }

            wrapper.addEventListener('click', (event) => {
                event.stopPropagation();
                state.selected = { pane: 'selected', id: entry.id, kind: entry.kind };
                state.selectedTargetGroup = entry.kind === 'group' ? entry.id : (parentGroupId || null);
                renderAll();
            });

            wrapper.addEventListener('dragstart', () => {
                state.dragging = { pane: 'selected', id: entry.id, kind: entry.kind };
                wrapper.classList.add('is-dragging');
            });

            wrapper.addEventListener('dragend', () => {
                state.dragging = null;
                clearDragFeedback();
            });

            wrapper.addEventListener('dragover', (event) => {
                if (!state.dragging) return;
                event.preventDefault();
                const rect = wrapper.getBoundingClientRect();
                const before = event.clientY < rect.top + rect.height / 2;
                wrapper.classList.toggle('ms-builder-drop-before', before);
                wrapper.classList.toggle('ms-builder-drop-after', !before);
            });

            wrapper.addEventListener('dragleave', () => {
                wrapper.classList.remove('ms-builder-drop-before', 'ms-builder-drop-after');
            });

            wrapper.addEventListener('drop', (event) => {
                if (!state.dragging) return;
                event.preventDefault();
                event.stopPropagation();
                const rect = wrapper.getBoundingClientRect();
                const before = event.clientY < rect.top + rect.height / 2;
                moveDraggedEntry({
                    type: parentGroupId ? 'group-node' : 'root-node',
                    targetId: entry.id,
                    targetKind: entry.kind,
                    before,
                    parentGroupId,
                });
            });

            if (entry.kind === 'group') {
                wrapper.innerHTML = `
                    <div class="ms-builder-group-header">
                        <span class="ms-builder-item-main">
                            <i class="bi ${entry.icon}"></i>
                            <span>${entry.label}</span>
                        </span>
                        <span class="badge text-bg-light">${(entry.items || []).length}</span>
                    </div>
                    <div class="ms-builder-group-items" data-group-dropzone="${entry.id}"></div>
                `;

                const itemsContainer = wrapper.querySelector('[data-group-dropzone]');
                itemsContainer.addEventListener('dragover', (event) => {
                    if (!state.dragging || state.dragging.kind !== 'item') return;
                    event.preventDefault();
                    itemsContainer.classList.add('ms-builder-drop-target');
                });
                itemsContainer.addEventListener('dragleave', () => {
                    itemsContainer.classList.remove('ms-builder-drop-target');
                });
                itemsContainer.addEventListener('drop', (event) => {
                    if (!state.dragging || state.dragging.kind !== 'item') return;
                    event.preventDefault();
                    event.stopPropagation();
                    moveDraggedEntry({ type: 'group-container', groupId: entry.id });
                });

                (entry.items || []).forEach(item => {
                    itemsContainer.appendChild(makeNode(item, entry.id));
                });
            } else {
                wrapper.innerHTML = `
                    <span class="ms-builder-item-main">
                        <i class="bi ${entry.icon}"></i>
                        <span>${entry.label}</span>
                    </span>
                    <span class="badge text-bg-light">${entry.url_name}</span>
                `;
            }

            return wrapper;
        }

        function renderSelected() {
            refs.selectedTree.innerHTML = '';

            state.config.entries.forEach(entry => {
                refs.selectedTree.appendChild(makeNode(entry, null));
            });

            if (!refs.selectedTree.children.length) {
                refs.selectedTree.innerHTML = `<div class="text-muted small">${t('sidebar_no_selected', 'No entries selected yet.')}</div>`;
            }
        }

        function renderInspector() {
            if (!state.selected || state.selected.pane !== 'selected') {
                refs.inspector.classList.add('d-none');
                refs.inspectorEmpty.classList.remove('d-none');
                return;
            }

            const location = findEntryLocation(state.config.entries, state.selected.id, state.selected.kind);
            if (!location) {
                refs.inspector.classList.add('d-none');
                refs.inspectorEmpty.classList.remove('d-none');
                return;
            }

            refs.inspector.classList.remove('d-none');
            refs.inspectorEmpty.classList.add('d-none');
            refs.labelInput.value = location.entry.label || '';
            refs.iconInput.value = location.entry.icon || '';
            refs.iconPreview.className = `bi ${location.entry.icon || 'bi-link-45deg'}`;
            refs.iconSuggestions.innerHTML = '';

            const iconFilter = (state.iconSearch || '').toLowerCase().replace(/\s+/g, '-');
            const filtered = iconFilter
                ? ICON_SUGGESTIONS.filter(icon => icon.includes(iconFilter))
                : ICON_SUGGESTIONS;

            if (refs.iconSearch && refs.iconSearch.value !== (state.iconSearch || '')) {
                refs.iconSearch.value = state.iconSearch || '';
            }

            filtered.forEach(icon => {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = `btn btn-sm ms-builder-icon-choice ${location.entry.icon === icon ? 'is-active' : ''}`;
                button.setAttribute('title', icon);
                button.setAttribute('aria-label', icon);
                button.innerHTML = `<i class="bi ${icon}"></i>`;
                button.addEventListener('click', () => {
                    refs.iconInput.value = icon;
                    location.entry.icon = icon;
                    refs.iconPreview.className = `bi ${icon}`;
                    renderAll();
                });
                refs.iconSuggestions.appendChild(button);
            });

            if (!filtered.length) {
                refs.iconSuggestions.innerHTML = `<div class="text-muted small p-2">${t('sidebar_no_icons_found', 'No icons match your search.')}</div>`;
            }
        }

        function renderAll() {
            serialize();
            renderSelected();
            renderAvailable();
            renderInspector();
        }

        function addSelectedAvailableItem() {
            if (!state.selected || state.selected.pane !== 'available') return;
            if (state.selected.kind === 'group') {
                const sourceGroup = groupedAvailableItems(state).find(group => group.id === state.selected.id);
                if (!sourceGroup || !sourceGroup.items.length) return;
                const nextGroup = cloneGroupEntry(sourceGroup);
                nextGroup.items = nextGroup.items.map((item) => ({
                    ...item,
                    label: resolveBuilderItemLabel(item, findCatalogEntry(item, catalogLookup), findCatalogEntry(item, fallbackCatalogLookup)),
                }));
                nextGroup.label = resolveBuilderGroupLabel(nextGroup, nextGroup.items, fallbackCatalogLookup);
                state.config.entries.push(nextGroup);
                state.selected = { pane: 'selected', id: nextGroup.id, kind: 'group' };
                renderAll();
                return;
            }

            const source = state.catalog.find(item => item.id === state.selected.id);
            if (!source) return;
            const nextItem = cloneEntry(source);
            nextItem.label = resolveBuilderItemLabel(nextItem, source, findCatalogEntry(source, fallbackCatalogLookup));
            state.config.entries.push(nextItem);

            state.selected = { pane: 'selected', id: nextItem.id, kind: 'item' };
            renderAll();
        }

        function addAllAvailableItems() {
            const groups = groupedAvailableItems(state)
                .map((group) => {
                    const nextGroup = cloneGroupEntry(group);
                    nextGroup.items = nextGroup.items.map((item) => ({
                        ...item,
                        label: resolveBuilderItemLabel(item, findCatalogEntry(item, catalogLookup), findCatalogEntry(item, fallbackCatalogLookup)),
                    }));
                    nextGroup.label = resolveBuilderGroupLabel(nextGroup, nextGroup.items, fallbackCatalogLookup);
                    return nextGroup;
                })
                .filter(group => group.items.length);
            if (!groups.length) return;
            state.config.entries = state.config.entries.concat(groups);
            state.selected = null;
            state.selectedTargetGroup = null;
            renderAll();
        }

        function removeSelectedEntry() {
            if (!state.selected || state.selected.pane !== 'selected') return;
            const location = findEntryLocation(state.config.entries, state.selected.id, state.selected.kind);
            if (!location) return;
            location.parent.splice(location.index, 1);
            state.selected = null;
            renderAll();
        }

        function removeAllSelectedEntries() {
            state.config.entries = [];
            state.selected = null;
            state.selectedTargetGroup = null;
            renderAll();
        }

        function moveSelectedToRoot() {
            if (!state.selected || state.selected.pane !== 'selected' || state.selected.kind !== 'item') return;
            const location = findEntryLocation(state.config.entries, state.selected.id, 'item');
            if (!location || location.container !== 'group') return;
            const [entry] = location.parent.splice(location.index, 1);
            state.config.entries.push(entry);
            renderAll();
        }

        function addGroup() {
            const group = {
                kind: 'group',
                id: makeGroupId('group'),
                label: t('sidebar_new_group', 'New Group'),
                icon: 'bi-folder2-open',
                items: [],
            };
            state.config.entries.push(group);
            state.selected = { pane: 'selected', id: group.id, kind: 'group' };
            renderAll();
        }

        function duplicateSelectedEntry() {
            if (!state.selected || state.selected.pane !== 'selected' || state.selected.kind !== 'group') return;
            const location = findEntryLocation(state.config.entries, state.selected.id, 'group');
            if (!location) return;
            const duplicate = {
                kind: 'group',
                id: makeGroupId(location.entry.label),
                label: `${location.entry.label} ${t('sidebar_copy_suffix', 'Copy')}`,
                icon: location.entry.icon,
                items: [],
            };
            location.parent.splice(location.index + 1, 0, duplicate);
            state.selected = { pane: 'selected', id: duplicate.id, kind: 'group' };
            renderAll();
        }

        function moveDraggedEntry(target) {
            const dragging = state.dragging;
            if (!dragging) return;

            if (dragging.pane === 'available') {
                addDraggedAvailableEntry(target);
                return;
            }

            const source = findEntryLocation(state.config.entries, dragging.id, dragging.kind);
            if (!source) return;
            if (dragging.kind === 'group' && target.type !== 'root-container' && target.type !== 'root-node') {
                return;
            }

            const [entry] = source.parent.splice(source.index, 1);
            insertEntryIntoConfig(state.config.entries, entry, target);

            state.selected = { pane: 'selected', id: entry.id, kind: entry.kind };
            state.dragging = null;
            renderAll();
        }

        function addDraggedAvailableEntry(target) {
            const dragging = state.dragging;
            if (!dragging || dragging.pane !== 'available') return;

            if (dragging.kind === 'group') {
                if (target.type !== 'root-container' && target.type !== 'root-node') {
                    return;
                }
                const sourceGroup = groupedAvailableItems(state).find(group => group.id === dragging.id);
                if (!sourceGroup || !sourceGroup.items.length) return;
                const nextGroup = cloneGroupEntry(sourceGroup);
                nextGroup.items = nextGroup.items.map((item) => ({
                    ...item,
                    label: resolveBuilderItemLabel(item, findCatalogEntry(item, catalogLookup), findCatalogEntry(item, fallbackCatalogLookup)),
                }));
                nextGroup.label = resolveBuilderGroupLabel(nextGroup, nextGroup.items, fallbackCatalogLookup);
                insertEntryIntoConfig(state.config.entries, nextGroup, target);
                state.selected = { pane: 'selected', id: nextGroup.id, kind: 'group' };
            } else {
                const source = state.catalog.find(item => item.id === dragging.id);
                if (!source) return;
                const nextItem = cloneEntry(source);
                nextItem.label = resolveBuilderItemLabel(nextItem, source, findCatalogEntry(source, fallbackCatalogLookup));
                insertEntryIntoConfig(state.config.entries, nextItem, target);
                state.selected = { pane: 'selected', id: nextItem.id, kind: 'item' };
            }

            state.dragging = null;
            renderAll();
        }

        function removeDraggedSelectedEntry() {
            const dragging = state.dragging;
            if (!dragging || dragging.pane !== 'selected') return;
            const location = findEntryLocation(state.config.entries, dragging.id, dragging.kind);
            if (!location) return;
            location.parent.splice(location.index, 1);
            state.selected = null;
            state.selectedTargetGroup = null;
            state.dragging = null;
            renderAll();
        }

        refs.search.addEventListener('input', () => {
            state.search = refs.search.value || '';
            renderAvailable();
        });

        if (refs.iconSearch) {
            refs.iconSearch.addEventListener('input', () => {
                state.iconSearch = refs.iconSearch.value || '';
                renderInspector();
            });
        }

        if (refs.systemToggle) {
            refs.systemToggle.addEventListener('change', () => {
                state.showSystemItems = Boolean(refs.systemToggle.checked);
                if (!state.showSystemItems && state.selected && state.selected.pane === 'available') {
                    const selectedAvailableItem = state.catalog.find(item => item.id === state.selected.id);
                    if (
                        (state.selected.kind === 'group' && state.selected.id === 'microsys') ||
                        (selectedAvailableItem && selectedAvailableItem.is_system)
                    ) {
                        state.selected = null;
                    }
                }
                renderAvailable();
            });
        }

        refs.labelInput.addEventListener('input', () => {
            if (!state.selected || state.selected.pane !== 'selected') return;
            const location = findEntryLocation(state.config.entries, state.selected.id, state.selected.kind);
            if (!location) return;
            location.entry.label = refs.labelInput.value || '';
            serialize();
            renderSelected();
            renderAvailable();
        });

        refs.iconInput.addEventListener('input', () => {
            if (!state.selected || state.selected.pane !== 'selected') return;
            const location = findEntryLocation(state.config.entries, state.selected.id, state.selected.kind);
            if (!location) return;
            location.entry.icon = refs.iconInput.value || 'bi-link-45deg';
            refs.iconPreview.className = `bi ${location.entry.icon}`;
            serialize();
            renderSelected();
            renderAvailable();
            renderInspector();
        });

        refs.selectedTree.addEventListener('dragover', (event) => {
            if (!state.dragging) return;
            event.preventDefault();
            refs.selectedTree.classList.add('ms-builder-drop-target');
        });
        refs.selectedTree.addEventListener('dragleave', () => {
            refs.selectedTree.classList.remove('ms-builder-drop-target');
        });
        refs.selectedTree.addEventListener('drop', (event) => {
            if (!state.dragging) return;
            event.preventDefault();
            event.stopPropagation();
            moveDraggedEntry({ type: 'root-container' });
        });

        refs.availableList.addEventListener('dragover', (event) => {
            if (!state.dragging || state.dragging.pane !== 'selected') return;
            event.preventDefault();
            refs.availableList.classList.add('ms-builder-drop-target');
        });
        refs.availableList.addEventListener('dragleave', () => {
            refs.availableList.classList.remove('ms-builder-drop-target');
        });
        refs.availableList.addEventListener('drop', (event) => {
            if (!state.dragging || state.dragging.pane !== 'selected') return;
            event.preventDefault();
            event.stopPropagation();
            removeDraggedSelectedEntry();
        });

        builder.querySelectorAll('[data-builder-action]').forEach(button => {
            button.addEventListener('click', () => {
                const action = button.getAttribute('data-builder-action');
                if (action === 'add-selected') addSelectedAvailableItem();
                if (action === 'add-all') addAllAvailableItems();
                if (action === 'remove-selected') removeSelectedEntry();
                if (action === 'remove-all') removeAllSelectedEntries();
                if (action === 'move-root') moveSelectedToRoot();
                if (action === 'add-group') addGroup();
                if (action === 'duplicate-entry') duplicateSelectedEntry();
                if (action === 'delete-entry') removeSelectedEntry();
            });
        });

        renderAll();
    }

    function initSetupHomeFields(root) {
        root.querySelectorAll('form').forEach((form) => {
            if (form.dataset.setupHomeFieldsBound === 'true') {
                return;
            }

            const routeFields = getNamedFieldInputs(form, 'home_url_discovered');
            const urlInput = form.querySelector('[name="home_url"]');
            if (!routeFields.length || !urlInput) {
                return;
            }

            form.dataset.setupHomeFieldsBound = 'true';

            const routeSelect = routeFields.find((field) => field.tagName === 'SELECT');
            const routeRadios = routeFields.filter((field) => field.type === 'radio');

            function selectableValues() {
                if (routeSelect) {
                    return new Set(
                        Array.from(routeSelect.options || [])
                            .map((option) => option.value)
                            .filter(Boolean)
                    );
                }
                return new Set(routeRadios.map((field) => field.value).filter(Boolean));
            }

            function syncSelectFromInput() {
                const currentValue = (urlInput.value || '').trim();
                const values = selectableValues();
                if (routeSelect) {
                    routeSelect.value = values.has(currentValue) ? currentValue : '';
                    return;
                }
                routeRadios.forEach((field) => {
                    if (!currentValue && !field.value) {
                        field.checked = true;
                        return;
                    }
                    field.checked = values.has(currentValue) && field.value === currentValue;
                });
            }

            if (routeSelect) {
                routeSelect.addEventListener('change', () => {
                    if (!routeSelect.value) {
                        return;
                    }
                    urlInput.value = routeSelect.value;
                    urlInput.dispatchEvent(new Event('input', { bubbles: true }));
                    urlInput.dispatchEvent(new Event('change', { bubbles: true }));
                });
            }

            routeRadios.forEach((field) => {
                field.addEventListener('change', () => {
                    if (!field.checked || !field.value) {
                        return;
                    }
                    urlInput.value = field.value;
                    urlInput.dispatchEvent(new Event('input', { bubbles: true }));
                    urlInput.dispatchEvent(new Event('change', { bubbles: true }));
                });
            });

            urlInput.addEventListener('input', syncSelectFromInput);
            urlInput.addEventListener('change', syncSelectFromInput);
            syncSelectFromInput();
        });
    }

    function initSetupLanguagePicker(root) {
        root.querySelectorAll('[data-setup-language-picker]').forEach((picker) => {
            if (picker.dataset.bound === 'true') return;
            picker.dataset.bound = 'true';

            const inputId = picker.getAttribute('data-language-input');
            const input = inputId ? document.getElementById(inputId) : null;
            const form = picker.closest('form');
            if (!input) return;

            const options = Array.from(picker.querySelectorAll('[data-setup-language-choice]'));

            function syncActive() {
                const activeLanguage = input.value || 'en';
                options.forEach((option) => {
                    option.classList.toggle('lang-active', option.getAttribute('data-setup-language-choice') === activeLanguage);
                });
            }

            options.forEach((option) => {
                option.addEventListener('click', () => {
                    const language = option.getAttribute('data-setup-language-choice') || 'en';
                    const currentLanguage = (window.USER_PREFS && window.USER_PREFS._lang) || 'en';
                    input.value = language;
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    syncActive();
                    if (language === currentLanguage) {
                        return;
                    }
                    persistSetupFormState(form);
                    if (typeof window.persistCurrentDynamicModalState === 'function') {
                        window.persistCurrentDynamicModalState();
                    }
                    if (window.setLanguage) {
                        window.setLanguage(language, { previewOnly: true });
                    }
                });
            });

            syncActive();
        });
    }

    function normalizeLanguageCode(value) {
        return String(value || '').trim().toLowerCase().replace(/_/g, '-').replace(/[^a-z0-9-]/g, '');
    }

    function escapeHtml(value) {
        return String(value || '').replace(/[&<>"']/g, (char) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        })[char]);
    }

    function syncLanguageCatalog(form) {
        if (!form) return;
        const languagesField = form.querySelector('[name="languages"]');
        const namesField = form.querySelector('[name="system_names"]');
        const defaultField = form.querySelector('[name="default_language"]');
        const languages = {};
        let fallbackLanguage = 'en';
        form.querySelectorAll('[data-language-row]').forEach((row, index) => {
            const code = normalizeLanguageCode(row.dataset.languageCode);
            if (!code) return;
            if (index === 0) fallbackLanguage = code;
            const nameInput = row.querySelector('[data-language-name]');
            const dirInput = row.querySelector('[data-language-dir]');
            const flagInput = row.querySelector('[data-language-flag]');
            const defaultInput = row.querySelector('[data-language-default]');
            languages[code] = {
                name: String(nameInput && nameInput.value ? nameInput.value : code).trim() || code,
                dir: dirInput && dirInput.value === 'rtl' ? 'rtl' : 'ltr',
                flag: String(flagInput && flagInput.value ? flagInput.value : '').trim()
            };
            if (defaultInput && defaultInput.checked) {
                fallbackLanguage = code;
            }
        });
        syncSystemNameRows(form, languages);
        const systemNames = readSystemNames(form);
        if (languagesField) languagesField.value = JSON.stringify(languages);
        if (namesField) namesField.value = JSON.stringify(systemNames);
        if (defaultField) {
            defaultField.value = fallbackLanguage;
        }
        syncTranslationOverrides(form);
        applyImmediateSystemSettingsPreview(form);
    }

    function createLanguageRow(code, name, dir, flag) {
        const row = document.createElement('div');
        row.className = 'ms-language-row';
        row.dataset.languageRow = 'true';
        row.dataset.languageCode = code;
        const locked = code === 'en' || code === 'ar';
        row.innerHTML = `
            <div class="ms-language-row__code">${code}</div>
            <input type="text" class="form-control glass-input" data-language-name value="${escapeHtml(name || code)}">
            <select class="form-select glass-input" data-language-dir>
                <option value="ltr"${dir !== 'rtl' ? ' selected' : ''}>LTR</option>
                <option value="rtl"${dir === 'rtl' ? ' selected' : ''}>RTL</option>
            </select>
            <input type="text" class="form-control glass-input ms-language-flag-input" data-language-flag value="${escapeHtml(flag || '')}">
            <label class="ms-language-default">
                <input type="radio" name="ms_language_default_choice" data-language-default value="${code}">
                <span>Default</span>
            </label>
            <button type="button" class="btn btn-sm btn-outline-danger" data-language-remove${locked ? ' disabled' : ''}>
                <i class="bi bi-trash"></i>
            </button>
        `;
        return row;
    }

    function createSystemNameRow(code, label, value) {
        const row = document.createElement('div');
        row.className = 'ms-system-name-row';
        row.dataset.systemNameRow = 'true';
        row.dataset.languageCode = code;
        row.innerHTML = `
            <div class="ms-system-name-row__meta">
                <span class="ms-system-name-row__code">${escapeHtml(code)}</span>
                <span class="ms-system-name-row__label">${escapeHtml(label || code)}</span>
            </div>
            <input type="text" class="form-control glass-input" data-system-name-input value="${escapeHtml(value || '')}" placeholder="System name">
        `;
        return row;
    }

    function findSystemNameRow(form, code) {
        return Array.from(form.querySelectorAll('[data-system-name-row]')).find((row) => {
            return normalizeLanguageCode(row.dataset.languageCode) === code;
        });
    }

    function ensureSystemNameRow(form, code, label, value) {
        const list = form && form.querySelector('[data-system-name-list]');
        if (!list || !code) return null;
        let row = findSystemNameRow(form, code);
        if (!row) {
            row = createSystemNameRow(code, label, value);
            list.appendChild(row);
            bindSystemNameRow(form, row);
        }
        const labelTarget = row.querySelector('.ms-system-name-row__label');
        if (labelTarget) {
            labelTarget.textContent = label || code;
        }
        return row;
    }

    function bindSystemNameRow(form, row) {
        if (!form || !row || row.dataset.bound === 'true') return;
        row.dataset.bound = 'true';
        row.querySelectorAll('[data-system-name-input]').forEach((input) => {
            input.addEventListener('input', () => syncLanguageCatalog(form));
            input.addEventListener('change', () => syncLanguageCatalog(form));
        });
    }

    function syncSystemNameRows(form, languages) {
        if (!form || !languages) return;
        Object.entries(languages).forEach(([code, payload]) => {
            ensureSystemNameRow(form, code, payload && payload.name ? payload.name : code, '');
        });
        form.querySelectorAll('[data-system-name-row]').forEach((row) => {
            const code = normalizeLanguageCode(row.dataset.languageCode);
            if (code && !languages[code]) {
                row.remove();
            }
        });
    }

    function readSystemNames(form) {
        const systemNames = {};
        if (!form) return systemNames;
        form.querySelectorAll('[data-system-name-row]').forEach((row) => {
            const code = normalizeLanguageCode(row.dataset.languageCode);
            const input = row.querySelector('[data-system-name-input]');
            const value = String(input && input.value ? input.value : '').trim();
            if (code && value) {
                systemNames[code] = value;
            }
        });
        return systemNames;
    }

    function ensureTranslationLanguageColumn(form, code, label) {
        const matrix = form && form.querySelector('[data-translation-matrix]');
        if (!matrix || !code || matrix.querySelector(`[data-translation-lang-header="${code}"]`)) return;
        const headerRow = matrix.querySelector('thead tr');
        if (headerRow) {
            const header = document.createElement('th');
            header.dataset.translationLangHeader = code;
            header.innerHTML = `${label || code} <span class="text-muted">(${code})</span>`;
            headerRow.appendChild(header);
        }
        matrix.querySelectorAll('[data-translation-row]').forEach((row) => {
            const key = row.getAttribute('data-translation-key') || '';
            const cell = document.createElement('td');
            cell.dataset.translationCell = 'true';
            cell.dataset.source = 'missing';
            cell.innerHTML = `
                <textarea class="form-control form-control-sm glass-input" rows="2" data-translation-input data-lang="${code}" data-key="${key}" data-base-value="" data-override-value="" placeholder=""></textarea>
                <span class="badge ms-translation-source">missing</span>
            `;
            row.appendChild(cell);
            const input = cell.querySelector('[data-translation-input]');
            input.addEventListener('input', () => syncTranslationOverrides(form));
        });
    }

    function removeTranslationLanguageColumn(form, code) {
        const matrix = form && form.querySelector('[data-translation-matrix]');
        if (!matrix || !code) return;
        matrix.querySelectorAll(`[data-translation-lang-header="${code}"], [data-translation-input][data-lang="${code}"]`).forEach((node) => {
            const cell = node.closest('[data-translation-cell]');
            (cell || node).remove();
        });
    }

    function syncTranslationOverrides(form) {
        const field = form && form.querySelector('[name="translations_override"]');
        if (!field) return;
        const overrides = {};
        form.querySelectorAll('[data-translation-input]').forEach((input) => {
            const lang = normalizeLanguageCode(input.dataset.lang);
            const key = String(input.dataset.key || '').trim();
            if (!lang || !key) return;
            const value = String(input.value || '').trim();
            const baseValue = String(input.dataset.baseValue || '').trim();
            if (value && value !== baseValue) {
                if (!overrides[lang]) overrides[lang] = {};
                overrides[lang][key] = value;
            }
        });
        field.value = JSON.stringify(overrides);
    }

    function bindLanguageCatalogRow(form, row) {
        if (!form || !row || row.dataset.languageBound === 'true') return;
        row.dataset.languageBound = 'true';
        row.querySelectorAll('input, select').forEach((input) => {
            input.addEventListener('input', () => syncLanguageCatalog(form));
            input.addEventListener('change', () => syncLanguageCatalog(form));
        });
        const removeButton = row.querySelector('[data-language-remove]');
        if (removeButton) {
            removeButton.addEventListener('click', () => {
                if (removeButton.disabled) return;
                const code = normalizeLanguageCode(row.dataset.languageCode);
                row.remove();
                removeTranslationLanguageColumn(form, code);
                const systemNameRow = findSystemNameRow(form, code);
                if (systemNameRow) systemNameRow.remove();
                const defaultField = form.querySelector('[name="default_language"]');
                if (defaultField && !form.querySelector(`[data-language-row][data-language-code="${defaultField.value}"]`)) {
                    const firstDefault = form.querySelector('[data-language-default]');
                    if (firstDefault) firstDefault.checked = true;
                }
                syncLanguageCatalog(form);
            });
        }
    }

    function addLanguageToCatalog(form, editor, code, name, dir, flag) {
        const list = editor && editor.querySelector('[data-language-list]');
        const normalizedCode = normalizeLanguageCode(code);
        if (!form || !list || !normalizedCode || list.querySelector(`[data-language-code="${normalizedCode}"]`)) {
            return null;
        }
        const label = name || normalizedCode;
        const row = createLanguageRow(normalizedCode, label, dir || 'ltr', flag || '');
        list.appendChild(row);
        bindLanguageCatalogRow(form, row);
        ensureSystemNameRow(form, normalizedCode, label, '');
        ensureTranslationLanguageColumn(form, normalizedCode, label);
        const defaultInput = row.querySelector('[data-language-default]');
        if (defaultInput && !form.querySelector('[data-language-default]:checked')) {
            defaultInput.checked = true;
        }
        syncLanguageCatalog(form);
        return row;
    }

    function rebuildLanguageCatalog(form, languages, systemNames, defaultLanguage) {
        const editor = form && form.querySelector('[data-language-catalog-editor]');
        const list = editor && editor.querySelector('[data-language-list]');
        if (!form || !editor || !list || !languages || typeof languages !== 'object') return;
        list.innerHTML = '';
        Object.entries(languages).forEach(([rawCode, payload]) => {
            const code = normalizeLanguageCode(rawCode);
            if (!code) return;
            const meta = payload && typeof payload === 'object' ? payload : { name: String(payload || code) };
            addLanguageToCatalog(form, editor, code, meta.name || code, meta.dir || 'ltr', meta.flag || '');
        });
        const defaultCode = normalizeLanguageCode(defaultLanguage);
        const defaultInput = defaultCode ? form.querySelector(`[data-language-row][data-language-code="${defaultCode}"] [data-language-default]`) : null;
        if (defaultInput) {
            defaultInput.checked = true;
        }
        Object.entries(systemNames || {}).forEach(([rawCode, value]) => {
            const code = normalizeLanguageCode(rawCode);
            const row = ensureSystemNameRow(form, code, languages[code] && languages[code].name ? languages[code].name : code, value);
            const input = row && row.querySelector('[data-system-name-input]');
            if (input) {
                input.value = value || '';
            }
        });
        syncLanguageCatalog(form);
    }

    function applyTranslationOverridesToMatrix(form, overrides) {
        if (!form || !overrides || typeof overrides !== 'object') return;
        Object.entries(overrides).forEach(([rawLang, values]) => {
            const lang = normalizeLanguageCode(rawLang);
            if (!lang || !values || typeof values !== 'object') return;
            Object.entries(values).forEach(([key, value]) => {
                const input = Array.from(form.querySelectorAll(`[data-translation-input][data-lang="${lang}"]`)).find((candidate) => {
                    return candidate.dataset.key === String(key);
                });
                if (input) {
                    input.value = value || '';
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                }
            });
        });
        syncTranslationOverrides(form);
    }

    function initLanguageCatalogEditor(root) {
        root.querySelectorAll('[data-language-catalog-editor]').forEach((editor) => {
            if (editor.dataset.bound === 'true') return;
            editor.dataset.bound = 'true';
            const form = editor.closest('form');
            const list = editor.querySelector('[data-language-list]');
            const codeInput = editor.querySelector('[data-language-code-input]');
            const nameInput = editor.querySelector('[data-language-name-input]');
            const dirInput = editor.querySelector('[data-language-dir-input]');
            const flagInput = editor.querySelector('[data-language-flag-input]');
            const addButton = editor.querySelector('[data-language-add]');
            if (!form || !list) return;

            list.querySelectorAll('[data-language-row]').forEach((row) => bindLanguageCatalogRow(form, row));
            form.querySelectorAll('[data-system-name-row]').forEach((row) => bindSystemNameRow(form, row));
            if (addButton) {
                addButton.addEventListener('click', () => {
                    addLanguageToCatalog(form, editor, codeInput && codeInput.value, nameInput && nameInput.value, dirInput && dirInput.value, flagInput && flagInput.value);
                    if (codeInput) codeInput.value = '';
                    if (nameInput) nameInput.value = '';
                    if (flagInput) flagInput.value = '';
                });
            }
            editor.querySelectorAll('[data-language-suggestion]').forEach((button) => {
                button.addEventListener('click', () => {
                    const code = button.getAttribute('data-language-suggestion');
                    addLanguageToCatalog(form, editor, code, code, 'ltr', '');
                });
            });
            syncLanguageCatalog(form);
        });
    }

    function initTranslationMatrixEditor(root) {
        root.querySelectorAll('[data-translation-matrix]').forEach((matrix) => {
            if (matrix.dataset.bound === 'true') return;
            matrix.dataset.bound = 'true';
            const form = matrix.closest('form');
            const searchInput = matrix.querySelector('[data-translation-search]');
            const statusInput = matrix.querySelector('[data-translation-status]');
            const groupTabs = Array.from(matrix.querySelectorAll('[data-translation-group-tab]'));
            let activeGroup = 'all';

            function applyFilter() {
                const needle = String(searchInput && searchInput.value ? searchInput.value : '').trim().toLowerCase();
                const status = statusInput && statusInput.value ? statusInput.value : 'all';
                matrix.querySelectorAll('[data-translation-row]').forEach((row) => {
                    const text = row.textContent.toLowerCase();
                    const hasStatus = status === 'all' || Boolean(row.querySelector(`[data-source="${status}"]`));
                    const hasGroup = activeGroup === 'all' || row.getAttribute('data-translation-group') === activeGroup;
                    row.classList.toggle('d-none', Boolean(needle && !text.includes(needle)) || !hasStatus || !hasGroup);
                });
            }

            matrix.querySelectorAll('[data-translation-input]').forEach((input) => {
                input.addEventListener('input', () => {
                    syncTranslationOverrides(form);
                    const cell = input.closest('[data-translation-cell]');
                    if (cell) {
                        const value = String(input.value || '').trim();
                        const baseValue = String(input.dataset.baseValue || '').trim();
                        cell.dataset.source = value && value !== baseValue ? 'override' : (value ? cell.dataset.source : 'missing');
                    }
                    applyFilter();
                });
            });
            if (searchInput) searchInput.addEventListener('input', applyFilter);
            if (statusInput) statusInput.addEventListener('change', applyFilter);
            groupTabs.forEach((tab) => {
                tab.addEventListener('click', () => {
                    activeGroup = tab.getAttribute('data-translation-group-tab') || 'all';
                    groupTabs.forEach((candidate) => {
                        candidate.classList.toggle('active', candidate === tab);
                    });
                    applyFilter();
                });
            });
            if (form) {
                form.addEventListener('submit', () => {
                    syncLanguageCatalog(form);
                    syncTranslationOverrides(form);
                });
            }
            syncTranslationOverrides(form);
            applyFilter();
        });
    }

    function isElementVisible(element) {
        if (!element) return false;
        return window.getComputedStyle(element).display !== 'none' && window.getComputedStyle(element).visibility !== 'hidden';
    }

    function initSystemSetupEnterBehavior(root) {
        root.querySelectorAll('form.ms-system-setup-form').forEach((form) => {
            if (form.dataset.enterBehaviorBound === 'true') return;
            form.dataset.enterBehaviorBound = 'true';

            form.addEventListener('keydown', (event) => {
                if (event.key !== 'Enter' || event.defaultPrevented || event.isComposing) {
                    return;
                }
                const target = event.target;
                const tagName = target && target.tagName ? target.tagName.toLowerCase() : '';
                if (tagName === 'textarea') {
                    return;
                }

                const languageEditor = target && target.closest && target.closest('[data-language-catalog-editor]');
                if (languageEditor && target.matches('input, select')) {
                    const addButton = languageEditor.querySelector('[data-language-add]');
                    if (addButton) {
                        event.preventDefault();
                        addButton.click();
                    }
                    return;
                }

                const steps = Array.from(form.querySelectorAll('.wizard-step'));
                if (steps.length < 2) {
                    return;
                }
                const visibleStepIndex = steps.findIndex((step) => isElementVisible(step));
                const nextButton = form.querySelector('.ms-btn-next');
                if (visibleStepIndex >= 0 && visibleStepIndex < steps.length - 1 && nextButton && isElementVisible(nextButton)) {
                    event.preventDefault();
                    nextButton.click();
                }
            });
        });
    }

    function extractImportedSettings(payload) {
        if (!payload || typeof payload !== 'object') return null;
        if (payload.format === 'django-microsys.system-settings' && payload.settings && typeof payload.settings === 'object') {
            return payload.settings;
        }
        return payload;
    }

    function setCheckboxField(form, name, value) {
        const field = form.querySelector(`[name="${name}"]`);
        if (!field || field.type !== 'checkbox') return;
        field.checked = Boolean(value);
        field.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function setJsonField(form, name, value) {
        const field = form.querySelector(`[name="${name}"]`);
        if (!field) return;
        field.value = JSON.stringify(value || {});
        field.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function applyImportedSetupSettings(form, payload) {
        const settings = extractImportedSettings(payload);
        if (!form || !settings) return false;

        const languages = settings.languages && typeof settings.languages === 'object' ? settings.languages : null;
        const systemNames = settings.system_names && typeof settings.system_names === 'object' ? settings.system_names : {};
        if (languages) {
            rebuildLanguageCatalog(form, languages, systemNames, settings.default_language || getNamedFieldValue(form, 'default_language') || 'en');
        } else if (Object.keys(systemNames).length) {
            Object.entries(systemNames).forEach(([rawCode, value]) => {
                const code = normalizeLanguageCode(rawCode);
                const row = ensureSystemNameRow(form, code, code, value);
                const input = row && row.querySelector('[data-system-name-input]');
                if (input) input.value = value || '';
            });
        }

        if (settings.system_names) setJsonField(form, 'system_names', settings.system_names);
        if (settings.languages) setJsonField(form, 'languages', settings.languages);
        if (settings.translations_override) {
            setJsonField(form, 'translations_override', settings.translations_override);
            applyTranslationOverridesToMatrix(form, settings.translations_override);
        }

        ['home_url', 'default_language', 'default_theme', 'default_table_density'].forEach((name) => {
            if (Object.prototype.hasOwnProperty.call(settings, name)) {
                setNamedFieldValue(form, name, settings[name]);
                getNamedFieldInputs(form, name).forEach((field) => field.dispatchEvent(new Event('change', { bubbles: true })));
            }
        });

        ['allow_user_theme_override', 'allow_user_language_override', 'email_2fa', 'public_root'].forEach((name) => {
            if (Object.prototype.hasOwnProperty.call(settings, name)) {
                setCheckboxField(form, name, settings[name]);
            }
        });

        if (Array.isArray(settings.allowed_themes)) {
            form.querySelectorAll('[data-setup-theme-allowed]').forEach((field) => {
                field.checked = settings.allowed_themes.includes(field.value);
                field.dispatchEvent(new Event('change', { bubbles: true }));
            });
        }

        const sidebar = settings.sidebar_config && typeof settings.sidebar_config === 'object' ? settings.sidebar_config : null;
        if (sidebar) {
            setJsonField(form, 'sidebar_config', sidebar);
            setCheckboxField(form, 'sidebar_enable_reorder', sidebar.enable_reorder !== false);
            setCheckboxField(form, 'sidebar_enable_toolbar', sidebar.show_toolbar !== false);
            setCheckboxField(form, 'sidebar_show_icons', sidebar.show_icons !== false);
            setCheckboxField(form, 'sidebar_allow_user_density', sidebar.allow_user_density !== false);
            setNamedFieldValue(form, 'sidebar_density', sidebar.density || 'balanced');
            setNamedFieldValue(form, 'sidebar_collapse_mode', sidebar.collapse_mode || 'icons');
        }

        const titlebar = settings.titlebar_config && typeof settings.titlebar_config === 'object' ? settings.titlebar_config : null;
        if (titlebar) {
            setCheckboxField(form, 'titlebar_show_title', titlebar.show_title !== false);
            setCheckboxField(form, 'titlebar_show_logo', titlebar.show_logo !== false);
            setCheckboxField(form, 'titlebar_show_home_button', titlebar.show_home_button !== false);
            setNamedFieldValue(form, 'titlebar_home_shape', titlebar.home_shape || 'circle');
            setNamedFieldValue(form, 'titlebar_title_align', titlebar.title_align || 'start');
            setNamedFieldValue(form, 'titlebar_title_size', titlebar.title_size || 'md');
            setNamedFieldValue(form, 'titlebar_height', titlebar.height || 'balanced');
            setNamedFieldValue(form, 'titlebar_surface', titlebar.surface || 'default');
        }

        syncLanguageCatalog(form);
        syncTranslationOverrides(form);
        applyImmediateSystemSettingsPreview(form);
        return true;
    }

    function initSystemSetupImportFile(root) {
        root.querySelectorAll('form.ms-system-setup-form [data-settings-import-file]').forEach((input) => {
            if (input.dataset.importBound === 'true') return;
            input.dataset.importBound = 'true';
            input.addEventListener('change', () => {
                const form = input.closest('form');
                const file = input.files && input.files[0];
                if (!form || !file) return;
                const reader = new FileReader();
                reader.onload = () => {
                    try {
                        const payload = JSON.parse(reader.result || '{}');
                        if (!applyImportedSetupSettings(form, payload)) {
                            throw new Error('Invalid setup file');
                        }
                        // Mark import as processed so server doesn't re-apply and override user edits
                        const processedFlag = form.querySelector('input[name="settings_import_processed"]');
                        if (processedFlag) {
                            processedFlag.value = 'true';
                        }
                        if (typeof showToast === 'function') {
                            showToast('System setup file imported.');
                        }
                    } catch (error) {
                        if (typeof showToast === 'function') {
                            showToast('Invalid system setup file.');
                        }
                    }
                };
                reader.readAsText(file);
            });
        });
    }

    function initSetupThemePicker(root) {
        root.querySelectorAll('[data-setup-theme-picker]').forEach((picker) => {
            if (picker.dataset.bound === 'true') return;
            picker.dataset.bound = 'true';

            const inputId = picker.getAttribute('data-theme-input');
            const input = inputId ? document.getElementById(inputId) : null;
            if (!input) return;

            const options = Array.from(picker.querySelectorAll('[data-setup-theme-choice]'));
            const allowedCheckboxes = Array.from(picker.querySelectorAll('[data-setup-theme-allowed]'));

            function getAllowedThemes() {
                return allowedCheckboxes
                    .filter((checkbox) => checkbox.checked)
                    .map((checkbox) => checkbox.getAttribute('data-setup-theme-allowed'));
            }

            function syncActive() {
                const allowedThemes = getAllowedThemes();
                if (!allowedThemes.length && allowedCheckboxes.length) {
                    allowedCheckboxes[0].checked = true;
                }
                const resolvedAllowedThemes = getAllowedThemes();
                const activeTheme = resolvedAllowedThemes.includes(input.value) ? input.value : (resolvedAllowedThemes[0] || 'light');
                input.value = activeTheme;
                allowedCheckboxes.forEach((checkbox) => {
                    const theme = checkbox.getAttribute('data-setup-theme-allowed');
                    checkbox.disabled = checkbox.checked && resolvedAllowedThemes.length === 1;
                    const container = checkbox.closest('[data-theme-option]');
                    if (!container) {
                        return;
                    }
                    const isAllowed = resolvedAllowedThemes.includes(theme);
                    const isDefault = theme === activeTheme;
                    container.classList.toggle('opacity-50', !isAllowed);
                    container.classList.toggle('is-default', isDefault);
                    const button = container.querySelector('[data-setup-theme-choice]');
                    const preview = container.querySelector('.theme-preview[data-theme]');
                    if (button) {
                        button.setAttribute('aria-pressed', isDefault ? 'true' : 'false');
                    }
                    if (preview) {
                        preview.classList.toggle('active', isDefault);
                    }
                });
            }

            options.forEach((option) => {
                option.addEventListener('click', (event) => {
                    event.preventDefault();
                    const theme = option.getAttribute('data-setup-theme-choice') || 'light';
                    const checkbox = picker.querySelector(`[data-setup-theme-allowed="${theme}"]`);
                    if (checkbox && !checkbox.checked) {
                        checkbox.checked = true;
                        checkbox.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    input.value = theme;
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    syncActive();
                    if (window.setTheme) {
                        window.setTheme(theme);
                    }
                });
            });

            allowedCheckboxes.forEach((checkbox) => {
                checkbox.addEventListener('change', () => {
                    if (!getAllowedThemes().length) {
                        checkbox.checked = true;
                    }
                    syncActive();
                });
            });

            syncActive();
        });
    }

    function initSetupTableDensityPicker(root) {
        root.querySelectorAll('[data-setup-table-density-picker]').forEach((picker) => {
            if (picker.dataset.bound === 'true') return;
            picker.dataset.bound = 'true';

            const inputId = picker.getAttribute('data-table-density-input');
            const input = inputId ? document.getElementById(inputId) : null;
            if (!input) return;

            const options = Array.from(picker.querySelectorAll('[data-setup-table-density-choice]'));

            function syncActive() {
                const activeDensity = input.value || 'balanced';
                options.forEach((option) => {
                    option.classList.toggle('is-active', option.getAttribute('data-setup-table-density-choice') === activeDensity);
                });
            }

            options.forEach((option) => {
                option.addEventListener('click', () => {
                    const density = option.getAttribute('data-setup-table-density-choice') || 'balanced';
                    input.value = density;
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    syncActive();
                });
            });

            syncActive();
        });
    }

    function initSetupSidebarDensityPicker(root) {
        root.querySelectorAll('[data-setup-sidebar-density-picker]').forEach((picker) => {
            if (picker.dataset.bound === 'true') return;
            picker.dataset.bound = 'true';

            const inputId = picker.getAttribute('data-sidebar-density-input');
            const input = inputId ? document.getElementById(inputId) : null;
            if (!input) return;

            const options = Array.from(picker.querySelectorAll('[data-setup-sidebar-density-choice]'));

            function syncActive() {
                const activeDensity = input.value || 'balanced';
                options.forEach((option) => {
                    option.classList.toggle('is-active', option.getAttribute('data-setup-sidebar-density-choice') === activeDensity);
                });
            }

            options.forEach((option) => {
                option.addEventListener('click', () => {
                    const density = option.getAttribute('data-setup-sidebar-density-choice') || 'balanced';
                    input.value = density;
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    syncActive();
                });
            });

            syncActive();
        });
    }

    function initSidebarBehaviorOptions(root) {
        root.querySelectorAll('form.ms-system-setup-form').forEach((form) => {
            if (form.dataset.sidebarBehaviorBound === 'true') {
                return;
            }

            const toolbarToggle = form.querySelector('#id_sidebar_enable_toolbar');
            const toolbarNote = form.querySelector('[data-sidebar-toolbar-note]');
            const showIconsToggle = form.querySelector('#id_sidebar_show_icons');
            const allowThemeOverrideToggle = form.querySelector('#id_allow_user_theme_override');
            const reorderToggle = form.querySelector('#id_sidebar_enable_reorder');
            const allowUserDensityToggle = form.querySelector('#id_sidebar_allow_user_density');
            const sectionsToolState = form.querySelector('[data-sidebar-tooling-state]');
            const themeAllowCheckboxes = Array.from(form.querySelectorAll('[data-setup-theme-allowed]'));
            if (!toolbarToggle || !toolbarNote) {
                return;
            }

            form.dataset.sidebarBehaviorBound = 'true';

            function getAllowedThemeCount() {
                return themeAllowCheckboxes.filter((checkbox) => checkbox.checked).length;
            }

            function hasLiveToolbarTool() {
                const themePickerEnabled = Boolean(
                    allowThemeOverrideToggle &&
                    allowThemeOverrideToggle.checked &&
                    getAllowedThemeCount() > 1
                );
                const densityPickerEnabled = Boolean(allowUserDensityToggle && allowUserDensityToggle.checked);
                const reorderEnabled = Boolean(reorderToggle && reorderToggle.checked);
                const sectionsManagerEnabled = Boolean(
                    sectionsToolState &&
                    sectionsToolState.getAttribute('data-sections-manager-available') === 'true'
                );
                return themePickerEnabled || densityPickerEnabled || reorderEnabled || sectionsManagerEnabled;
            }

            function syncToolbarAvailability() {
                const available = hasLiveToolbarTool();
                toolbarToggle.disabled = !available;
                if (!available) {
                    toolbarToggle.checked = false;
                }
                toolbarNote.classList.toggle('d-none', !available || Boolean(toolbarToggle.checked));
                applyImmediateSystemSettingsPreview(form);
            }

            function syncCollapseMode() {
                if (!showIconsToggle) {
                    applyImmediateSystemSettingsPreview(form);
                    return;
                }
                if (!showIconsToggle.checked && getNamedFieldValue(form, 'sidebar_collapse_mode') === 'icons') {
                    setNamedFieldValue(form, 'sidebar_collapse_mode', 'hidden');
                }
                applyImmediateSystemSettingsPreview(form);
            }

            toolbarToggle.addEventListener('change', syncToolbarAvailability);
            if (showIconsToggle) {
                showIconsToggle.addEventListener('change', syncCollapseMode);
            }
            getNamedFieldInputs(form, 'sidebar_collapse_mode').forEach((field) => {
                field.addEventListener('change', syncCollapseMode);
            });
            themeAllowCheckboxes.forEach((checkbox) => {
                checkbox.addEventListener('change', syncToolbarAvailability);
            });
            [allowThemeOverrideToggle, reorderToggle, allowUserDensityToggle].forEach((field) => {
                if (field) {
                    field.addEventListener('change', syncToolbarAvailability);
                }
            });
            if (showIconsToggle) {
                showIconsToggle.addEventListener('change', syncToolbarAvailability);
            }
            syncCollapseMode();
            syncToolbarAvailability();
        });
    }

    function initTitlebarBehaviorOptions(root) {
        root.querySelectorAll('form.ms-system-setup-form').forEach((form) => {
            if (form.dataset.titlebarBehaviorBound === 'true') {
                return;
            }

            const showTitleToggle = form.querySelector('#id_titlebar_show_title');
            const showHomeButtonToggle = form.querySelector('#id_titlebar_show_home_button');
            if (!showTitleToggle || !showHomeButtonToggle) {
                return;
            }

            form.dataset.titlebarBehaviorBound = 'true';

            function syncTitlebarDependencies() {
                setNamedFieldReadonly(form, 'titlebar_title_align', !showTitleToggle.checked);
                setNamedFieldReadonly(form, 'titlebar_title_size', !showTitleToggle.checked);
                setNamedFieldReadonly(form, 'titlebar_home_shape', !showHomeButtonToggle.checked);
                applyImmediateSystemSettingsPreview(form);
            }

            showTitleToggle.addEventListener('change', syncTitlebarDependencies);
            showHomeButtonToggle.addEventListener('change', syncTitlebarDependencies);
            syncTitlebarDependencies();
        });
    }

    function scan(root) {
        restoreSetupFormState(root);
        initSetupHomeFields(root);
        root.querySelectorAll('.ms-setup-builder').forEach(initBuilder);
        initLanguageCatalogEditor(root);
        initTranslationMatrixEditor(root);
        initSystemSetupEnterBehavior(root);
        initSystemSetupImportFile(root);
        initSetupLanguagePicker(root);
        initSetupThemePicker(root);
        initSetupTableDensityPicker(root);
        initSetupSidebarDensityPicker(root);
        initSidebarBehaviorOptions(root);
        initTitlebarBehaviorOptions(root);
        initImmediateSystemSettingsPreview(root);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => scan(document));
    } else {
        scan(document);
    }

    const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            for (const node of mutation.addedNodes) {
                if (node.nodeType !== 1) continue;
                if (
                    node.matches && (
                        node.matches('form.ms-system-setup-form') ||
                        node.matches('.ms-setup-builder') ||
                        node.matches('[data-ms-selector]') ||
                        node.querySelector('.ms-setup-builder') ||
                        node.querySelector('form.ms-system-setup-form') ||
	                        node.querySelector('[data-ms-selector]') ||
	                        node.querySelector('[data-language-catalog-editor]') ||
	                        node.querySelector('[data-translation-matrix]') ||
	                        node.querySelector('[data-setup-language-picker]') ||
                        node.querySelector('[data-setup-table-density-picker]') ||
                        node.querySelector('[data-setup-sidebar-density-picker]')
                    )
                ) {
                    scan(node);
                    return;
                }
            }
        }
    });

    observer.observe(document.body, { childList: true, subtree: true });
})();
