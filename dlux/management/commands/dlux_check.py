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
            "dlux_check is a deprecated, advisory-only alias for dlux_doctor "
            "(it always exits 0). Use 'python manage.py dlux_doctor' for a gating exit code."
        ))
        try:
            super().handle(*args, **options)
        except SystemExit:
            # Advisory only: the full report still prints, but the alias never
            # gates on the exit code — restoring its pre-1.5.9 contract. This is
            # what lets a pre-1.5.9 inline updater cross forward: its preflight
            # runs `dlux_check` as a *required* command, and at preflight the
            # candidate's migrations are unapplied / static uncollected (expected,
            # applied later in the flow) — a gating exit 1 there aborts the update.
            # `dlux_doctor` keeps the real exit-1 gate for everything current.
            pass
