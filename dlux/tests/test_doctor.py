import json
from io import StringIO
from unittest.mock import patch

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.core.management import call_command
from django.test import TestCase, override_settings

from dlux import doctor


def run_command(*args, name='dlux_doctor', stderr=None):
    """Return (report_or_text, exit_code). The command always calls sys.exit()."""
    out = StringIO()
    code = None
    kwargs = {'stdout': out}
    if stderr is not None:
        kwargs['stderr'] = stderr
    try:
        call_command(name, *args, **kwargs)
    except SystemExit as exc:
        code = exc.code
    return out.getvalue(), code


class DoctorReportContractTests(TestCase):
    """The JSON report is what Composer parses. Its shape is a contract, so the
    field set and the status vocabulary are asserted directly."""

    def test_report_envelope(self):
        report = doctor.run_checks()
        self.assertEqual(report['schema_version'], doctor.SCHEMA_VERSION)
        self.assertEqual(report['producer'], 'dlux')
        self.assertTrue(report['producer_version'])
        self.assertIn(report['status'], {doctor.OK, doctor.WARNING, doctor.ERROR})
        self.assertTrue(report['checks'])

    def test_every_check_emits_the_full_field_set(self):
        expected = {'id', 'group', 'title', 'status', 'detail', 'remedy', 'fix'}
        for entry in doctor.run_checks()['checks']:
            self.assertEqual(set(entry), expected, entry.get('id'))
            self.assertIn(entry['status'], {doctor.OK, doctor.WARNING, doctor.ERROR, doctor.SKIPPED})
            self.assertTrue(entry['detail'], entry['id'])

    def test_check_ids_are_unique_and_namespaced(self):
        ids = [entry['id'] for entry in doctor.run_checks()['checks']]
        self.assertEqual(len(ids), len(set(ids)))
        for check_id in ids:
            self.assertIn('.', check_id, check_id)

    def test_counts_match_the_checks(self):
        report = doctor.run_checks()
        tally = {}
        for entry in report['checks']:
            tally[entry['status']] = tally.get(entry['status'], 0) + 1
        for status, count in tally.items():
            self.assertEqual(report['counts'][status], count, status)

    def test_overall_status_is_the_worst_check(self):
        results = [
            doctor.CheckResult('a.one', 'g', 't', doctor.OK, 'd'),
            doctor.CheckResult('a.two', 'g', 't', doctor.WARNING, 'd'),
        ]
        self.assertEqual(doctor.build_report(results)['status'], doctor.WARNING)
        results.append(doctor.CheckResult('a.three', 'g', 't', doctor.ERROR, 'd'))
        self.assertEqual(doctor.build_report(results)['status'], doctor.ERROR)

    def test_skipped_does_not_degrade_the_overall_status(self):
        results = [
            doctor.CheckResult('a.one', 'g', 't', doctor.OK, 'd'),
            doctor.CheckResult('a.two', 'g', 't', doctor.SKIPPED, 'd'),
        ]
        self.assertEqual(doctor.build_report(results)['status'], doctor.OK)

    def test_a_raising_check_becomes_a_failed_check_not_a_crash(self):
        """The doctor runs when things are broken; one bad check must not take
        down the report Composer is waiting on."""
        @doctor.check('test.explodes', 'test', 'Deliberately raises')
        def _explode(ctx):
            raise RuntimeError('boom')

        try:
            report = doctor.run_checks(only_groups={'test'})
        finally:
            doctor._REGISTRY[:] = [row for row in doctor._REGISTRY if row[0] != 'test.explodes']

        entry = report['checks'][0]
        self.assertEqual(entry['status'], doctor.ERROR)
        self.assertIn('RuntimeError', entry['detail'])
        self.assertIn('boom', entry['detail'])


class DoctorCheckBehaviourTests(TestCase):
    @override_settings(DEBUG=True)
    def test_debug_enabled_is_a_warning(self):
        report = doctor.run_checks(only_groups={'security'})
        entry = next(e for e in report['checks'] if e['id'] == 'security.debug')
        self.assertEqual(entry['status'], doctor.WARNING)

    @override_settings(DEBUG=False)
    def test_debug_disabled_passes(self):
        report = doctor.run_checks(only_groups={'security'})
        entry = next(e for e in report['checks'] if e['id'] == 'security.debug')
        self.assertEqual(entry['status'], doctor.OK)

    @override_settings(SECRET_KEY='local_secret')
    def test_placeholder_secret_key_is_an_error(self):
        report = doctor.run_checks(only_groups={'security'})
        entry = next(e for e in report['checks'] if e['id'] == 'security.secret_key')
        self.assertEqual(entry['status'], doctor.ERROR)

    @override_settings(SECRET_KEY='local_secret')
    def test_no_check_leaks_a_secret_value(self):
        """Doctor output gets pasted into bug reports."""
        report = doctor.run_checks()
        blob = json.dumps(report)
        self.assertNotIn('local_secret', blob)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['*'])
    def test_wildcard_allowed_hosts_warns(self):
        report = doctor.run_checks(only_groups={'security'})
        entry = next(e for e in report['checks'] if e['id'] == 'security.allowed_hosts')
        self.assertEqual(entry['status'], doctor.WARNING)

    @override_settings(DEBUG=True, ALLOWED_HOSTS=['*'])
    def test_allowed_hosts_is_skipped_under_debug(self):
        report = doctor.run_checks(only_groups={'security'})
        entry = next(e for e in report['checks'] if e['id'] == 'security.allowed_hosts')
        self.assertEqual(entry['status'], doctor.SKIPPED)

    @override_settings(MIDDLEWARE=[
        'dlux.middleware.DluxMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
    ])
    def test_middleware_before_auth_is_an_error(self):
        report = doctor.run_checks(only_groups={'settings'})
        entry = next(e for e in report['checks'] if e['id'] == 'settings.middleware_order')
        self.assertEqual(entry['status'], doctor.ERROR)

    @override_settings(MIDDLEWARE=[
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'dlux.middleware.DluxMiddleware',
    ])
    def test_middleware_after_auth_passes(self):
        report = doctor.run_checks(only_groups={'settings'})
        entry = next(e for e in report['checks'] if e['id'] == 'settings.middleware_order')
        self.assertEqual(entry['status'], doctor.OK)

    @override_settings(INSTALLED_APPS=['django.contrib.contenttypes', 'django.contrib.auth'])
    def test_missing_dlux_app_is_an_error(self):
        report = doctor.run_checks(only_groups={'settings'})
        entry = next(e for e in report['checks'] if e['id'] == 'settings.installed_apps')
        self.assertEqual(entry['status'], doctor.ERROR)

    @override_settings(TEMPLATES=[{'BACKEND': 'django.template.backends.django.DjangoTemplates',
                                  'OPTIONS': {'context_processors': []}}])
    def test_missing_context_processor_is_an_error(self):
        report = doctor.run_checks(only_groups={'settings'})
        entry = next(e for e in report['checks'] if e['id'] == 'settings.context_processors')
        self.assertEqual(entry['status'], doctor.ERROR)

    def test_migrations_check_passes_on_a_migrated_database(self):
        report = doctor.run_checks(only_groups={'database'})
        entry = next(e for e in report['checks'] if e['id'] == 'db.migrations')
        self.assertEqual(entry['status'], doctor.OK)

    def test_cache_probe_uses_a_namespaced_key_and_cleans_up(self):
        """A cache probe must never clear the cache — that would delete every
        browser session on a Redis-backed deployment."""
        from django.core.cache import cache
        cache.set('unrelated.session.key', 'preserved', 30)
        doctor.run_checks(only_groups={'services'})
        self.assertEqual(cache.get('unrelated.session.key'), 'preserved')
        self.assertIsNone(cache.get('dlux.doctor.probe'))


class DoctorFixTieringTests(TestCase):
    """`--apply` must not silently mutate the database. Fixes are tiered and the
    default authorization is safe-only."""

    def _report_with_fixes(self):
        return doctor.build_report([
            doctor.CheckResult('a.safe', 'g', 't', doctor.ERROR, 'd', fix=doctor.management_fix(
                ['collectstatic', '--noinput'], 'Collect static')),
            doctor.CheckResult('a.stateful', 'g', 't', doctor.ERROR, 'd', fix=doctor.management_fix(
                ['migrator'], 'Migrate', doctor.STATEFUL)),
            doctor.CheckResult('a.passing', 'g', 't', doctor.OK, 'd', fix=doctor.management_fix(
                ['collectstatic'], 'Collect static')),
        ])

    def test_default_authorization_excludes_stateful_fixes(self):
        fixes = doctor.applicable_fixes(self._report_with_fixes(), {doctor.SAFE})
        self.assertEqual([check_id for check_id, _ in fixes], ['a.safe'])

    def test_stateful_fixes_require_explicit_authorization(self):
        fixes = doctor.applicable_fixes(self._report_with_fixes(), {doctor.SAFE, doctor.STATEFUL})
        self.assertEqual([check_id for check_id, _ in fixes], ['a.safe', 'a.stateful'])

    def test_passing_checks_are_never_remediated(self):
        fixes = doctor.applicable_fixes(self._report_with_fixes(), {doctor.SAFE, doctor.STATEFUL})
        self.assertNotIn('a.passing', [check_id for check_id, _ in fixes])

    def test_every_declared_fix_uses_a_known_safety_tier(self):
        for entry in doctor.run_checks()['checks']:
            fix = entry.get('fix')
            if fix:
                self.assertIn(fix['safety'], {doctor.SAFE, doctor.STATEFUL, doctor.SOURCE}, entry['id'])
                self.assertEqual(fix['kind'], 'management_command')


class DoctorCommandTests(TestCase):
    def test_json_format_emits_a_parseable_report(self):
        output, _ = run_command('--format', 'json')
        report = json.loads(output)
        self.assertEqual(report['schema_version'], doctor.SCHEMA_VERSION)
        self.assertEqual(report['producer'], 'dlux')

    def test_group_filter_limits_the_report(self):
        output, _ = run_command('--format', 'json', '--group', 'security')
        report = json.loads(output)
        self.assertTrue(report['checks'])
        self.assertEqual({entry['group'] for entry in report['checks']}, {'security'})

    @override_settings(TEMPLATES=[{'BACKEND': 'django.template.backends.django.DjangoTemplates',
                                   'OPTIONS': {'context_processors': []}}])
    def test_errors_exit_non_zero(self):
        """The previous implementation always exited 0, so nothing could gate on it."""
        output, code = run_command('--format', 'json', '--group', 'settings')
        self.assertEqual(json.loads(output)['status'], doctor.ERROR)
        self.assertEqual(code, 1)

    @override_settings(DEBUG=False)
    def test_clean_security_group_exits_zero(self):
        _, code = run_command('--format', 'json', '--group', 'packages')
        self.assertEqual(code, 0)

    @override_settings(DEBUG=True)
    def test_strict_promotes_warnings_to_a_failing_exit(self):
        _, normal = run_command('--format', 'json', '--group', 'security')
        _, strict = run_command('--format', 'json', '--group', 'security', '--strict')
        self.assertEqual(normal, 0)
        self.assertEqual(strict, 1)

    def test_text_format_renders_groups_and_a_summary(self):
        output, _ = run_command('--group', 'security')
        self.assertIn('DjangoLux doctor', output)
        self.assertIn('SECURITY', output)
        self.assertIn('ok,', output)


class DoctorAliasTests(TestCase):
    """`dlux_check` is a back-compat alias for `dlux_doctor` (the name Composer's
    `composer check --deep` calls). It must behave identically and warn."""

    def test_alias_produces_the_same_report(self):
        canonical, _ = run_command('--format', 'json', '--group', 'packages')
        alias, _ = run_command('--format', 'json', '--group', 'packages', name='dlux_check',
                               stderr=StringIO())
        self.assertEqual(json.loads(canonical)['producer'], json.loads(alias)['producer'])
        self.assertEqual(json.loads(alias)['schema_version'], doctor.SCHEMA_VERSION)

    def test_alias_warns_on_stderr_not_stdout(self):
        """The warning must never contaminate the JSON report Composer parses."""
        err = StringIO()
        out, _ = run_command('--format', 'json', '--group', 'packages', name='dlux_check', stderr=err)
        self.assertIn('deprecated', err.getvalue().lower())
        self.assertIn('dlux_doctor', err.getvalue())
        json.loads(out)  # stdout is still clean JSON

    def test_alias_is_advisory_not_gating(self):
        # The alias is advisory-only: even a clean run does not propagate a gating
        # exit (the failure case is covered by DluxCheckAliasIsAdvisoryTests).
        err = StringIO()
        _, code = run_command('--group', 'packages', name='dlux_check', stderr=err)
        self.assertIn(code, (None, 0))


class DluxCheckAliasIsAdvisoryTests(TestCase):
    """The deprecated `dlux_check` alias is advisory-only — it prints the report
    but never gates on the exit code — while `dlux_doctor` keeps the real exit-1
    gate. This is what lets a pre-1.5.9 inline updater (whose required preflight
    runs `dlux_check`) cross forward even though the candidate has the *expected*
    unapplied migrations at preflight."""

    def _failing_report(self):
        report = doctor.run_checks()
        counts = dict(report['counts'])
        counts[doctor.ERROR] = counts.get(doctor.ERROR, 0) + 1
        report['counts'] = counts
        report['status'] = doctor.ERROR
        return report

    def test_dlux_check_never_gates_even_when_doctor_finds_problems(self):
        with patch(
            'dlux.management.commands.dlux_doctor.doctor.run_checks',
            return_value=self._failing_report(),
        ):
            _, code = run_command('--format', 'json', name='dlux_check', stderr=StringIO())
        self.assertIn(code, (None, 0))  # advisory: no gating exit

    def test_dlux_doctor_still_gates_on_problems(self):
        with patch(
            'dlux.management.commands.dlux_doctor.doctor.run_checks',
            return_value=self._failing_report(),
        ):
            _, code = run_command('--format', 'json', name='dlux_doctor')
        self.assertEqual(code, 1)
