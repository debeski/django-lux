document.addEventListener('DOMContentLoaded', function() {
    // Auto-submit filters on change
    const autoSubmitElements = document.querySelectorAll('.auto-submit-filter');
    autoSubmitElements.forEach(element => {
        element.addEventListener('change', function() {
            this.form.submit();
        });
    });

    document.addEventListener('dlux:view-log-details', function(e) {
        const detail = e.detail;
        const data = detail.data || detail.actionData?.data || detail.action?.data;
        const url = data?.url;

        if (!url) {
            return;
        }

        const modalEl = document.getElementById('activityLogDetailModal');
        const modalBody = document.getElementById('activityLogDetailModalBody');

        if (!modalEl || !modalBody) {
            return;
        }

        const loadingText = modalBody.dataset.loadingText || 'Loading...';
        const errorText = modalBody.dataset.errorText || 'Error loading details.';
        const closeText = modalBody.dataset.closeText || 'Close';

        modalBody.innerHTML = `
            <div class="modal-body text-center p-5">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">${loadingText}</span>
                </div>
            </div>`;

        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        modal.show();

        fetch(url, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(response => response.text())
            .then(html => {
                modalBody.innerHTML = html;
            })
            .catch(err => {
                console.error('Error loading log details:', err);
                modalBody.innerHTML = `
                    <div class="modal-body text-center p-5 text-danger">
                        <i class="bi bi-exclamation-circle display-1 mb-3"></i>
                        <p>${errorText}</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">${closeText}</button>
                    </div>`;
            });
    });
});
