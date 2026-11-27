import json
import os
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
import unittest
from importlib.util import find_spec
from unittest.mock import patch

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.core.management import call_command
from django.test import TestCase, override_settings

from dlux import doctor
from dlux.tests.test_email_step import _IsolatedSettingsTestCase


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


class DoctorStackSchemaTests(TestCase):
    def _run(self, env):
        from dlux.contracts.stack import STACK_SCHEMA_ENV

        environ = {k: v for k, v in os.environ.items() if k != STACK_SCHEMA_ENV}
        if env is not None:
            environ[STACK_SCHEMA_ENV] = env
        with patch.dict('os.environ', environ, clear=True):
            return doctor._check_stack_schema(None)

    def test_unstamped_stack_is_informational(self):
        self.assertEqual(self._run(None).status, doctor.SKIPPED)

    def test_matching_stamp_passes(self):
        from dlux.contracts.stack import stack_schema

        self.assertEqual(self._run(str(stack_schema())).status, doctor.OK)

    def test_older_or_newer_stamp_warns_never_errors(self):
        from dlux.contracts.stack import stack_schema

        current = stack_schema()
        for value in (current - 1, current + 1):
            self.assertEqual(self._run(str(value)).status, doctor.WARNING)

    def test_an_older_stamp_names_the_recreate_first(self):
        # The number is this container's environment: after composer check --fix
        # restamps compose.yml, a service not yet recreated still reports the old
        # one, and telling the operator to edit compose.yml would be wrong.
        from dlux.contracts.stack import stack_schema

        finding = self._run(str(stack_schema() - 1))
        self.assertIn('This service runs with stack schema', finding.detail)
        self.assertIn('recreate web and worker', finding.remedy)
        self.assertIn('docs/stack-schema.md', finding.remedy)

    def test_a_newer_stamp_asks_for_a_newer_djangolux(self):
        from dlux.contracts.stack import stack_schema

        self.assertIn('Update DjangoLux', self._run(str(stack_schema() + 1)).remedy)

    def test_garbage_stamp_warns(self):
        self.assertEqual(self._run('two').status, doctor.WARNING)

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


class DoctorEmailTests(_IsolatedSettingsTestCase):
    """The email checks follow the Email step, not Django's EMAIL_* settings."""

    RELAY_ENV = {
        'SMTP_RELAY_HOST': 'smtp.provider.example', 'SMTP_RELAY_PORT': '587', 'SMTP_RELAY_USE_TLS': 'True',
        'SMTP_RELAY_USER': '', 'SMTP_RELAY_PASSWORD_SET': '',
    }

    def _store(self, **config):
        from dlux.models import SystemSettings
        from dlux.system.normalizers import normalize_email_config

        instance = SystemSettings.load()
        instance.email_config = normalize_email_config({'default_from_email': 'app@example.test', **config})
        instance.save(update_fields=['email_config'])

    def _run(self, env=None):
        environ = {k: v for k, v in os.environ.items() if not k.startswith('SMTP_RELAY_')}
        environ.update(env or {})
        with patch.dict('os.environ', environ, clear=True):
            return doctor._check_email_config(None), doctor._check_email_reachable(None)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
                       EMAIL_HOST='unreachable.invalid', EMAIL_PORT=25)
    def test_email_off_skips_both_checks(self):
        self._store(enabled=False, transport='direct', secret_storage='env')
        with patch('socket.create_connection', side_effect=AssertionError('probed with email off')):
            configured, reachable = self._run()
        for finding in (configured, reachable):
            self.assertEqual(finding.status, doctor.SKIPPED)
            self.assertIn('email delivery is off', finding.detail)

    def test_the_relay_route_probes_the_relay_not_the_provider(self):
        self._store(enabled=True, transport='relay', secret_storage='env')
        with patch('dlux.utils.internal_smtp_relay_available', return_value=False) as probe, \
                patch('socket.create_connection', side_effect=AssertionError('connected to the provider')):
            configured, reachable = self._run(self.RELAY_ENV)
        self.assertEqual(configured.status, doctor.OK)
        self.assertIn('through the internal SMTP relay to smtp.provider.example:587', configured.detail)
        self.assertEqual(reachable.status, doctor.ERROR)
        self.assertIn('internal SMTP relay does not answer on smtp-relay:1025', reachable.detail)
        self.assertEqual(probe.call_args.kwargs, {'host': 'smtp-relay', 'port': 1025})
        with patch('dlux.utils.internal_smtp_relay_available', return_value=True):
            self.assertEqual(self._run(self.RELAY_ENV)[1].status, doctor.OK)

    def test_relay_settings_web_cannot_see_warn(self):
        self._store(enabled=True, transport='relay', secret_storage='env')
        with patch('dlux.utils.internal_smtp_relay_available', return_value=True):
            configured, _reachable = self._run()
        self.assertEqual(configured.status, doctor.WARNING)
        self.assertIn('./start.sh check --fix', configured.remedy)

    def test_the_direct_route_probes_the_provider_the_step_names(self):
        self._store(enabled=True, transport='direct', secret_storage='encrypted_db',
                    host='smtp.provider.example', port=587)
        with patch('socket.create_connection') as connect:
            configured, reachable = self._run()
        self.assertEqual(configured.status, doctor.OK)
        self.assertIn('directly from the web service to smtp.provider.example:587', configured.detail)
        self.assertEqual(reachable.status, doctor.OK)
        self.assertEqual(connect.call_args.args[0], ('smtp.provider.example', 587))
        with patch('socket.create_connection', side_effect=OSError('no route')):
            reachable = self._run()[1]
        self.assertEqual(reachable.status, doctor.ERROR)
        self.assertIn('internal SMTP relay', reachable.remedy)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
                       EMAIL_HOST='smtp.web.example', EMAIL_PORT=465)
    def test_the_direct_environment_route_uses_the_web_settings(self):
        self._store(enabled=True, transport='direct', secret_storage='env')
        with patch('socket.create_connection') as connect:
            configured, reachable = self._run()
        self.assertEqual(configured.status, doctor.OK)
        self.assertEqual(reachable.status, doctor.OK)
        self.assertEqual(connect.call_args.args[0], ('smtp.web.example', 465))

    def test_incomplete_settings_fail_with_the_reason(self):
        self._store(enabled=True, transport='direct', secret_storage='encrypted_db', host='', port=587)
        configured, reachable = self._run()
        self.assertEqual(configured.status, doctor.ERROR)
        self.assertIn('provider host or port, or the sender address, is missing', configured.detail)
        self.assertEqual(reachable.status, doctor.SKIPPED)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend')
    def test_a_non_smtp_backend_warns_and_skips_the_probe(self):
        self._store(enabled=True, transport='direct', secret_storage='env')
        configured, reachable = self._run()
        self.assertEqual(configured.status, doctor.WARNING)
        self.assertEqual(reachable.status, doctor.SKIPPED)

    def test_an_unavailable_database_skips_both(self):
        ctx = doctor.Context()
        ctx._db_probed, ctx._db_error = True, 'OperationalError: down'
        for check in (doctor._check_email_config, doctor._check_email_reachable):
            self.assertEqual(check(ctx).status, doctor.SKIPPED)


def _registered(check_id, group, func):
    """Register a throwaway check; returns a cleanup callable."""
    doctor.check(check_id, group, check_id)(func)
    return lambda: doctor._REGISTRY.__setitem__(
        slice(None), [row for row in doctor._REGISTRY if row[0] != check_id])


class DoctorTaskWorkerTests(TestCase):
    """Break-it #5: with no worker, scheduled backups and jobs silently stop."""

    def test_no_live_worker_is_an_error_and_fails_the_run(self):
        finding = doctor._check_task_worker(doctor.Context())
        self.assertEqual(finding.status, doctor.ERROR)
        self.assertIn('not running', finding.detail)
        output, code = run_command('--format', 'json', '--group', 'services')
        entry = next(e for e in json.loads(output)['checks'] if e['id'] == 'tasks.worker')
        self.assertEqual(entry['status'], doctor.ERROR)
        self.assertEqual(code, 1)


class DoctorStaticTests(TestCase):
    """Break-it #6: STATIC_ROOT held files but none of DjangoLux's, every asset
    404'd, and the doctor exited 0 with a warning."""

    def setUp(self):
        import tempfile

        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(__import__('shutil').rmtree, self.root, True)

    def _populate(self, names):
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('x')

    def _check(self):
        with override_settings(STATIC_ROOT=str(self.root)):
            return doctor._check_static(doctor.Context())

    def test_content_without_dlux_assets_is_an_error_with_the_collectstatic_fix(self):
        self._populate(['.moved-by-breakit/app.css', 'documents/main.js'])
        finding = self._check()
        self.assertEqual(finding.status, doctor.ERROR)
        self.assertIn('404', finding.detail)
        self.assertEqual(finding.fix['argv'], ['collectstatic', '--noinput'])
        self.assertEqual(finding.fix['safety'], doctor.SAFE)

    def test_one_missing_dlux_asset_is_named(self):
        shipped = doctor._shipped_static_files()
        self.assertIn('dlux/titlebar/js/main.js', shipped)
        self._populate(name for name in shipped if name != 'dlux/titlebar/js/main.js')
        finding = self._check()
        self.assertEqual(finding.status, doctor.ERROR)
        self.assertIn('1 of the', finding.detail)
        self.assertIn('dlux/titlebar/js/main.js', finding.detail)

    def test_every_shipped_file_present_passes(self):
        self._populate(doctor._shipped_static_files())
        self.assertEqual(self._check().status, doctor.OK)

    def test_apply_runs_collectstatic_and_the_rerun_passes(self):
        self._populate(['documents/main.js'])
        with override_settings(STATIC_ROOT=str(self.root)):
            output, code = run_command('--format', 'json', '--group', 'static', '--apply')
        report = json.loads(output)
        self.assertEqual(report['applied_fixes'][0]['argv'], ['collectstatic', '--noinput'])
        self.assertEqual(report['applied_fixes'][0]['status'], 'succeeded')
        self.assertEqual(report['checks'][0]['status'], doctor.OK)
        self.assertEqual(code, 0)


class DoctorDatabaseDownTests(_IsolatedSettingsTestCase):
    """Break-it #7: with the database down the doctor printed 937 lines of logged
    tracebacks, and the outage cascaded into runtime-volume and worker errors."""

    @contextmanager
    def _down(self):
        from django.db.utils import OperationalError

        def refuse(*args, **kwargs):
            raise OperationalError('could not translate host name "db" to address')

        with patch('django.db.backends.base.base.BaseDatabaseWrapper.ensure_connection', refuse), \
                patch('django.db.backends.base.base.BaseDatabaseWrapper.cursor', refuse):
            yield

    @override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
    def test_dependent_checks_are_skipped_with_the_reason(self):
        from django.core.cache import cache

        cache.clear()
        with self._down():
            report = doctor.run_checks(only_groups={'database', 'services'})
        status = {e['id']: e for e in report['checks']}
        self.assertEqual(status['db.reachable']['status'], doctor.ERROR)
        for check_id in ('db.migrations', 'db.system_config', 'db.setup_status',
                         'updater.runtime_volume', 'tasks.worker'):
            self.assertEqual(status[check_id]['status'], doctor.SKIPPED, check_id)
            self.assertIn('database is unreachable', status[check_id]['detail'], check_id)
        self.assertEqual(report['counts'][doctor.ERROR], 1, [
            e['id'] for e in report['checks'] if e['status'] == doctor.ERROR])

    def test_config_is_built_once_and_its_failure_logged_once_without_a_traceback(self):
        """Outside a request every translated string rebuilt the system config:
        one failed database read and one logged traceback each."""
        from django.core.cache import cache
        from django.utils.translation import gettext

        from dlux.utils import config as config_module

        builds = []
        original = config_module._build_system_config

        def counting():
            builds.append(1)
            return original()

        cleanup = _registered('test.translates', 'test',
                              lambda ctx: doctor.ok(' '.join(str(gettext('Save')) for _ in range(50))))
        self.addCleanup(cleanup)
        cache.clear()
        with patch.object(config_module, '_build_system_config', counting), self._down(), \
                self.assertLogs('dlux', level='WARNING') as logs:
            report = doctor.run_checks(only_groups={'test', 'database'})
        self.assertEqual(report['checks'][-1]['status'], doctor.OK)
        self.assertEqual(len(builds), 1)
        failures = [r for r in logs.records if 'Failed to read SystemSettings' in r.getMessage()]
        self.assertEqual(len(failures), 1)
        self.assertIsNone(failures[0].exc_info)
        self.assertIn('OperationalError: could not translate host name', failures[0].getMessage())
        self.assertNotIn('Traceback', '\n'.join(logs.output))

    def test_a_record_reaching_two_handlers_is_shown_by_both(self):
        import logging

        streams = [StringIO(), StringIO()]
        logger = logging.getLogger('dlux.tests.once')
        handlers = [logging.StreamHandler(stream) for stream in streams]
        for handler in handlers:
            logger.addHandler(handler)
            self.addCleanup(logger.removeHandler, handler)
        logger.propagate = False
        self.addCleanup(setattr, logger, 'propagate', True)
        with doctor._logged_once():
            logger.warning('the same line')
            logger.warning('the same line')
        self.assertEqual([stream.getvalue() for stream in streams], ['the same line\n'] * 2)

    def test_the_once_filter_is_removed_after_the_run(self):
        import logging

        handler = logging.StreamHandler(StringIO())
        logging.getLogger('dlux').addHandler(handler)
        self.addCleanup(logging.getLogger('dlux').removeHandler, handler)
        doctor.run_checks(only_groups={'packages'})
        self.assertEqual(handler.filters, [])


class DoctorNeverHangsTests(TestCase):
    """Break-it #8: with Redis paused the doctor hung for over 240 s."""

    def test_a_hung_check_is_an_error_with_its_timing_and_the_report_goes_on(self):
        import threading
        import time

        release = threading.Event()
        self.addCleanup(release.set)
        self.addCleanup(_registered('test.hangs', 'test', lambda ctx: release.wait(30) and doctor.ok('late')))
        self.addCleanup(_registered('test.after', 'test', lambda ctx: doctor.ok('ran')))
        started = time.monotonic()
        with patch.object(doctor, 'CHECK_TIMEOUT', 0.3):
            report = doctor.run_checks(only_groups={'test'})
        self.assertLess(time.monotonic() - started, 5)
        hung, after = report['checks']
        self.assertEqual(hung['status'], doctor.ERROR)
        self.assertRegex(hung['detail'], r'No answer within 0\.\d s')
        self.assertIn('paused', hung['remedy'])
        self.assertEqual(after['status'], doctor.OK)

    def test_the_whole_pass_has_a_deadline(self):
        import threading

        release = threading.Event()
        self.addCleanup(release.set)
        self.addCleanup(_registered('test.slow', 'test', lambda ctx: release.wait(30)))
        self.addCleanup(_registered('test.never', 'test', lambda ctx: doctor.ok('ran')))
        with patch.object(doctor, 'CHECK_TIMEOUT', 5), patch.object(doctor, 'RUN_TIMEOUT', 0.3):
            report = doctor.run_checks(only_groups={'test'})
        slow, never = report['checks']
        self.assertEqual(slow['status'], doctor.ERROR)
        self.assertEqual(never['status'], doctor.SKIPPED)
        self.assertIn('0.3 s limit', never['detail'])

    def test_a_paused_redis_is_one_error_and_the_rest_reads_the_database(self):
        """A listening socket that never answers is what a paused container looks
        like: connects succeed, reads block. The project's own CACHES wait 20 s."""
        import socket
        import time

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1', 0))
        listener.listen(64)
        self.addCleanup(listener.close)
        port = listener.getsockname()[1]
        caches = {'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': f'redis://127.0.0.1:{port}/1',
            'OPTIONS': {'SOCKET_CONNECT_TIMEOUT': 20, 'SOCKET_TIMEOUT': 20},
        }}
        started = time.monotonic()
        with override_settings(CACHES=caches), patch.object(doctor, 'PROBE_TIMEOUT', 0.5), \
                patch.object(doctor, 'CHECK_TIMEOUT', 3):
            report = doctor.run_checks(only_groups={'database', 'services'})
        self.assertLess(time.monotonic() - started, 15)
        status = {e['id']: e for e in report['checks']}
        self.assertEqual(status['cache.reachable']['status'], doctor.ERROR)
        self.assertIn('django_redis.cache.RedisCache', status['cache.reachable']['detail'])
        self.assertRegex(status['cache.reachable']['detail'], r'(no answer within|after) \d+\.\d s')
        self.assertEqual(status['db.system_config']['status'], doctor.OK)
        self.assertNotIn('No answer', status['db.system_config']['detail'])

    def test_a_paused_database_is_one_error_and_the_run_ends_with_its_probe(self):
        """Live proof C2: with Postgres paused, Django's system checks and the URL
        check each waited out the watchdog (27 s, 3 errors). Importing the URLconf
        translates strings, and every translation built the system config from the
        database, one connect timeout per read."""
        import time

        from django.core.cache import cache
        from django.db.utils import OperationalError

        attempts = []

        def paused(*args, **kwargs):
            attempts.append(1)
            time.sleep(0.4)
            raise OperationalError('connection to server at "db", port 5432 failed: timeout expired')

        cache.clear()
        started = time.monotonic()
        with patch('django.db.backends.base.base.BaseDatabaseWrapper.ensure_connection', paused), \
                patch('django.db.backends.base.base.BaseDatabaseWrapper.cursor', paused), \
                patch.object(doctor, 'CHECK_TIMEOUT', 1.0):
            report = doctor.run_checks()
        elapsed = time.monotonic() - started
        status = {e['id']: e for e in report['checks']}
        self.assertEqual([e['id'] for e in report['checks'] if e['status'] == doctor.ERROR], ['db.reachable'])
        for check_id in (doctor.DJANGO_CHECKS_ID, 'urls.mounted'):
            self.assertEqual(status[check_id]['status'], doctor.SKIPPED, check_id)
            self.assertIn('database is unreachable', status[check_id]['detail'], check_id)
        self.assertEqual(len(attempts), 1, 'only the opening probe waits on the database')
        self.assertLess(elapsed, 2.0)

    def test_project_cache_timeouts_are_capped_whatever_settings_say(self):
        with patch.object(doctor, 'PROBE_TIMEOUT', 5):
            bounded = doctor._bounded_caches({
                'default': {'BACKEND': 'django_redis.cache.RedisCache',
                            'OPTIONS': {'SOCKET_TIMEOUT': 20}},
                'fast': {'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                         'OPTIONS': {'socket_timeout': 1}},
                'local': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
            })
        self.assertEqual(bounded['default']['OPTIONS'],
                         {'SOCKET_TIMEOUT': 5, 'SOCKET_CONNECT_TIMEOUT': 5})
        self.assertEqual(bounded['fast']['OPTIONS'], {'socket_timeout': 1, 'socket_connect_timeout': 5})
        self.assertNotIn('OPTIONS', bounded['local'])
        self.assertIsNone(doctor._bounded_caches({'local': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}))

    @unittest.skipUnless(find_spec('psycopg') or find_spec('psycopg2'), 'needs a PostgreSQL driver')
    def test_postgres_connect_timeout_is_capped_for_the_run_and_restored(self):
        from django.db.utils import ConnectionHandler

        handler = ConnectionHandler({
            'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'},
            'pg': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'x', 'HOST': 'db',
                   'OPTIONS': {'connect_timeout': 60}},
            'pg_default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'x', 'HOST': 'db'},
        })
        with patch('django.db.connections', handler):
            with doctor._short_network_timeouts():
                self.assertEqual(handler['pg'].settings_dict['OPTIONS']['connect_timeout'], doctor.PROBE_TIMEOUT)
                self.assertEqual(handler['pg_default'].settings_dict['OPTIONS']['connect_timeout'],
                                 doctor.PROBE_TIMEOUT)
            self.assertEqual(handler['pg'].settings_dict['OPTIONS']['connect_timeout'], 60)
            self.assertNotIn('connect_timeout', handler['pg_default'].settings_dict['OPTIONS'])

    def test_the_process_deadline_prints_a_report_and_exits(self):
        import threading

        from dlux.management.commands.dlux_check import Command as AliasCommand
        from dlux.management.commands.dlux_doctor import Command as DoctorCommand

        for command_class, expected_code in ((DoctorCommand, 1), (AliasCommand, 0)):
            exited = threading.Event()
            codes = []

            def fake_exit(code):
                codes.append(code)
                exited.set()

            out = StringIO()
            with patch.object(doctor, 'PROCESS_TIMEOUT', 0.05), \
                    patch('dlux.management.commands.dlux_doctor.os._exit', fake_exit), \
                    patch('sys.stdout', out), patch('sys.stderr', StringIO()):
                command_class()._arm_process_deadline('json')
                self.assertTrue(exited.wait(5))
            self.assertEqual(codes, [expected_code])
            report = json.loads(out.getvalue())
            self.assertEqual(report['checks'][0]['id'], 'doctor.deadline')
            self.assertEqual(report['status'], doctor.ERROR)

    def test_only_a_report_run_from_the_command_line_arms_the_deadline(self):
        from dlux.management.commands.dlux_doctor import Command as DoctorCommand

        with patch.object(DoctorCommand, '_arm_process_deadline') as arm:
            run_command('--format', 'json', '--group', 'packages')
            arm.assert_not_called()
            command = DoctorCommand(stdout=StringIO())
            with self.assertRaises(SystemExit):
                command.run_from_argv(['manage.py', 'dlux_doctor', '--group', 'packages', '--skip-checks'])
            arm.assert_called_once()
            arm.reset_mock()
            command = DoctorCommand(stdout=StringIO())
            with self.assertRaises(SystemExit), override_settings(STATIC_ROOT=''):
                command.run_from_argv(['manage.py', 'dlux_doctor', '--group', 'packages', '--apply',
                                       '--skip-checks'])
            arm.assert_not_called()


class DoctorStackSchemaAdviceTests(TestCase):
    """Break-it #2: Composer 1.10 and older restamp only the first stamp in a
    file, so "check --fix updates it" was false for a compose.yml that also
    carries the comment stamp."""

    def test_the_advice_names_the_composer_that_restamps_every_stamp(self):
        from dlux.contracts.stack import STACK_SCHEMA_ENV, stack_schema

        expected = stack_schema()
        with patch.dict('os.environ', {STACK_SCHEMA_ENV: str(expected - 1)}):
            finding = doctor._check_stack_schema(None)
        self.assertNotIn('check --fix updates it', finding.remedy)
        self.assertIn('Composer 1.11.0 or later restamps every stamp', finding.remedy)
        self.assertIn(f'set it to "{expected}" by hand', finding.remedy)


class ImageFloorCheckTests(TestCase):
    """break-it #11: an image rolled back under a newer inline release is an error."""

    def setUp(self):
        from tempfile import TemporaryDirectory

        from dlux.updater.runtime import RuntimeStore

        holder = TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.store = RuntimeStore(Path(holder.name)).ensure()
        package = self.store.release_path('1.17.2') / 'dlux'
        package.mkdir(parents=True)
        manifest = {'schema_version': 2, 'version': '1.17.2', 'requires': {'baked_image': '>=1.17.0'}}
        (package / 'release-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        self.store.write_active('1.17.2', source='volume', generation=1)

    def finding(self, baked):
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=str(self.store.root)), \
                patch.dict('os.environ', {'DLUX_BAKED_VERSION': baked}):
            return doctor._check_updater_image_floor(None)

    def test_an_image_below_the_active_release_floor_is_an_error(self):
        finding = self.finding('1.16.6')
        self.assertEqual(finding.status, doctor.ERROR)
        self.assertIn('1.17.0', finding.detail)
        self.assertIn('1.16.6', finding.detail)
        self.assertIn('dlux rollback', finding.remedy)

    def test_an_image_on_the_floor_passes(self):
        self.assertEqual(self.finding('1.17.0').status, doctor.OK)

    def test_the_detail_names_the_baked_release_that_runs(self):
        with patch.object(doctor, '__version__', '1.16.6'):
            finding = self.finding('1.16.6')
        self.assertIn('The baked DjangoLux 1.16.6 runs instead.', finding.detail)

    def test_an_older_supervisor_runs_the_release_and_the_detail_says_so(self):
        """Live proof S6: an image's own supervisor older than the floor check
        serves the release anyway, so this process runs it."""
        with patch.object(doctor, '__version__', '1.17.2'):
            finding = self.finding('1.15.1')
        self.assertEqual(finding.status, doctor.ERROR)
        self.assertIn("This image's supervisor predates the floor check, so DjangoLux 1.17.2 runs "
                      'on an image below its floor.', finding.detail)
        self.assertNotIn('instead', finding.detail)
        self.assertIn('dlux rollback', finding.remedy)


class DoctorDjangoSystemChecksTests(TestCase):
    """Run before handle(), one error-level system check stopped the doctor
    with no report, so composer check --deep had nothing to parse."""

    def _with_django_check(self, *messages):
        from django.core.checks import registry

        def project_check(app_configs, **kwargs):
            return list(messages)

        registry.registry.register(project_check)
        self.addCleanup(registry.registry.registered_checks.discard, project_check)

    def _finding(self, report):
        return next(e for e in report['checks'] if e['id'] == doctor.DJANGO_CHECKS_ID)

    def test_an_error_is_a_finding_and_the_report_still_prints(self):
        from django.core.checks import Error

        self._with_django_check(Error('broken thing', id='project.E001'))
        out = StringIO()
        try:
            call_command('dlux_doctor', '--format', 'json', skip_checks=False, stdout=out)
            code = None
        except SystemExit as exc:
            code = exc.code
        finding = self._finding(json.loads(out.getvalue()))
        self.assertEqual(finding['status'], doctor.ERROR)
        self.assertIn('project.E001', finding['detail'])
        self.assertIn('broken thing', finding['detail'])
        self.assertEqual(code, 1)

    def test_a_warning_warns_and_a_silenced_one_is_ignored(self):
        from django.core.checks import Warning

        self._with_django_check(Warning('odd thing', id='project.W001'))
        self.assertEqual(self._finding(doctor.run_checks(only_groups={'settings'}))['status'], doctor.WARNING)
        with override_settings(SILENCED_SYSTEM_CHECKS=['project.W001']):
            self.assertEqual(self._finding(doctor.run_checks(only_groups={'settings'}))['status'], doctor.OK)

    def test_a_message_that_ends_in_a_period_gets_one_period(self):
        from django.core.checks import Warning

        self._with_django_check(
            Warning('first thing can run.', id='project.W001'),
            Warning('second thing', id='project.W002'),
        )
        detail = self._finding(doctor.run_checks(only_groups={'settings'}))['detail']
        self.assertNotIn('..', detail)
        self.assertIn('first thing can run; project.W002', detail)
        self.assertTrue(detail.endswith('second thing.'), detail)

    def test_skip_checks_leaves_the_finding_out(self):
        output, _ = run_command('--format', 'json', '--group', 'settings', '--skip-checks')
        self.assertNotIn(doctor.DJANGO_CHECKS_ID, [e['id'] for e in json.loads(output)['checks']])
        out = StringIO()
        with self.assertRaises(SystemExit):
            call_command('dlux_doctor', '--format', 'json', '--group', 'settings', skip_checks=False, stdout=out)
        self.assertIn(doctor.DJANGO_CHECKS_ID, [e['id'] for e in json.loads(out.getvalue())['checks']])


class DoctorApplyWithDeadCacheTests(TestCase):
    """A database-changing fix run while the cache is down leaves the cache
    holding pre-fix settings for when it comes back."""

    def _run(self, cache_up):
        from unittest.mock import PropertyMock

        report = doctor.build_report([doctor.CheckResult(
            'test.stateful', 'test', 't', doctor.ERROR, 'd',
            fix=doctor.management_fix(['check'], 'Harmless stand-in', doctor.STATEFUL),
        )])
        with patch('dlux.management.commands.dlux_doctor.doctor.run_checks', return_value=report), \
                patch.object(doctor.Context, 'cache_available', new_callable=PropertyMock, return_value=cache_up), \
                patch.object(doctor.Context, 'cache_error', new_callable=PropertyMock,
                             return_value='no answer within 10.0 s'):
            output, _ = run_command('--format', 'json', '--apply', '--allow-stateful')
        return json.loads(output)['applied_fixes'][0]

    def test_stateful_fixes_are_skipped_while_the_cache_is_down(self):
        record = self._run(cache_up=False)
        self.assertEqual(record['status'], 'skipped')
        self.assertIn('cache is unreachable', record['error'])
        self.assertIn('no answer within 10.0 s', record['error'])

    def test_they_run_when_the_cache_answers(self):
        self.assertEqual(self._run(cache_up=True)['status'], 'succeeded')


class DoctorConnectionIsolationTests(TestCase):
    """An abandoned check must never hold a connection this thread uses next:
    --apply runs the migrator here, with no deadline."""

    def test_a_worker_opens_its_own_connection_outside_a_transaction(self):
        from django.db import connections

        main = connections['default']
        with patch.object(main, 'in_atomic_block', False):
            outcome = doctor._Runner().run(lambda: connections['default'] is main, 5)
        self.assertIs(outcome.value, False)

    def test_a_worker_shares_a_connection_held_in_a_transaction(self):
        from django.db import connections

        main = connections['default']
        self.assertTrue(main.in_atomic_block)
        outcome = doctor._Runner().run(lambda: connections['default'] is main, 5)
        self.assertIs(outcome.value, True)
