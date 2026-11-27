"""Internal SMTP relay — ``python -m dlux.smtp_relay``.

Generated projects put the web and worker containers on an ``internal: true``
network with no route off the host. This process is the one component that sits on
both that network and an egress one: the app hands it mail in plaintext on
``smtp-relay:1025`` and it makes the real provider connection.

It ships inside dlux rather than as a per-project ``tools/smtp_relay.py`` because
every fix to it — timeout pairing, failure reporting, secret handling — otherwise
had to be hand-copied into each project that had already been scaffolded, which in
practice meant projects silently ran years-old copies. Same reasoning that moved the
runtime supervisor into ``dlux.updater.supervisor``.

Configuration comes from the Dlux UI (``SystemSettings.email_config``) when relay
transport is selected with an encrypted-database secret, and from ``SMTP_RELAY_*``
environment variables otherwise. The UI's timeout applies either way. Nothing here
is project-specific: the settings module is read from ``DJANGO_SETTINGS_MODULE``,
which the container already sets.

The provider's certificate is verified on both routes: it must chain to a system
CA or to one in ``SMTP_RELAY_CA_FILE``, and name the host. ``SMTP_RELAY_TLS_VERIFY=False``
(environment route) or the Email step's switch (database route) turns that off.

The encryption rule, step tracking and failure codes live in
``dlux.smtp_session``, which the web process shares.
"""

import asyncio
import os
import smtplib
import socket
import sys
import threading

from dlux.smtp_session import (  # noqa: F401 — re-exported for the relay's callers
    DEFAULT_UPSTREAM_PORT,
    IMPLICIT_TLS_PORT,
    RELAY_GREETING,
    SMTPStepError,
    STEP_AUTH,
    STEP_CONFIG,
    STEP_CONNECT,
    STEP_GREETING,
    STEP_SEND,
    STEP_TLS,
    StagedSMTP,
    StagedSMTP_SSL,
    StepTracker,
    _coerce_bool,
    _env,
    _env_int,
    env_ca_file,
    env_flag,
    env_upstream_config,
    failure_hint,
    failure_reason,
    parse_failure_reply,
    resolve_encryption,
    server_detail,
    step_error,
    tls_context,
)

# Bind address for the plaintext listener the app talks to. Never exposed off the
# internal network — it deliberately speaks no TLS and requires no auth, because
# the only thing that can reach it is the app itself.
DEFAULT_LISTEN_HOST = "0.0.0.0"
DEFAULT_LISTEN_PORT = 1025
DEFAULT_MAX_MESSAGE_BYTES = 10 * 1024 * 1024
# Must stay BELOW dlux's relay-transport client timeout
# (dlux.utils.mail.DLUX_SMTP_RELAY_CLIENT_TIMEOUT). Delivery is two hops and only
# this process can see why the provider hop failed; if the app gives up first it
# reports a bare "timed out" and the reason never reaches the operator. Losing the
# race on purpose is what lets the 451 below carry the real cause. Sized for a slow
# upstream: servers that scan mail in-line often answer connect/EHLO/AUTH instantly
# and then take 30-60s on DATA.
DEFAULT_UPSTREAM_TIMEOUT = 60
# Longest SMTP line accepted, commands and message body alike. RFC 5321 allows
# 1000 octets; real mail carries longer unwrapped lines, so the cap only stops a
# client that never sends a line end.
DEFAULT_MAX_LINE_BYTES = 1024 * 1024
# RFC 5321 §4.5.3.2: a server waits at least five minutes for the next command.
DEFAULT_IDLE_TIMEOUT = 300
DEFAULT_MAX_CONNECTIONS = 100

_active_connections = 0


def listen_address():
    return _env("SMTP_RELAY_LISTEN_HOST", DEFAULT_LISTEN_HOST), _env_int(
        "SMTP_RELAY_LISTEN_PORT", DEFAULT_LISTEN_PORT
    )


def max_message_bytes():
    return _env_int("SMTP_RELAY_MAX_MESSAGE_BYTES", DEFAULT_MAX_MESSAGE_BYTES)


def upstream_timeout():
    return _env_int("SMTP_RELAY_UPSTREAM_TIMEOUT", DEFAULT_UPSTREAM_TIMEOUT)


def max_line_bytes():
    return max(_env_int("SMTP_RELAY_MAX_LINE_BYTES", DEFAULT_MAX_LINE_BYTES), 1024)


def idle_timeout():
    return max(_env_int("SMTP_RELAY_IDLE_TIMEOUT", DEFAULT_IDLE_TIMEOUT), 1)


def max_connections():
    return max(_env_int("SMTP_RELAY_MAX_CONNECTIONS", DEFAULT_MAX_CONNECTIONS), 1)


def stored_email_config():
    """The normalized ``email_config`` from Dlux System Settings, or ``None``.

    The relay runs in the project image, so it shares the app's Django settings,
    database and secret key — the last of which is what lets it decrypt the stored
    SMTP password.

    Each read runs on a pool thread that keeps its database connection between
    sends, with no request cycle to retire it. A database restart leaves that
    connection closed, so the read is bracketed by ``close_old_connections()``
    and the thread's connection is closed afterwards; a read that still fails
    on a dead connection is retried once on a fresh one.
    """
    try:
        import django

        if not os.getenv("DJANGO_SETTINGS_MODULE"):
            raise RuntimeError("DJANGO_SETTINGS_MODULE is not set")
        django.setup()

        from django.db import Error as DatabaseError, close_old_connections, connection

        from dlux.models import SystemSettings
        from dlux.utils import normalize_email_config

        try:
            for attempt in (1, 2):
                close_old_connections()
                try:
                    return normalize_email_config(SystemSettings.load().email_config)
                except DatabaseError:
                    connection.close()
                    if attempt == 2:
                        raise
        finally:
            connection.close()
    except Exception as exc:
        print(
            f"SMTP relay could not read Dlux UI config, using env fallback: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return None


def django_upstream_config(email_config=None):
    """UI-managed relay settings from Dlux System Settings, or ``None``.

    Returns ``None`` (falling back to the environment) unless relay transport is
    selected with an encrypted-database secret.
    """
    if email_config is None:
        email_config = stored_email_config()
    if not email_config:
        return None
    if email_config.get("transport") != "relay":
        return None
    if email_config.get("secret_storage") != "encrypted_db":
        return None
    try:
        from dlux.utils import decrypt_email_secret

        password = decrypt_email_secret(email_config.get("encrypted_password", ""))
    except Exception as exc:
        print(f"SMTP relay could not decrypt the stored password: {exc}", file=sys.stderr, flush=True)
        password = ""
    return {
        "host": email_config.get("host", ""),
        "port": int(email_config.get("port") or DEFAULT_UPSTREAM_PORT),
        "use_tls": bool(email_config.get("use_tls", True)),
        "use_ssl": bool(email_config.get("use_ssl", False)),
        "encryption_derived": False,
        "username": email_config.get("username", ""),
        "password": password,
        "tls_verify": email_config.get("tls_verify", True) is not False,
        "ca_file": env_ca_file(),
        "timeout": int(email_config.get("timeout") or 0),
        "source": "database",
    }


def upstream_config():
    """Provider settings for one delivery: the UI's, else this container's environment.

    The UI timeout applies to the environment route too. It is not a secret, and
    the app waits for the relay on that same number, so ignoring it left every
    environment-configured send capped at the relay's own default.
    """
    email_config = stored_email_config()
    config = django_upstream_config(email_config) or env_upstream_config()
    if email_config and email_config.get("transport") == "relay" and not config.get("timeout"):
        config["timeout"] = int(email_config.get("timeout") or 0)
    return config


def parse_address(command):
    value = command.split(":", 1)[1].strip() if ":" in command else ""
    if value.startswith("<") and ">" in value:
        return value[1:value.index(">")].strip()
    parts = value.split()
    return parts[0].strip() if parts else ""


def deliver(mail_from, recipients, message_bytes):
    upstream = upstream_config()
    host = upstream.get("host", "")
    port = int(upstream.get("port") or DEFAULT_UPSTREAM_PORT)
    username = upstream.get("username", "")
    password = upstream.get("password", "")
    use_ssl = bool(upstream.get("use_ssl"))
    use_tls = bool(upstream.get("use_tls")) and not use_ssl
    if not host:
        raise SMTPStepError(STEP_CONFIG, "missing_host", detail="SMTP_RELAY_HOST is not configured")
    if not mail_from:
        raise RuntimeError("MAIL FROM is missing")
    if not recipients:
        raise RuntimeError("RCPT TO is missing")

    # A timeout set in the UI wins over the environment, so an operator can widen
    # it for a slow provider without editing compose and recreating the service.
    timeout = int(upstream.get("timeout") or 0) or upstream_timeout()
    context = None
    if use_ssl or use_tls:
        context = _provider_tls_context(upstream, host, port, use_tls, use_ssl)
    tracker = StepTracker()
    smtp = None
    # ``timeout`` bounds the whole delivery, not each step: a provider answering
    # every step just inside a per-step timeout would otherwise keep going after
    # the app stopped waiting (the app waits ``timeout`` plus headroom), and the
    # app's retry would send the mail twice.
    deadline = _DeliveryDeadline(timeout)
    try:
        if use_ssl:
            smtp = StagedSMTP_SSL(host, port, timeout=timeout, context=context, dlux_tracker=tracker)
        else:
            smtp = StagedSMTP(host, port, timeout=timeout, dlux_tracker=tracker)
        deadline.watch(smtp)
        smtp.ehlo()
        if use_tls:
            smtp.starttls(context=context)
            smtp.ehlo()
        if username or password:
            smtp.login(username, password)
        smtp.sendmail(mail_from, recipients, message_bytes)
    except Exception as exc:
        deadline.cancel()
        # No QUIT after a failure: on a stalled server it waits a whole second
        # timeout, and the app stops listening before the reason arrives.
        if smtp is not None:
            smtp.close()
        if deadline.expired:
            exc = TimeoutError(f"the provider did not finish the delivery within {timeout} seconds")
        raise step_error(
            exc, tracker.step, host=host, port=port, use_tls=use_tls, use_ssl=use_ssl, timeout=timeout,
        ) from exc
    deadline.cancel()
    try:
        smtp.quit()
    except (OSError, smtplib.SMTPException):
        smtp.close()


class _DeliveryDeadline:
    """Shut the provider socket down once a delivery's total time is used up.

    Shutting the socket down wakes the step blocked on it with an error, which
    ``deliver`` reports as a timeout of the step it reached.
    """

    def __init__(self, seconds):
        self.expired = False
        self._smtp = None
        self._timer = threading.Timer(max(float(seconds), 0.1), self._expire)
        self._timer.daemon = True
        self._timer.start()

    def watch(self, smtp):
        self._smtp = smtp
        if self.expired:
            self._expire()

    def _expire(self):
        self.expired = True
        sock = getattr(self._smtp, "sock", None)
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def cancel(self):
        self._timer.cancel()


def _provider_tls_context(upstream, host, port, use_tls, use_ssl):
    """The verifying context for this delivery; logs every send made without one."""
    verify = upstream.get("tls_verify", True) is not False
    ca_file = upstream.get("ca_file", "")
    try:
        context = tls_context(verify, ca_file)
    except OSError as exc:
        raise SMTPStepError(
            STEP_CONFIG, "ca_file", host=host, port=port, use_tls=use_tls, use_ssl=use_ssl,
            detail=f"SMTP_RELAY_CA_FILE {ca_file}: {server_detail(exc)}",
        ) from exc
    if not verify:
        switch = "the Email step" if upstream.get("source") == "database" else "SMTP_RELAY_TLS_VERIFY=False"
        print(
            f"SMTP relay: certificate verification is off for {host}:{port} ({switch}); "
            "the provider's identity is not checked before signing in",
            file=sys.stderr,
            flush=True,
        )
    return context


def smtp_reason(exc):
    """One-line, length-capped failure reason safe to put in an SMTP reply.

    A reply line cannot contain CR/LF and must stay short, so the exception text is
    folded and truncated. Credentials are never part of smtplib's exception text —
    only the server's own response — so this does not leak the relay password.
    """
    reason = " ".join(str(exc).split()) or exc.__class__.__name__
    return reason[:180]


async def _send(writer, line):
    writer.write((line + "\r\n").encode("utf-8"))
    await writer.drain()


class _LineTooLong(Exception):
    pass


class _IdleTimeout(Exception):
    pass


async def _readline(reader, timeout=None):
    """One line, or ``_LineTooLong`` / ``_IdleTimeout`` instead of a traceback.

    ``StreamReader.readline`` raises ``ValueError`` for a line over the reader's
    limit, after dropping what it buffered.
    """
    try:
        return await asyncio.wait_for(reader.readline(), timeout or idle_timeout())
    except asyncio.TimeoutError as exc:
        raise _IdleTimeout() from exc
    except (ValueError, asyncio.LimitOverrunError) as exc:
        raise _LineTooLong() from exc


async def handle_client(reader, writer):
    global _active_connections
    peer = writer.get_extra_info("peername")
    _active_connections += 1
    try:
        if _active_connections > max_connections():
            await _send(writer, "421 Too many connections, try again later")
            return
        await _converse(reader, writer, peer)
    except _LineTooLong:
        await _send_quietly(writer, "500 Line too long")
    except _IdleTimeout:
        await _send_quietly(writer, "421 Idle timeout, closing connection")
    except (ConnectionError, asyncio.IncompleteReadError):
        # A health check or reachability probe that hangs up without QUIT is
        # routine, not a fault worth a traceback.
        pass
    finally:
        _active_connections -= 1
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass


async def _send_quietly(writer, line):
    try:
        await _send(writer, line)
    except (ConnectionError, OSError):
        pass


async def _read_data(reader, size_limit):
    """The DATA payload, read to its terminator: ``(chunks, oversized, terminated)``.

    A line over the line limit marks the message oversized and reading goes on,
    so the session stays in step with the client.
    """
    chunks = []
    total = 0
    oversized = False
    while True:
        try:
            line = await _readline(reader)
        except _LineTooLong:
            oversized = True
            chunks = []
            continue
        if not line:
            return chunks, oversized, False
        if line in {b".\r\n", b".\n"}:
            return chunks, oversized, True
        # Undo dot-stuffing (RFC 5321 §4.5.2) before the body is forwarded.
        if line.startswith(b".."):
            line = line[1:]
        total += len(line)
        if total > size_limit:
            # Keep reading to the terminator, or the rest of the body would be
            # read back as commands.
            oversized = True
            chunks = []
            continue
        chunks.append(line)


async def _converse(reader, writer, peer):
    size_limit = max_message_bytes()
    mail_from = ""
    recipients = []

    await _send(writer, f"220 {RELAY_GREETING}")

    while not reader.at_eof():
        raw = await _readline(reader)
        if not raw:
            break
        command = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        upper = command.upper()

        if upper.startswith(("EHLO", "HELO")):
            await _send(writer, "250-dlux-smtp-relay")
            await _send(writer, f"250 SIZE {size_limit}")
        elif upper.startswith("MAIL FROM:"):
            mail_from = parse_address(command)
            recipients = []
            await _send(writer, "250 OK")
        elif upper.startswith("RCPT TO:"):
            recipient = parse_address(command)
            if recipient:
                recipients.append(recipient)
            await _send(writer, "250 OK")
        elif upper == "RSET":
            mail_from = ""
            recipients = []
            await _send(writer, "250 OK")
        elif upper == "NOOP":
            await _send(writer, "250 OK")
        elif upper == "DATA":
            await _send(writer, "354 End data with <CR><LF>.<CR><LF>")
            chunks, oversized, terminated = await _read_data(reader, size_limit)
            if not terminated:
                break
            if oversized:
                await _send(writer, "552 Message exceeds configured size limit")
                continue
            try:
                # Blocking smtplib work belongs off the event loop, or one slow
                # upstream would stall every other connection.
                await asyncio.to_thread(deliver, mail_from, recipients, b"".join(chunks))
                await _send(writer, "250 Message accepted")
            except Exception as exc:
                print(
                    f"SMTP relay delivery failed for {peer}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                await _send(writer, f"451 Relay delivery failed: {smtp_reason(exc)}")
        elif upper == "QUIT":
            await _send(writer, "221 Bye")
            break
        else:
            await _send(writer, "502 Command not implemented")


async def serve():
    host, port = listen_address()
    server = await asyncio.start_server(handle_client, host, port, limit=max_line_bytes())
    sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    print(f"Dlux SMTP relay listening on {sockets}", flush=True)
    async with server:
        await server.serve_forever()


def main():
    asyncio.run(serve())


if __name__ == "__main__":
    main()
