"""The package suite resolves no hostnames.

Generated stacks reach their services by Compose name (``smtp-relay``, ``ocr``),
and the code under test reaches for them as a stack would: the System Settings
form probes the SMTP relay every time it is built. Outside a stack those names do
not exist, yet each lookup still went to the machine's resolver, and the probe's
socket timeout does not cover name resolution. When a CI runner's resolver stopped
answering, every lookup waited out glibc's default (5 s, two attempts) and the
suite, which builds that form hundreds of times, crawled for hours.

``dlux.tests.settings`` installs this: every hostname except ``localhost`` fails at
once with ``EAI_NONAME``, the answer a stack without that service gives. IP
literals pass through, so loopback servers in tests keep working.
"""

import ipaddress
import socket

_real_getaddrinfo = socket.getaddrinfo


def needs_dns(host):
    """Whether resolving ``host`` would ask a name server."""
    if host is None:
        return False
    if isinstance(host, bytes):
        host = host.decode('ascii', 'replace')
    name = str(host).strip().rstrip('.').lower()
    if name in ('', 'localhost'):
        return False
    try:
        ipaddress.ip_address(name.split('%', 1)[0])
    except ValueError:
        return True
    return False


def getaddrinfo(host, *args, **kwargs):
    if needs_dns(host):
        raise socket.gaierror(socket.EAI_NONAME, f'{host}: the package test suite does not use DNS')
    return _real_getaddrinfo(host, *args, **kwargs)


def install():
    socket.getaddrinfo = getaddrinfo
