import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

TEST_LABELS = [
    'dlux.tests.test_models',
    'dlux.tests.test_views',
    'dlux.tests.test_api',
    'dlux.tests.test_activitylog',
    'dlux.tests.test_agent_bridge',
    'dlux.tests.test_control_link',
    'dlux.tests.test_auth_security',
    'dlux.tests.test_celery_health',
    'dlux.tests.test_context_processors',
    'dlux.tests.test_defaults_and_urls',
    'dlux.tests.test_groups',
    'dlux.tests.test_middleware',
    'dlux.tests.test_notifications',
    'dlux.tests.test_permissions_ui',
    'dlux.tests.test_registration',
    'dlux.tests.test_report_backup',
    'dlux.tests.test_scaffold',
    'dlux.tests.test_search',
    'dlux.tests.test_seed',
    'dlux.tests.test_options_layout',
    'dlux.tests.test_options_registry',
    'dlux.tests.test_settings_theme_persistence',
    'dlux.tests.test_data_reset',
    'dlux.tests.test_password_reset',
    'dlux.tests.test_dlux_setup',
    'dlux.tests.test_doctor',
    'dlux.tests.test_audit_visibility',
    'dlux.tests.test_migrator',
    'dlux.tests.test_sidebar_discovery',
    'dlux.tests.test_signals',
    'dlux.tests.test_system_registry',
    'dlux.tests.test_system_backup',
    'dlux.tests.test_tables',
    'dlux.tests.test_utils',
    'dlux.tests.test_utils_discovery',
    'dlux.tests.test_updater',
]


def run_all_tests(argv=None):
    """Run the package CI suite through Django's test runner."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dlux.tests.settings')

    from django.core.management import execute_from_command_line

    args = list(argv or sys.argv[1:])
    verbosity = []
    if not any(arg.startswith('--verbosity') or arg == '-v' for arg in args):
        verbosity = ['--verbosity=2']
    execute_from_command_line(
        [sys.argv[0], 'test', *TEST_LABELS, *verbosity, *args]
    )
    return 0


if __name__ == '__main__':
    sys.exit(run_all_tests())
