# ScanLink workstation setup

Enable ScanLink in System Settings → Extra Features, then publish the Windows
installer through Options → ScanLink. Operators download the installer from the
project they use, install it, open ScanLink, and approve any Windows or browser
prompt. They do not run commands or import certificates.

## Stress-test fixes

DjangoLux 1.15.1b2 and ScanLink 0.8.0b1 are published betas. The browser client
checks health before every scan and sends the scan POST once, to the transport
that just answered. If HTTPS stops answering (for example after a ScanLink
restart whose certificate setup failed), the next scan uses HTTP :5000; if
ScanLink is closed, the scan reports `helper_unavailable` (or `insecure_origin`)
without posting. If the request or accepted response body loses its connection,
`scan_request_uncertain` asks the operator to check ScanLink before starting
another scan. File fields and the PDF editor share English/Arabic guidance.
Health/status reads retain HTTP/HTTPS fallback; old helpers remain supported.

ScanLink 0.8.0b1 keeps a job in `generating_pdf` until the child exits and the PDF
is stored, enforces the parent scan deadline despite ongoing progress, rejects
malformed public/protocol scan bodies before queueing, and retains consumed-job
metadata until its TTL for consistent single-use result responses.

## Compatible versions

The current pair is ScanLink 0.8.0b2 with the next DjangoLux release after
1.15.2b1 (unreleased): both clients health-check before every scan POST, and the
paired suite (`dlux/tests/fixtures/scanlink/scenarios.mjs`, run with ScanLink's
`static/scanlink.js` as the second argument) passes 34/34 against both. ScanLink
0.8.0b2 keeps the 0.8.0b1 HTTP protocol, so DjangoLux 1.15.1b2 through 1.15.2b1
(paired with 0.8.0b1) still work with it; their file-field and PDF-editor scans
already ran a health check before each scan, so only direct
`window.ScanLink.startScan()` callers could keep a stale transport. The previous
DjangoLux 1.15.1b1 beta pairs with ScanLink 0.7.5b1. The client retains
health/status/result compatibility with ScanLink 0.7.4; older helpers do not
report certificate setup progress.

## Automatic secure connection

ScanLink 0.7.5b1 starts HTTP on 127.0.0.1:5000, then provisions HTTPS on
127.0.0.1:5443 in its server thread. A per-user self-signed server certificate
covers localhost, 127.0.0.1 and ::1. ScanLink installs that specific certificate
in the current Windows user's trusted roots; it does not install a general
certificate authority or change machine-wide trust. The private key is encrypted
with a random password protected by Windows DPAPI. Nothing is downloaded during
setup. Healthy launches reuse the identity, repair missing trust, and renew
within 30 days of expiry; hourly checks also cover long-running sessions.

The panel reads optional `/health.https_setup` values `preparing`, `ready`, and
`failed`. While preparing it checks again automatically for up to 20 cycles;
existing HTTP scanning remains available. A setup failure offers Retry in the
ScanLink app; its tray also has **Retry secure connection setup**. Organization
policies may require support to approve trust changes. Browsers may require a
local-device permission or reopening the page after trust changes. ScanLink
cannot grant browser permissions or override an enterprise browser trust policy.

## Browser connection failures

Both the shared scan routine and the installer panel try HTTPS followed by
HTTP loopback. Each health attempt, including its response body, has a
three-second timeout. HTTP loopback is eligible from an HTTPS page; the browser
still enforces CORS, CSP, local network permission and enterprise policy.

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

English and Arabic guidance is shared by file-field and PDF-editor scanning.
No endpoint or browser security policy is weakened by this patch.

## Beta distribution

Publish the `0.7.5b1` x64/x86 installers through Options → ScanLink. Upload
validation and version ordering accept beta and RC suffixes: beta < RC < stable
for the same numeric release, while a newer release beta outranks an older
stable. Only active installer rows are advertised; enabling a beta on a testbed
is explicit. The DjangoLux patch allows inline installation only on images
already baked with >=1.15.0b1; older images still require rebuilding.

## Server preparation and acceptance

The reverse proxy must accept the installer upload size. The generated Caddy
configuration defaults to 10 MB; the 0.7.5b1 installers are about 28–31 MB.
Set the existing `CADDY_MAX_SIZE` environment value above the larger installer
plus multipart overhead (64MB was accepted on the development testbed).
This is a deployment setting for the operator publishing installers.

Projects using the PDF editor must install `django-lux[pdf]`; its optional
`pypdf` dependency is needed to assemble and save scanned pages. The ScanLink
file-field button does not require the PDF editor to be enabled.

Published-pair acceptance on 2026-10-25 verified Windows x64/x86 first-launch
consent, normally trusted HTTPS, 120 HTTPS requests per architecture and restart
reuse. The development testbed on port 8097 verified the published DjangoLux
wheel's 694 package files, rollback/reapply through Composer, real installer
upload/download checksums, file-field scanning, PDF append/save, Arabic error
messages, busy/disconnect handling and concurrent request loads. Local scanner
endpoints were simulated; real scanner hardware remains a manual acceptance
step.

## Published stress-fix pair acceptance

On 2026-10-26, the published 1.15.1b2/0.8.0b1 pair passed development-testbed
acceptance. Composer installed the PyPI wheel after a full database/media backup;
all 694 files matched the candidate and active web/Celery packages. Published
browser assets/templates passed file-field scanning, PDF append/save/download,
Arabic errors, 300 health checks, 30 scans, 20-way contention and reconnect. A lost
accepted response produced one POST, translated guidance and a retrievable PDF.
Installer hashes and 100 manifest checks passed; anonymous access was denied.
Doctor reported no errors.

Only the TWAIN child was simulated locally; the worker and API were real. No
frontend/template overrides were used in the final run. Native x64/x86 release
gates separately verified certificate consent, 120 trusted HTTPS requests per
architecture and restart identity reuse. Physical scanner and native browser/
enterprise-policy acceptance remain manual.
