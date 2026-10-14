(function () {
    // One scan routine for every DjangoLux surface: the file card's Scan button
    // and the PDF editor both call window.DluxScan.scan(), so they share the
    // ScanLink health checks, scanner selection, progress and error wording.
    if (window.DluxScan) return;

    function messagesFor(element) {
        const data = (element && element.dataset) || {};
        return {
            label: data.scanLabel || "Scan",
            preparing: data.scanPreparing || "Preparing scan",
            selecting: data.scanSelecting || "Select a scanner",
            processing: data.scanProcessing || "Scanning",
            pageTemplate: data.scanPageTemplate || "Page {count} scanned",
            generating: data.scanGenerating || "Generating PDF",
            completed: data.scanCompleted || "Scanned",
            helperUnavailable: data.scanHelperUnavailable || "ScanLink is not available on this computer.",
            busy: data.scanBusy || "Another scan is already running.",
            cancelled: data.scanCancelled || "The scan was cancelled.",
            timeout: data.scanTimeout || "The scan took too long to finish.",
            noScanners: data.scanNoScanners || "No TWAIN scanner is available on this computer.",
            openSource: data.scanOpenSource || "The selected scanner could not be opened.",
            failed: data.scanFailed || "The scan could not be completed.",
        };
    }

    function errorMessage(messages, error) {
        switch (error && error.code) {
            case "helper_unavailable":
                return messages.helperUnavailable;
            case "busy":
                return messages.busy;
            case "scanner_selection_cancelled":
            case "cancelled":
                return messages.cancelled;
            case "acquire_timeout":
            case "scan_timeout":
                return messages.timeout;
            case "no_scanners":
            case "twain_unavailable":
                return messages.noScanners;
            case "open_source_failed":
                return messages.openSource;
            default:
                return (error && error.message) || messages.failed;
        }
    }

    function statusMessage(messages, data) {
        switch (data && data.status) {
            case "queued":
                return messages.preparing;
            case "processing":
            case "acquiring":
                return messages.processing;
            case "selecting_scanner":
                return messages.selecting;
            case "page_scanned":
                return messages.pageTemplate.replace("{count}", String(data.page_count || 0));
            case "generating_pdf":
                return messages.generating;
            case "completed":
                return messages.completed;
            default:
                return "";
        }
    }

    const listeners = new Map();
    let scanner = null;

    function client() {
        if (!window.ScanLink) {
            throw new window.ScanLinkError("ScanLink is not available on this computer.", "helper_unavailable");
        }
        if (!scanner) {
            scanner = new window.ScanLink({
                onStatus: function (data) {
                    const listener = data && data.job_id ? listeners.get(data.job_id) : null;
                    if (listener) listener(data);
                },
                onError: function () {
                    return undefined;
                },
            });
        }
        return scanner;
    }

    // Resolves to the scanned PDF as a Blob. `onProgress(text, status)` receives
    // translated progress; failures reject with a ScanLinkError whose message is
    // already translated through `messages`.
    async function scan(options) {
        const messages = (options && options.messages) || messagesFor(null);
        const onProgress = (options && options.onProgress) || function () {};
        let jobId = null;
        try {
            const scanLink = client();
            onProgress(messages.preparing, { status: "queued" });
            const health = await scanLink.checkHealth(true);
            if (!health) throw new window.ScanLinkError(messages.helperUnavailable, "helper_unavailable");
            if (health.twain_available === false) throw new window.ScanLinkError(messages.noScanners, "twain_unavailable");
            if (health.busy) throw new window.ScanLinkError(messages.busy, "busy");

            const job = await scanLink.startScan({ metadata: (options && options.metadata) || { path: window.location.pathname } });
            jobId = job.job_id;
            listeners.set(jobId, function (data) {
                const text = statusMessage(messages, data);
                if (text) onProgress(text, data);
            });
            return await scanLink.waitForResult(jobId, { timeoutMs: 5 * 60 * 1000 });
        } catch (error) {
            const translated = new window.ScanLinkError(errorMessage(messages, error), (error && error.code) || "scan_failed");
            throw translated;
        } finally {
            if (jobId) listeners.delete(jobId);
        }
    }

    window.DluxScan = { scan: scan, messagesFor: messagesFor, errorMessage: errorMessage };

    // File card Scan buttons (`.scan-btn[data-target]`), including ones inside
    // modals loaded after the page: the scanned PDF becomes the input's file.
    function widgetMeta(button) {
        const widget = button.closest("[data-dlux-file-widget]");
        return widget ? widget.querySelector("[data-dlux-file-meta]") : null;
    }

    function setMeta(button, message) {
        const meta = widgetMeta(button);
        if (!meta) return;
        if (button.dataset.scanOriginalMeta === undefined) button.dataset.scanOriginalMeta = meta.textContent || "";
        meta.textContent = message;
    }

    function restoreMeta(button) {
        const meta = widgetMeta(button);
        if (meta && button.dataset.scanOriginalMeta !== undefined) {
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
        button.innerHTML = icons[state] || icons.idle;
        button.title = title;
        button.setAttribute("aria-label", title);
        button.dataset.bsTitle = title;
    }

    function showButtonError(button, message) {
        button.title = message;
        button.setAttribute("aria-label", message);
        button.dataset.bsTitle = message;
        if (window.bootstrap && typeof window.bootstrap.Tooltip === "function") {
            const existing = window.bootstrap.Tooltip.getInstance(button);
            if (existing) existing.dispose();
            const tooltip = new window.bootstrap.Tooltip(button, { title: message, trigger: "manual" });
            tooltip.show();
            window.setTimeout(function () { tooltip.dispose(); }, 3000);
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

    function prepare(root) {
        (root || document).querySelectorAll(".scan-btn").forEach(function (button) {
            if (button.dataset.scanReady) return;
            button.dataset.scanReady = "1";
            setVisualState(button, "idle", messagesFor(button).label);
        });
    }

    document.addEventListener("click", async function (event) {
        const button = event.target.closest(".scan-btn");
        if (!button) return;
        event.preventDefault();
        event.stopPropagation();
        if (typeof event.stopImmediatePropagation === "function") event.stopImmediatePropagation();
        if (button.dataset.scanBusyFlag === "true") return;

        const targetId = button.getAttribute("data-target");
        const fileInput = targetId ? document.getElementById(targetId) : null;
        if (!fileInput) return;

        const messages = messagesFor(button);
        button.disabled = true;
        button.dataset.scanBusyFlag = "true";
        setVisualState(button, "working", messages.preparing);
        try {
            const blob = await scan({
                messages: messages,
                metadata: { target_id: targetId, path: window.location.pathname },
                onProgress: function (text) {
                    setMeta(button, text);
                    setVisualState(button, "working", text);
                },
            });
            assignBlobToInput(fileInput, blob);
            restoreMeta(button);
            setVisualState(button, "complete", messages.completed);
        } catch (error) {
            restoreMeta(button);
            setVisualState(button, "idle", messages.label);
            setMeta(button, error.message);
            showButtonError(button, error.message);
        } finally {
            button.disabled = false;
            delete button.dataset.scanBusyFlag;
        }
    }, true);

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () { prepare(document); });
    } else {
        prepare(document);
    }
    new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            mutation.addedNodes.forEach(function (node) {
                if (node.nodeType === 1) prepare(node.matches && node.matches(".scan-btn") ? node.parentNode : node);
            });
        });
    }).observe(document.documentElement, { childList: true, subtree: true });
})();
