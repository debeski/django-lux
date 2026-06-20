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

        fieldWrapper.classList.add('dlux-choice-selector-field');
        fieldWrapper.classList.toggle(
            'dlux-choice-selector-field--toggle',
            selector.getAttribute('data-dlux-selector-variant') === 'toggle'
        );
    }

    function normalizeText(value) {
        return String(value || '').toLowerCase().trim();
    }

    function filterSelectorOptions(searchInput) {
        const selector = searchInput.closest('[data-dlux-selector]');
        if (!selector) {
            return;
        }

        const query = normalizeText(searchInput.value);
        selector.querySelectorAll('[data-dlux-selector-option]').forEach((option) => {
            const haystack = normalizeText(option.getAttribute('data-dlux-selector-text'));
            option.style.display = !query || haystack.includes(query) ? '' : 'none';
        });
    }

    function syncToggleSelector(selector) {
        if (!selector || selector.getAttribute('data-dlux-selector-variant') !== 'toggle') {
            return;
        }

        decorateSelectorField(selector);

        const options = Array.from(selector.querySelectorAll('[data-dlux-selector-option]'));
        const visibleOptions = options.filter((option) => option.style.display !== 'none');
        const columnCount = Math.max(visibleOptions.length || options.length || 1, 1);
        selector.style.setProperty('--dlux-choice-toggle-columns', String(columnCount));

        options.forEach((option) => {
            const input = option.querySelector('.dlux-choice-option__input');
            const surface = option.querySelector('[data-dlux-selector-surface]');
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
        root.querySelectorAll('[data-dlux-selector]').forEach(decorateSelectorField);
        root.querySelectorAll('[data-dlux-selector-variant="toggle"]').forEach(syncToggleSelector);
        if (root instanceof Element && root.matches('[data-dlux-selector]')) {
            decorateSelectorField(root);
        }
        if (root instanceof Element && root.matches('[data-dlux-selector-variant="toggle"]')) {
            syncToggleSelector(root);
        }
    }

    document.addEventListener('input', function (event) {
        if (!(event.target instanceof HTMLElement) || !event.target.matches('[data-dlux-selector-search]')) {
            return;
        }
        filterSelectorOptions(event.target);
    });

    document.addEventListener('change', function (event) {
        if (!(event.target instanceof HTMLElement) || !event.target.matches('.dlux-choice-option__input')) {
            return;
        }
        const selector = event.target.closest('[data-dlux-selector]');
        if (!selector) {
            return;
        }
        syncToggleSelector(selector);
    });

    // A choice option's input is `position:absolute; opacity:0` (focusable). Clicking
    // an off-screen card focuses that input, and the browser scrolls it into view —
    // yanking a scroll container (e.g. the system setup body) so the header/logo
    // appears to jump up out of sight. The scroll happens during focus, so we must
    // snapshot scroll positions on pointerdown (BEFORE the click) and restore them
    // once the focus has landed. Keyboard focus (no pointerdown) is left alone so it
    // stays accessible.
    let choiceScrollRestore = null;
    document.addEventListener('pointerdown', function (event) {
        if (!(event.target instanceof HTMLElement)
            || !event.target.closest('[data-dlux-selector-option], .dlux-choice-option')) {
            choiceScrollRestore = null;
            return;
        }
        const scrollers = [];
        let node = event.target;
        while (node && node !== document.body && node !== document.documentElement) {
            const overflowY = window.getComputedStyle(node).overflowY;
            if (overflowY === 'auto' || overflowY === 'scroll') {
                scrollers.push([node, node.scrollTop, node.scrollLeft]);
            }
            node = node.parentElement;
        }
        choiceScrollRestore = { scrollers: scrollers, x: window.scrollX, y: window.scrollY };
    }, true);
    document.addEventListener('focusin', function (event) {
        if (!choiceScrollRestore) {
            return;
        }
        if (!(event.target instanceof HTMLElement) || !event.target.matches('.dlux-choice-option__input')) {
            choiceScrollRestore = null;
            return;
        }
        const snapshot = choiceScrollRestore;
        choiceScrollRestore = null;
        const restore = function () {
            snapshot.scrollers.forEach(function (entry) {
                entry[0].scrollTop = entry[1];
                entry[0].scrollLeft = entry[2];
            });
            window.scrollTo(snapshot.x, snapshot.y);
        };
        restore();
        window.requestAnimationFrame(restore);
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
                if (node.matches('[data-dlux-selector]') || node.querySelector('[data-dlux-selector]')) {
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
