# dlux/management/commands/dlux_check.py
"""
Deprecated alias for `dlux_doctor`.

The deployment doctor is `dlux_doctor` (the name Composer's `composer check
--deep` calls). `dlux_check` remains as a back-compatible alias so existing
scripts and muscle memory keep working; it prints a deprecation notice to stderr
and delegates. Prefer `dlux_doctor`.
"""
from dlux.management.commands.dlux_doctor import Command as DoctorCommand


class Command(DoctorCommand):
    help = 'Deprecated alias for dlux_doctor; use dlux_doctor instead'

    def handle(self, *args, **options):
        # stderr, so it never contaminates the --format json report on stdout
        # that Composer parses.
        self.stderr.write(self.style.WARNING(
            "dlux_check is a deprecated alias for dlux_doctor. Use 'python manage.py dlux_doctor'."
        ))
        super().handle(*args, **options)
