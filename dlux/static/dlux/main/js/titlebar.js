(function () {
    'use strict';

    // Adaptive titlebar brand: keep the system name readable as space tightens by first
    // dropping the " - scope" suffix, then (only when there is barely any room and a logo
    // can carry the brand) collapsing the heading to logo-only. Whenever any part of the
    // title is hidden or clipped, the full text is exposed on hover/focus through the
    // shared Dlux tooltip (data-dlux-tooltip) so nothing is ever lost.
    function syncBrand(brand) {
        const title = brand.querySelector('.titlebar__title[data-titlebar-title]');
        const heading = brand.querySelector('.titlebar__heading');
        if (!title || !heading) {
            return;
        }
        const name = title.querySelector('.titlebar__title-name');
        if (!name) {
            return;
        }
        const scope = title.querySelector('.titlebar__title-scope');
        const logo = brand.querySelector('.titlebar__logo');
        const logoVisible = !!(logo && logo.offsetParent !== null);

        // Reset to the fullest state so measurements reflect the real content widths.
        title.classList.remove('titlebar__title--name-only');
        heading.classList.remove('titlebar__heading--collapsed');

        let truncated = false;

        // 1) Sacrifice the scope suffix before the system name.
        if (scope && title.scrollWidth > title.clientWidth + 1) {
            title.classList.add('titlebar__title--name-only');
            truncated = true;
        }

        // 2) The name itself may still be ellipsized; when it is reduced to almost nothing
        //    and a logo is present, let the logo carry the brand on its own.
        if (name.scrollWidth > name.clientWidth + 1) {
            truncated = true;
            if (logoVisible && name.clientWidth < 56) {
                heading.classList.add('titlebar__heading--collapsed');
            }
        }

        // 3) Reveal the full title on demand via the shared tooltip.
        const full = `${name.textContent}${scope ? scope.textContent : ''}`.replace(/\s+/g, ' ').trim();
        if (truncated && full) {
            brand.setAttribute('data-dlux-tooltip', full);
        } else {
            brand.removeAttribute('data-dlux-tooltip');
        }
    }

    function syncAll() {
        document.querySelectorAll('.titlebar__brand').forEach(syncBrand);
    }

    let frame = 0;
    function schedule() {
        window.cancelAnimationFrame(frame);
        frame = window.requestAnimationFrame(syncAll);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', syncAll);
    } else {
        syncAll();
    }
    window.addEventListener('resize', schedule);
    window.addEventListener('load', schedule);
    // Web fonts can resolve after load and change text width — re-measure once ready.
    if (document.fonts && typeof document.fonts.ready === 'object') {
        document.fonts.ready.then(schedule).catch(function () {});
    }

    // Expose a manual re-sync hook (e.g. the System Settings live titlebar preview).
    window.__dluxSyncTitlebar = syncAll;
}());
