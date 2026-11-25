"""The 1.17 break-it run's runtime findings: a hung cache, an image below the
release floor, model caches across an upgrade, and an unverified update.

#8   A paused Redis hung sign-in for 80 s and then answered 500.
#11  An image older than the active release's floor still ran that release.
#15  An upgrade unpickled model instances another Django version wrote.
S5   Composer's success ack completed a run whose release was not active.
"""
from dlux.tests.harness import setup_test_environment

setup_test_environment()

import io
import json
import socket
import threading
import time
from contextlib import redirect_stderr
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import path
from django.utils import timezone

from dlux import __version__
from dlux.updater import get_baked_version, package_request
from dlux.updater.runtime import RuntimeStore

from .version_helpers import newer_version


OLD_SCAFFOLD_CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://:secret@redis:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 20,
            "CONNECTION_POOL_KWARGS": {"max_connections": 50},
        },
    }
}


def _settings_scope(**extra):
    import copy

    return {
        "SECRET_KEY": "x" * 50,
        "INSTALLED_APPS": [],
        "MIDDLEWARE": [
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
        ],
        "TEMPLATES": [],
        "CACHES": copy.deepcopy(OLD_SCAFFOLD_CACHES),
        "DLUX_ISOLATE_TEST_CACHE": False,
        **extra,
    }


class HungServer:
    """A TCP port that accepts connections and never answers: a paused Redis."""

    def __enter__(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(64)
        self.port = self.socket.getsockname()[1]
        return self

    def __exit__(self, *exc):
        self.socket.close()

    def caches(self, timeout=0.3):
        return {
            "default": {
                "BACKEND": "dlux.resilient_cache.FailFastRedisCache",
                "LOCATION": f"redis://127.0.0.1:{self.port}/1",
                "OPTIONS": {
                    "CLIENT_CLASS": "django_redis.client.DefaultClient",
                    "SOCKET_CONNECT_TIMEOUT": timeout,
                    "SOCKET_TIMEOUT": timeout,
                },
            }
        }


class CacheSettingsTests(SimpleTestCase):
    """#8: projects never regenerate settings.py, so dlux_settings() applies it."""

    def test_an_old_scaffold_cache_is_capped_and_fails_fast(self):
        from dlux.utils.settings import dlux_settings

        scope = dlux_settings(_settings_scope())
        default = scope["CACHES"]["default"]
        self.assertEqual(default["BACKEND"], "dlux.resilient_cache.FailFastRedisCache")
        self.assertEqual(default["OPTIONS"]["SOCKET_CONNECT_TIMEOUT"], 2.0)
        self.assertEqual(default["OPTIONS"]["SOCKET_TIMEOUT"], 2.0)
        self.assertEqual(default["OPTIONS"]["CONNECTION_POOL_KWARGS"], {"max_connections": 50})
        self.assertEqual(scope["MIDDLEWARE"][:2], [
            "dlux.cache_outage.CacheOutageMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
        ])

    def test_a_shorter_timeout_is_kept_and_the_cap_is_configurable(self):
        from dlux.utils.settings import dlux_settings

        scope = _settings_scope(DLUX_CACHE_SOCKET_TIMEOUT=1)
        scope["CACHES"]["default"]["OPTIONS"]["SOCKET_TIMEOUT"] = 0.5
        scope = dlux_settings(scope)
        options = scope["CACHES"]["default"]["OPTIONS"]
        self.assertEqual(options["SOCKET_TIMEOUT"], 0.5)
        self.assertEqual(options["SOCKET_CONNECT_TIMEOUT"], 1.0)

    def test_the_opt_out_keeps_the_cache_as_written(self):
        from dlux.utils.settings import dlux_settings

        scope = dlux_settings(_settings_scope(DLUX_CACHE_FAIL_FAST=False))
        self.assertEqual(scope["CACHES"], OLD_SCAFFOLD_CACHES)
        self.assertNotIn("dlux.cache_outage.CacheOutageMiddleware", scope["MIDDLEWARE"])

    def test_other_backends_are_left_alone(self):
        from dlux.utils.settings import dlux_settings

        locmem = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
        scope = dlux_settings(_settings_scope(CACHES=locmem))
        self.assertEqual(scope["CACHES"], locmem)
        self.assertNotIn("dlux.cache_outage.CacheOutageMiddleware", scope["MIDDLEWARE"])

    def test_applying_twice_changes_nothing_more(self):
        from dlux.utils.settings import dlux_settings

        scope = dlux_settings(dlux_settings(_settings_scope()))
        self.assertEqual(scope["MIDDLEWARE"].count("dlux.cache_outage.CacheOutageMiddleware"), 1)


class FailFastBackendTests(SimpleTestCase):
    """#8 / F4: one short wait per outage, then no waiting at all."""

    def setUp(self):
        from dlux.resilient_cache import reset_breakers

        reset_breakers()
        self.addCleanup(reset_breakers)

    def _backend(self, server):
        from django_redis.cache import RedisCache  # noqa: F401 - django_redis must exist
        from dlux.resilient_cache import FailFastRedisCache

        config = server.caches()["default"]
        return FailFastRedisCache(config["LOCATION"], {"OPTIONS": config["OPTIONS"]})

    def test_a_paused_cache_costs_one_timeout_then_fails_at_once(self):
        from dlux.resilient_cache import CacheUnavailable

        with HungServer() as server, self.assertLogs("dlux.cache", level="WARNING") as logged:
            backend = self._backend(server)
            started = time.monotonic()
            with self.assertRaises(CacheUnavailable):
                backend.get("key")
            first = time.monotonic() - started
            started = time.monotonic()
            for _ in range(20):
                with self.assertRaises(CacheUnavailable):
                    backend.set("key", "value")
            following = time.monotonic() - started
        self.assertLess(first, 2.0)
        self.assertLess(following, 0.2, "an open breaker must not touch the network")
        self.assertEqual(len(logged.output), 1, "one warning per outage, not per operation")
        self.assertNotIn("secret", "\n".join(logged.output))

    def test_the_breaker_is_shared_across_backend_instances(self):
        """Django builds a cache object per thread; the outage is per server."""
        from dlux.resilient_cache import CacheUnavailable

        with HungServer() as server, self.assertLogs("dlux.cache", level="WARNING"):
            with self.assertRaises(CacheUnavailable):
                self._backend(server).get("key")
            started = time.monotonic()
            with self.assertRaises(CacheUnavailable):
                self._backend(server).get("key")
            self.assertLess(time.monotonic() - started, 0.1)

    def test_safe_reads_treat_an_outage_as_a_miss(self):
        from dlux.resilient_cache import safe_delete, safe_get, safe_set

        with HungServer() as server, self.assertLogs("dlux.cache", level="WARNING"):
            backend = self._backend(server)
            self.assertEqual(safe_get("key", "fallback", cache=backend), "fallback")
            self.assertFalse(safe_set("key", "value", 5, cache=backend))
            self.assertFalse(safe_delete("key", cache=backend))

    def test_a_cache_outage_is_recognised_through_its_cause(self):
        from redis.exceptions import TimeoutError as RedisTimeout

        from dlux.resilient_cache import is_cache_outage

        try:
            try:
                raise RedisTimeout("Timeout reading from redis:6379")
            except RedisTimeout as exc:
                raise RuntimeError("wrapped") from exc
        except RuntimeError as wrapped:
            self.assertTrue(is_cache_outage(wrapped))
        self.assertFalse(is_cache_outage(TimeoutError("a socket that is not the cache")))
        self.assertFalse(is_cache_outage(ValueError("x")))


def _raise_outage(request):
    from dlux.resilient_cache import CacheUnavailable

    raise CacheUnavailable("The cache at redis:6379 did not answer.")


class _SessionSaveFails:
    """An inner middleware failing the way SessionMiddleware does on save."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        _raise_outage(request)
        return response


urlpatterns = [
    path("outage/", _raise_outage),
    path("fine/", lambda request: HttpResponse("ok")),
]


@override_settings(
    ROOT_URLCONF=__name__,
    MIDDLEWARE=["dlux.cache_outage.CacheOutageMiddleware"],
)
class CacheOutageMiddlewareTests(SimpleTestCase):
    def test_a_view_failing_on_the_cache_answers_503(self):
        with self.assertLogs("dlux.cache", level="WARNING"):
            response = Client(raise_request_exception=False).get("/outage/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Retry-After"], "10")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("not responding", response.content.decode())

    @override_settings(MIDDLEWARE=[
        "dlux.cache_outage.CacheOutageMiddleware",
        "dlux.tests.test_runtime_resilience._SessionSaveFails",
    ])
    def test_a_middleware_failing_on_the_cache_answers_503(self):
        with self.assertLogs("django.request", level="ERROR"):
            response = Client(raise_request_exception=False).get("/fine/")
        self.assertEqual(response.status_code, 503)

    def test_ajax_gets_json(self):
        with self.assertLogs("dlux.cache", level="WARNING"):
            response = Client(raise_request_exception=False).get(
                "/outage/", HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["success"])

    def test_other_errors_stay_errors(self):
        self.assertEqual(Client().get("/fine/").status_code, 200)


class SignInDuringCacheOutageTests(TestCase):
    """Log 29: with Redis paused, sign-in returned 500 after 80 s."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from dlux.resilient_cache import reset_breakers

        reset_breakers()
        self.addCleanup(reset_breakers)
        self.user = get_user_model().objects.create_user("outage-user", password="pw-123456")

    def test_sign_in_fails_fast_and_clearly(self):
        from dlux.models import SystemSettings

        settings_row = SystemSettings.load()
        settings_row.is_configured = True
        settings_row.save()
        with HungServer() as server, override_settings(
            CACHES=server.caches(),
            SESSION_ENGINE="django.contrib.sessions.backends.cache",
            MIDDLEWARE=["dlux.cache_outage.CacheOutageMiddleware", *settings.MIDDLEWARE],
        ), self.assertLogs("dlux", level="WARNING"):
            client = Client(raise_request_exception=False)
            started = time.monotonic()
            response = client.post("/accounts/login/", {"username": "outage-user", "password": "pw-123456"})
            elapsed = time.monotonic() - started
        self.assertEqual(response.status_code, 503)
        self.assertLess(elapsed, 5.0)
        self.assertIn("not responding", response.content.decode())


def _write_release(store, version, floor=None):
    package = store.release_path(version) / "dlux"
    package.mkdir(parents=True)
    manifest = {"schema_version": 2, "version": version}
    if floor:
        manifest["requires"] = {"baked_image": f">={floor}"}
    (package / "release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return package.parent


class ImageFloorSupervisorTests(SimpleTestCase):
    """#11: runtime 1.16.6b1 ran inside the 1.15.1 image (log 35)."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = RuntimeStore(Path(self._tmp.name)).ensure()

    def test_a_release_above_the_image_floor_is_not_served(self):
        from dlux.updater import supervisor

        release = _write_release(self.store, "1.17.2", floor="1.17.0")
        self.store.write_active("1.17.2", source="volume", generation=1)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertIsNone(supervisor.resolve_release(self.store.root, "1.16.6"))
            self.assertIsNone(supervisor.resolve_release(self.store.root, "1.16.6"))
        self.assertEqual(stderr.getvalue().count("dlux runtime:"), 1)
        self.assertIn("1.17.0", stderr.getvalue())
        self.assertIn("1.16.6", stderr.getvalue())
        self.assertEqual(supervisor.resolve_release(self.store.root, "1.17.0"), release.resolve())
        self.assertIn("1.17.0", supervisor.runtime_fallback(self.store.root, "1.16.6"))
        self.assertEqual(supervisor.runtime_fallback(self.store.root, "1.17.1"), "")

    def test_the_child_environment_follows_the_floor(self):
        from dlux.updater import supervisor

        _write_release(self.store, "1.17.2", floor="1.17.0")
        self.store.write_active("1.17.2", source="volume", generation=1)
        with mock.patch.dict("os.environ", {"DLUX_BAKED_VERSION": "1.16.6", "PYTHONPATH": ""}):
            with redirect_stderr(io.StringIO()):
                env = supervisor.runtime_environment(self.store.root)
        self.assertNotIn("1.17.2", env.get("PYTHONPATH", ""))

    def test_a_release_without_a_floor_is_served_as_before(self):
        from dlux.updater import supervisor

        release = _write_release(self.store, "1.17.2")
        self.store.write_active("1.17.2", source="volume", generation=1)
        self.assertEqual(supervisor.resolve_release(self.store.root, "1.16.6"), release.resolve())

    def test_read_active_reports_the_baked_release_and_what_is_held(self):
        _write_release(self.store, "1.17.2", floor="1.17.0")
        self.store.write_active("1.17.2", source="volume", generation=1)
        active = self.store.read_active("1.16.6")
        self.assertEqual(active["version"], "1.16.6")
        self.assertEqual(active["source"], "image")
        self.assertEqual(active["held"]["version"], "1.17.2")
        self.assertEqual(self.store.recorded_version(), "1.17.2", "the pointer is kept")


class ImageFloorReconcileTests(TestCase):
    def setUp(self):
        from django.apps import apps

        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = RuntimeStore(Path(self._tmp.name)).ensure()
        self.State = apps.get_model("dlux", "DluxUpdateState")
        self.baked = get_baked_version()
        self.release = newer_version(self.baked)
        self.floor = newer_version(self.baked)
        _write_release(self.store, self.release, floor=self.floor)
        self.store.write_active(self.release, source="volume", generation=3)
        self.store.set_generation(3)
        state = self.State.load()
        state.baked_version = self.baked
        state.active_version = self.release
        state.generation = 3
        state.save()

    def _reconcile(self, baked):
        from dlux.updater.service import UpdateService

        with mock.patch("dlux.updater.service.get_baked_version", return_value=baked):
            return UpdateService(store=self.store).reconcile()

    def test_an_image_below_the_floor_is_reported_and_the_pointer_kept(self):
        with self.assertLogs("dlux.updater", level="WARNING"):
            state = self._reconcile(self.baked)
        self.assertEqual(state.active_version, self.baked)
        self.assertTrue(state.degraded)
        self.assertIn(self.floor, state.degraded_reason)
        self.assertIn(self.release, state.degraded_reason)
        self.assertEqual(self.store.recorded_version(), self.release)
        self.assertFalse(self.store.degraded_file.exists(), "the worker's health check stays green")

        state = self._reconcile(self.floor)
        self.assertFalse(state.degraded)
        self.assertEqual(state.degraded_reason, "")

    def test_dlux_reconcile_says_so_and_keeps_the_pointer(self):
        from django.core.management import call_command

        stderr = io.StringIO()
        with override_settings(DLUX_UPDATE_RUNTIME_ROOT=str(self.store.root)), mock.patch(
            "dlux.management.commands.dlux_reconcile.get_baked_version", return_value=self.baked,
        ):
            call_command("dlux_reconcile", stderr=stderr, stdout=io.StringIO())
        self.assertIn("is not served", stderr.getvalue())
        self.assertEqual(self.store.recorded_version(), self.release)

    def test_an_image_update_below_the_floor_is_refused(self):
        """The gate read `active_manifest.image_baseline`, which holds release
        notes only, so it never refused anything."""
        from dlux.updater.image_update import assess_image_candidate

        release = newer_version(self.release)
        _write_release(self.store, release, floor=self.baked)
        self.store.write_active(release, source="volume", generation=4)
        state = self.State.load()
        verdict = assess_image_candidate("1.0.0", state, store=self.store)
        self.assertEqual(verdict["verdict"], "abort")
        self.assertEqual(verdict["image_baseline"], self.baked)
        self.assertEqual(assess_image_candidate(self.baked, state, store=self.store)["verdict"], "keep")


class SingletonCacheAcrossUpgradeTests(TestCase):
    """#15: "Pickled model instance's Django version 6.1.2 does not match" (log 19)."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def _row(self, home_url):
        from dlux.models import SystemSettings

        row = SystemSettings.load()
        row.home_url = home_url
        row.save()
        return SystemSettings

    def test_the_cache_holds_field_values_not_a_pickled_model(self):
        from django.db import models

        SystemSettings = self._row("/now/")
        payload = cache.get(SystemSettings.cache_key())
        self.assertIsInstance(payload, dict)
        self.assertFalse(any(isinstance(value, models.Model) for value in payload["fields"].values()))
        self.assertIn(__version__, payload["token"])

    def test_an_entry_another_version_wrote_is_a_miss(self):
        SystemSettings = self._row("/now/")
        payload = cache.get(SystemSettings.cache_key())
        payload["token"] = "1.16.6|6.1.2"
        payload["fields"]["home_url"] = "/stale/"
        cache.set(SystemSettings.cache_key(), payload)
        self.assertEqual(SystemSettings.load().home_url, "/now/")
        self.assertEqual(cache.get(SystemSettings.cache_key())["token"], SystemSettings._cache_token())

    def test_an_instance_an_older_release_pickled_is_replaced(self):
        SystemSettings = self._row("/now/")
        stale = SystemSettings.objects.get(pk=1)
        stale.home_url = "/stale/"
        cache.set("SystemSettings", stale)
        self.assertEqual(SystemSettings.load().home_url, "/now/")
        self.assertIsInstance(cache.get("SystemSettings"), dict)

    def test_an_entry_missing_a_field_is_a_miss(self):
        SystemSettings = self._row("/now/")
        payload = cache.get(SystemSettings.cache_key())
        del payload["fields"]["home_url"]
        cache.set(SystemSettings.cache_key(), payload)
        self.assertEqual(SystemSettings.load().home_url, "/now/")

    def test_sessions_survive_a_version_change(self):
        """Users stay signed in across an update: session keys are not versioned."""
        from django.contrib.sessions.backends.cache import SessionStore
        from dlux.models import SystemSettings

        session = SessionStore()
        session["user"] = "kept"
        session.save()
        with mock.patch.object(SystemSettings, "_cache_token", return_value="1.17.1|6.2"):
            self.assertEqual(SessionStore(session.session_key).load().get("user"), "kept")


class _VersionHandler(BaseHTTPRequestHandler):
    version = ""
    token = ""

    def do_GET(self):
        if self.headers.get("X-Dlux-Updater-Probe") != self.token:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps({"ok": True, "version": self.version}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class WebProbe:
    def __init__(self, version):
        from dlux.updater.health import runtime_probe_token

        handler = type("Handler", (_VersionHandler,), {
            "version": version, "token": runtime_probe_token(settings.SECRET_KEY),
        })
        self.server = HTTPServer(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


class WebProbeTests(SimpleTestCase):
    def test_web_reports_its_version(self):
        from dlux.updater.service import probe_web_version

        with WebProbe("1.17.0") as web, override_settings(DLUX_UPDATE_WEB_URL=web.url):
            self.assertEqual(probe_web_version(), ("1.17.0", ""))

    def test_no_address_outside_a_generated_stack(self):
        from dlux.updater.service import probe_web_version

        with mock.patch.dict("os.environ", {}, clear=False) as env:
            env.pop("DLUX_STACK_SCHEMA", None)
            env.pop("DLUX_UPDATE_WEB_URL", None)
            version, problem = probe_web_version()
        self.assertEqual(version, "")
        self.assertIn("DLUX_UPDATE_WEB_URL", problem)


class HandoffVerificationTests(TestCase):
    """S5: Composer's exit 0 completed the run although reconcile kept another
    release active."""

    def setUp(self):
        from django.apps import apps

        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.store = RuntimeStore(root / "runtime").ensure()
        self.base_dir = root / "project"
        self.base_dir.mkdir()
        (self.base_dir / "manage.py").write_text("# generated\n", encoding="utf-8")
        self.Run = apps.get_model("dlux", "DluxUpdateRun")
        self.State = apps.get_model("dlux", "DluxUpdateState")
        self.baked = get_baked_version()

    def _run(self, target, action=None, source=""):
        run = self.Run.objects.create(
            action=action or self.Run.ACTION_APPLY,
            status=self.Run.STATUS_APPLYING,
            is_active=True,
            target_version=target,
            source_version=source,
            started_at=timezone.now(),
        )
        state = self.State.load()
        state.active_run_token = run.token
        state.save(update_fields=["active_run_token"])
        package_request.ack_path(self.store).write_text(
            json.dumps({"token": run.token, "exit_code": 0}), encoding="utf-8",
        )
        return run

    def _tick(self, *, running=None, web=("", "no web address to probe")):
        from dlux.updater.service import UpdateService

        class _Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        service = UpdateService(store=self.store, command_runner=lambda *a, **k: _Completed())
        with override_settings(BASE_DIR=self.base_dir), mock.patch(
            "dlux.updater.service.running_version", return_value=running or self.baked,
        ), mock.patch("dlux.updater.service.probe_web_version", return_value=web):
            return service.tick_package_update()

    def _activate(self, version):
        _write_release(self.store, version)
        self.store.write_active(version, source="volume", generation=self.store.read_generation() + 1)
        self.store.set_generation(self.store.read_generation() + 1)

    def test_an_ack_for_a_release_that_is_not_active_fails_the_run(self):
        """The S5 reproduction: a newer image is baked, the older target is not."""
        run = self._run("1.8.8")
        finished = self._tick()
        finished.refresh_from_db()
        self.assertEqual(finished.status, self.Run.STATUS_FAILED)
        self.assertIn("1.8.8", finished.error)
        self.assertIn(self.baked, finished.error)
        self.assertFalse(finished.is_active)
        self.assertEqual(self.State.load().active_run_token, "")

    def test_the_active_release_run_by_every_process_completes(self):
        target = newer_version(self.baked)
        self._activate(target)
        run = self._run(target)
        finished = self._tick(running=target, web=(target, ""))
        finished.refresh_from_db()
        self.assertEqual(finished.status, self.Run.STATUS_COMPLETED)
        self.assertEqual(finished.report["active_version"], target)
        self.assertEqual(finished.report["worker_version"], target)
        self.assertEqual(finished.report["web_version"], target)

    def test_a_process_still_on_the_old_release_is_waited_for_then_failed(self):
        target = newer_version(self.baked)
        self._activate(target)
        run = self._run(target)
        self.assertIsNone(self._tick(running=target, web=(self.baked, "")))
        run.refresh_from_db()
        self.assertTrue(run.is_active)
        self.assertEqual(run.status, self.Run.STATUS_APPLYING)

        report = dict(run.report)
        report["verify_since"] = (timezone.now() - timedelta(minutes=10)).isoformat()
        self.Run.objects.filter(pk=run.pk).update(report=report)
        finished = self._tick(running=target, web=(self.baked, ""))
        finished.refresh_from_db()
        self.assertEqual(finished.status, self.Run.STATUS_FAILED)
        self.assertIn(f"web runs {self.baked}", finished.error)

    def test_a_worker_that_has_not_restarted_is_waited_for(self):
        target = newer_version(self.baked)
        self._activate(target)
        self._run(target)
        self.assertIsNone(self._tick(running=self.baked, web=(target, "")))

    def test_an_unreachable_web_is_recorded_not_failed(self):
        target = newer_version(self.baked)
        self._activate(target)
        self._run(target)
        finished = self._tick(running=target, web=("", "http://web:8000 did not answer"))
        finished.refresh_from_db()
        self.assertEqual(finished.status, self.Run.STATUS_COMPLETED)
        self.assertIn("did not answer", finished.progress_log)

    def test_a_rollback_that_left_the_source_active_fails(self):
        source = newer_version(self.baked)
        self._activate(source)
        self._run("", action=self.Run.ACTION_ROLLBACK, source=source)
        finished = self._tick(running=source)
        finished.refresh_from_db()
        self.assertEqual(finished.status, self.Run.STATUS_FAILED)
        self.assertIn("still active", finished.error)
