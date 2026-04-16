import os
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.apps import apps
from django.conf import settings

class Command(BaseCommand):
    help = "Performs initial setup: collectstatic, migrate, create superuser, and populate initial data."

    def add_arguments(self, parser):
        parser.add_argument(
            '-a', '--app',
            type=str,
            help='The main app name for initial migration check and data population logic. If not provided, all local apps are checked.'
        )
        parser.add_argument(
            '-mm', '--make-migrations',
            action='store_true',
            help='Force makemigrations for all target apps.'
        )

    def is_local_app(self, app_config):
        """Check if an app is local to the project."""
        # Check if the app path starts with BASE_DIR
        return app_config.path.startswith(str(settings.BASE_DIR)) and 'site-packages' not in app_config.path

    def handle(self, *args, **options):
        specified_app = options['app']
        force_mm = options['make_migrations']
        target_apps = []

        if specified_app:
            try:
                app_config = apps.get_app_config(specified_app)
                target_apps.append(app_config)
                self.stdout.write(f"Using specified target app: {specified_app}")
            except LookupError:
                self.stdout.write(self.style.ERROR(f"App '{specified_app}' not found."))
                return # Exit if specified app is invalid
        else:
            # Auto-discover local apps
            self.stdout.write("Auto-discovering local apps...")
            for app_config in apps.get_app_configs():
                if self.is_local_app(app_config) and app_config.name != 'core': # potentially exclude 'core' if it's just utility, or keep it.
                     # logic: include all local apps.
                     target_apps.append(app_config)
            
            # Sort for consistent output/processing
            target_apps.sort(key=lambda x: x.name)
            
            if not target_apps:
                self.stdout.write(self.style.WARNING("No local apps found."))
            else:
                self.stdout.write(f"Targeting local apps: {', '.join([app.name for app in target_apps])}")

        self.stdout.write("DATABASE INITIALIZATION...")

        # Collect static files
        self.stdout.write("Collecting static files...")
        from io import StringIO
        out = StringIO()
        try:
            call_command('collectstatic', '--noinput', '--clear', stdout=out)
            self.stdout.write(out.getvalue().splitlines()[-1] if out.getvalue() else "Static files collected.")
        except Exception as e:
            self.stdout.write(out.getvalue())
            raise e

        # 1. Migration Checks
        self.stdout.write("Checking migrations...")
        apps_needing_migrations = []
        
        for app_config in target_apps:
            migration_dir = os.path.join(app_config.path, 'migrations')
            
            # Check if migrations directory exists
            if not os.path.isdir(migration_dir):
                 # Apps without migrations module usually don't need migrations or handle it differently
                 # But if it's a local app, it arguably SHOULD have one.
                 # Let's check permissions or create it? No, makemigrations does that.
                 pass

            has_migrations = False
            if os.path.isdir(migration_dir):
                # Check for any .py file that is not __init__.py
                for filename in os.listdir(migration_dir):
                    if filename.endswith('.py') and filename != '__init__.py':
                        has_migrations = True
                        break
            
            if not has_migrations or force_mm:
                reason = "Force makemigrations requested" if force_mm else "No migrations found"
                self.stdout.write(self.style.WARNING(f"{reason} for '{app_config.name}'. adding to makemigrations list..."))
                apps_needing_migrations.append(app_config.name)
            else:
                 self.stdout.write(f"Migrations found for '{app_config.name}'.")

        # Run makemigrations for apps that need it
        if apps_needing_migrations:
            for app_label in apps_needing_migrations:
                self.stdout.write(f"Running makemigrations for {app_label}...")
                call_command('makemigrations', app_label, '--noinput')
        
        # Run migrate
        self.stdout.write("Running migrate...")
        call_command('migrate', '--noinput')

        # Create superuser if it doesn't exist
        User = get_user_model()
        username = 'admin'
        email = 'admin@eidc.gov.ly'
        password = os.getenv("ADMIN_PASS", "admin")

        if password == "admin":
            self.stdout.write(self.style.WARNING(
                "ADMIN_PASS not supplied — falling back to default password: 'admin'"
            ))

        try:
            if not User.objects.filter(username=username).exists():
                self.stdout.write("Superuser not found. Creating superuser...")
                User.objects.create_superuser(username=username, email=email, password=password)
                self.stdout.write(self.style.SUCCESS(f'Successfully created superuser: {username}'))
            else:
                self.stdout.write(self.style.WARNING(f'Superuser {username} already exists.'))
        except Exception as e:
             self.stdout.write(self.style.ERROR(f"Error checking/creating superuser: {e}"))

        # Microsys Setup
        if apps.is_installed('microsys'):
            self.stdout.write("Microsys app detected. Running microsys_setup...")
            try:
                call_command('microsys_setup')
                self.stdout.write(self.style.SUCCESS("microsys_setup completed successfully."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error running microsys_setup: {e}"))
        
        # Population Check
        # Check if ANY logic app has data.
        data_exists = False
        from django.db import ProgrammingError, OperationalError
        
        self.stdout.write("Checking for existing data in target apps...")
        for app_config in target_apps:
            app_models = app_config.get_models()
            for model in app_models:
                try:
                    if model.objects.exists():
                        data_exists = True
                        self.stdout.write(f"Data found in {app_config.name}.{model.__name__}.")
                        break
                except (ProgrammingError, OperationalError):
                    continue
            if data_exists:
                break

        if not data_exists:
            self.stdout.write("No initial data found in target local apps. Running populate...")
            try:
                call_command('populate')
            except Exception as e:
                 self.stdout.write(self.style.ERROR(f"Failed to run populate command: {e}"))
                 self.stdout.write("Ensure the 'populate' management command exists.")
        else:
            self.stdout.write("Initial data already exists. Skipping population.")

        self.stdout.write(self.style.SUCCESS("INITIALIZATION COMPLETE."))
