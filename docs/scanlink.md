# ScanLink workstation setup

Enable ScanLink in System Settings → Extra Features, then publish the Windows
installer through Options → ScanLink. Operators download the installer from the
project they use, install it, open ScanLink, and approve any Windows or browser
prompt. The first time they scan from this site, ScanLink asks them once to allow
it (see [Allowed websites](#allowed-websites)). They do not run commands or import
certificates.

## Allowed websites

ScanLink lets no website scan until it is allowed, so a page the operator opens
elsewhere cannot use their scanner. Allowing happens once per site and computer:

1. The first scan from a site that ScanLink has not allowed (or **Allow this site
   in ScanLink** on Options → ScanLink) sends `POST /link` to the helper.
2. ScanLink opens its own window naming the site as the browser reported it, and
   the websites this site's administrator also allows. The page shows *Choose Allow
   in the ScanLink window on this computer to let this site scan.*
3. When the operator chooses **Allow**, the scan carries on. **Don't allow** stops
   it (`link_declined`), and the site cannot ask again for 10 minutes. An
   unanswered window closes after two minutes (`link_timeout`), and only one window
   is open at a time (`link_pending`).

The administrator lists the other websites in System Settings → Extra Features →
**Other websites that may use ScanLink**, one address per line (stored as website
origins in `extra_config['scanlink']['sites']`, at most 19). Use it when the same
workstations scan for another DjangoLux site. This site is always allowed and is
not listed. Every page sends the list (`json_script` `dlux-scanlink-sites`); when it
no longer matches what ScanLink holds for this site, the next scan sends it. A list
that only drops sites is updated without asking. A list that gains a site opens
ScanLink's window again, naming the added sites, and the page shows the same *Choose
Allow* message while it waits; if the operator does not allow them, the site keeps
the list it had and the scan goes on.

ScanLink and DjangoLux store a website as its origin in ASCII: a non-ASCII host is
kept in its IDNA (`xn--`) form, and an address whose host carries invisible, bidi
or other control characters, or ends in a dot, is refused, so the approval window
always shows the host the browser will report.

Operators remove a site from the ScanLink tray menu (**Linked Websites → Unlink**).
IT can allow sites without the window by listing them in `cors_origins` in
ScanLink's `config.json`; ScanLink ignores `"*"` there.

## How a scan connects

`window.DluxScan.scan()` (from `scan_button.js`) is the one scan routine: file
fields and the PDF editor both call it. It drives the `window.ScanLink` client
(`dlux/static/dlux/helpers/scanlink/js/main.js`), which talks to the helper at
`https://localhost:5443` and `http://localhost:5000`.

For every scan, `ScanLink.startScan()`:

1. Checks `GET /health`, first on the transport that last answered, then on the
   other one. Each attempt, including its response body, has a three-second
   timeout. Only a JSON answer with `"status": "ok"` counts as ScanLink. When
   ScanLink answers only on HTTP :5000, the client logs a console warning: plain
   HTTP on localhost has no per-user identity, so on a shared computer another
   user's program could answer on that port.
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
the HTTPS/HTTP fallback, and every request has a deadline, body included: a status
read 10 seconds, the result 60 seconds, the scan POST 15 seconds (then
`scan_request_uncertain`), `POST /link` 135 seconds. A slow status answer is
retried; when ScanLink has not answered for 30 seconds the scan ends with
`helper_stalled`. The result must start with `%PDF-`; anything else ends the scan
with `invalid_result` and never reaches the file field.

File fields and the PDF editor share the translated messages in
`dlux/helpers/scanlink/scan_messages.html`. The file widget passes the active
language's strings table to it; rendered without one, it emits no attributes and
`scan_button.js` reads `window.DLUX_STRINGS` instead.

The page waits up to 11 minutes for a scan, longer than ScanLink's own job deadline
(10 minutes plus 15 s), so a slow scan ends with ScanLink's reason rather than the
page giving up while the scanner keeps going. ScanLink's error codes are shown
translated:

| Code | Message |
|---|---|
| `no_pages_scanned` | The scanner returned no pages; check the paper. |
| `acquire_failed` | The scanner stopped before the scan finished. |
| `scan_worker_crashed` | ScanLink's scanning process stopped; try again, then restart ScanLink. |
| `origin_not_allowed` | ScanLink has not allowed this site; scan again and choose Allow in its window. |
| `link_declined`, `link_timeout`, `link_pending` | The operator chose Don't allow, did not answer, or another site's window is open. |
| `link_rate_limited` | ScanLink asked about this site a moment ago; wait a few minutes. |
| `acquire_timeout`, `scan_timeout`, `scan_idle_timeout` | The scan took too long. |
| `helper_stalled` | ScanLink stopped answering; check its tray app, the scanner dialog or the driver. |
| `job_not_found`, `result_unavailable` | ScanLink restarted or the scan was lost; scan again. |
| `invalid_result` | ScanLink did not return a PDF; scan again, then restart ScanLink. |
| Any other code | The scan could not be completed. |

The page never shows ScanLink's own message: it is English, can carry exception
details or file paths, and comes from whatever answers on the port.

On the helper side, ScanLink keeps a job in `generating_pdf` until the child
process exits and the PDF is stored, and enforces the parent scan deadline even
while progress keeps arriving. It rejects malformed scan bodies before queueing
hardware work, and keeps a consumed job's metadata until its TTL so a repeated
result download gets the same single-use answer.

## Compatible versions

The client keeps health, status and result compatibility with ScanLink 0.7.4 or
later. ScanLink 0.7.4 does not report certificate setup progress, so the
installer panel shows no setup guidance for it. Releases before ScanLink 0.8.0
allow every website and have no `POST /link`; the page scans with them unchanged.

ScanLink 0.8.0 or later needs DjangoLux 1.16.0 or later to scan: an older page
cannot link the site and reports ScanLink as not running. Publish its installer
only on deployments that run DjangoLux 1.16.0 or later.

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
