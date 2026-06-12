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

        fieldWrapper.classList.add('dl-choice-selector-field');
        fieldWrapper.classList.toggle(
            'dl-choice-selector-field--toggle',
            selector.getAttribute('data-dl-selector-variant') === 'toggle'
        );
    }

    function normalizeText(value) {
        return String(value || '').toLowerCase().trim();
    }

    function filterSelectorOptions(searchInput) {
        const selector = searchInput.closest('[data-dl-selector]');
        if (!selector) {
            return;
        }

        const query = normalizeText(searchInput.value);
        selector.querySelectorAll('[data-dl-selector-option]').forEach((option) => {
            const haystack = normalizeText(option.getAttribute('data-dl-selector-text'));
            option.style.display = !query || haystack.includes(query) ? '' : 'none';
        });
    }

    function syncToggleSelector(selector) {
        if (!selector || selector.getAttribute('data-dl-selector-variant') !== 'toggle') {
            return;
        }

        decorateSelectorField(selector);

        const options = Array.from(selector.querySelectorAll('[data-dl-selector-option]'));
        const visibleOptions = options.filter((option) => option.style.display !== 'none');
        const columnCount = Math.max(visibleOptions.length || options.length || 1, 1);
        selector.style.setProperty('--dl-choice-toggle-columns', String(columnCount));

        options.forEach((option) => {
            const input = option.querySelector('.dl-choice-option__input');
            const surface = option.querySelector('[data-dl-selector-surface]');
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
        root.querySelectorAll('[data-dl-selector]').forEach(decorateSelectorField);
        root.querySelectorAll('[data-dl-selector-variant="toggle"]').forEach(syncToggleSelector);
        if (root instanceof Element && root.matches('[data-dl-selector]')) {
            decorateSelectorField(root);
        }
        if (root instanceof Element && root.matches('[data-dl-selector-variant="toggle"]')) {
            syncToggleSelector(root);
        }
    }

    document.addEventListener('input', function (event) {
        if (!(event.target instanceof HTMLElement) || !event.target.matches('[data-dl-selector-search]')) {
            return;
        }
        filterSelectorOptions(event.target);
    });

    document.addEventListener('change', function (event) {
        if (!(event.target instanceof HTMLElement) || !event.target.matches('.dl-choice-option__input')) {
            return;
        }
        const selector = event.target.closest('[data-dl-selector]');
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
                if (node.matches('[data-dl-selector]') || node.querySelector('[data-dl-selector]')) {
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
