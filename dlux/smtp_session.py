"""SMTP session helpers shared by the internal relay and the app.

Standard library only, and no ``dlux`` imports: ``dlux.smtp_relay`` runs as its
own process, and ``dlux.utils.mail`` must not import the relay module, which
reaches back into ``dlux.utils`` at call time.

- ``resolve_encryption``: SSL on port 465, STARTTLS otherwise, unless set.
- ``env_upstream_config``: the provider in this process's ``SMTP_RELAY_*``.
- ``tls_context``: the verifying TLS context for a provider connection.
- ``StagedSMTP``/``StagedSMTP_SSL``: smtplib clients that record which step
  (connect, TLS, greeting, auth, send) a session is on.
- ``SMTPStepError``/``failure_reason``/``failure_hint``/``parse_failure_reply``:
  a failure as stable codes, carried through the relay's 451 reply.
"""

import os
import re
import smtplib
import socket
import ssl

DEFAULT_UPSTREAM_PORT = 587
# Implicit TLS submission (RFC 8314). Every other port starts in plaintext and
# upgrades with STARTTLS.
IMPLICIT_TLS_PORT = 465

# The SMTP step a delivery was on when it failed.
STEP_CONFIG = "config"
STEP_CONNECT = "connect"
STEP_TLS = "tls"
STEP_GREETING = "greeting"
STEP_AUTH = "auth"
STEP_SEND = "send"


def _env(name, default=None):
    value = os.getenv(name)
    return default if value is None or value == "" else value


def _env_int(name, default):
    try:
        return int(_env(name, default))
    except (TypeError, ValueError):
        return default


def _coerce_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def env_flag(value):
    """True/False for a set flag, ``None`` when the variable is unset or empty."""
    if value is None or str(value).strip() == "":
        return None
    return _coerce_bool(value)


def resolve_encryption(port, use_tls=None, use_ssl=None):
    """``(use_tls, use_ssl, derived)`` for one provider connection.

    An unset SSL flag follows the port: 465 is implicit TLS, every other port is
    plaintext that upgrades with STARTTLS unless STARTTLS is switched off. A set
    flag always wins. ``derived`` says the SSL choice came from the port.
    """
    derived = use_ssl is None
    if use_ssl is None:
        try:
            use_ssl = int(port or 0) == IMPLICIT_TLS_PORT
        except (TypeError, ValueError):
            use_ssl = False
    if use_tls is None:
        use_tls = True
    if use_ssl:
        use_tls = False
    return bool(use_tls), bool(use_ssl), derived


def env_ca_file():
    """``SMTP_RELAY_CA_FILE``: extra CA certificates the relay trusts, on either route."""
    return _env("SMTP_RELAY_CA_FILE", "")


def env_upstream_config():
    """The provider settings in this container's ``SMTP_RELAY_*`` variables."""
    port = _env_int("SMTP_RELAY_PORT", DEFAULT_UPSTREAM_PORT)
    use_tls, use_ssl, derived = resolve_encryption(
        port, env_flag(os.getenv("SMTP_RELAY_USE_TLS")), env_flag(os.getenv("SMTP_RELAY_USE_SSL"))
    )
    return {
        "host": _env("SMTP_RELAY_HOST", ""),
        "port": port,
        "use_tls": use_tls,
        "use_ssl": use_ssl,
        "encryption_derived": derived,
        "username": _env("SMTP_RELAY_USER", ""),
        "password": _env("SMTP_RELAY_PASSWORD", ""),
        "tls_verify": env_flag(os.getenv("SMTP_RELAY_TLS_VERIFY")) is not False,
        "ca_file": env_ca_file(),
        "source": "environment",
    }


def tls_context(verify=True, ca_file=""):
    """The TLS context for one provider connection.

    Verifying: the certificate must chain to a system CA, or to one in
    ``ca_file``, and name the host the relay dialled. smtplib's own default
    checks neither, so a relay without this signs in to whatever answers.
    ``verify=False`` is the deliberate way out; ``ca_file`` is then not read.
    A ``ca_file`` that cannot be loaded raises ``OSError`` or ``ssl.SSLError``.
    """
    context = ssl.create_default_context()
    if not verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    if ca_file:
        context.load_verify_locations(cafile=ca_file)
    return context


class StepTracker:
    """Which SMTP step a connection is on; shared with the code that opened it."""

    def __init__(self):
        self.step = STEP_CONNECT


class _StepTracking:
    """smtplib mixin that records the current step on a ``StepTracker``.

    smtplib connects inside its constructor, so a failure there leaves no object
    to ask. The tracker is handed in, and outlives the failed constructor.
    """

    def __init__(self, *args, dlux_tracker=None, **kwargs):
        self.dlux_tracker = dlux_tracker or StepTracker()
        super().__init__(*args, **kwargs)

    def _get_socket(self, host, port, timeout):
        self.dlux_tracker.step = STEP_CONNECT
        sock = smtplib.SMTP._get_socket(self, host, port, timeout)
        if isinstance(self, smtplib.SMTP_SSL):
            self.dlux_tracker.step = STEP_TLS
            sock = self.context.wrap_socket(sock, server_hostname=host)
        self.dlux_tracker.step = STEP_GREETING
        return sock

    def starttls(self, *args, **kwargs):
        self.dlux_tracker.step = STEP_TLS
        return super().starttls(*args, **kwargs)

    def login(self, *args, **kwargs):
        self.dlux_tracker.step = STEP_AUTH
        return super().login(*args, **kwargs)

    def sendmail(self, *args, **kwargs):
        self.dlux_tracker.step = STEP_SEND
        return super().sendmail(*args, **kwargs)


class StagedSMTP(_StepTracking, smtplib.SMTP):
    pass


class StagedSMTP_SSL(_StepTracking, smtplib.SMTP_SSL):
    pass


def failure_reason(exc):
    """A stable reason code for one SMTP failure."""
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "timeout"
    if isinstance(exc, socket.gaierror):
        return "dns"
    if isinstance(exc, ConnectionRefusedError):
        return "refused"
    if isinstance(exc, ssl.SSLCertVerificationError):
        return "certificate"
    if isinstance(exc, ssl.SSLError):
        return "tls"
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        # smtplib reports a read that timed out as "Connection unexpectedly
        # closed: timed out", with the timeout as the context.
        if isinstance(exc.__context__, (socket.timeout, TimeoutError)) or "timed out" in str(exc):
            return "timeout"
        return "closed"
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return "unsupported"
    if isinstance(exc, (smtplib.SMTPResponseException, smtplib.SMTPRecipientsRefused)):
        return "rejected"
    if isinstance(exc, OSError):
        return "network"
    return "error"


def failure_hint(step, reason, port, use_tls, use_ssl, *, relay=False):
    """The likeliest fix for a failure, or ``""``. Read by the app, not shown raw.

    ``relay`` marks a failure on the relay's provider hop, the one with a
    certificate switch (``tls_verify``) and CA file.
    """
    try:
        port = int(port or 0)
    except (TypeError, ValueError):
        port = 0
    if relay and step == STEP_TLS and reason == "certificate":
        return "tls_verify"
    if step == STEP_CONNECT and reason in {"timeout", "network"}:
        return "firewall"
    if step in {STEP_GREETING, STEP_TLS} and reason in {"timeout", "closed", "tls"}:
        if port == IMPLICIT_TLS_PORT and not use_ssl:
            return "implicit_tls"
        if port != IMPLICIT_TLS_PORT and use_ssl:
            return "starttls_port"
    if step == STEP_AUTH and reason == "rejected":
        return "credentials"
    return ""


def server_detail(exc):
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        refused = next(iter(exc.recipients.values()), None)
        if refused:
            code, message = refused
            return f"{code} {message.decode('utf-8', 'replace') if isinstance(message, bytes) else message}"
    code = getattr(exc, "smtp_code", None)
    message = getattr(exc, "smtp_error", None)
    if code is not None:
        if isinstance(message, bytes):
            message = message.decode("utf-8", "replace")
        return f"{code} {message or ''}".strip()
    return " ".join(str(exc).split()) or exc.__class__.__name__


class SMTPStepError(smtplib.SMTPException):
    """A provider delivery failure that names its step.

    ``str()`` starts with ``key=value`` tokens so the app can read them back out
    of the relay's one-line 451 reply and say, in the operator's language, which
    step failed and what to try.
    """

    def __init__(self, step, reason, *, host="", port=0, use_tls=False, use_ssl=False, timeout=0, detail=""):
        self.step = step
        self.reason = reason
        self.host = host
        self.port = port
        self.timeout = timeout
        self.hint = failure_hint(step, reason, port, use_tls, use_ssl, relay=True)
        self.detail = detail
        self.encryption = "ssl" if use_ssl else ("starttls" if use_tls else "none")
        super().__init__(self.reply())

    def reply(self):
        tokens = [f"step={self.step}", f"reason={self.reason}"]
        if self.hint:
            tokens.append(f"hint={self.hint}")
        if self.reason == "timeout" and self.timeout:
            tokens.append(f"seconds={int(self.timeout)}")
        target = f"{self.host}:{self.port}" if self.host else ""
        text = f"{self.step} {target} {self.encryption}: {self.detail}".replace("  ", " ")
        return " ".join(tokens) + " " + text


def step_error(exc, step, *, host, port, use_tls, use_ssl, timeout):
    reason = failure_reason(exc)
    if reason in {"tls", "certificate"}:
        step = STEP_TLS
    return SMTPStepError(
        step, reason, host=host, port=port, use_tls=use_tls, use_ssl=use_ssl,
        timeout=timeout, detail=server_detail(exc),
    )


_REPLY_TOKEN = re.compile(r"\b(step|reason|hint|seconds)=([a-z0-9_]+)")


def parse_failure_reply(text):
    """The ``step``/``reason``/``hint``/``seconds`` tokens in a relay reply, or ``{}``."""
    text = text.decode("utf-8", "replace") if isinstance(text, bytes) else str(text or "")
    if "step=" not in text:
        return {}
    return dict(_REPLY_TOKEN.findall(text))
