import atexit
import shutil
import tempfile
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
SECRET_KEY = 'dlux-test-key'
DEBUG = True
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'crispy_forms',
    'crispy_bootstrap5',
    'django_filters',
    'django_tables2',
    'dlux',
]

MIDDLEWARE = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'dlux.middleware.DluxMiddleware',
]

ROOT_URLCONF = 'dlux.urls'
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'dlux.context_processors.dlux_context',
            ],
        },
    },
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    },
}

STATIC_URL = '/static/'
MEDIA_URL = '/media/'
# Default ``MEDIA_ROOT`` is the empty string, which resolves ``default_storage``
# writes (system-backup ``.dlb`` artifacts, profile pictures, etc.) relative to
# the current working directory — i.e. straight into the tracked working tree.
# Anchor it at a process-scoped temp dir so no test can persist into the repo,
# even ones that forget to ``override_settings(MEDIA_ROOT=...)``. Per-test temp
# overrides still take precedence; this is the backstop.
MEDIA_ROOT = tempfile.mkdtemp(prefix='dlux-test-media-')
atexit.register(shutil.rmtree, MEDIA_ROOT, ignore_errors=True)

# The updater tests simulate a deployment whose runtime volume exists and is
# writable, so say so explicitly. Left at the default '/opt/dlux-runtime' the
# suite's result depends on whether the runner can write to /opt — it passes as
# root in CI and fails on a developer's machine.
DLUX_UPDATE_RUNTIME_ROOT = tempfile.mkdtemp(prefix='dlux-test-runtime-')
atexit.register(shutil.rmtree, DLUX_UPDATE_RUNTIME_ROOT, ignore_errors=True)
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = True

CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
DEFAULT_FROM_EMAIL = 'security@example.com'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'dlux-test-cache',
    },
}
