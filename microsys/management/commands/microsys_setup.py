# microsys/management/commands/microsys_setup.py
"""
Management command for initial microsys package setup.
Runs migrations and performs initial configuration.
"""
from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Initial setup for microsys package - runs migrations and validates configuration'

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

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('\n📦 MicroSys Setup\n'))
        self.stdout.write('=' * 40 + '\n')

        # Step 1: Create migrations if needed
        if not options['no_migrate']:
            self.stdout.write('\n🔄 Creating migrations for microsys...\n')
            try:
                call_command('makemigrations', 'microsys', verbosity=1)
                self.stdout.write(self.style.SUCCESS('   ✓ Migrations created\n'))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'   ⚠ Migration creation: {e}\n'))

            # Step 2: Run migrations
            self.stdout.write('\n🔄 Running migrations...\n')
            try:
                call_command('migrate', 'microsys', verbosity=1)
                self.stdout.write(self.style.SUCCESS('   ✓ Migrations applied\n'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'   ✗ Migration failed: {e}\n'))
                return

        # Step 3: Run configuration check
        if not options['skip_check']:
            self.stdout.write('\n')
            call_command('microsys_check')

        self.stdout.write('\n' + '=' * 40)
        self.stdout.write(self.style.SUCCESS('\n✅ MicroSys setup complete!\n'))
