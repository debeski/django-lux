(function () {
    // One scan routine for every DjangoLux surface: the file card's Scan button
    // and the PDF editor both call window.DluxScan.scan(), so they share the
    // ScanLink health checks, scanner selection, progress and error wording.
    if (window.DluxScan) return;

    const SCAN_WAIT_MS = 11 * 60 * 1000;

    // A message is the element's data-scan-* override, else the page's strings
    // table, else English. The widget renders data-scan-* only when it has the
    // translated strings, so an untranslated attribute never hides DLUX_STRINGS.
    const MESSAGES = {
        label: ["scanLabel", "scan_label", "Scan"],
        preparing: ["scanPreparing", "scan_preparing_label", "Preparing scan"],
        selecting: ["scanSelecting", "scan_selecting_label", "Select a scanner"],
        processing: ["scanProcessing", "scan_processing_label", "Scanning"],
        pageTemplate: ["scanPageTemplate", "scan_page_progress_template", "Page {count} scanned"],
        generating: ["scanGenerating", "scan_generating_label", "Generating PDF"],
        completed: ["scanCompleted", "scan_completed_label", "Scanned"],
        helperUnavailable: ["scanHelperUnavailable", "scan_helper_unavailable_message", "Start ScanLink on this computer and try again. If your browser asks to connect to this computer, choose Allow."],
        insecureOrigin: ["scanInsecureOrigin", "scan_insecure_origin_message", "Open this application using its secure address, or contact your support team to enable scanning."],
        requestUncertain: ["scanRequestUncertain", "scan_request_uncertain_message", "The scan request lost its connection. Check ScanLink before starting another scan."],
        busy: ["scanBusy", "scan_busy_message", "Another scan is already running. Wait for it to finish, then try again."],
        cancelled: ["scanCancelled", "scan_cancelled_message", "The scan was cancelled."],
        timeout: ["scanTimeout", "scan_timeout_message", "The scan took too long to finish."],
        stalled: ["scanStalled", "scan_stalled_message", "The scan helper appears to be stuck. Check the ScanLink tray app, scanner dialog, or scanner driver and try again."],
        noScanners: ["scanNoScanners", "scan_no_scanners_message", "No TWAIN scanner is available on this computer."],
        openSource: ["scanOpenSource", "scan_open_source_failed_message", "The selected scanner could not be opened."],
        noPages: ["scanNoPages", "scan_no_pages_message", "The scanner returned no pages. Check that paper is loaded, then try again."],
        acquireFailed: ["scanAcquireFailed", "scan_acquire_failed_message", "The scanner stopped before the scan finished. Check the scanner and try again."],
        workerCrashed: ["scanWorkerCrashed", "scan_worker_crashed_message", "ScanLink's scanning process stopped unexpectedly. Try again; if it happens again, restart ScanLink."],
        lost: ["scanLost", "scan_lost_message", "ScanLink restarted or the scan was lost. Scan again."],
        invalidResult: ["scanInvalidResult", "scan_invalid_result_message", "ScanLink did not return a PDF. Scan again; if it happens again, restart ScanLink."],
        originNotAllowed: ["scanOriginNotAllowed", "scan_origin_not_allowed_message", "ScanLink on this computer has not allowed this site. Scan again and choose Allow in the ScanLink window."],
        linking: ["scanLinking", "scan_linking_message", "Choose Allow in the ScanLink window on this computer to let this site scan."],
        linkDeclined: ["scanLinkDeclined", "scan_link_declined_message", "ScanLink was not allowed to scan for this site. Wait a few minutes, scan again and choose Allow."],
        linkTimeout: ["scanLinkTimeout", "scan_link_timeout_message", "Nobody answered the ScanLink window. Scan again and choose Allow."],
        linkPending: ["scanLinkPending", "scan_link_pending_message", "ScanLink is waiting for an answer about another site. Answer its window, then scan again."],
        linkRateLimited: ["scanLinkRateLimited", "scan_link_rate_limited_message", "ScanLink asked about this site a moment ago. Wait a few minutes, then scan again."],
        failed: ["scanFailed", "scan_failed_message", "The scan could not be completed."],
    };

    function messagesFor(element) {
        const data = (element && element.dataset) || {};
        const strings = window.DLUX_STRINGS || {};
        const messages = {};
        Object.keys(MESSAGES).forEach(function (name) {
            const [attribute, key, fallback] = MESSAGES[name];
            messages[name] = data[attribute] || strings[key] || fallback;
        });
        return messages;
    }

    // Every message is the page's own: ScanLink's text is English, may carry
    // exception details or paths, and comes from whatever answers on the port.
    function errorMessage(messages, error) {
        switch (error && error.code) {
            case "insecure_origin":
                return messages.insecureOrigin;
            case "helper_unavailable":
                return messages.helperUnavailable;
            case "scan_request_uncertain":
                return messages.requestUncertain;
            case "helper_stalled":
                return messages.stalled;
            case "busy":
                return messages.busy;
            case "scanner_selection_cancelled":
            case "cancelled":
                return messages.cancelled;
            case "acquire_timeout":
            case "scan_timeout":
            case "scan_idle_timeout":
                return messages.timeout;
            case "no_scanners":
            case "twain_unavailable":
                return messages.noScanners;
            case "open_source_failed":
                return messages.openSource;
            case "no_pages_scanned":
                return messages.noPages;
            case "acquire_failed":
                return messages.acquireFailed;
            case "scan_worker_crashed":
                return messages.workerCrashed;
            case "job_not_found":
            case "result_unavailable":
                return messages.lost;
            case "invalid_result":
                return messages.invalidResult;
            case "origin_not_allowed":
                return messages.originNotAllowed;
            case "link_declined":
                return messages.linkDeclined;
            case "link_timeout":
                return messages.linkTimeout;
            case "link_pending":
                return messages.linkPending;
            case "link_rate_limited":
                return messages.linkRateLimited;
            default:
                return messages.failed;
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

    // Other websites the administrator lets use ScanLink (System Settings); this
    // site is always included by ScanLink itself.
    function adminSites() {
        const element = typeof document !== "undefined" && document.getElementById
            ? document.getElementById("dlux-scanlink-sites") : null;
        try {
            const sites = JSON.parse((element && element.textContent) || "[]");
            return Array.isArray(sites) ? sites.filter((site) => typeof site === "string") : [];
        } catch (error) {
            return [];
        }
    }

    function sameSites(linked, sites) {
        const have = new Set(linked || []);
        const want = new Set([window.location.origin].concat(sites));
        return have.size === want.size && Array.from(want).every((site) => have.has(site));
    }

    // A healthy, linked ScanLink, or a rejection. An unlinked site asks ScanLink
    // to link it, which opens ScanLink's approval window; a linked site whose
    // administrator changed the list updates it without asking again.
    async function linkedHealth(scanLink, messages, onProgress) {
        let health = await scanLink.checkHealth(true);
        const sites = adminSites();
        if (!health && scanLink.connectionError && scanLink.connectionError.code === "origin_not_allowed") {
            onProgress(messages.linking, { status: "linking" });
            await scanLink.link(sites);
            health = await scanLink.checkHealth(true);
        } else if (health && health.link && health.link.linked && !sameSites(health.link.sites, sites)) {
            // A list that gains a site opens ScanLink's window again.
            onProgress(messages.linking, { status: "linking" });
            try {
                await scanLink.link(sites);
            } catch (error) {
                // The site stays linked with its previous list; scanning goes on.
            }
            onProgress(messages.preparing, { status: "queued" });
        }
        if (!health) throw scanLink.connectionError || new window.ScanLinkError(messages.helperUnavailable, "helper_unavailable");
        return health;
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
            const health = await linkedHealth(scanLink, messages, onProgress);
            if (health.twain_available === false) throw new window.ScanLinkError(messages.noScanners, "twain_unavailable");
            if (health.busy) throw new window.ScanLinkError(messages.busy, "busy");

            const job = await scanLink.startScan({ metadata: (options && options.metadata) || { path: window.location.pathname } });
            jobId = job.job_id;
            listeners.set(jobId, function (data) {
                const text = statusMessage(messages, data);
                if (text) onProgress(text, data);
            });
            // Longer than ScanLink's own job deadline (10 minutes plus 15 s), so a
            // slow scan ends with ScanLink's reason instead of the page giving up
            // while the scanner keeps going.
            return await scanLink.waitForResult(jobId, { timeoutMs: SCAN_WAIT_MS });
        } catch (error) {
            const translated = new window.ScanLinkError(errorMessage(messages, error), (error && error.code) || "scan_failed");
            throw translated;
        } finally {
            if (jobId) listeners.delete(jobId);
        }
    }

    // Links this site without scanning (the Options ScanLink card's Allow button).
    async function link(options) {
        const messages = (options && options.messages) || messagesFor(null);
        try {
            return await linkedHealth(client(), messages, (options && options.onProgress) || function () {});
        } catch (error) {
            throw new window.ScanLinkError(errorMessage(messages, error), (error && error.code) || "scan_failed");
        }
    }

    window.DluxScan = { scan: scan, link: link, messagesFor: messagesFor, errorMessage: errorMessage, waitMs: SCAN_WAIT_MS };

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
