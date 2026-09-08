"""The release channel: eligibility, the policy handoff, and the Options view.

Stable is the default and beta is an explicit opt-in, so most of these tests are
about what does NOT happen — a prerelease that is not offered, a corrupt file
that does not turn beta on, an opt-out that does not walk a deployment backwards.
"""

import json
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from dlux.models.settings import SystemSettings
from dlux.models.updater import DluxUpdateState
from dlux.updater import UpdaterError, channel
from dlux.updater.manifest import select_latest_candidate
from dlux.updater.release_check import changelog_section, classify_tag
from dlux.updater.runtime import RuntimeStore
from dlux.updater.service import (
    channel_status,
    selected_channel,
    set_update_channel,
)


def _index(*versions):
    return {
        "files": [
            {
                "filename": f"django_lux-{v}-py3-none-any.whl",
                "url": f"https://files.pythonhosted.org/p/django_lux-{v}-py3-none-any.whl",
                "hashes": {"sha256": "a" * 64},
            }
            for v in versions
        ]
    }


class EligibilityTests(SimpleTestCase):
    def test_stable_is_the_default_and_excludes_prereleases(self):
        chosen = select_latest_candidate(_index("1.8.14", "1.9.0b1"), "1.8.13")
        self.assertEqual(chosen.version, "1.8.14")

    def test_beta_admits_a_prerelease(self):
        chosen = select_latest_candidate(
            _index("1.8.14", "1.9.0b1"), "1.8.13", allow_prereleases=True,
        )
        self.assertEqual(chosen.version, "1.9.0b1")

    def test_beta_still_prefers_a_newer_final(self):
        # "Include beta releases" widens eligibility; it does not mean a beta
        # outranks a final that is genuinely newer.
        chosen = select_latest_candidate(
            _index("1.9.0b1", "1.9.0"), "1.8.14", allow_prereleases=True,
        )
        self.assertEqual(chosen.version, "1.9.0")

    def test_opting_out_on_a_beta_offers_nothing_rather_than_downgrading(self):
        # The deployment runs 1.9.0b2 and the admin turns beta off. Only 1.8.14
        # is published as stable, and offering it would be a downgrade — which
        # is the explicit rollback path's job, not the update check's.
        self.assertIsNone(select_latest_candidate(_index("1.8.14"), "1.9.0b2"))

    def test_opting_out_on_a_beta_offers_the_final_when_it_exists(self):
        chosen = select_latest_candidate(_index("1.8.14", "1.9.0"), "1.9.0b2")
        self.assertEqual(chosen.version, "1.9.0")

    def test_a_later_beta_supersedes_an_earlier_one(self):
        chosen = select_latest_candidate(
            _index("1.9.0b2", "1.9.0b10"), "1.9.0b1", allow_prereleases=True,
        )
        self.assertEqual(chosen.version, "1.9.0b10", "b10 is newer than b2")

    def test_skipping_still_applies_on_the_beta_channel(self):
        chosen = select_latest_candidate(
            _index("1.9.0b1", "1.9.0b2"), "1.8.14",
            skip_versions=["1.9.0b2"], allow_prereleases=True,
        )
        self.assertEqual(chosen.version, "1.9.0b1")

    def test_development_releases_are_never_eligible(self):
        self.assertIsNone(
            select_latest_candidate(_index("1.9.0.dev1"), "1.8.14", allow_prereleases=True)
        )


class PolicyFileTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.store = RuntimeStore(self.root).ensure()

    def test_an_unpublished_policy_reads_stable(self):
        self.assertEqual(channel.read_policy(self.store), (channel.STABLE, ""))

    def test_a_published_policy_round_trips(self):
        channel.publish_policy(self.store, channel.BETA, source="test")
        self.assertEqual(channel.read_policy(self.store), (channel.BETA, ""))

    def test_corrupting_the_policy_cannot_enable_beta(self):
        channel.policy_path(self.store).write_text("{ broken", encoding="utf-8")
        read, error = channel.read_policy(self.store)
        self.assertEqual(read, channel.STABLE)
        self.assertTrue(error)

    def test_a_future_schema_refuses_beta_and_says_why(self):
        channel.policy_path(self.store).write_text(
            json.dumps({"schema_version": 99, "channel": "beta"}), encoding="utf-8",
        )
        read, error = channel.read_policy(self.store)
        self.assertEqual(read, channel.STABLE)
        self.assertIn("schema 99", error)

    def test_publishing_requires_the_writable_store(self):
        # The guard against a web container writing a volume it mounts
        # read-only: without a store there is nothing to publish through.
        with self.assertRaises(UpdaterError):
            channel.publish_policy(None, channel.BETA)

    def test_an_unknown_channel_is_refused_not_coerced(self):
        with self.assertRaises(UpdaterError):
            channel.normalize_channel("nightly")

    def test_a_request_stays_pending_until_its_own_token_is_acked(self):
        request = channel.write_request(channel.BETA, store=self.store, requested_by="admin")
        self.assertEqual(channel.pending_request(self.store), channel.BETA)
        channel.write_ack(self.store, token="some-other-token", channel=channel.BETA)
        self.assertEqual(
            channel.pending_request(self.store), channel.BETA,
            "an ack for a different token must not clear this request",
        )
        channel.write_ack(self.store, token=request["token"], channel=channel.BETA)
        self.assertEqual(channel.pending_request(self.store), "")


class WorkerReconciliationTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.store = RuntimeStore(self.root).ensure()
        self.service = mock.Mock(store=self.store)
        DluxUpdateState.load()

    def _reconcile(self):
        from dlux.updater.service import reconcile_channel_policy

        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=str(self.root)):
            return reconcile_channel_policy(self.service)

    def test_a_deployment_starts_on_stable(self):
        self.assertEqual(selected_channel(), channel.STABLE)

    def test_the_worker_applies_a_pending_request_and_acknowledges_it(self):
        channel.write_request(channel.BETA, store=self.store, requested_by="admin")
        self.assertEqual(self._reconcile(), channel.BETA)
        self.assertEqual(DluxUpdateState.load().update_channel, channel.BETA)
        self.assertEqual(channel.read_policy(self.store)[0], channel.BETA)
        self.assertTrue(channel.read_ack(self.store)["applied"])
        self.assertEqual(channel.pending_request(self.store), "")

    def test_the_worker_republishes_a_policy_that_went_missing(self):
        # The file lives on the runtime volume. A volume that was recreated
        # must not silently downgrade the deployment's recorded choice.
        DluxUpdateState.objects.filter(pk=1).update(update_channel=channel.BETA)
        self.assertEqual(self._reconcile(), channel.BETA)
        self.assertEqual(channel.read_policy(self.store)[0], channel.BETA)

    def test_the_database_column_wins_over_a_stale_mirror(self):
        channel.publish_policy(self.store, channel.BETA)
        DluxUpdateState.objects.filter(pk=1).update(update_channel=channel.STABLE)
        self.assertEqual(self._reconcile(), channel.STABLE)
        self.assertEqual(channel.read_policy(self.store)[0], channel.STABLE)

    def test_opting_out_drops_a_prerelease_offer_left_by_the_old_channel(self):
        DluxUpdateState.objects.filter(pk=1).update(
            update_channel=channel.BETA,
            latest_version="1.9.0b1",
            latest_compatible=True,
            active_version="1.8.14",
        )
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=str(self.root)):
            set_update_channel(channel.STABLE, username="admin", store=self.store)
        state = DluxUpdateState.load()
        self.assertFalse(state.latest_compatible, "a stale beta offer must not stay applicable")
        self.assertEqual(state.latest_version, "1.8.14")
        self.assertIn("prerelease", state.latest_reason)

    def test_opting_in_leaves_a_stable_offer_alone(self):
        DluxUpdateState.objects.filter(pk=1).update(
            update_channel=channel.STABLE,
            latest_version="1.8.14",
            latest_compatible=True,
            active_version="1.8.13",
        )
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=str(self.root)):
            set_update_channel(channel.BETA, username="admin", store=self.store)
        state = DluxUpdateState.load()
        self.assertTrue(state.latest_compatible)
        self.assertEqual(state.latest_version, "1.8.14")

    def test_web_leaves_a_request_instead_of_writing_the_policy(self):
        # Called without a store: the read-only side of the mount.
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=str(self.root)):
            state = set_update_channel(channel.BETA, username="admin")
            self.assertEqual(DluxUpdateState.load().update_channel, channel.BETA)
            self.assertEqual(channel.read_policy(self.store)[0], channel.STABLE)
            self.assertEqual(state["channel_pending"], channel.BETA)
            self.assertEqual(self._reconcile(), channel.BETA)
            self.assertEqual(channel_status()["channel_pending"], "")


@override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
class ComposerReportedPrereleaseTests(TestCase):
    """Composer resolves the candidate; DjangoLux still checks the channel.

    Both sides read the same policy file, so they normally agree. They can drift
    for a tick after an opt-out — the database column moves before the worker
    republishes the mirror — and the safe direction to drift is to offer less.
    """

    def setUp(self):
        from dlux.models.updater import DluxUpdateRun

        self.Run = DluxUpdateRun
        self.user = get_user_model().objects.create_superuser(
            username="channel-admin", email="a@example.com", password="pw-1234-abcd",
        )
        DluxUpdateState.load()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _check_with_report(self, version):
        import json as _json

        from dlux.updater.package_request import availability_path
        from dlux.updater.runtime import RuntimeStore
        from dlux.updater.service import UpdateService, queue_run

        store = RuntimeStore(self._tmp.name).ensure()
        availability_path(store).write_text(
            _json.dumps({
                "available": True, "version": version, "inline_safe": True, "reason": "",
            }),
            encoding="utf-8",
        )
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=self._tmp.name):
            queue_run(self.Run.ACTION_CHECK, self.user.username)
            UpdateService(store=store).process_next()
        return DluxUpdateState.load()

    def test_a_reported_prerelease_is_not_offered_on_stable(self):
        state = self._check_with_report("1.9.0b1")
        self.assertFalse(state.latest_compatible)
        self.assertIn("prerelease", state.latest_reason)

    def test_the_same_report_is_offered_once_beta_is_on(self):
        DluxUpdateState.objects.filter(pk=1).update(update_channel=channel.BETA)
        state = self._check_with_report("1.9.0b1")
        self.assertTrue(state.latest_compatible)
        self.assertEqual(state.latest_version, "1.9.0b1")

    def test_a_reported_final_is_offered_on_either_channel(self):
        state = self._check_with_report("99.0.0")
        self.assertTrue(state.latest_compatible)


@override_settings(DLUX_INLINE_UPDATES_ENABLED=True)
class ChannelViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="root", email="root@example.com", password="pw-root-1234",
        )
        self.staff = User.objects.create_user(
            username="staff", email="staff@example.com", password="pw-staff-1234",
            is_staff=True,
        )
        # Without this the setup wizard intercepts every request with a redirect
        # and each assertion below would be testing the wizard, not the view.
        settings_row = SystemSettings.load()
        settings_row.is_configured = True
        settings_row.save()
        DluxUpdateState.load()
        self.url = reverse("dlux_update_channel")

    def test_a_superuser_can_opt_in(self):
        client = Client()
        client.force_login(self.superuser)
        response = client.post(self.url, {"channel": "beta"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"]["update_channel"], "beta")
        self.assertEqual(DluxUpdateState.load().update_channel, "beta")

    def test_the_checkbox_shape_is_accepted(self):
        client = Client()
        client.force_login(self.superuser)
        client.post(self.url, {"beta": "on"})
        self.assertEqual(DluxUpdateState.load().update_channel, "beta")
        client.post(self.url, {"beta": ""})
        self.assertEqual(DluxUpdateState.load().update_channel, "stable")

    def test_an_unknown_channel_is_rejected(self):
        client = Client()
        client.force_login(self.superuser)
        response = client.post(self.url, {"channel": "nightly"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(DluxUpdateState.load().update_channel, "stable")

    def test_a_non_superuser_cannot_change_the_channel(self):
        client = Client()
        client.force_login(self.staff)
        response = client.post(self.url, {"channel": "beta"})
        self.assertIn(response.status_code, (302, 403, 404))
        self.assertEqual(DluxUpdateState.load().update_channel, "stable")

    def test_get_is_not_a_mutation(self):
        client = Client()
        client.force_login(self.superuser)
        self.assertEqual(client.get(self.url).status_code, 405)


class ReleaseTagTests(SimpleTestCase):
    def test_a_plain_version_is_stable_and_claims_latest(self):
        decision = classify_tag("v1.8.14")
        self.assertEqual(decision["channel"], "stable")
        self.assertTrue(decision["make_latest"])

    def test_a_beta_tag_is_a_prerelease_and_never_latest(self):
        decision = classify_tag("v1.8.14b1")
        self.assertEqual(decision["channel"], "beta")
        self.assertTrue(decision["prerelease"])
        self.assertFalse(decision["make_latest"])

    def test_release_candidates_publish_through_beta(self):
        self.assertEqual(classify_tag("v1.9.0rc1")["channel"], "beta")

    def test_non_canonical_and_unpublishable_tags_are_refused(self):
        for tag in ("1.8.14", "v1.9.0-beta1", "v1.9.0.dev1", "v1.9.0+local", "v1.9.0.post1"):
            with self.assertRaises(RuntimeError, msg=tag):
                classify_tag(tag)

    def test_a_tag_that_disagrees_with_the_manifest_is_refused(self):
        with self.assertRaises(RuntimeError):
            classify_tag("v1.9.0", manifest_version="1.8.14")

    def test_the_stable_changelog_section_is_not_its_betas(self):
        # A prefix match on "## v1.8.14" also matches "## v1.8.14b1", so the
        # stable release would publish its beta's notes and look correct.
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "CHANGELOG.md"
            path.write_text(
                "# Changelog\n\n## v1.8.14\n\nfinal notes\n\n"
                "## v1.8.14b1\n\nbeta notes\n\n## v1.8.13\n\nolder\n",
                encoding="utf-8",
            )
            self.assertEqual(changelog_section("1.8.14", path), "final notes")
            self.assertEqual(changelog_section("1.8.14b1", path), "beta notes")
            self.assertEqual(changelog_section("9.9.9", path), "")
