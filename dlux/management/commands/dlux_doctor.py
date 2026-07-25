# dlux/management/commands/dlux_doctor.py
"""
Run the DjangoLux deployment diagnostics and report the result.

This is the app-side half of the doctor. Composer's `composer check --deep`
executes this command inside the app container (default `python manage.py
dlux_doctor`) for everything that needs Django loaded, and merges the `--format
json` report with its own project-directory checks. That JSON is the contract
between the two; see dlux/doctor.py.
"""
import json
import sys

from django.core.management.base import BaseCommand

from dlux import doctor


EXIT_OK = 0
EXIT_PROBLEMS = 1

_STATUS_MARK = {
    doctor.OK: ('✓', 'SUCCESS'),
    doctor.WARNING: ('!', 'WARNING'),
    doctor.ERROR: ('✗', 'ERROR'),
    doctor.SKIPPED: ('-', 'HTTP_INFO'),
}


class Command(BaseCommand):
    help = 'Diagnose this DjangoLux deployment and optionally apply safe remediations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--format', choices=['text', 'json'], default='text',
            help='text for humans, json for Composer and CI',
        )
        parser.add_argument(
            '--group', action='append', dest='groups', metavar='GROUP',
            help='Limit to a check group (settings, urls, database, services, static, security, packages)',
        )
        parser.add_argument(
            '--strict', action='store_true',
            help='Exit non-zero on warnings as well as errors',
        )
        parser.add_argument(
            '--apply', action='store_true',
            help='Apply remediations for failing checks that ship a safe fix',
        )
        parser.add_argument(
            '--allow-stateful', action='store_true',
            help='With --apply, also run fixes that mutate the database (migrations)',
        )

    def handle(self, *args, **options):
        report = doctor.run_checks(only_groups=set(options['groups'] or []) or None)

        applied = []
        if options['apply']:
            allowed = {doctor.SAFE}
            if options['allow_stateful']:
                allowed.add(doctor.STATEFUL)
            applied = self._apply(report, allowed, options['format'])
            if applied:
                report = doctor.run_checks(only_groups=set(options['groups'] or []) or None)
                report['applied_fixes'] = applied

        if options['format'] == 'json':
            self.stdout.write(json.dumps(report, indent=2))
        else:
            self._render_text(report, applied)

        failed = report['counts'].get(doctor.ERROR, 0)
        warned = report['counts'].get(doctor.WARNING, 0)
        if failed or (options['strict'] and warned):
            sys.exit(EXIT_PROBLEMS)
        sys.exit(EXIT_OK)

    def _apply(self, report, allowed, output_format):
        from django.core.management import call_command

        applied = []
        for check_id, fix in doctor.applicable_fixes(report, allowed):
            argv = fix['argv']
            if output_format == 'text':
                self.stdout.write(self.style.MIGRATE_HEADING(f"→ {fix['label']} ({check_id})"))
            try:
                call_command(*argv)
                applied.append({'check': check_id, 'argv': argv, 'status': 'succeeded', 'error': ''})
            except Exception as exc:
                applied.append({
                    'check': check_id,
                    'argv': argv,
                    'status': 'failed',
                    'error': f'{type(exc).__name__}: {exc}',
                })
        return applied

    def _render_text(self, report, applied):
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nDjangoLux doctor — dlux {report['producer_version']}\n"
        ))

        current_group = None
        for entry in report['checks']:
            if entry['group'] != current_group:
                current_group = entry['group']
                self.stdout.write(self.style.MIGRATE_LABEL(f'\n{current_group.upper()}'))
            mark, style_name = _STATUS_MARK.get(entry['status'], ('?', 'WARNING'))
            style = getattr(self.style, style_name, self.style.WARNING)
            self.stdout.write(f"  {style(mark)} {entry['title']}")
            if entry['status'] != doctor.OK:
                self.stdout.write(f"      {entry['detail']}")
                if entry['remedy']:
                    for line in entry['remedy'].splitlines():
                        self.stdout.write(f'      {line}')

        if applied:
            self.stdout.write(self.style.MIGRATE_LABEL('\nAPPLIED'))
            for record in applied:
                if record['status'] == 'succeeded':
                    self.stdout.write(f"  {self.style.SUCCESS('✓')} {' '.join(record['argv'])}")
                else:
                    self.stdout.write(f"  {self.style.ERROR('✗')} {' '.join(record['argv'])}: {record['error']}")

        counts = report['counts']
        summary = (
            f"{counts.get(doctor.OK, 0)} ok, {counts.get(doctor.WARNING, 0)} warning, "
            f"{counts.get(doctor.ERROR, 0)} error, {counts.get(doctor.SKIPPED, 0)} skipped"
        )
        self.stdout.write('')
        if counts.get(doctor.ERROR, 0):
            self.stdout.write(self.style.ERROR(f'{summary}\n'))
        elif counts.get(doctor.WARNING, 0):
            self.stdout.write(self.style.WARNING(f'{summary}\n'))
        else:
            self.stdout.write(self.style.SUCCESS(f'{summary}\n'))

        unfixed = [
            entry for entry in report['checks']
            if entry.get('fix') and entry['status'] in {doctor.WARNING, doctor.ERROR}
        ]
        if unfixed:
            stateful = any(entry['fix']['safety'] == doctor.STATEFUL for entry in unfixed)
            hint = 'python manage.py dlux_doctor --apply'
            if stateful:
                hint += ' --allow-stateful'
            self.stdout.write(f'{len(unfixed)} finding(s) have an automatic fix. Run: {hint}\n')
