(function () {
    function messagesFor(button) {
        return {
            label: button.dataset.scanLabel || "Scan",
            preparing: button.dataset.scanPreparing || "Preparing scan",
            selecting: button.dataset.scanSelecting || "Select a scanner",
            processing: button.dataset.scanProcessing || "Scanning",
            pageTemplate: button.dataset.scanPageTemplate || "Page {count} scanned",
            generating: button.dataset.scanGenerating || "Generating PDF",
            completed: button.dataset.scanCompleted || "Scanned",
            helperUnavailable: button.dataset.scanHelperUnavailable || "ScanLink is not available on this computer.",
            busy: button.dataset.scanBusy || "Another scan is already running.",
            cancelled: button.dataset.scanCancelled || "The scan was cancelled.",
            timeout: button.dataset.scanTimeout || "The scan took too long to finish.",
            noScanners: button.dataset.scanNoScanners || "No TWAIN scanner is available on this computer.",
            openSource: button.dataset.scanOpenSource || "The selected scanner could not be opened.",
            failed: button.dataset.scanFailed || "The scan could not be completed.",
        };
    }

    function widgetForButton(button) {
        return button.closest("[data-archive-file-widget]");
    }

    function setWidgetStatus(button, message) {
        const widget = widgetForButton(button);
        if (!widget) return;

        const meta = widget.querySelector("[data-archive-file-meta]");
        if (!meta) return;

        if (!button.dataset.scanOriginalMeta) {
            button.dataset.scanOriginalMeta = meta.textContent || "";
        }

        meta.textContent = message;
    }

    function restoreWidgetStatus(button) {
        const widget = widgetForButton(button);
        if (!widget) return;

        const meta = widget.querySelector("[data-archive-file-meta]");
        if (!meta) return;

        if (button.dataset.scanOriginalMeta !== undefined) {
            meta.textContent = button.dataset.scanOriginalMeta;
            delete button.dataset.scanOriginalMeta;
        }
    }

    function setVisualState(button, state, title) {
        const icons = {
            idle: '<i class="bi bi-printer"></i>',
            working: '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>',
            complete: '<i class="bi bi-check-lg"></i>',
        };

        const html = icons[state] || icons.idle;
        button.innerHTML = html;
        button.title = title;
        button.setAttribute("aria-label", title);
        button.dataset.bsTitle = title;
    }

    function resetButton(button) {
        const messages = messagesFor(button);
        button.disabled = false;
        delete button.dataset.scanJobId;
        delete button.dataset.scanBusyFlag;
        restoreWidgetStatus(button);
        setVisualState(button, "idle", messages.label);
    }

    function setWorkingState(button, message) {
        button.disabled = true;
        button.dataset.scanBusyFlag = "true";
        setWidgetStatus(button, message);
        setVisualState(button, "working", message);
    }

    function setCompletedState(button) {
        const messages = messagesFor(button);
        button.disabled = false;
        delete button.dataset.scanBusyFlag;
        restoreWidgetStatus(button);
        setVisualState(button, "complete", messages.completed);
    }

    function showButtonError(button, message) {
        button.title = message;
        button.setAttribute("aria-label", message);
        button.dataset.bsTitle = message;

        if (window.bootstrap && typeof window.bootstrap.Tooltip === "function") {
            const existing = window.bootstrap.Tooltip.getInstance(button);
            if (existing) existing.dispose();

            const tooltip = new window.bootstrap.Tooltip(button, {
                title: message,
                trigger: "manual",
            });

            tooltip.show();
            window.setTimeout(() => tooltip.dispose(), 3000);
        }
    }

    function resolveErrorMessage(button, error) {
        const messages = messagesFor(button);
        const code = error && error.code;

        switch (code) {
            case "helper_unavailable":
                return messages.helperUnavailable;
            case "busy":
                return messages.busy;
            case "scanner_selection_cancelled":
                return messages.cancelled;
            case "acquire_timeout":
            case "scan_timeout":
                return messages.timeout;
            case "no_scanners":
            case "twain_unavailable":
                return messages.noScanners;
            case "open_source_failed":
                return messages.openSource;
            case "cancelled":
                return messages.cancelled;
            default:
                return (error && error.message) || messages.failed;
        }
    }

    function assignBlobToInput(fileInput, blob) {
        const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
        const file = new File([blob], `scanned-document-${timestamp}.pdf`, { type: "application/pdf" });
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        fileInput.files = dataTransfer.files;
        fileInput.dispatchEvent(new Event("change", { bubbles: true }));
    }

    document.addEventListener("DOMContentLoaded", function () {
        const activeButtonsByJobId = new Map();

        const scanner = new ScanLink({
            onStatus: function (data) {
                const button = data && data.job_id ? activeButtonsByJobId.get(data.job_id) : null;
                if (!button) return;

                const messages = messagesFor(button);

                switch (data.status) {
                    case "queued":
                        setWorkingState(button, messages.preparing);
                        break;
                    case "processing":
                    case "acquiring":
                        setWorkingState(button, messages.processing);
                        break;
                    case "selecting_scanner":
                        setWorkingState(button, messages.selecting);
                        break;
                    case "page_scanned":
                        setWorkingState(
                            button,
                            messages.pageTemplate.replace("{count}", String(data.page_count || 0))
                        );
                        break;
                    case "generating_pdf":
                        setWorkingState(button, messages.generating);
                        break;
                    case "completed":
                        setCompletedState(button);
                        break;
                    default:
                        break;
                }
            },
            onError: function () {
                return undefined;
            },
        });

        document.querySelectorAll(".scan-btn").forEach((button) => {
            setVisualState(button, "idle", messagesFor(button).label);

            button.addEventListener("click", async function (event) {
                event.preventDefault();
                event.stopPropagation();
                if (typeof event.stopImmediatePropagation === "function") {
                    event.stopImmediatePropagation();
                }

                if (button.dataset.scanBusyFlag === "true") {
                    return;
                }

                const targetId = button.getAttribute("data-target");
                const fileInput = targetId ? document.getElementById(targetId) : null;
                if (!fileInput) {
                    return;
                }

                setWorkingState(button, messagesFor(button).preparing);

                let jobId = null;
                try {
                    const health = await scanner.checkHealth(true);
                    if (!health) {
                        throw new ScanLinkError(messagesFor(button).helperUnavailable, "helper_unavailable");
                    }
                    if (health.twain_available === false) {
                        throw new ScanLinkError(messagesFor(button).noScanners, "twain_unavailable");
                    }
                    if (health.busy) {
                        throw new ScanLinkError(messagesFor(button).busy, "busy");
                    }

                    const job = await scanner.startScan({
                        metadata: {
                            target_id: targetId,
                            path: window.location.pathname,
                        },
                    });

                    jobId = job.job_id;
                    button.dataset.scanJobId = jobId;
                    activeButtonsByJobId.set(jobId, button);

                    const blob = await scanner.waitForResult(jobId, {
                        timeoutMs: 5 * 60 * 1000,
                    });
                    assignBlobToInput(fileInput, blob);
                    setCompletedState(button);
                } catch (error) {
                    const message = resolveErrorMessage(button, error);
                    resetButton(button);
                    setWidgetStatus(button, message);
                    showButtonError(button, message);
                } finally {
                    if (jobId) {
                        activeButtonsByJobId.delete(jobId);
                    }
                    delete button.dataset.scanJobId;
                    if (button.innerHTML.indexOf("bi-check-lg") === -1) {
                        button.disabled = false;
                        delete button.dataset.scanBusyFlag;
                    }
                }
            });
        });
    });
})();
