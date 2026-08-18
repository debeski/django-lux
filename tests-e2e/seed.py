"""Build the harness database from scratch.

Idempotent by deletion: the sqlite file is dropped and rebuilt every run, so a
baseline captured last week and a comparison captured today start from identical
state. Anything that varies between runs (row ids, timestamps rendered into a
page) would otherwise show up as a phantom pixel diff.
"""
import os
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')

STATE = BASE_DIR / 'state'
USERNAME = 'visual'
PASSWORD = 'visual-harness-pw'


def main():
    if STATE.exists():
        shutil.rmtree(STATE)
    (STATE / 'media').mkdir(parents=True)

    import django
    django.setup()

    from django.core.management import call_command
    call_command('migrate', verbosity=0, interactive=False)

    from django.contrib.auth import get_user_model
    from dlux.models import SystemSettings

    User = get_user_model()
    User.objects.create_superuser(
        username=USERNAME, email='visual@example.com', password=PASSWORD,
    )

    # `DluxMiddleware` bounces every request to the setup wizard until this is
    # set, and `system_setup_view` redirects away from the wizard once it is —
    # so the two shoot phases need opposite values and cannot share a database.
    configured = '--unconfigured' not in sys.argv
    s = SystemSettings.load()
    s.is_configured = configured
    if '--disable-language-override' in sys.argv:
        s.allow_user_language_override = False
    if '--always-search' in sys.argv:
        search = dict(s.search_config or {})
        search.update({'enabled': True, 'display_mode': 'always'})
        s.search_config = search
    # ScanLink ships off; the tests that need it on ask for it explicitly, so a
    # run without the flag also proves the gate keeps everything off the page.
    extra = dict(s.extra_config or {})
    extra['scanlink'] = {'enabled': '--scanlink' in sys.argv}
    s.extra_config = extra
    s.save()

    print(
        f'seeded: {STATE / "harness.sqlite3"} '
        f'(is_configured={configured}, scanlink={"--scanlink" in sys.argv}, '
        f'language_override={"--disable-language-override" not in sys.argv}, '
        f'search_mode={"always" if "--always-search" in sys.argv else "icon"})'
    )


if __name__ == '__main__':
    main()
