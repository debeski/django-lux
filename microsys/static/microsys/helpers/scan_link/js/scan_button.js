/**
 * Scanner Button Integration
 * 
 * Handles the UI integration for scan buttons in forms.
 * Uses ScanLink class for communication with the desktop scanner app.
 */

document.addEventListener("DOMContentLoaded", function () {
    // Initialize ScanLink with callbacks
    const scanner = new ScanLink({
        autoConnect: true,
        onStatus: (data) => {
            console.log('[DEBUG] ScanLink Status Update:', data);

            const scanButtons = document.querySelectorAll('.scan-btn');
            scanButtons.forEach(btn => {
                if (btn.disabled) {
                    if (data.status === 'processing' || data.status === 'scanning') {
                        btn.innerHTML = '<span class="spinner-grow spinner-grow-sm me-2" role="status"></span>قيد المسح...';
                    } else if (data.status === 'page_scanned') {
                        btn.innerHTML = `<span class="spinner-grow spinner-grow-sm me-2" role="status"></span>مسح صفحة ${data.page_count || ''}...`;
                    } else if (data.status === 'uploading' || data.status === 'generating_pdf') {
                        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span>جاري الرفع...';
                    } else if (data.status === 'completed' || data.status === 'done') {
                        btn.innerHTML = '<i class="bi bi-check-lg me-2"></i>اكتمل المسح';
                        btn.classList.remove('btn-warning');
                        btn.classList.add('btn-success');
                    }
                }
            });
        },
        onError: (error) => {
            console.error('[DEBUG] ScanLink Error:', error);
            document.querySelectorAll('.scan-btn').forEach(btn => {
                btn.disabled = false;
            });
        }
    });

    scanner.onConnectionChange = (connected) => {
        console.log('[DEBUG] ScanLink Connection:', connected ? "Connected (WebSocket)" : "Disconnected");
    };

    // Scanner Button Integration
    const scanButtons = document.querySelectorAll('.scan-btn');
    scanButtons.forEach(btn => {
        btn.addEventListener('click', async function () {
            const targetId = this.getAttribute('data-target');
            const fileInput = document.getElementById(targetId);

            if (!fileInput) return;

            console.log('[DEBUG] Scan button clicked, target:', targetId);

            const originalText = this.innerHTML;
            const originalClasses = this.className;

            this.disabled = true;
            this.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span>جاري التحضير...';

            try {
                console.log('[DEBUG] Checking health...');
                const health = await scanner.checkHealth();
                console.log('[DEBUG] Health check result:', health);

                if (!health) {
                    throw new Error('تطبيق الماسحة غير متاح. تأكد من تشغيله.');
                }

                console.log('[DEBUG] Starting scan...');
                const scanResult = await scanner.startScan();
                console.log('[DEBUG] Scan started, result:', scanResult);

                const jobId = scanResult.job_id;
                if (!jobId) throw new Error("No job_id received from server");

                console.log('[DEBUG] Waiting for result for job:', jobId);
                const blob = await scanner.waitForResult(jobId);
                console.log('[DEBUG] Result received, blob size:', blob.size);

                if (blob) {
                    const file = new File([blob], "scanned_document.pdf", { type: "application/pdf" });
                    const dataTransfer = new DataTransfer();
                    dataTransfer.items.add(file);
                    fileInput.files = dataTransfer.files;
                    fileInput.dispatchEvent(new Event('change', { bubbles: true }));

                    this.innerHTML = '<i class="bi bi-check-lg me-2"></i>تم الحفظ';
                    this.classList.remove('btn-warning');
                    this.classList.add('btn-success');
                }

            } catch (error) {
                console.error('[DEBUG] Full Scan Error Stack:', error);
                this.disabled = false;
                this.innerHTML = originalText;
                this.className = originalClasses;

                let tooltipInstance = bootstrap.Tooltip.getInstance(this);
                if (tooltipInstance) tooltipInstance.dispose();

                this.setAttribute('title', error.message || 'Scan failed');
                const tooltip = new bootstrap.Tooltip(this);
                tooltip.show();
                setTimeout(() => tooltip.dispose(), 3000);
            }
        });
    });
});
