"""Show what the Composer agent's egress relay offers this project.

Reads ``state/relay/capabilities.json`` from the runtime volume, so it can run in
any service that mounts it. Exit status is 0 when an agent is answering and every
operation you use is on offer, 1 when no agent is answering, 2 when something
declared is unapproved or invalid.

    python manage.py dlux_relay              # summary
    python manage.py dlux_relay finance.cbl_page other.op   # require these operations
"""
from django.core.management.base import BaseCommand

from dlux import relay


class Command(BaseCommand):
    help = "Report whether the Composer egress relay is answering and which operations it offers."

    def add_arguments(self, parser):
        parser.add_argument(
            'operations', nargs='*', metavar='OPERATION',
            help='Operations this project depends on; exit non-zero if any is not on offer.',
        )

    def handle(self, *args, **options):
        summary = relay.status()
        if not summary['answering']:
            self.stdout.write(self.style.ERROR(
                'The Composer agent is not answering. The relay needs a Composer with the egress relay '
                '(1.6.0b1 or newer): ./start.sh self update && ./start.sh agent update.'
            ))
            return self._exit(1)
        self.stdout.write(f"Agent answering (Composer {summary['composer'] or 'unknown'}).")
        for name in summary['operations']:
            self.stdout.write(f'  on offer   {name}')
        for name in summary['unapproved']:
            self.stdout.write(self.style.WARNING(f'  unapproved {name}  (run `composer relay approve` and redeploy relay/operations.lock)'))
        for problem in summary['problems']:
            self.stdout.write(self.style.ERROR(f"  invalid    {problem.get('name') or 'operations.json'}: {problem.get('reason', '')}"))
        missing = [name for name in options['operations'] if name not in summary['operations']]
        for name in missing:
            self.stdout.write(self.style.ERROR(f'  MISSING    {name}'))
        return self._exit(2 if (missing or summary['unapproved'] or summary['problems']) else 0)

    def _exit(self, code):
        if code:
            raise SystemExit(code)
