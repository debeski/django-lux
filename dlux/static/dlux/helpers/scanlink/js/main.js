// Declared with `var ... || existing` (not `class`/`const`) so that a second
// load/execution of this file — e.g. from a project-level custom_scripts include,
// an AJAX fragment that re-runs it, or a stale/duplicated static copy — reuses the
// existing globals instead of throwing "Identifier 'ScanLinkError' has already
// been declared". The window.* exports at the bottom keep both available globally.
var ScanLinkError = window.ScanLinkError || class ScanLinkError extends Error {
    constructor(message, code = "scan_failed", details = {}) {
        super(message);
        this.name = "ScanLinkError";
        this.code = code;
        this.details = details;
    }
};

var ScanLink = window.ScanLink || class ScanLink {
    constructor(options = {}) {
        this.httpUrl = options.httpUrl || "http://localhost:5000";
        this.httpsUrl = options.httpsUrl || "https://localhost:5443";
        this.protocol = options.protocol || "scanlink";
        this.healthTimeoutMs = options.healthTimeoutMs || 3000;
        // Every other request has a deadline too, so a frozen or stalled helper
        // ends the wait instead of keeping the page busy for as long as it hangs.
        this.statusTimeoutMs = options.statusTimeoutMs || 10000;
        this.resultTimeoutMs = options.resultTimeoutMs || 60000;
        this.submitTimeoutMs = options.submitTimeoutMs || 15000;
        // POST /link waits up to two minutes for the operator's answer.
        this.linkTimeoutMs = options.linkTimeoutMs || 135000;
        this.stallWindowMs = options.stallWindowMs || 30000;
        this.connectionError = null;

        this.onStatus = options.onStatus || (() => {});
        this.onPageScanned = options.onPageScanned || (() => {});
        this.onComplete = options.onComplete || (() => {});
        this.onError = options.onError || (() => {});
        this.onConnectionChange = options.onConnectionChange || (() => {});

        this.currentJobId = null;
        this.preferredUrl = options.baseUrl || null;
    }

    get baseUrl() {
        return this.preferredUrl || this.httpsUrl || this.httpUrl;
    }

    async connect() {
        return this.checkHealth(true);
    }

    disconnect() {
        return undefined;
    }

    async checkHealth(force = false) {
        const candidates = this._candidateUrls(force);

        for (const baseUrl of candidates) {
            try {
                const health = await this._healthAt(baseUrl);
                if (!health) continue;
                this._setPreferredUrl(baseUrl);
                this.connectionError = null;
                this.onConnectionChange(true);
                return health;
            } catch (error) {
                if (error instanceof ScanLinkError && error.code === "origin_not_allowed") {
                    // ScanLink answered, but this website is not linked: link() can fix that.
                    this._setPreferredUrl(baseUrl);
                    this.connectionError = error;
                    this.onConnectionChange(false);
                    return null;
                }
                continue;
            }
        }

        this.connectionError = this._connectionFailure();
        this.onConnectionChange(false);
        return null;
    }

    async _healthAt(baseUrl) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.healthTimeoutMs);
        try {
            const response = await fetch(`${baseUrl}/health`, {
                method: "GET", mode: "cors", signal: controller.signal,
            });
            // Read the body before clearing the timeout, including stalled responses.
            if (response.status === 403) {
                const refusal = await this._responseToError(response, "ScanLink refused this website.");
                if (refusal.code === "origin_not_allowed") throw refusal;
                return null;
            }
            if (!response.ok) return null;
            const health = await response.json();
            // Anything else answering on the port is not ScanLink.
            return health && typeof health === "object" && health.status === "ok" ? health : null;
        } finally {
            clearTimeout(timer);
        }
    }

    _stalled() {
        return new ScanLinkError("ScanLink stopped answering.", "helper_stalled");
    }

    // Runs `work(signal)` under a deadline: the request is aborted and the call
    // rejects with `helper_stalled` once `timeoutMs` passes, body read included.
    _timed(timeoutMs, work) {
        const controller = new AbortController();
        let timer = null;
        const deadline = new Promise((resolve, reject) => {
            timer = setTimeout(() => {
                reject(this._stalled());
                controller.abort();
            }, Math.max(1, timeoutMs));
        });
        return Promise.race([work(controller.signal), deadline]).finally(() => clearTimeout(timer));
    }

    _connectionFailure(cause) {
        if (window.isSecureContext === false) {
            return new ScanLinkError("Open this application using its secure address, or contact your support team to enable scanning.", "insecure_origin", { cause });
        }
        return new ScanLinkError("Start ScanLink on this computer and try again. If your browser asks to connect to this computer, choose Allow.", "helper_unavailable", { cause });
    }

    async startScan(options = {}) {
        const payload = {};
        if (options.docId) payload.doc_id = options.docId;
        if (options.callbackUrl) payload.callback_url = options.callbackUrl;
        if (options.metadata && typeof options.metadata === "object") payload.metadata = options.metadata;

        try {
            // Re-negotiate every scan so a lost transport is reported before the single POST.
            if (!await this.checkHealth()) {
                throw this.connectionError;
            }
            let data;
            try {
                data = await this._timed(this.submitTimeoutMs, async (signal) => {
                    const response = await this._fetchResponse("/scan", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload),
                        mode: "cors",
                        signal,
                    });
                    if (!response.ok) {
                        throw await this._responseToError(response, "Failed to start scan.");
                    }
                    let body;
                    try {
                        body = await response.json();
                    } catch (error) {
                        throw this._uncertainRequest(error);
                    }
                    if (!body || !body.job_id) throw this._uncertainRequest(new Error("Missing scan job ID"));
                    return body;
                });
            } catch (error) {
                // A stalled answer may still have started the scan.
                if (error && error.code === "helper_stalled") throw this._uncertainRequest(error);
                throw error;
            }
            this.currentJobId = data.job_id;
            this.onStatus(data);
            return data;
        } catch (error) {
            const normalized = this._normalizeError(error, "Failed to start scan.");
            this.onError(normalized);
            throw normalized;
        }
    }

    async getStatus(jobId, timeoutMs = this.statusTimeoutMs) {
        return this._timed(timeoutMs, async (signal) => {
            const response = await this._fetchResponse(`/scan/${jobId}`, {
                method: "GET",
                mode: "cors",
                signal,
            });

            if (!response.ok) {
                throw await this._responseToError(response, "Failed to get scan status.");
            }

            return response.json();
        });
    }

    async waitForResult(jobId, options = {}) {
        const pollIntervalMs = options.pollIntervalMs || 1000;
        const timeoutMs = options.timeoutMs || 10 * 60 * 1000;
        const deadline = Date.now() + timeoutMs;
        let previousPageCount = 0;
        let lastSignature = null;
        let lastAnswer = Date.now();

        while (Date.now() < deadline) {
            let status;
            try {
                status = await this.getStatus(jobId, Math.min(this.statusTimeoutMs, deadline - Date.now()));
                lastAnswer = Date.now();
            } catch (error) {
                // One slow answer is retried; a helper silent for the whole stall
                // window, or past the scan's deadline, ends the wait.
                if (error && error.code === "helper_stalled" && Date.now() < deadline
                    && Date.now() - lastAnswer < this.stallWindowMs) {
                    await this._sleep(Math.min(pollIntervalMs, Math.max(0, deadline - Date.now())));
                    continue;
                }
                if (error && error.code === "helper_stalled" && Date.now() >= deadline) break;
                const normalized = this._normalizeError(error, "Failed while waiting for scan result.");
                this.onError(normalized);
                throw normalized;
            }

            const signature = JSON.stringify([
                status.status,
                status.page_count || 0,
                status.error && status.error.code,
            ]);

            if (signature !== lastSignature) {
                lastSignature = signature;
                this.currentJobId = status.job_id;
                this.onStatus(status);

                if (status.status === "page_scanned" && (status.page_count || 0) !== previousPageCount) {
                    previousPageCount = status.page_count || 0;
                    this.onPageScanned(previousPageCount);
                }
            }

            if (status.status === "completed") {
                let blob;
                try {
                    blob = await this.getResult(jobId, Math.max(1000, Math.min(this.resultTimeoutMs, deadline - Date.now())));
                } catch (error) {
                    const normalized = this._normalizeError(error, "Failed to download the scanned PDF.");
                    this.onError(normalized);
                    throw normalized;
                }
                this.onComplete(jobId, status.page_count || 0);
                return blob;
            }

            if (["failed", "cancelled", "timed_out"].includes(status.status)) {
                const error = this._errorFromJob(status);
                this.onError(error);
                throw error;
            }

            await this._sleep(Math.min(pollIntervalMs, Math.max(0, deadline - Date.now())));
        }

        const timeoutError = new ScanLinkError("The scan timed out while waiting for a result.", "scan_timeout");
        this.onError(timeoutError);
        throw timeoutError;
    }

    async getResult(jobId, timeoutMs = this.resultTimeoutMs) {
        const blob = await this._timed(timeoutMs, async (signal) => {
            const response = await this._fetchResponse(`/scan/${jobId}/result`, {
                method: "GET",
                mode: "cors",
                signal,
            });

            if (!response.ok) {
                throw await this._responseToError(response, "Failed to download the scanned PDF.");
            }

            return response.blob();
        });
        // Only a PDF becomes the field's file, whatever answered on the port.
        if (!blob || typeof blob.slice !== "function" || await blob.slice(0, 5).text() !== "%PDF-") {
            throw new ScanLinkError("ScanLink did not return a PDF.", "invalid_result");
        }
        return blob;
    }

    async downloadResult(jobId, filename = null) {
        const blob = await this.getResult(jobId);
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = filename || `scan_${jobId}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }

    openDeepLink(options = {}) {
        const { docId, callbackUrl, action = "scan" } = options;
        let url = `${this.protocol}://${action}`;
        const params = new URLSearchParams();

        if (docId) params.append("docId", docId);
        if (callbackUrl) params.append("callback", callbackUrl);

        if (params.toString()) {
            url += `?${params.toString()}`;
        }

        window.location.href = url;
    }

    async link(sites = []) {
        // Resolves once the operator approves in ScanLink's own window (or at once
        // for a website that is already linked); rejects with link_declined,
        // link_pending or link_timeout otherwise.
        if (!this.preferredUrl) await this.checkHealth(true);
        return this._timed(this.linkTimeoutMs, async (signal) => {
            let response;
            try {
                response = await this._fetchResponse("/link", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ sites }),
                    mode: "cors",
                    signal,
                });
            } catch (error) {
                throw this._connectionFailure(error);
            }
            if (!response.ok) {
                throw await this._responseToError(response, "ScanLink did not link this website.");
            }
            return response.json();
        });
    }

    _uncertainRequest(cause) {
        return new ScanLinkError("The scan request lost its connection. Check ScanLink before starting another scan.", "scan_request_uncertain", { cause });
    }

    async _fetchResponse(path, options = {}) {
        const readOnly = ["GET", "HEAD"].includes((options.method || "GET").toUpperCase());
        const urls = this._candidateUrls(false);
        const candidates = readOnly ? urls : urls.slice(0, 1);
        let lastError = null;

        for (const baseUrl of candidates) {
            if (options.signal && options.signal.aborted) break;
            try {
                const response = await fetch(`${baseUrl}${path}`, options);
                this._setPreferredUrl(baseUrl);
                this.onConnectionChange(true);
                return response;
            } catch (error) {
                lastError = error;
            }
        }
        if (options.signal && options.signal.aborted) throw this._stalled();

        this.onConnectionChange(false);
        this.connectionError = readOnly ? this._connectionFailure(lastError) : this._uncertainRequest(lastError);
        throw this.connectionError;
    }

    _candidateUrls(force = false) {
        if (force || !this.preferredUrl) {
            return [this.httpsUrl, this.httpUrl].filter(Boolean);
        }

        const fallback = this.preferredUrl === this.httpsUrl ? this.httpUrl : this.httpsUrl;
        return [this.preferredUrl, fallback].filter(Boolean);
    }

    _setPreferredUrl(baseUrl) {
        if (baseUrl === this.httpUrl && this.httpsUrl && this.preferredUrl !== baseUrl && typeof console !== "undefined") {
            // Plain HTTP on localhost has no per-user identity: on a shared
            // computer another user's process could answer on the port.
            console.warn("ScanLink answered over HTTP; HTTPS (localhost:5443) was not available.");
        }
        this.preferredUrl = baseUrl;
    }

    async _responseToError(response, fallbackMessage) {
        let payload = null;
        try {
            payload = await response.json();
        } catch (error) {
            payload = null;
        }

        if (payload && payload.error) {
            return new ScanLinkError(
                payload.error.message || fallbackMessage,
                payload.error.code || "scan_failed",
                payload.error
            );
        }

        return new ScanLinkError(`${fallbackMessage} HTTP ${response.status}.`, "scan_failed", {
            status: response.status,
        });
    }

    _errorFromJob(job) {
        if (job && job.error) {
            return new ScanLinkError(
                job.error.message || "The scan could not be completed.",
                job.error.code || job.status || "scan_failed",
                job.error
            );
        }

        return new ScanLinkError(
            "The scan could not be completed.",
            job && job.status ? job.status : "scan_failed"
        );
    }

    _normalizeError(error, fallbackMessage) {
        if (error instanceof ScanLinkError) {
            return error;
        }

        return new ScanLinkError(
            error && error.message ? error.message : fallbackMessage,
            error && error.code ? error.code : "scan_failed"
        );
    }

    _sleep(delayMs) {
        return new Promise((resolve) => {
            window.setTimeout(resolve, delayMs);
        });
    }
};

window.ScanLink = ScanLink;
window.ScanLinkError = ScanLinkError;

if (typeof module !== "undefined" && module.exports) {
    module.exports = { ScanLink, ScanLinkError };
}
