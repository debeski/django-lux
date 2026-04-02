/**
 * ScanLink.js - Django/Browser Integration Library
 * 
 * Provides easy integration with ScanLink desktop scanner bridge.
 * Supports both WebSocket (real-time) and REST API (polling) modes.
 * 
 * Usage:
 *   const scanner = new ScanLink({
 *       onStatus: (status) => console.log('Status:', status),
 *       onPageScanned: (count) => updateUI(`Page ${count} scanned`),
 *       onComplete: (jobId) => fetchPdf(jobId),
 *       onError: (error) => showError(error)
 *   });
 *   
 *   // Start a scan
 *   scanner.startScan({ docId: '123' });
 *   
 *   // Or use deep link (opens desktop app directly)
 *   scanner.openDeepLink({ docId: '123', callback: '/api/upload/' });
 */

class ScanLink {
    constructor(options = {}) {
        // Configuration
        this.httpUrl = options.httpUrl || 'http://localhost:5000';
        this.httpsUrl = options.httpsUrl || 'https://localhost:5443';
        this.useSSL = options.useSSL ?? true;  // Try HTTPS first
        this.protocol = options.protocol || 'scanlink';

        // Callbacks
        this.onStatus = options.onStatus || (() => { });
        this.onPageScanned = options.onPageScanned || (() => { });
        this.onComplete = options.onComplete || (() => { });
        this.onError = options.onError || (() => { });
        this.onConnectionChange = options.onConnectionChange || (() => { });

        // State
        this.socket = null;
        this.connected = false;
        this.currentJobId = null;
        this.pollInterval = null;

        // Auto-connect if WebSocket available
        if (options.autoConnect !== false) {
            this.connect();
        }
    }

    /**
     * Get the base URL (tries HTTPS first, falls back to HTTP)
     */
    get baseUrl() {
        return this.useSSL ? this.httpsUrl : this.httpUrl;
    }

    /**
     * Check if ScanLink is available on the local machine
     */
    async checkHealth() {
        try {
            const response = await fetch(`${this.baseUrl}/health`, {
                method: 'GET',
                mode: 'cors'
            });
            if (response.ok) {
                return await response.json();
            }
        } catch (e) {
            // Try HTTP if HTTPS failed
            if (this.useSSL) {
                this.useSSL = false;
                return this.checkHealth();
            }
        }
        return null;
    }

    /**
     * Connect to ScanLink via WebSocket
     */
    connect() {
        if (this.socket && this.connected) {
            return Promise.resolve();
        }

        return new Promise((resolve, reject) => {
            try {
                // Use socket.io-client if available, otherwise fall back to polling
                if (typeof io !== 'undefined') {
                    const wsUrl = this.useSSL
                        ? this.httpsUrl.replace('https:', 'wss:')
                        : this.httpUrl.replace('http:', 'ws:');

                    this.socket = io(this.baseUrl, {
                        transports: ['websocket', 'polling'],
                        reconnection: true,
                        reconnectionAttempts: 5,
                        reconnectionDelay: 1000
                    });

                    this.socket.on('connect', () => {
                        this.connected = true;
                        this.onConnectionChange(true);
                        resolve();
                    });

                    this.socket.on('disconnect', () => {
                        this.connected = false;
                        this.onConnectionChange(false);
                    });

                    this.socket.on('scan_status', (data) => {
                        this._handleStatus(data);
                    });

                    this.socket.on('error', (error) => {
                        this.onError(error);
                    });

                    this.socket.on('connect_error', (error) => {
                        // Try HTTP if HTTPS WebSocket failed
                        if (this.useSSL) {
                            this.useSSL = false;
                            this.socket.disconnect();
                            this.connect().then(resolve).catch(reject);
                        } else {
                            reject(error);
                        }
                    });
                } else {
                    // No socket.io, use REST polling
                    console.warn('ScanLink: socket.io not found, using REST polling');
                    this.connected = false;
                    resolve();
                }
            } catch (e) {
                reject(e);
            }
        });
    }

    /**
     * Disconnect from WebSocket
     */
    disconnect() {
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
        }
        this.connected = false;
        this.stopPolling();
    }

    /**
     * Start a scan via WebSocket or REST API
     */
    async startScan(options = {}) {
        const { docId, callbackUrl } = options;

        if (this.connected && this.socket) {
            // Use WebSocket with acknowledgment and timeout
            return new Promise((resolve, reject) => {
                const timeout = setTimeout(() => {
                    console.warn('[DEBUG] WebSocket acknowledgment timed out, falling back to REST');
                    this.startScanRest(docId, callbackUrl).then(resolve).catch(reject);
                }, 5000);

                this.socket.emit('start_scan', { doc_id: docId, callback_url: callbackUrl }, (response) => {
                    clearTimeout(timeout);
                    resolve(response);
                });
            });
        } else {
            return this.startScanRest(docId, callbackUrl);
        }
    }

    /**
     * Start a scan via REST API (extracted helper)
     */
    async startScanRest(docId, callbackUrl) {
        try {
            const response = await fetch(`${this.baseUrl}/scan`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ doc_id: docId, callback_url: callbackUrl }),
                mode: 'cors'
            });

            if (response.ok) {
                const data = await response.json();
                this.currentJobId = data.job_id;
                this.onStatus({ job_id: data.job_id, status: 'queued', doc_id: docId });
                this.startPolling(data.job_id);
                return data;
            } else {
                throw new Error(`HTTP ${response.status}`);
            }
        } catch (e) {
            this.onError(`Failed to start scan: ${e.message}`);
            throw e;
        }
    }

    /**
     * Poll until a job is completed or failed and return the result blob.
     */
    async waitForResult(jobId) {
        return new Promise((resolve, reject) => {
            const check = async () => {
                try {
                    const response = await fetch(`${this.baseUrl}/scan/${jobId}`, {
                        method: 'GET',
                        mode: 'cors'
                    });
                    if (response.ok) {
                        const data = await response.json();
                        if (data.status === 'completed') {
                            const blob = await this.getResult(jobId);
                            resolve(blob);
                        } else if (data.status === 'failed') {
                            reject(new Error(data.error || 'Scan failed (no paper or scanner error)'));
                        } else {
                            setTimeout(check, 1000);
                        }
                    } else {
                        reject(new Error(`Polling failed: HTTP ${response.status}`));
                    }
                } catch (e) {
                    reject(e);
                }
            };
            check();
        });
    }

    /**
     * Open a deep link to trigger ScanLink directly
     */
    openDeepLink(options = {}) {
        const { docId, callbackUrl, action = 'scan' } = options;

        let url = `${this.protocol}://${action}`;
        const params = new URLSearchParams();

        if (docId) params.append('docId', docId);
        if (callbackUrl) params.append('callback', callbackUrl);

        if (params.toString()) {
            url += '?' + params.toString();
        }

        // Open the deep link
        window.location.href = url;
    }

    /**
     * Get scan result as Blob
     */
    async getResult(jobId) {
        const response = await fetch(`${this.baseUrl}/scan/${jobId}/result`, {
            method: 'GET',
            mode: 'cors'
        });

        if (response.ok) {
            return await response.blob();
        }
        throw new Error(`Failed to get result: HTTP ${response.status}`);
    }

    /**
     * Get scan result as download
     */
    async downloadResult(jobId, filename = null) {
        const blob = await this.getResult(jobId);
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename || `scan_${jobId}.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // =========================================================================
    // Private Methods
    // =========================================================================

    _handleStatus(data) {
        const { status, job_id, page_count, doc_id, error } = data;

        this.currentJobId = job_id;
        this.onStatus(data);

        switch (status) {
            case 'page_scanned':
                this.onPageScanned(page_count);
                break;
            case 'completed':
                this.onComplete(job_id, page_count);
                this.stopPolling();
                break;
            case 'failed':
                this.onError(error || 'Scan failed');
                this.stopPolling();
                break;
        }
    }

    startPolling(jobId) {
        this.stopPolling();

        this.pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`${this.baseUrl}/scan/${jobId}`, {
                    method: 'GET',
                    mode: 'cors'
                });

                if (response.ok) {
                    const data = await response.json();
                    this._handleStatus(data);
                }
            } catch (e) {
                console.warn('ScanLink poll error:', e);
            }
        }, 1000);
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ScanLink;
}
