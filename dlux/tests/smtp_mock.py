"""A local SMTP server for mail tests: plaintext with STARTTLS, or implicit TLS.

Speaks just enough SMTP for smtplib and Django's backend: greeting, EHLO,
STARTTLS, AUTH PLAIN/LOGIN, MAIL, RCPT, DATA, QUIT. The certificate is a
throwaway self-signed one made at start, so nothing is read from or written to
disk outside a temporary directory. ``silent=True`` accepts connections and
never greets, which is what a client speaking the wrong protocol sees.
"""

import base64
import datetime
import socket
import ssl
import tempfile
import threading
from pathlib import Path


def _self_signed_context():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), critical=False)
        .sign(key, hashes.SHA256())
    )
    with tempfile.TemporaryDirectory() as tmp:
        cert_path = Path(tmp) / 'cert.pem'
        key_path = Path(tmp) / 'key.pem'
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)
    return context


class MockSMTPServer:
    def __init__(self, *, implicit_tls=False, starttls=True, username='', password='', silent=False):
        self.implicit_tls = implicit_tls
        self.offer_starttls = starttls and not implicit_tls
        self.username = username
        self.password = password
        self.silent = silent
        self.messages = []
        self.context = _self_signed_context() if (implicit_tls or starttls) else None
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(('127.0.0.1', 0))
        self._sock.listen(8)
        self.port = self._sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, name='mock-smtp', daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        try:
            socket.create_connection(('127.0.0.1', self.port), 1).close()
        except OSError:
            pass
        self._sock.close()
        self._thread.join(2)

    def _serve(self):
        while not self._stop.is_set():
            try:
                conn, _addr = self._sock.accept()
            except OSError:
                return
            if self._stop.is_set():
                conn.close()
                return
            threading.Thread(target=self._session, args=(conn,), daemon=True).start()

    def _session(self, conn):
        try:
            conn.settimeout(10)
            if self.silent:
                self._stop.wait(10)
                return
            if self.implicit_tls:
                conn = self.context.wrap_socket(conn, server_side=True)
            self._converse(conn)
        except (OSError, ssl.SSLError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _converse(self, conn):
        reader = conn.makefile('rb')
        tls_active = self.implicit_tls

        def send(line):
            conn.sendall((line + '\r\n').encode())

        send('220 mock.smtp ESMTP ready')
        authed = not self.username
        mail_from, recipients = '', []
        while True:
            raw = reader.readline()
            if not raw:
                return
            line = raw.decode('utf-8', 'replace').rstrip('\r\n')
            verb = line.split(' ', 1)[0].upper()
            if verb in {'EHLO', 'HELO'}:
                extensions = ['mock.smtp']
                if self.offer_starttls and not tls_active:
                    extensions.append('STARTTLS')
                if self.username:
                    extensions.append('AUTH PLAIN LOGIN')
                for item in extensions[:-1]:
                    send(f'250-{item}')
                send(f'250 {extensions[-1]}')
            elif verb == 'STARTTLS' and self.offer_starttls and not tls_active:
                send('220 Go ahead')
                conn = self.context.wrap_socket(conn, server_side=True)
                reader = conn.makefile('rb')
                tls_active = True
            elif verb == 'AUTH':
                parts = line.split()
                if parts[1].upper() == 'PLAIN':
                    payload = parts[2] if len(parts) > 2 else ''
                    if not payload:
                        send('334 ')
                        payload = reader.readline().decode().strip()
                    _authzid, user, secret = base64.b64decode(payload).decode().split('\0')
                else:
                    send('334 VXNlcm5hbWU6')
                    user = base64.b64decode(reader.readline().strip()).decode()
                    send('334 UGFzc3dvcmQ6')
                    secret = base64.b64decode(reader.readline().strip()).decode()
                if user == self.username and secret == self.password:
                    authed = True
                    send('235 Authentication succeeded')
                else:
                    send('535 5.7.8 Authentication credentials invalid')
            elif verb == 'MAIL':
                if not authed:
                    send('530 5.7.0 Authentication required')
                    continue
                mail_from, recipients = line.split(':', 1)[1].strip(), []
                send('250 OK')
            elif verb == 'RCPT':
                recipients.append(line.split(':', 1)[1].strip())
                send('250 OK')
            elif verb == 'DATA':
                send('354 End data with <CR><LF>.<CR><LF>')
                body = []
                while True:
                    chunk = reader.readline()
                    if not chunk or chunk in {b'.\r\n', b'.\n'}:
                        break
                    body.append(chunk)
                self.messages.append({
                    'from': mail_from, 'to': recipients, 'data': b''.join(body), 'tls': tls_active,
                })
                send('250 Queued')
            elif verb == 'RSET':
                send('250 OK')
            elif verb == 'QUIT':
                send('221 Bye')
                return
            else:
                send('502 Not implemented')
