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

        function parseKey(value) {
            const matched = String(value == null ? '' : value).match(/^(\d+(?:\.\d+){0,3})(?:(b|rc)(\d+))?$/);
            if (!matched) return [-1];
            const release = matched[1].split('.').map(Number);
            while (release.length < 4) release.push(0);
            return release.concat([matched[2] === 'b' ? 0 : matched[2] === 'rc' ? 1 : 2, Number(matched[3] || 0)]);
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

        function setNotice(message) {
            if (!els.notice) return;
            els.notice.textContent = message;
            els.notice.hidden = !message;
        }

        async function checkLocalHealth() {
            // Loopback HTTP is eligible even when the page uses HTTPS.
            for (const origin of origins) {
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), 3000);
                try {
                    const response = await fetch(`${origin}/health`, {
                        method: 'GET', mode: 'cors', signal: controller.signal,
                    });
                    if (response.ok) return await response.json();
                } catch (error) {
                    // Try the other transport before reporting an unavailable helper.
                } finally {
                    clearTimeout(timer);
                }
            }
            return null;
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
            if (els.actions) els.actions.replaceChildren();
            setNotice('');
            if (health && health.https_setup === 'preparing') {
                setNotice(t('scanlink_secure_preparing', 'ScanLink is setting up its secure connection. Approve any Windows prompt; this page will check again automatically.'));
            } else if (health && health.https_setup === 'failed') {
                setNotice(t('scanlink_secure_failed', 'Open ScanLink and choose Retry secure connection setup. Approve any Windows prompt. If setup is blocked, contact your support team.'));
            } else if (!health) {
                setNotice(window.isSecureContext === false
                    ? t('scan_insecure_origin_message', 'Open this application using its secure address, or contact your support team to enable scanning.')
                    : t('scan_helper_unavailable_message', 'Start ScanLink on this computer and try again. If your browser asks to connect to this computer, choose Allow.'));
            }
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

        Promise.all([checkLocalHealth(), fetchManifest()]).then(async ([health, manifest]) => {
            render(health, manifest);
            for (let attempt = 0; health && health.https_setup === 'preparing' && attempt < 20; attempt += 1) {
                await new Promise((resolve) => setTimeout(resolve, 1500));
                if (!root.isConnected) break;
                health = await checkLocalHealth();
                render(health, manifest);
            }
        });
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
