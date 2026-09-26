/* Settings preview guard. A preview frame renders a real page with unsaved
 * settings (dlux/system/preview.py); it is for looking, never for acting, so
 * every click, submit and activation key is swallowed before the page sees it. */
(function () {
    'use strict';

    const stop = (event) => {
        event.preventDefault();
        event.stopImmediatePropagation();
    };
    ['click', 'dblclick', 'auxclick', 'submit', 'contextmenu', 'dragstart'].forEach((type) => {
        document.addEventListener(type, stop, true);
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') stop(event);
    }, true);
    document.documentElement.setAttribute('data-dlux-preview', '');
})();
