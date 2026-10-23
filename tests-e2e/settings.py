"""Django settings for the local visual-regression harness.

Development-only. `prune tests-e2e` keeps it out of the wheel and sdist, and
nothing in `dlux/` imports this module.

It exists because `dlux.tests.settings` uses an in-memory SQLite database, which
dies with the process that created it — a seeding process and a server process
cannot share one. Everything else is inherited so the harness renders the same
stack the suite does.
"""
from pathlib import Path

from dlux.tests.settings import *  # noqa: F401,F403

BASE_DIR = Path(__file__).resolve().parent
ROOT_URLCONF = 'urls'
TEMPLATES = [{**TEMPLATES[0], 'DIRS': [BASE_DIR / 'templates']}]

DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': str(BASE_DIR / 'state' / 'harness.sqlite3'),
    },
}

MEDIA_ROOT = str(BASE_DIR / 'state' / 'media')

# Screenshots must be byte-identical across runs, so nothing may vary on wall
# time. The session cookie is the only such input the pages read.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365

# The email step probes the internal SMTP relay and greys out the `relay`
# transport when nothing answers. The default host `smtp-relay` resolves (or
# times out) differently per network, which made the email tests flaky. A closed
# loopback port answers "not running" immediately, on every machine.
DLUX_SMTP_RELAY_HOST = '127.0.0.1'
DLUX_SMTP_RELAY_PORT = 1
