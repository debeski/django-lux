document.addEventListener('DOMContentLoaded', function() {
    document.addEventListener('click', function(e) {
        const printButton = e.target.closest('[data-ms-user-report-print]');
        if (!printButton) return;
        e.preventDefault();
        window.print();
    });

    document.addEventListener('shown.bs.tab', function(e) {
        const tab = e.target.closest('[data-ms-user-report-window]');
        if (!tab) return;
        const report = tab.closest('[data-ms-user-report]');
        // The export button may have been pinned into the modal footer (moved out of
        // [data-ms-user-report]); fall back to a document-wide lookup. Only one report
        // modal is open at a time, so this is unambiguous.
        const exportLink = report?.querySelector('[data-ms-user-report-export-base]')
            || document.querySelector('[data-ms-user-report-export-base]');
        if (!exportLink) return;
        const baseUrl = exportLink.dataset.msUserReportExportBase;
        const windowName = tab.dataset.msUserReportWindow || 'week';
        exportLink.href = `${baseUrl}?window=${encodeURIComponent(windowName)}`;
    });

    function updateUserReportActivityPager(report, requestedPage) {
        const timeline = report.querySelector('[data-ms-user-report-activity]');
        const pager = report.querySelector('[data-ms-user-report-activity-pagination]');
        if (!timeline || !pager) {
            return;
        }

        const items = Array.from(timeline.querySelectorAll('[data-ms-user-report-activity-item]'));
        const pageSize = Math.max(parseInt(timeline.dataset.msUserReportPageSize || '8', 10), 1);
        const totalPages = Math.max(Math.ceil(items.length / pageSize), 1);
        const currentPage = Math.min(Math.max(requestedPage || parseInt(timeline.dataset.currentPage || '1', 10), 1), totalPages);

        timeline.dataset.currentPage = String(currentPage);
        items.forEach((item, index) => {
            const itemPage = Math.floor(index / pageSize) + 1;
            item.classList.toggle('d-none', itemPage !== currentPage);
        });

        const state = pager.querySelector('[data-ms-user-report-page-state]');
        if (state) {
            const pageLabel = state.dataset.pageLabel || '';
            const ofLabel = state.dataset.ofLabel || '';
            state.textContent = `${pageLabel} ${currentPage} ${ofLabel} ${totalPages}`.trim();
        }

        const previous = pager.querySelector('[data-ms-user-report-page-prev]');
        const next = pager.querySelector('[data-ms-user-report-page-next]');
        if (previous) previous.disabled = currentPage <= 1;
        if (next) next.disabled = currentPage >= totalPages;
    }

    function initUserReportActivityPagers(root) {
        root.querySelectorAll('[data-ms-user-report]').forEach(report => {
            if (report.dataset.activityPagerReady === 'true') {
                return;
            }
            report.dataset.activityPagerReady = 'true';
            updateUserReportActivityPager(report, 1);
        });
    }

    document.addEventListener('click', function(e) {
        const previous = e.target.closest('[data-ms-user-report-page-prev]');
        const next = e.target.closest('[data-ms-user-report-page-next]');
        if (!previous && !next) {
            return;
        }

        const report = e.target.closest('[data-ms-user-report]');
        const timeline = report?.querySelector('[data-ms-user-report-activity]');
        if (!report || !timeline) {
            return;
        }

        e.preventDefault();
        const currentPage = parseInt(timeline.dataset.currentPage || '1', 10);
        updateUserReportActivityPager(report, currentPage + (next ? 1 : -1));
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
