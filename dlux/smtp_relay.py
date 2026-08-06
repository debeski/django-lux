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
environment variables otherwise. Nothing here is project-specific: the settings
module is read from ``DJANGO_SETTINGS_MODULE``, which the container already sets.
"""

import asyncio
import os
import smtplib
import sys

# Bind address for the plaintext listener the app talks to. Never exposed off the
# internal network — it deliberately speaks no TLS and requires no auth, because
# the only thing that can reach it is the app itself.
DEFAULT_LISTEN_HOST = "0.0.0.0"
DEFAULT_LISTEN_PORT = 1025
DEFAULT_UPSTREAM_PORT = 587
DEFAULT_MAX_MESSAGE_BYTES = 10 * 1024 * 1024
# Must stay BELOW dlux's relay-transport client timeout
# (dlux.utils.mail.DLUX_SMTP_RELAY_CLIENT_TIMEOUT). Delivery is two hops and only
# this process can see why the provider hop failed; if the app gives up first it
# reports a bare "timed out" and the reason never reaches the operator. Losing the
# race on purpose is what lets the 451 below carry the real cause. Sized for a slow
# upstream: servers that scan mail in-line often answer connect/EHLO/AUTH instantly
# and then take 30-60s on DATA.
DEFAULT_UPSTREAM_TIMEOUT = 60


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


def listen_address():
    return _env("SMTP_RELAY_LISTEN_HOST", DEFAULT_LISTEN_HOST), _env_int(
        "SMTP_RELAY_LISTEN_PORT", DEFAULT_LISTEN_PORT
    )


def max_message_bytes():
    return _env_int("SMTP_RELAY_MAX_MESSAGE_BYTES", DEFAULT_MAX_MESSAGE_BYTES)


def upstream_timeout():
    return _env_int("SMTP_RELAY_UPSTREAM_TIMEOUT", DEFAULT_UPSTREAM_TIMEOUT)


def env_upstream_config():
    """Bootstrap/fallback configuration for deployments not using UI-managed mail."""
    return {
        "host": _env("SMTP_RELAY_HOST", ""),
        "port": _env_int("SMTP_RELAY_PORT", DEFAULT_UPSTREAM_PORT),
        "use_tls": _coerce_bool(os.getenv("SMTP_RELAY_USE_TLS"), True),
        "use_ssl": _coerce_bool(os.getenv("SMTP_RELAY_USE_SSL"), False),
        "username": _env("SMTP_RELAY_USER", ""),
        "password": _env("SMTP_RELAY_PASSWORD", ""),
    }


def django_upstream_config():
    """UI-managed relay settings from Dlux System Settings, or ``None``.

    The relay runs in the project image, so it shares the app's Django settings,
    database and secret key — the last of which is what lets it decrypt the stored
    SMTP password. Returns ``None`` (falling back to the environment) when the UI is
    not the source of truth for this deployment.
    """
    try:
        import django

        if not os.getenv("DJANGO_SETTINGS_MODULE"):
            raise RuntimeError("DJANGO_SETTINGS_MODULE is not set")
        django.setup()

        from dlux.models import SystemSettings
        from dlux.utils import decrypt_email_secret, normalize_email_config

        email_config = normalize_email_config(SystemSettings.load().email_config)
        if email_config.get("transport") != "relay":
            return None
        if email_config.get("secret_storage") != "encrypted_db":
            return None
        return {
            "host": email_config.get("host", ""),
            "port": int(email_config.get("port") or DEFAULT_UPSTREAM_PORT),
            "use_tls": bool(email_config.get("use_tls", True)),
            "use_ssl": bool(email_config.get("use_ssl", False)),
            "username": email_config.get("username", ""),
            "password": decrypt_email_secret(email_config.get("encrypted_password", "")),
            "timeout": int(email_config.get("timeout") or 0),
        }
    except Exception as exc:
        print(
            f"SMTP relay could not read Dlux UI config, using env fallback: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return None


def upstream_config():
    return django_upstream_config() or env_upstream_config()


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
    if not host:
        raise RuntimeError("SMTP_RELAY_HOST is not configured")
    if not mail_from:
        raise RuntimeError("MAIL FROM is missing")
    if not recipients:
        raise RuntimeError("RCPT TO is missing")

    # A timeout set in the UI wins over the environment, so an operator can widen
    # it for a slow provider without editing compose and recreating the service.
    timeout = int(upstream.get("timeout") or 0) or upstream_timeout()
    smtp_class = smtplib.SMTP_SSL if upstream.get("use_ssl") else smtplib.SMTP
    with smtp_class(host, port, timeout=timeout) as smtp:
        smtp.ehlo()
        if upstream.get("use_tls") and not upstream.get("use_ssl"):
            smtp.starttls()
            smtp.ehlo()
        if username or password:
            smtp.login(username, password)
        smtp.sendmail(mail_from, recipients, message_bytes)


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


async def handle_client(reader, writer):
    peer = writer.get_extra_info("peername")
    size_limit = max_message_bytes()
    mail_from = ""
    recipients = []

    await _send(writer, "220 dlux smtp relay ready")

    while not reader.at_eof():
        raw = await reader.readline()
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
            chunks = []
            total = 0
            while True:
                line = await reader.readline()
                if not line:
                    break
                if line in {b".\r\n", b".\n"}:
                    break
                # Undo dot-stuffing (RFC 5321 §4.5.2) before the body is forwarded.
                if line.startswith(b".."):
                    line = line[1:]
                total += len(line)
                if total > size_limit:
                    await _send(writer, "552 Message exceeds configured size limit")
                    chunks = []
                    break
                chunks.append(line)

            if chunks:
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

    writer.close()
    await writer.wait_closed()


async def serve():
    host, port = listen_address()
    server = await asyncio.start_server(handle_client, host, port)
    sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    print(f"Dlux SMTP relay listening on {sockets}", flush=True)
    async with server:
        await server.serve_forever()


def main():
    asyncio.run(serve())


if __name__ == "__main__":
    main()
