document.addEventListener('DOMContentLoaded', function() {
    document.addEventListener('click', function(e) {
        const printButton = e.target.closest('[data-dlux-user-report-print]');
        if (!printButton) return;
        e.preventDefault();
        window.print();
    });

    document.addEventListener('shown.bs.tab', function(e) {
        const tab = e.target.closest('[data-dlux-user-report-window]');
        if (!tab) return;
        const report = tab.closest('[data-dlux-user-report]');
        // The export button may have been pinned into the modal footer (moved out of
        // [data-dlux-user-report]); fall back to a document-wide lookup. Only one report
        // modal is open at a time, so this is unambiguous.
        const exportLink = report?.querySelector('[data-dlux-user-report-export-base]')
            || document.querySelector('[data-dlux-user-report-export-base]');
        const windowName = tab.dataset.dluxUserReportWindow || 'week';
        if (exportLink) {
            const baseUrl = exportLink.dataset.dluxUserReportExportBase;
            exportLink.href = `${baseUrl}?window=${encodeURIComponent(windowName)}`;
        }
        const totalActions = report?.querySelector('[data-dlux-user-report-total-actions]');
        if (totalActions) {
            totalActions.textContent = tab.dataset.dluxUserReportActivityCount || '0';
        }
        report?.querySelectorAll('[data-dlux-user-report-recent-window]').forEach(container => {
            container.classList.toggle(
                'd-none',
                container.dataset.dluxUserReportRecentWindow !== windowName
            );
        });
    });

    function updateUserReportActivityPager(container, requestedPage) {
        const timeline = container.querySelector('[data-dlux-user-report-activity]');
        const pager = container.querySelector('[data-dlux-user-report-activity-pagination]');
        if (!timeline || !pager) {
            return;
        }

        const items = Array.from(timeline.querySelectorAll('[data-dlux-user-report-activity-item]'));
        const pageSize = Math.max(parseInt(timeline.dataset.dluxUserReportPageSize || '8', 10), 1);
        const totalPages = Math.max(Math.ceil(items.length / pageSize), 1);
        const currentPage = Math.min(Math.max(requestedPage || parseInt(timeline.dataset.currentPage || '1', 10), 1), totalPages);

        timeline.dataset.currentPage = String(currentPage);
        items.forEach((item, index) => {
            const itemPage = Math.floor(index / pageSize) + 1;
            item.classList.toggle('d-none', itemPage !== currentPage);
        });

        const state = pager.querySelector('[data-dlux-user-report-page-state]');
        if (state) {
            const pageLabel = state.dataset.pageLabel || '';
            const ofLabel = state.dataset.ofLabel || '';
            state.textContent = `${pageLabel} ${currentPage} ${ofLabel} ${totalPages}`.trim();
        }

        const previous = pager.querySelector('[data-dlux-user-report-page-prev]');
        const next = pager.querySelector('[data-dlux-user-report-page-next]');
        if (previous) previous.disabled = currentPage <= 1;
        if (next) next.disabled = currentPage >= totalPages;
    }

    function initUserReportActivityPagers(root) {
        root.querySelectorAll('[data-dlux-user-report-recent-window]').forEach(container => {
            if (container.dataset.activityPagerReady === 'true') {
                return;
            }
            container.dataset.activityPagerReady = 'true';
            updateUserReportActivityPager(container, 1);
        });
    }

    document.addEventListener('click', function(e) {
        const previous = e.target.closest('[data-dlux-user-report-page-prev]');
        const next = e.target.closest('[data-dlux-user-report-page-next]');
        if (!previous && !next) {
            return;
        }

        const container = e.target.closest('[data-dlux-user-report-recent-window]');
        const timeline = container?.querySelector('[data-dlux-user-report-activity]');
        if (!container || !timeline) {
            return;
        }

        e.preventDefault();
        const currentPage = parseInt(timeline.dataset.currentPage || '1', 10);
        updateUserReportActivityPager(container, currentPage + (next ? 1 : -1));
    });

    initUserReportActivityPagers(document);
    const universalModalBody = document.getElementById('universalDynamicModalBody');
    if (universalModalBody) {
        new MutationObserver(() => initUserReportActivityPagers(universalModalBody)).observe(
            universalModalBody,
            { childList: true, subtree: true }
        );
    }
});
