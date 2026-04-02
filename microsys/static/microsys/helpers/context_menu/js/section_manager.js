(function() {
    'use strict';

    // Helper to get CSRF token
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                // Does this cookie string begin with the name we want?
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // Modal Builder
    function showModal(title, bodyContent, footerContent, variant = 'primary') {
        const modalId = 'sectionManagerModal';
        let modalEl = document.getElementById(modalId);
        
        if (modalEl) {
            modalEl.remove();
        }

        const modalHtml = `
            <div class="modal fade" id="${modalId}" tabindex="-1" aria-hidden="true">
                <div class="modal-dialog modal-dialog-centered modal-lg">
                    <div class="modal-content glass-card border-0 shadow-lg" style="border-radius: 12px; overflow: hidden;">
                        <div class="modal-header border-0 pb-0">
                            <h5 class="modal-title fw-bold text-${variant}"><i class="bi bi-info-circle me-2"></i> ${title}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body p-4">
                            ${bodyContent}
                        </div>
                        <div class="modal-footer border-0 pt-0">
                            ${footerContent}
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);
        modalEl = document.getElementById(modalId);
        const modal = new bootstrap.Modal(modalEl);
        modal.show();
        
        modalEl.addEventListener('hidden.bs.modal', () => {
             modalEl.remove();
        });
    }

    function buildRelatedHtml(relatedData) {
        if (!relatedData || Object.keys(relatedData).length === 0) {
            return '<p class="text-muted text-center my-3 small italic">لا توجد سجلات مرتبطة.</p>';
        }
        
        let html = '<div class="row g-3">';
        for (const [modelName, items] of Object.entries(relatedData)) {
            html += `
                <div class="col-sm-12">
                    <div class="glass-card h-100 p-3">
                        <div class="info-label-sm mb-2 text-primary fw-bold border-bottom pb-1" style="font-size: 0.8rem;">
                            <i class="bi bi-diagram-2 me-1"></i> ${modelName}
                        </div>
                        <ul class="list-group list-group-flush bg-transparent">
                            ${items.map(item => `<li class="list-group-item bg-transparent border-0 py-1 px-1 small text-muted"><i class="bi bi-dot me-1"></i> ${item}</li>`).join('')}
                        </ul>
                    </div>
                </div>
            `;
        }
        html += '</div>';
        return html;
    }

    document.addEventListener('DOMContentLoaded', function() {
        if (window.__microSectionManagerInitialized) return;
        window.__microSectionManagerInitialized = true;

        const sectionDataEl = document.getElementById('sectionData');
        if (!sectionDataEl) return;
        
        const sectionData = JSON.parse(sectionDataEl.textContent);
        const csrfToken = sectionData.csrf || getCookie('csrftoken');

        // ---------------------------------------------------------
        // Smart Delete Handler
        // ---------------------------------------------------------
        document.body.addEventListener('micro:record:delete', function(e) {
            // Ignore events that originated from inside a dynamic modal (handled by dynamic_modals.js)
            if (e.target.closest('.modal')) return;

            const data = e.detail.data;
            if (!confirm('هل أنت متأكد من حذف: ' + data.name + ' ؟')) return;

            // Perform AJAX delete checks
            fetch(sectionData.deleteUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    model: data.model,
                    pk: data.id 
                })
            })
            .then(response => response.json())
            .then(res => {
                if (res.success) {
                    // Success -> Reload
                    window.location.reload();
                } else {
                    // Error
                    if (res.related) {
                        // Smart Delete: Show Blocking Relations
                        const body = `
                            <div class="alert alert-danger border-0 d-flex align-items-center mb-4">
                                <i class="bi bi-exclamation-triangle-fill fs-3 me-3"></i>
                                <div>
                                    <div class="fw-bold fs-5">لا يمكن حذف العنصر</div>
                                    <div class="small">هذا القسم مرتبط بالسجلات التالية، يجب حذفها أو فك ارتباطها أولاً.</div>
                                </div>
                            </div>
                            <h6 class="fw-bold mb-3 text-secondary">السجلات المرتبطة:</h6>
                            ${buildRelatedHtml(res.related)}
                        `;
                        const footer = '<button type="button" class="btn btn-secondary rounded-pill px-4" data-bs-dismiss="modal">إغلاق</button>';
                        showModal('خطأ في الحذف', body, footer, 'danger');
                    } else {
                        // Generic Error
                        alert('خطأ: ' + res.error);
                    }
                }
            })
            .catch(err => {
                console.error('Delete Error:', err);
                alert('حدث خطأ غير متوقع.');
            });
        });

        // ---------------------------------------------------------
        // Smart View Handler
        // ---------------------------------------------------------
        document.body.addEventListener('micro:record:view', function(e) {
            // Ignore events that originated from inside a dynamic modal
            if (e.target.closest('.modal')) return;

            const data = e.detail.data;
            const url = `${sectionData.detailsUrl}?model=${data.model}&pk=${data.id}`;

            fetch(url, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(res => {
                if (res.success) {
                    // Build Fields HTML - Mirrors Profile Info Grid
                    let fieldsHtml = '<div class="row g-3 mb-4">';
                    for (const [label, value] of Object.entries(res.fields)) {
                        fieldsHtml += `
                            <div class="col-md-6">
                                <div class="mb-2 px-2">
                                    <div class="info-label">${label}</div>
                                    <div class="info-value" style="font-size: 1rem;">${value || '-'}</div>
                                </div>
                            </div>
                        `;
                    }
                    fieldsHtml += '</div>';

                    // Build Related HTML
                    const relatedHtml = buildRelatedHtml(res.related);

                    const body = `
                        <div class="mb-4">
                            ${fieldsHtml}
                        </div>
                        <h6 class="fw-bold mb-3 text-secondary border-bottom pb-2">
                            <i class="bi bi-link-45deg me-1"></i> السجلات والاستخدامات المرتبطة
                        </h6>
                        ${relatedHtml}
                    `;
                    const footer = '<button type="button" class="btn btn-primary rounded-pill px-4" data-bs-dismiss="modal">تم</button>';
                    
                    showModal(res.title || data.name, body, footer, 'primary');
                } else {
                    alert('خطأ: ' + res.error);
                }
            })
            .catch(err => {
                console.error('View Error:', err);
                alert('حدث خطأ أثناء جلب البيانات.');
            });
        });

        // ---------------------------------------------------------
        // Smart Edit Handler (Fallback for generic Section Managers)
        // ---------------------------------------------------------
        document.body.addEventListener('micro:record:edit', function(e) {
            // Ignore events that originated from inside a dynamic modal
            if (e.target.closest('.modal')) return;

            const data = e.detail.data;
            if (sectionData && sectionData.editUrlTemplate) {
                const url = sectionData.editUrlTemplate.replace('{id}', data.id);
                window.location.href = url;
            } else {
                window.location.href = `?model=${data.model}&id=${data.id}`;
            }
        });

    });
})();
