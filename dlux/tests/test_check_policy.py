"""The update check interval, and a manual check that asks Composer first."""

import json
import tempfile
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from dlux.models.settings import SystemSettings
from dlux.models.updater import DluxUpdateRun, DluxUpdateState
from dlux.updater import UpdaterError, check_policy
from dlux.updater.package_request import availability_path
from dlux.updater.runtime import RuntimeStore
from dlux.updater.service import (
    UpdateService, get_ui_state, queue_run, reconcile_check_policy, set_check_interval,
)


class IntervalValidationTests(SimpleTestCase):
    def test_every_offered_choice_is_accepted(self):
        for minutes in check_policy.INTERVAL_CHOICES_MINUTES:
            self.assertEqual(check_policy.normalize_interval(str(minutes)), minutes)

    def test_anything_else_is_refused(self):
        for value in ("0", "7", "-15", "abc", "", None, "15.5"):
            with self.subTest(value=value), self.assertRaises(UpdaterError):
                check_policy.normalize_interval(value)

    def test_the_default_is_an_offered_choice(self):
        self.assertIn(check_policy.DEFAULT_INTERVAL_MINUTES, check_policy.INTERVAL_CHOICES_MINUTES)


class CheckPolicyPublicationTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = RuntimeStore(self._tmp.name).ensure()
        self.service = mock.Mock(store=self.store)
        DluxUpdateState.load()

    def _published(self):
        return json.loads(check_policy.policy_path(self.store).read_text(encoding="utf-8"))

    def test_the_worker_publishes_the_default_in_seconds(self):
        self.assertEqual(reconcile_check_policy(self.service), 15)
        self.assertEqual(self._published()["interval_seconds"], 900)
        self.assertEqual(self._published()["schema_version"], 1)

    def test_a_changed_column_is_republished(self):
        reconcile_check_policy(self.service)
        set_check_interval(5, username="admin")
        reconcile_check_policy(self.service)
        self.assertEqual(self._published()["interval_seconds"], 300)

    def test_an_unchanged_policy_is_not_rewritten(self):
        reconcile_check_policy(self.service)
        first = self._published()["published_at"]
        reconcile_check_policy(self.service)
        self.assertEqual(self._published()["published_at"], first)

    def test_the_ui_state_carries_the_interval_and_its_choices(self):
        set_check_interval(60)
        state = get_ui_state()
        self.assertEqual(state["check_interval_minutes"], 60)
        self.assertEqual(state["check_interval_choices"], list(check_policy.INTERVAL_CHOICES_MINUTES))


@override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
class IntervalViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="root", email="root@example.com", password="pw-root-1234",
        )
        self.staff = User.objects.create_user(
            username="staff", email="staff@example.com", password="pw-staff-1234", is_staff=True,
        )
        settings_row = SystemSettings.load()
        settings_row.is_configured = True
        settings_row.save()
        DluxUpdateState.load()
        self.url = reverse("dlux_update_interval")

    def test_a_superuser_sets_the_interval_on_a_read_only_mount(self):
        client = Client()
        client.force_login(self.superuser)
        erofs = OSError(30, "Read-only file system")
        with mock.patch("dlux.updater.channel._atomic_json", side_effect=erofs):
            response = client.post(self.url, {"minutes": "30"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"]["check_interval_minutes"], 30)
        self.assertEqual(DluxUpdateState.load().check_interval_minutes, 30)

    def test_an_unsupported_interval_is_rejected(self):
        client = Client()
        client.force_login(self.superuser)
        response = client.post(self.url, {"minutes": "7"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(DluxUpdateState.load().check_interval_minutes, 15)

    def test_a_non_superuser_cannot_change_it(self):
        client = Client()
        client.force_login(self.staff)
        response = client.post(self.url, {"minutes": "5"})
        self.assertIn(response.status_code, (302, 403, 404))
        self.assertEqual(DluxUpdateState.load().check_interval_minutes, 15)


@override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
class ManualCheckRequestTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="checker", email="c@example.com", password="pw-1234-abcd",
        )
        DluxUpdateState.objects.filter(pk=1).delete()
        DluxUpdateState.load()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = RuntimeStore(self._tmp.name).ensure()
        self.service = UpdateService(store=self.store)
        availability_path(self.store).write_text(json.dumps({
            "available": True, "version": "99.0.0", "inline_safe": True, "reason": "",
        }), encoding="utf-8")

    def _queue(self):
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=self._tmp.name):
            run = queue_run(DluxUpdateRun.ACTION_CHECK, self.user.username)
            self.service.process_next()
        run.refresh_from_db()
        return run

    def test_a_check_asks_composer_and_waits(self):
        run = self._queue()
        request = json.loads(check_policy.request_path(self.store).read_text(encoding="utf-8"))
        self.assertEqual(request["token"], run.token)
        self.assertEqual(run.status, DluxUpdateRun.STATUS_CHECKING)
        self.assertTrue(run.is_active)
        self.assertIsNone(self.service.tick_check_request())
        self.assertEqual(DluxUpdateState.load().latest_version, "")

    def test_the_acknowledged_report_finishes_the_run(self):
        run = self._queue()
        check_policy.ack_path(self.store).write_text(json.dumps({"token": run.token}), encoding="utf-8")
        self.service.tick_check_request()
        run.refresh_from_db()
        self.assertEqual(run.status, DluxUpdateRun.STATUS_COMPLETED)
        state = DluxUpdateState.load()
        self.assertEqual(state.latest_version, "99.0.0")
        self.assertTrue(state.latest_compatible)

    def test_an_ack_for_another_check_is_not_this_ones(self):
        run = self._queue()
        check_policy.ack_path(self.store).write_text(json.dumps({"token": "older"}), encoding="utf-8")
        self.assertIsNone(self.service.tick_check_request())
        run.refresh_from_db()
        self.assertEqual(run.status, DluxUpdateRun.STATUS_CHECKING)

    def test_an_older_composer_that_never_answers_falls_back_to_its_last_report(self):
        run = self._queue()
        expired = timezone.now() - timedelta(seconds=check_policy.REQUEST_TIMEOUT_SECONDS + 1)
        DluxUpdateRun.objects.filter(pk=run.pk).update(report={"check_requested_at": expired.isoformat()})
        self.service.tick_check_request()
        run.refresh_from_db()
        self.assertEqual(run.status, DluxUpdateRun.STATUS_COMPLETED)
        self.assertIn("did not answer", run.progress_log)
        self.assertEqual(DluxUpdateState.load().latest_version, "99.0.0")

    def test_an_unwritable_request_reads_the_last_report_at_once(self):
        with mock.patch("dlux.updater.check_policy.write_request", side_effect=OSError("ro")):
            run = self._queue()
        self.assertEqual(run.status, DluxUpdateRun.STATUS_COMPLETED)
