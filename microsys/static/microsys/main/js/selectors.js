(function () {
    'use strict';

    function decorateSelectorField(selector) {
        if (!selector) {
            return;
        }

        const fieldWrapper = selector.closest('div[id^="div_id_"]');
        if (!fieldWrapper) {
            return;
        }

        fieldWrapper.classList.add('ms-choice-selector-field');
        fieldWrapper.classList.toggle(
            'ms-choice-selector-field--toggle',
            selector.getAttribute('data-ms-selector-variant') === 'toggle'
        );
    }

    function normalizeText(value) {
        return String(value || '').toLowerCase().trim();
    }

    function filterSelectorOptions(searchInput) {
        const selector = searchInput.closest('[data-ms-selector]');
        if (!selector) {
            return;
        }

        const query = normalizeText(searchInput.value);
        selector.querySelectorAll('[data-ms-selector-option]').forEach((option) => {
            const haystack = normalizeText(option.getAttribute('data-ms-selector-text'));
            option.style.display = !query || haystack.includes(query) ? '' : 'none';
        });
    }

    function syncToggleSelector(selector) {
        if (!selector || selector.getAttribute('data-ms-selector-variant') !== 'toggle') {
            return;
        }

        decorateSelectorField(selector);

        const options = Array.from(selector.querySelectorAll('[data-ms-selector-option]'));
        const visibleOptions = options.filter((option) => option.style.display !== 'none');
        const columnCount = Math.min(Math.max(visibleOptions.length || options.length || 1, 1), 3);
        selector.style.setProperty('--ms-choice-toggle-columns', String(columnCount));

        options.forEach((option) => {
            const input = option.querySelector('.ms-choice-option__input');
            const surface = option.querySelector('[data-ms-selector-surface]');
            if (!input || !surface) {
                return;
            }
            surface.classList.toggle('lang-active', Boolean(input.checked));
        });
    }

    function scan(root) {
        if (!root || !(root instanceof Element || root instanceof Document)) {
            return;
        }
        root.querySelectorAll('[data-ms-selector]').forEach(decorateSelectorField);
        root.querySelectorAll('[data-ms-selector-variant="toggle"]').forEach(syncToggleSelector);
        if (root instanceof Element && root.matches('[data-ms-selector]')) {
            decorateSelectorField(root);
        }
        if (root instanceof Element && root.matches('[data-ms-selector-variant="toggle"]')) {
            syncToggleSelector(root);
        }
    }

    document.addEventListener('input', function (event) {
        if (!(event.target instanceof HTMLElement) || !event.target.matches('[data-ms-selector-search]')) {
            return;
        }
        filterSelectorOptions(event.target);
    });

    document.addEventListener('change', function (event) {
        if (!(event.target instanceof HTMLElement) || !event.target.matches('.ms-choice-option__input')) {
            return;
        }
        const selector = event.target.closest('[data-ms-selector]');
        if (!selector) {
            return;
        }
        syncToggleSelector(selector);
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            scan(document);
        });
    } else {
        scan(document);
    }

    const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            for (const node of mutation.addedNodes) {
                if (!(node instanceof Element)) {
                    continue;
                }
                if (node.matches('[data-ms-selector]') || node.querySelector('[data-ms-selector]')) {
                    scan(node);
                }
            }
        }
    });

    observer.observe(document.documentElement, {
        childList: true,
        subtree: true,
    });
})();
