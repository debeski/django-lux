# ScanLink workstation setup

Enable ScanLink in System Settings → Extra Features, then publish the Windows
installer through Options → ScanLink. Operators download the installer from the
project they use, install it, open ScanLink, and approve any Windows or browser
prompt. They do not run commands or import certificates.

## How a scan connects

`window.DluxScan.scan()` (from `scan_button.js`) is the one scan routine: file
fields and the PDF editor both call it. It drives the `window.ScanLink` client
(`dlux/static/dlux/helpers/scanlink/js/main.js`), which talks to the helper at
`https://localhost:5443` and `http://localhost:5000`.

For every scan, `ScanLink.startScan()`:

1. Checks `GET /health`, first on the transport that last answered, then on the
   other one. Each attempt, including its response body, has a three-second
   timeout.
2. Sends the scan POST once, to the transport that just answered. If HTTPS stops
   answering (for example after a ScanLink restart whose certificate setup
   failed), the next scan uses HTTP :5000.
3. Reports `helper_unavailable` (or `insecure_origin`, see
   [Browser connection failures](#browser-connection-failures)) without posting
   when no transport answers, for example because ScanLink is closed.
4. Reports `scan_request_uncertain` when the request or the accepted response body
   loses its connection, and asks the operator to check ScanLink before starting
   another scan. It never resubmits a scan automatically.

Status and result reads (`GET /scan/<job_id>` and `/scan/<job_id>/result`) keep
the HTTPS/HTTP fallback. File fields and the PDF editor share the English/Arabic
guidance in `dlux/helpers/scanlink/scan_messages.html`.

The page waits up to 11 minutes for a scan, longer than ScanLink's own job deadline
(10 minutes plus 15 s), so a slow scan ends with ScanLink's reason rather than the
page giving up while the scanner keeps going. ScanLink's error codes are shown
translated:

| Code | Message |
|---|---|
| `no_pages_scanned` | The scanner returned no pages; check the paper. |
| `acquire_failed` | The scanner stopped before the scan finished. |
| `scan_worker_crashed` | ScanLink's scanning process stopped; try again, then restart ScanLink. |
| `origin_not_allowed` | ScanLink does not accept scans from this site; add it to ScanLink's allowed sites. |
| `acquire_timeout`, `scan_timeout`, `scan_idle_timeout` | The scan took too long. |
| `payload_too_large`, `invalid_host`, `local_only` | The scan could not be completed. |

A code the page does not know shows ScanLink's own message.

On the helper side, ScanLink keeps a job in `generating_pdf` until the child
process exits and the PDF is stored, and enforces the parent scan deadline even
while progress keeps arriving. It rejects malformed scan bodies before queueing
hardware work, and keeps a consumed job's metadata until its TTL so a repeated
result download gets the same single-use answer.

## Compatible versions

The client keeps health, status and result compatibility with ScanLink 0.7.4 or
later. ScanLink 0.7.4 does not report certificate setup progress, so the
installer panel shows no setup guidance for it.

`dlux/tests/fixtures/scanlink/scenarios.mjs` holds the paired connection
scenarios; `dlux/tests/test_scanlink_connection.py` runs them against the
DjangoLux client. To check the helper's own client against the same scenarios,
pass its `static/scanlink.js` as the second argument:

```bash
node dlux/tests/fixtures/scanlink/scenarios.mjs . <scanlink-checkout>/static/scanlink.js
```

## Automatic secure connection

A helper that reports `/health.https_setup` sets up HTTPS itself. It starts HTTP
on 127.0.0.1:5000, then provisions HTTPS on 127.0.0.1:5443 in its server thread:

- A per-user self-signed server certificate covers localhost, 127.0.0.1 and ::1.
- ScanLink installs that specific certificate in the current Windows user's
  trusted roots. It does not install a general certificate authority or change
  machine-wide trust.
- The private key is encrypted with a random password protected by Windows
  DPAPI. Nothing is downloaded during setup.
- Healthy launches reuse the identity, repair missing trust, and renew within 30
  days of expiry; hourly checks also cover long-running sessions.

The installer panel reads `https_setup` values `preparing`, `ready` and `failed`.
While preparing, it checks again automatically up to 20 times, 1.5 seconds apart;
HTTP scanning stays available meanwhile. A setup failure offers Retry in the
ScanLink app, and its tray has **Retry secure connection setup**.

Organization policies may require support to approve trust changes. Browsers may
require a local-device permission, or reopening the page after trust changes.
ScanLink cannot grant browser permissions or override an enterprise browser trust
policy.

## Browser connection failures

Both the shared scan routine and the installer panel try HTTPS, then HTTP
loopback, with the three-second health timeout. HTTP loopback is eligible from an
HTTPS page; the browser still enforces CORS, CSP, local network permission and
enterprise policy.

If all transports fail and `window.isSecureContext` is false, the shared scan
client reports `insecure_origin`. Otherwise it reports `helper_unavailable` and
asks the operator to start ScanLink and approve a browser connection prompt if
one appears. JavaScript cannot reliably distinguish an untrusted certificate,
a denied permission, a stopped helper and a network refusal, so the UI does not
claim to have diagnosed which one occurred.

`http://localhost` on the operator's own PC is usually a secure context.
An HTTP application opened at a workstation's LAN address is not; a certificate
on ScanLink does not secure that application's origin. Support must provide an
appropriate application address in browsers enforcing this restriction.

## Publishing installers

Upload the x64 and x86 installers through Options → ScanLink. A version may carry
a beta or RC suffix (`bN` or `rcN`) and is ordered like a package version: beta <
RC < stable for the same numeric release, and a newer release's beta outranks an
older stable.

The update manifest (`scanlink/update.json`) advertises the highest active
version per architecture, with its SHA-256. An uploaded row is active by
default, so a beta reaches every operator unless **Advertise this release** is
cleared. Signed-in users download installers through `scanlink/download/<pk>/`;
the stored bytes sit under the protected asset prefix, which the proxy denies.

## Server preparation

The reverse proxy must accept the installer upload size. The generated Caddy
configuration defaults to `CADDY_MAX_SIZE=10MB`, and the installers are about
28–31 MB. Set `CADDY_MAX_SIZE` above the larger installer plus multipart overhead
(for example `64MB`). This is a deployment setting for the operator publishing
installers.

Projects using the PDF editor must install `django-lux[pdf]`; its optional
`pypdf` dependency is needed to assemble and save scanned pages. The ScanLink
file-field button does not require the PDF editor to be enabled.
