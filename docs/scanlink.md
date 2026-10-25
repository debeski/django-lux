# ScanLink workstation setup

Enable ScanLink in System Settings → Extra Features, then publish the Windows
installer through Options → ScanLink. Operators download the installer from the
project they use, install it, open ScanLink, and approve any Windows or browser
prompt. They do not run commands or import certificates.

## Compatible versions

This unreleased DjangoLux 1.15.1b1 patch pairs with ScanLink 0.7.5. It retains
health/status/result compatibility with ScanLink 0.7.4; older helpers do not
report certificate setup progress.

## Automatic secure connection

ScanLink 0.7.5 starts HTTP on 127.0.0.1:5000, then provisions HTTPS on
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
