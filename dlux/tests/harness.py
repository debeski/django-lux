import os


def setup_test_environment():
    """Configure Django for package-local tests when run outside manage.py."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dlux.tests.settings')

    import django
    from django.apps import apps

    if not apps.ready:
        django.setup()
