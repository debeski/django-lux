class ScanLinkError extends Error {
    constructor(message, code = "scan_failed", details = {}) {
        super(message);
        this.name = "ScanLinkError";
        this.code = code;
        this.details = details;
    }
}

class ScanLink {
    constructor(options = {}) {
        this.httpUrl = options.httpUrl || "http://localhost:5000";
        this.httpsUrl = options.httpsUrl || "https://localhost:5443";
        this.protocol = options.protocol || "scanlink";

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
                const response = await fetch(`${baseUrl}/health`, {
                    method: "GET",
                    mode: "cors",
                });
                if (!response.ok) {
                    continue;
                }

                const health = await response.json();
                this._setPreferredUrl(baseUrl);
                this.onConnectionChange(true);
                return health;
            } catch (error) {
                continue;
            }
        }

        this.onConnectionChange(false);
        return null;
    }

    async startScan(options = {}) {
        const payload = {};
        if (options.docId) payload.doc_id = options.docId;
        if (options.callbackUrl) payload.callback_url = options.callbackUrl;
        if (options.metadata && typeof options.metadata === "object") payload.metadata = options.metadata;

        try {
            const response = await this._fetchResponse("/scan", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
                mode: "cors",
            });

            if (!response.ok) {
                throw await this._responseToError(response, "Failed to start scan.");
            }

            const data = await response.json();
            this.currentJobId = data.job_id;
            this.onStatus(data);
            return data;
        } catch (error) {
            const normalized = this._normalizeError(error, "Failed to start scan.");
            this.onError(normalized);
            throw normalized;
        }
    }

    async getStatus(jobId) {
        const response = await this._fetchResponse(`/scan/${jobId}`, {
            method: "GET",
            mode: "cors",
        });

        if (!response.ok) {
            throw await this._responseToError(response, "Failed to get scan status.");
        }

        return response.json();
    }

    async waitForResult(jobId, options = {}) {
        const pollIntervalMs = options.pollIntervalMs || 1000;
        const timeoutMs = options.timeoutMs || 10 * 60 * 1000;
        const startedAt = Date.now();
        let previousPageCount = 0;
        let lastSignature = null;

        while (Date.now() - startedAt < timeoutMs) {
            let status;
            try {
                status = await this.getStatus(jobId);
            } catch (error) {
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
                const blob = await this.getResult(jobId);
                this.onComplete(jobId, status.page_count || 0);
                return blob;
            }

            if (["failed", "cancelled", "timed_out"].includes(status.status)) {
                const error = this._errorFromJob(status);
                this.onError(error);
                throw error;
            }

            await this._sleep(pollIntervalMs);
        }

        const timeoutError = new ScanLinkError("The scan timed out while waiting for a result.", "scan_timeout");
        this.onError(timeoutError);
        throw timeoutError;
    }

    async getResult(jobId) {
        const response = await this._fetchResponse(`/scan/${jobId}/result`, {
            method: "GET",
            mode: "cors",
        });

        if (!response.ok) {
            throw await this._responseToError(response, "Failed to download the scanned PDF.");
        }

        return response.blob();
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

    async _fetchResponse(path, options = {}) {
        const candidates = this._candidateUrls(false);
        let lastError = null;

        for (const baseUrl of candidates) {
            try {
                const response = await fetch(`${baseUrl}${path}`, options);
                this._setPreferredUrl(baseUrl);
                this.onConnectionChange(true);
                return response;
            } catch (error) {
                lastError = error;
            }
        }

        this.onConnectionChange(false);
        throw new ScanLinkError(
            "ScanLink is not available on this computer.",
            "helper_unavailable",
            { cause: lastError }
        );
    }

    _candidateUrls(force = false) {
        if (force || !this.preferredUrl) {
            return [this.httpsUrl, this.httpUrl].filter(Boolean);
        }

        const fallback = this.preferredUrl === this.httpsUrl ? this.httpUrl : this.httpsUrl;
        return [this.preferredUrl, fallback].filter(Boolean);
    }

    _setPreferredUrl(baseUrl) {
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
}

window.ScanLink = ScanLink;
window.ScanLinkError = ScanLinkError;

if (typeof module !== "undefined" && module.exports) {
    module.exports = { ScanLink, ScanLinkError };
}
