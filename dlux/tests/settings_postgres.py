"""The package test settings on PostgreSQL, the database every deployed stack runs."""

import os

from .settings import *  # noqa: F403

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
