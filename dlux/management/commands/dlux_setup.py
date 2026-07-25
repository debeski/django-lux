# dlux/management/commands/dlux_setup.py
"""
Management command for initial dlux package setup.
Runs migrations and performs initial configuration.
"""
import ast
import importlib
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management import call_command


DLUX_SETTINGS_BLOCK = """
# DjangoLux integration
from dlux.utils import dlux_settings
dlux_settings(globals())
""".strip()


class Command(BaseCommand):
    help = 'Initial setup for dlux package - runs migrations and validates configuration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-check',
            action='store_true',
            help='Skip configuration validation after setup',
        )
        parser.add_argument(
            '--no-migrate',
            action='store_true',
            help='Skip running migrations',
        )
        parser.add_argument(
            '--skip-configure',
            action='store_true',
            help='Skip appending the recommended dlux settings helper to the active project settings file',
        )

    def _get_settings_file(self):
        module_name = getattr(settings, "SETTINGS_MODULE", None)
        if not module_name:
            return None
        module = importlib.import_module(module_name)
        module_file = getattr(module, "__file__", None)
        return Path(module_file).resolve() if module_file else None

    @staticmethod
    def _settings_block_present(contents):
        """Return True if the dlux settings helper is already wired up.

        Parses the AST and checks whether ``dlux_settings`` is imported from
        ``dlux.utils`` *and* called, rather than matching a literal import line.
        This recognizes every valid import style — combined
        (``from dlux.utils import get_secret, dlux_settings``), reordered,
        aliased (``... as ds``), or multi-line — so the block is never appended
        a second time when it is already present (e.g. in a scaffolded project,
        whose settings.py imports ``get_secret, dlux_settings`` together).
        """
        try:
            tree = ast.parse(contents)
        except SyntaxError:
            # Unparseable settings — fall back to a conservative literal check.
            return "dlux_settings" in contents and "dlux_settings(globals())" in contents

        bound_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "dlux.utils":
                for alias in node.names:
                    if alias.name == "dlux_settings":
                        bound_names.add(alias.asname or alias.name)
        if not bound_names:
            return False
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in bound_names
            ):
                return True
        return False

    def _ensure_settings_block(self):
        settings_file = self._get_settings_file()
        if not settings_file or not settings_file.exists():
            raise RuntimeError("Could not resolve the active Django settings.py file")

        contents = settings_file.read_text(encoding="utf-8")
        if self._settings_block_present(contents):
            return settings_file, False

        suffix = "" if contents.endswith("\n") else "\n"
        settings_file.write_text(
            f"{contents}{suffix}\n{DLUX_SETTINGS_BLOCK}\n",
            encoding="utf-8",
        )
        return settings_file, True

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('\n📦 DjangoLux Setup\n'))
        self.stdout.write('=' * 40 + '\n')

        if not options['skip_configure']:
            self.stdout.write('\n🛠 Ensuring settings.py includes the DjangoLux helper...\n')
            try:
                settings_file, changed = self._ensure_settings_block()
                status = 'appended' if changed else 'already present'
                self.stdout.write(
                    self.style.SUCCESS(f'   ✓ Settings helper {status}: {settings_file}\n')
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'   ✗ Settings configuration failed: {e}\n'))
                return

        # Step 1: Create migrations if needed
        if not options['no_migrate']:
            self.stdout.write('\n🔄 Creating migrations for dlux...\n')
            try:
                call_command('makemigrations', 'dlux', verbosity=1)
                self.stdout.write(self.style.SUCCESS('   ✓ Migrations created\n'))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'   ⚠ Migration creation: {e}\n'))

            # Step 2: Run migrations
            self.stdout.write('\n🔄 Running migrations...\n')
            try:
                call_command('migrate', 'dlux', verbosity=1)
                self.stdout.write(self.style.SUCCESS('   ✓ Migrations applied\n'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'   ✗ Migration failed: {e}\n'))
                return

        # Step 3: Run configuration check
        if not options['skip_check']:
            self.stdout.write('\n')
            # dlux_doctor sys.exit()s with its status code (for CLI/CI); swallow
            # that here so a non-zero doctor result does not abort setup.
            try:
                call_command('dlux_doctor')
            except SystemExit:
                pass

        self.stdout.write('\n' + '=' * 40)
        self.stdout.write(self.style.SUCCESS('\n✅ DjangoLux setup complete!\n'))
