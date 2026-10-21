"""Isolated PostgreSQL settings for the settings-persistence CI gate."""

import os

from .settings import *  # noqa: F403

# The unrelated document fixture app has no migrations; its foreign keys cannot
# be synchronized before the migrated dlux tables on PostgreSQL.
INSTALLED_APPS = [
    app for app in INSTALLED_APPS if 'document_files_app' not in app
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ['DLUX_TEST_POSTGRES_DB'],
        'USER': os.environ['DLUX_TEST_POSTGRES_USER'],
        'PASSWORD': os.environ['DLUX_TEST_POSTGRES_PASSWORD'],
        'HOST': os.environ['DLUX_TEST_POSTGRES_HOST'],
        'PORT': os.environ.get('DLUX_TEST_POSTGRES_PORT', '5432'),
    },
}
