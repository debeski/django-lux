import os
from glob import glob
from io import StringIO

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command, get_commands
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Brings a deployment up to date: makemigrations (conditionally), migrate, "
        "collectstatic, then first-launch setup."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '-a', '--app',
            type=str,
            help='The main app name for initial migration check and data population logic. If not provided, all local apps are checked.'
        )
        parser.add_argument(
            '-mm', '--make-migrations',
            action='store_true',
            help='Force makemigrations for every target app, then migrate.'
        )
        parser.add_argument(
            '-nm', '--no-migrate',
            action='store_true',
            help='Skip makemigrations and migrate. collectstatic still runs.'
        )

    def is_local_app(self, app_config):
        """Check if an app is local to the project."""
        # Check if the app path starts with BASE_DIR
        return app_config.path.startswith(str(settings.BASE_DIR)) and 'site-packages' not in app_config.path

    def needs_initial_migration(self, app_config):
        """True when the app has no 0001_* migration yet.

        This is the only thing that triggers makemigrations by default. Counting
        any non-__init__ module instead treats a stray helper in migrations/ as
        proof the app is migrated, which is how apps silently never get one.
        """
        return not glob(os.path.join(app_config.path, 'migrations', '0001_*.py'))

    def unwritable_migration_dirs(self, app_configs):
        """Migration targets that makemigrations could not write to.

        Deployed images often ship the app tree read-only, where makemigrations
        dies with a bare OSError halfway through generating a set.
        """
        blocked = []
        for app_config in app_configs:
            migration_dir = os.path.join(app_config.path, 'migrations')
            probe = migration_dir if os.path.isdir(migration_dir) else app_config.path
            if not os.access(probe, os.W_OK):
                blocked.append(f"{app_config.name} ({probe})")
        return blocked

    def bootstrap_system_settings(self):
        from dlux.utils import (
            SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_APPLIED,
            SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_CONFIGURED,
            bootstrap_system_settings_config_json,
            resolve_system_settings_config_json_path,
        )

        config_path = resolve_system_settings_config_json_path()
        display_path = str(config_path or 'BASE_DIR/config.json')
        self.stdout.write("Checking first-launch System Settings configuration...")
        try:
            status, _, _ = bootstrap_system_settings_config_json(config_path)
        except ValueError as exc:
            self.stdout.write(self.style.WARNING(
                f"Invalid first-launch config at {display_path}: {exc} Manual setup remains available."
            ))
            return 'invalid'

        if status == SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_APPLIED:
            self.stdout.write(self.style.SUCCESS(
                f"Applied first-launch System Settings from {display_path}."
            ))
        elif status == SYSTEM_SETTINGS_CONFIG_BOOTSTRAP_CONFIGURED:
            self.stdout.write("System Settings are already configured; first-launch import skipped.")
        else:
            self.stdout.write(
                f"No first-launch config found at {display_path}; manual setup remains available."
            )
        return status

    def resolve_target_apps(self, specified_app):
        if specified_app:
            try:
                app_config = apps.get_app_config(specified_app)
            except LookupError:
                raise CommandError(f"App '{specified_app}' not found.")
            self.stdout.write(f"Using specified target app: {specified_app}")
            return [app_config]

        self.stdout.write("Auto-discovering local apps...")
        target_apps = sorted(
            (a for a in apps.get_app_configs() if self.is_local_app(a) and a.name != 'core'),
            key=lambda a: a.name,
        )
        if not target_apps:
            self.stdout.write(self.style.WARNING("No local apps found."))
        else:
            self.stdout.write(f"Targeting local apps: {', '.join(a.name for a in target_apps)}")
        return target_apps

    def run_schema(self, target_apps, force_mm):
        if force_mm:
            selected = list(target_apps)
            reason = "Force makemigrations requested"
            self.stdout.write(self.style.WARNING(
                "-mm writes migrations into the container filesystem; unless the app "
                "tree is bind-mounted they are lost when the container is recreated."
            ))
        else:
            selected = [a for a in target_apps if self.needs_initial_migration(a)]
            reason = "No 0001_* migration found"

        for app_config in target_apps:
            if app_config in selected:
                self.stdout.write(self.style.WARNING(
                    f"{reason} for '{app_config.name}'. Adding to makemigrations list..."
                ))
            else:
                self.stdout.write(f"Migrations found for '{app_config.name}'.")

        if selected:
            blocked = self.unwritable_migration_dirs(selected)
            if blocked:
                raise CommandError(
                    "MAKEMIGRATIONS BLOCKED: migrations directory is not writable for "
                    + ", ".join(blocked)
                    + ". Bind-mount the app source or drop -mm."
                )

            labels = [a.label for a in selected]
            self.stdout.write(f"Running makemigrations for {', '.join(labels)}...")
            try:
                # One call for the whole set. Per-app calls resolve cross-app
                # dependencies against a half-written migration graph, so a model
                # pointing at another target app's new table fails.
                call_command('makemigrations', *labels, '--noinput')
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"MAKEMIGRATIONS FAILED: {e}"))
                self.stderr.write(
                    "With --noinput Django cannot prompt, so this usually means a new "
                    "non-nullable field needs a default, or two apps changed in a way "
                    "that needs a manual merge. Run 'python manage.py makemigrations' "
                    "interactively to see the question."
                )
                raise

        self.stdout.write("Running migrate...")
        try:
            call_command('migrate', '--noinput')
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"MIGRATE FAILED: {e}"))
            self.stderr.write("Common causes: database unavailable, migration conflicts, or invalid SQL.")
            self.stderr.write("Run 'python manage.py migrate --verbosity 2' for more details.")
            raise

    def run_collectstatic(self):
        self.stdout.write("Collecting static files...")
        out = StringIO()
        try:
            call_command('collectstatic', '--noinput', '--clear', stdout=out)
            self.stdout.write(out.getvalue().splitlines()[-1] if out.getvalue() else "Static files collected.")
        except Exception as e:
            self.stdout.write(out.getvalue())
            self.stderr.write(self.style.ERROR(f"STATIC FILES COLLECTION FAILED: {e}"))
            self.stderr.write("Check that your STATIC_ROOT is configured and writable.")
            raise

    def ensure_superuser(self, warnings):
        username = 'admin'
        email = 'admin@eidc.gov.ly'
        password = os.getenv("ADMIN_PASS", "admin")

        if password == "admin":
            self.stdout.write(self.style.WARNING(
                "ADMIN_PASS not supplied — falling back to default password: 'admin'"
            ))

        try:
            User = get_user_model()
            if not User.objects.filter(username=username).exists():
                self.stdout.write("Superuser not found. Creating superuser...")
                User.objects.create_superuser(username=username, email=email, password=password)
                self.stdout.write(self.style.SUCCESS(f'Successfully created superuser: {username}'))
            else:
                self.stdout.write(self.style.WARNING(f'Superuser {username} already exists.'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"SUPERUSER CREATION FAILED: {e}"))
            self.stderr.write("Check that AUTH_USER_MODEL is correctly configured and the user model has is_superuser field.")
            warnings.append(f"superuser creation failed: {e}")

    def run_populate(self, target_apps, warnings):
        from django.db import OperationalError, ProgrammingError

        data_exists = False
        self.stdout.write("Checking for existing data in target apps...")
        for app_config in target_apps:
            for model in app_config.get_models():
                try:
                    if model.objects.exists():
                        data_exists = True
                        self.stdout.write(f"Data found in {app_config.name}.{model.__name__}.")
                        break
                except (ProgrammingError, OperationalError) as db_err:
                    self.stdout.write(self.style.WARNING(
                        f"  Could not query {app_config.name}.{model.__name__}: {db_err}"
                    ))
                    continue
            if data_exists:
                break

        if data_exists:
            self.stdout.write("Initial data already exists. Skipping population.")
            return

        if 'populate' not in get_commands():
            self.stdout.write(self.style.WARNING(
                "No initial data found, and no 'populate' command is installed. Skipping population."
            ))
            return

        self.stdout.write("No initial data found in target local apps. Running populate...")
        try:
            call_command('populate')
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"POPULATE FAILED: {e}"))
            self.stderr.write("The populate command exists but failed while running.")
            warnings.append(f"populate failed: {e}")

    def handle(self, *args, **options):
        specified_app = options['app']
        force_mm = options['make_migrations']
        no_migrate = options['no_migrate']

        if force_mm and no_migrate:
            raise CommandError("-mm and -nm are mutually exclusive.")

        target_apps = self.resolve_target_apps(specified_app)
        warnings = []

        self.stdout.write("DATABASE INITIALIZATION...")

        if no_migrate:
            self.stdout.write(self.style.WARNING(
                "Skipping makemigrations and migrate (-nm). Static files are still collected."
            ))
        else:
            self.stdout.write("Checking migrations...")
            self.run_schema(target_apps, force_mm)

        self.run_collectstatic()

        if apps.is_installed('dlux'):
            self.bootstrap_system_settings()

        self.ensure_superuser(warnings)

        if apps.is_installed('dlux'):
            self.stdout.write("Dlux app detected. Running dlux_setup...")
            try:
                call_command('dlux_setup')
                self.stdout.write(self.style.SUCCESS("dlux_setup completed successfully."))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"DLUX_SETUP FAILED: {e}"))
                self.stderr.write("Check that dlux is in INSTALLED_APPS and the database is migrated.")
                raise

        self.run_populate(target_apps, warnings)

        if warnings:
            self.stdout.write(self.style.WARNING(
                "INITIALIZATION COMPLETE WITH WARNINGS:\n  - " + "\n  - ".join(warnings)
            ))
        else:
            self.stdout.write(self.style.SUCCESS("INITIALIZATION COMPLETE."))
