/* ScanLink update check, run in the operator's own browser.
 *
 * The page is the only place that can reach BOTH the helper on this workstation
 * (localhost:5443/5000) and this server's release manifest, so the version
 * comparison happens here rather than server-side.
 *
 * Ported from project-archive. Config arrives through data-* attributes on the
 * card, never inline JS, so it works under the nonce-based CSP.
 */
(function () {
    'use strict';

    function init(root) {
        if (!root || root.dataset.scanlinkUpdateBound === 'true') return;
        root.dataset.scanlinkUpdateBound = 'true';

        let origins = [];
        try {
            origins = JSON.parse(root.dataset.origins || '[]');
        } catch (error) {
            origins = [];
        }
        const manifestUrl = root.dataset.manifestUrl;

        const els = {
            conn: root.querySelector('[data-scanlink-connection]'),
            local: root.querySelector('[data-scanlink-local-version]'),
            latest: root.querySelector('[data-scanlink-latest-version]'),
            status: root.querySelector('[data-scanlink-status]'),
            actions: root.querySelector('[data-scanlink-actions]'),
            notice: root.querySelector('[data-scanlink-notice]'),
        };

        function t(key, fallback) {
            const strings = window.DLUX_STRINGS || {};
            return (typeof strings[key] === 'string' && strings[key]) || fallback;
        }

        // Numeric-segment compare, so 0.10.0 sorts above 0.9.0. A lexical
        // compare gets that backwards and would report an upgrade as a
        // downgrade.
        function parseKey(value) {
            const matched = String(value == null ? '' : value).match(/\d+/g);
            return matched ? matched.map(Number) : [-1];
        }

        function compareVersions(a, b) {
            const ka = parseKey(a);
            const kb = parseKey(b);
            const length = Math.max(ka.length, kb.length);
            for (let i = 0; i < length; i += 1) {
                const x = ka[i] || 0;
                const y = kb[i] || 0;
                if (x < y) return -1;
                if (x > y) return 1;
            }
            return 0;
        }

        // Mixed-content / Private Network Access guard: an HTTPS page is blocked
        // from fetching http://localhost, so filter to what this scheme may
        // actually reach rather than firing a request the browser will refuse.
        function reachableOrigins() {
            if (window.location.protocol !== 'https:') return origins.slice();
            return origins.filter((origin) => origin.indexOf('https:') === 0);
        }

        function setNotice(message) {
            if (!els.notice) return;
            els.notice.textContent = message;
            els.notice.hidden = !message;
        }

        function checkLocalHealth() {
            const candidates = reachableOrigins();
            if (!candidates.length) {
                setNotice(t(
                    'scanlink_mixed_content_warning',
                    'This page is served over HTTPS, so the browser blocks contacting the local ScanLink service over HTTP.',
                ));
                return Promise.resolve(null);
            }
            const attempt = (index) => {
                if (index >= candidates.length) return Promise.resolve(null);
                return fetch(`${candidates[index]}/health`, { method: 'GET', mode: 'cors' })
                    .then((response) => {
                        if (!response.ok) throw new Error('bad status');
                        return response.json();
                    })
                    .catch(() => attempt(index + 1));
            };
            return attempt(0);
        }

        function fetchManifest() {
            return fetch(manifestUrl, { method: 'GET', credentials: 'same-origin' })
                .then((response) => {
                    if (!response.ok) throw new Error('manifest unavailable');
                    return response.json();
                })
                .catch(() => null);
        }

        function pickDownload(manifest, health) {
            if (!manifest || !manifest.downloads) return null;
            // /health reports the workstation's architecture; prefer the
            // matching build, then whatever is published.
            const arch = health && health.arch;
            return (arch && manifest.downloads[arch])
                || manifest.downloads.x64
                || manifest.downloads.x86
                || null;
        }

        function addButton(label, url, cssClass) {
            if (!els.actions) return;
            const link = document.createElement('a');
            link.href = url;
            link.className = `btn rounded-pill px-4 ${cssClass || 'btn-primary'}`;
            link.textContent = label;
            link.setAttribute('download', '');
            els.actions.appendChild(link);
        }

        function render(health, manifest) {
            const latest = manifest && manifest.latest_version;
            if (els.latest) els.latest.textContent = latest || t('scanlink_none', '—');

            if (!health) {
                if (els.conn) {
                    els.conn.textContent = t('scanlink_not_connected', 'Not detected');
                    els.conn.className = 'badge bg-secondary';
                }
                if (els.local) els.local.textContent = t('scanlink_unknown', 'Unknown');
            } else {
                if (els.conn) {
                    els.conn.textContent = t('scanlink_connected', 'Connected');
                    els.conn.className = 'badge bg-success';
                }
                if (els.local) els.local.textContent = health.version || t('scanlink_unknown', 'Unknown');
            }

            const downloadUrl = pickDownload(manifest, health);

            if (!health) {
                if (els.status) {
                    els.status.textContent = t('scanlink_install_prompt', 'ScanLink was not detected on this computer.');
                }
                if (downloadUrl) {
                    addButton(t('scanlink_install', 'Download and install ScanLink'), downloadUrl, 'btn-primary');
                }
                return;
            }

            if (!latest || !downloadUrl) {
                if (els.status) {
                    els.status.textContent = t('scanlink_no_release', 'No installer is published on the server yet.');
                }
                return;
            }

            if (compareVersions(health.version, latest) < 0) {
                if (els.status) {
                    els.status.textContent = t('scanlink_update_available', 'A newer ScanLink version is available.');
                }
                addButton(`${t('scanlink_update', 'Download update')} (${latest})`, downloadUrl, 'btn-warning');
            } else if (els.status) {
                els.status.textContent = t('scanlink_up_to_date', 'ScanLink is up to date.');
            }
        }

        Promise.all([checkLocalHealth(), fetchManifest()])
            .then((results) => render(results[0], results[1]));
    }

    function scan() {
        document.querySelectorAll('[data-scanlink-update-card]').forEach(init);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', scan);
    } else {
        scan();
    }
})();
