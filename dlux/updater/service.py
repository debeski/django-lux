from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import timedelta
from pathlib import Path

from packaging.version import InvalidVersion, Version

from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import UpdaterError, get_baked_version
from .manifest import (
    ReleaseCandidate,
    assess_wheel,
    download_wheel,
    fetch_simple_index,
    select_latest_candidate,
    verify_pypi_attestation,
)
from .health import runtime_probe_token
from .runtime import RuntimeStore


logger = logging.getLogger("dlux.updater")

# How long a run handed to Composer may sit unacknowledged. Its work is bounded
# (download, swap, restart, health wait); past this, nothing is coming.
PACKAGE_HANDOFF_TIMEOUT = timedelta(minutes=30)

TERMINAL_STATUSES = frozenset({"completed", "failed", "rolled_back"})
# The state tick runs every few seconds; the writer's report is only rewritten
# once a minute, and counts as gone after ten.
WORKER_REPORT_MIN_INTERVAL = 60
WORKER_REPORT_STALE_AFTER = 600
_SECRET_KEY_PATTERN = r"[A-Za-z0-9_.-]*(?:password|secret|token|authorization)[A-Za-z0-9_.-]*"
_SECRET_VALUE_PATTERN = r'''(?:(?:bearer|basic)\s+\S+|"(?:\\.|[^"])*"|'(?:\\.|[^'])*'|[^\s,;]+)'''
SECRET_RE = re.compile(
    rf'''(?ix)(["']?{_SECRET_KEY_PATTERN}["']?\s*[:=]\s*){_SECRET_VALUE_PATTERN}'''
)
SECRET_FLAG_RE = re.compile(rf"(?i)(--?{_SECRET_KEY_PATTERN}\s+)(\S+)")


def updates_enabled():
    return bool(getattr(settings, "DLUX_INLINE_UPDATES_ENABLED", False))


def composer_executes_updates():
    """True when Composer performs inline updates and DjangoLux only states intent.

    Default since 1.8.0. Composer stages and verifies a release before activating
    it and health-gates the restart from *outside* the container being swapped —
    a rollback guarantee an in-container updater cannot offer.

    ``DLUX_UPDATE_EXECUTOR = "inline"`` restores the legacy in-container path for
    a deployment whose Composer predates the ``dlux.package_update`` action. That
    escape hatch is removed in 1.9.0 along with the executor itself.
    """
    mode = str(getattr(settings, "DLUX_UPDATE_EXECUTOR", "composer") or "composer").strip().lower()
    return mode != "inline"


def local_runtime_volume_problem():
    """Why *this process* cannot write the runtime volume, or "" when it can.

    A pure stat probe — no mkdir — so the panel can call it per request.

    It answers for the calling process only. Since 1.8.0 the web container
    mounts the runtime volume read-only and Celery owns every write, so a
    failure here is the normal healthy arrangement in web and says nothing about
    whether updates can run. ``runtime_volume_problem()`` is the deployment-wide
    verdict; call this one only when you mean the current process.

    Deliberately NOT a fallback to some other writable directory. The supervisor
    and Composer both resolve releases through the path in
    ``runtime_contract.json``; staging somewhere else would make an update look
    like it worked while nothing ever loaded it.
    """
    root = Path(getattr(settings, "DLUX_UPDATE_RUNTIME_ROOT", "/opt/dlux-runtime")).expanduser()
    probe = root
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if not probe.exists():
        return f"The runtime volume path {root} does not exist and cannot be created."
    if not os.access(probe, os.W_OK):
        return (
            f"The runtime volume at {root} is not writable. Inline updates need a "
            "writable runtime volume; set DLUX_UPDATE_RUNTIME_ROOT, or leave "
            "DLUX_INLINE_UPDATES_ENABLED off outside a Compose deployment."
        )
    return ""


def worker_volume_report(state=None):
    """What the runtime-volume writer last reported, or None if it never has.

    ``{"seen_at": datetime, "problem": str, "stale": bool}``. The writer is the
    only process whose probe is worth anything, so this is what every reader
    consults. Pass an already-loaded state row to avoid a second query.
    """
    if state is None:
        try:
            state = (
                _state_model().objects
                .filter(pk=1)
                .only("worker_seen_at", "worker_volume_problem")
                .first()
            )
        except Exception:
            return None
    seen_at = getattr(state, "worker_seen_at", None)
    if not seen_at:
        return None
    return {
        "seen_at": seen_at,
        "problem": str(getattr(state, "worker_volume_problem", "") or ""),
        "stale": timezone.now() - seen_at > timedelta(seconds=WORKER_REPORT_STALE_AFTER),
    }


def record_worker_volume_report(problem=""):
    """Stamp the writer's own runtime-volume verdict on the state row.

    Celery owns the write side of the runtime volume, so it is the only process
    whose writability probe describes the mount updates actually run against.
    Recording the verdict here is what lets web decide from a read-only mount:
    it reads this instead of probing a volume it is deliberately not given write
    access to. Rate-limited because the state tick fires every few seconds.
    """
    problem = _sanitize(problem, 1000)
    try:
        state = _state_model().load()
    except Exception:
        return None
    now = timezone.now()
    fields = ["worker_seen_at"]
    if state.worker_volume_problem != problem:
        state.worker_volume_problem = problem
        fields.append("worker_volume_problem")
    elif (
        state.worker_seen_at
        and now - state.worker_seen_at < timedelta(seconds=WORKER_REPORT_MIN_INTERVAL)
    ):
        return state
    state.worker_seen_at = now
    state.save(update_fields=fields + ["updated_at"])
    return state


def runtime_volume_problem(state=None):
    """Why inline updates cannot proceed in this deployment, or "" when they can.

    The authority is whichever process writes the runtime volume — Celery since
    1.8.0 — because only its probe reflects the mount an update runs against.
    Web mounts the same volume read-only by design, so its own probe answers a
    different question and must never decide for the deployment; that leftover
    is what disabled the panel and refused queueing on a perfectly healthy
    read-only web mount.

    Until a writer has reported — a fresh install whose worker has not ticked
    yet, a single-process deployment, a management command on a laptop — the
    local probe is the only evidence there is, so it still stands in.
    """
    report = worker_volume_report(state)
    if report is not None:
        return report["problem"]
    return local_runtime_volume_problem()


def worker_report_is_stale(state=None):
    """The writer reported once and then went quiet: a queued run would sit."""
    report = worker_volume_report(state)
    return bool(report and report["stale"])


def inline_updates_available():
    """Updates are switched on *and* the volume backing them is usable."""
    return updates_enabled() and not runtime_volume_problem()


def runtime_store():
    """The runtime volume, created on demand.

    A deployment that is not a generated Compose project may have no volume and
    no permission to create one at the default location — running the worker on
    a laptop, say. That is a configuration problem, not a bug, so it gets a
    named error instead of a raw OSError from deep inside ``mkdir``. Reading the
    panel does not come through here; only queue work does.
    """
    root = getattr(settings, "DLUX_UPDATE_RUNTIME_ROOT", "/opt/dlux-runtime")
    try:
        return RuntimeStore(root).ensure()
    except OSError as exc:
        raise UpdaterError(
            f"The DjangoLux runtime volume at {root} is not usable ({exc.strerror or exc}). "
            "Inline updates need a writable runtime volume; set DLUX_UPDATE_RUNTIME_ROOT, "
            "or leave DLUX_INLINE_UPDATES_ENABLED off outside a Compose deployment."
        ) from exc


def _state_model():
    return apps.get_model("dlux", "DluxUpdateState")


def _run_model():
    return apps.get_model("dlux", "DluxUpdateRun")


def _sanitize(value, limit=4000):
    value = str(value or "").replace("\x00", "")
    value = SECRET_FLAG_RE.sub(r"\1<redacted>", value)
    value = SECRET_RE.sub(r"\1<redacted>", value)
    return value[-limit:]


def serialize_state(state):
    report = worker_volume_report(state)
    unavailable_reason = runtime_volume_problem(state) if updates_enabled() else ""
    return {
        "enabled": updates_enabled() and not unavailable_reason,
        "unavailable_reason": unavailable_reason,
        "worker_seen_at": report["seen_at"].isoformat() if report else None,
        "worker_stale": bool(report and report["stale"]),
        "baked_version": state.baked_version,
        "active_version": state.active_version,
        "previous_version": state.previous_version,
        "latest_version": state.latest_version,
        "latest_manifest": state.latest_manifest or {},
        "latest_compatible": state.latest_compatible,
        "latest_reason": state.latest_reason,
        "last_checked_at": state.last_checked_at.isoformat() if state.last_checked_at else None,
        "last_check_error": state.last_check_error,
        "generation": state.generation,
        "degraded": state.degraded,
        "degraded_reason": state.degraded_reason,
        "active_run_token": state.active_run_token,
        "skipped_versions": list(state.skipped_versions or []),
    }


def serialize_run(run, *, include_log=False):
    result = {
        "token": run.token,
        "action": run.action,
        "status": run.status,
        "active": run.is_active,
        "source_version": run.source_version,
        "target_version": run.target_version,
        "manifest": run.manifest or {},
        "backup_token": run.backup_token,
        "report": run.report or {},
        "error": run.error,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }
    if include_log:
        result["progress_log"] = run.progress_log
    return result


def get_ui_state():
    from dlux import __version__

    try:
        state = _state_model().load()
    except Exception:
        return {
            "enabled": updates_enabled(),
            "baked_version": get_baked_version(),
            "active_version": __version__,
            "previous_version": "",
            "latest_version": "",
            "latest_manifest": {},
            "latest_compatible": False,
            "latest_reason": "",
            "last_checked_at": None,
            "last_check_error": "",
            "generation": 0,
            "degraded": False,
            "degraded_reason": "",
            "active_run_token": "",
            "skipped_versions": [],
            "worker_seen_at": None,
            "worker_stale": False,
        }
    return serialize_state(state)


def previous_apply_failure(version):
    """If the most recent apply of ``version`` failed (or was auto-rolled-back),
    return a small dict describing it, else None. Powers a re-apply confirmation
    guard: the admin is warned that a version they're about to install already
    failed once, but can still retry on their own responsibility (not a block).
    A later successful apply of the same version clears the warning.
    """
    version = str(version or "").strip()
    if not version:
        return None
    Run = _run_model()
    run = (
        Run.objects.filter(action=Run.ACTION_APPLY, target_version=version)
        .order_by("-created_at")
        .first()
    )
    if run is None or run.status not in (Run.STATUS_FAILED, Run.STATUS_ROLLED_BACK):
        return None
    when = run.completed_at or run.created_at
    return {
        "version": version,
        "status": run.status,
        "error": (run.error or "")[:500],
        "at": when.isoformat() if when else None,
    }


def set_version_skipped(version, skipped=True):
    """Add or remove a version from the permanent skip list. When skipping the
    version currently offered as the latest update, clear the ``latest_*`` fields
    so the UI stops offering it immediately (the next check then selects the
    latest non-skipped release). Returns the refreshed UI state dict."""
    version = str(version or "").strip()
    if not version:
        return get_ui_state()
    state = _state_model().load()
    skipped_list = list(state.skipped_versions or [])
    changed = []
    if skipped:
        if version not in skipped_list:
            skipped_list.append(version)
            state.skipped_versions = skipped_list
            changed.append("skipped_versions")
        if state.latest_version == version:
            baseline = state.active_version or state.baked_version
            for field, value in {
                "latest_version": baseline,
                "latest_wheel_url": "",
                "latest_wheel_sha256": "",
                "latest_manifest": {},
                "latest_compatible": False,
                "latest_reason": "This version was skipped.",
            }.items():
                if getattr(state, field) != value:
                    setattr(state, field, value)
                    changed.append(field)
    elif version in skipped_list:
        state.skipped_versions = [v for v in skipped_list if v != version]
        changed.append("skipped_versions")
    if changed:
        state.save(update_fields=list(dict.fromkeys(changed + ["updated_at"])))
    return get_ui_state()


def queue_run(action, username="", backup_mode=None):
    if not updates_enabled():
        raise UpdaterError("Inline DjangoLux updates are disabled for this project.")
    problem = runtime_volume_problem()
    if problem:
        # Refuse here rather than letting the run queue: nothing could drain it.
        # The verdict is the writer's, not this process's — web queues intent
        # from a read-only mount and is not entitled to an opinion on it.
        raise UpdaterError(problem)
    if worker_report_is_stale():
        raise UpdaterError(
            "The DjangoLux update worker has not reported for over "
            f"{WORKER_REPORT_STALE_AFTER // 60} minutes, so a queued run would not be "
            "picked up. Check that the Celery worker and beat services are running."
        )
    Run = _run_model()
    if action not in {Run.ACTION_CHECK, Run.ACTION_APPLY, Run.ACTION_ROLLBACK}:
        raise UpdaterError("The requested updater action is invalid.")
    backup_mode = backup_mode if backup_mode in dict(Run.BACKUP_MODE_CHOICES) else Run.BACKUP_DATA
    State = _state_model()
    State.load()
    with transaction.atomic():
        state = State.objects.select_for_update().get(pk=1)
        Image = apps.get_model("dlux", "DluxImageUpdate")
        if Image.objects.filter(is_active=True).exists():
            raise UpdaterError("An image update is already in progress.")
        if state.active_run_token:
            active = Run.objects.filter(token=state.active_run_token, is_active=True).first()
            if active:
                raise UpdaterError("Another DjangoLux update operation is already running.")
            state.active_run_token = ""
        if action == Run.ACTION_APPLY:
            if not state.latest_version or not state.latest_compatible:
                raise UpdaterError("No verified inline-safe DjangoLux update is available.")
            source = state.active_version or state.baked_version
            target = state.latest_version
        elif action == Run.ACTION_ROLLBACK:
            if not state.previous_version:
                raise UpdaterError("No previous DjangoLux release is available for rollback.")
            source = state.active_version or state.baked_version
            target = state.previous_version
        else:
            source = state.active_version or state.baked_version
            target = ""
        run = Run.objects.create(
            action=action,
            source_version=source,
            target_version=target,
            requested_by_username=str(username or "")[:150],
            backup_mode=backup_mode,
        )
        state.active_run_token = run.token
        state.save(update_fields=["active_run_token", "updated_at"])
    return run


_PROCESS_RECONCILED = False


def reconcile_state_if_due(service):
    """Refresh the state row against the runtime when it can have drifted.

    ``UpdateService.reconcile()`` is what keeps ``baked_version``,
    ``active_version`` and the rollback target true. Its only caller was
    ``dlux_update_worker`` at startup, and when the Celery state tick replaced
    that worker in 1.8.0 the call was not carried over — so an upgraded
    deployment kept rendering the versions recorded before the upgrade and kept
    offering a rollback to a release that is no longer installed anywhere. The
    pre-start ``dlux_reconcile`` cannot stand in for it: that command runs before
    migrations and deliberately never touches the database.

    Runs once per worker process — the boot case, after ``migrator`` — and after
    that only when the recorded baked version stops matching the package actually
    installed, which is a project-image swap under a running worker. Reconcile
    reads the volume and writes the state row; the tick fires every few seconds.
    """
    global _PROCESS_RECONCILED

    if _PROCESS_RECONCILED:
        try:
            recorded = (
                _state_model().objects
                .filter(pk=1)
                .values_list("baked_version", flat=True)
                .first()
            )
        except Exception:
            return None
        if recorded is None or recorded == get_baked_version():
            return None
    try:
        state = service.reconcile()
    except Exception:
        logger.warning(
            "The DjangoLux state reconcile failed; the reported versions may be stale.",
            exc_info=True,
        )
        return None
    _PROCESS_RECONCILED = True
    if service.restart_worker:
        # Nothing to do here: reconcile bumped the generation, and the supervisor
        # this worker runs under restarts it onto the selected release.
        logger.info("The runtime release changed during reconcile; awaiting a supervisor restart.")
    return state


def queue_daily_check_if_due():
    if not updates_enabled():
        return None
    interval = max(300, int(getattr(settings, "DLUX_UPDATE_CHECK_INTERVAL", 86400) or 86400))
    State = _state_model()
    try:
        state = State.load()
    except Exception:
        return None
    if state.active_run_token:
        return None
    if state.last_checked_at and timezone.now() - state.last_checked_at < timedelta(seconds=interval):
        return None
    try:
        return queue_run(_run_model().ACTION_CHECK, username="system")
    except UpdaterError:
        return None


class UpdateService:
    def __init__(self, *, store=None, command_runner=subprocess.run):
        self.store = store or runtime_store()
        self.command_runner = command_runner
        self.restart_worker = False

    def reconcile(self):
        State = _state_model()
        state = State.load()
        changed = []
        restoration_succeeded = False
        baked_version = get_baked_version()
        if state.baked_version != baked_version:
            state.baked_version = baked_version
            changed.append("baked_version")
        try:
            active = self.store.read_active(baked_version)
        except UpdaterError:
            active = None
        _rebuild_reason = "A newer project-image DjangoLux release was activated."
        if active and active["source"] == "volume" and self._version_is_newer(
            baked_version, active["version"]
        ):
            next_generation = self.store.read_generation() + 1
            self._reset_to_baked_image(state, baked_version, next_generation, _rebuild_reason, changed)
            self.store.set_generation(next_generation)
            active = self.store.read_active(baked_version)
            self.restart_worker = True
        elif active and active["source"] == "image" and (
            not state.active_version
            or self._version_is_newer(baked_version, state.active_version)
        ):
            # A normal project-image rebuild replaces the old baked package.
            # Treat that as an intentional activation, not as a missing volume
            # release that should be reconstructed from stale database metadata.
            generation = self.store.read_generation()
            self._reset_to_baked_image(state, baked_version, generation, _rebuild_reason, changed)
            active = self.store.read_active(baked_version)
        if active is None or (
            not self.store.active_file.exists()
            and state.active_version
            and state.active_version != baked_version
        ):
            if (
                state.active_version
                and state.active_version != baked_version
                and not self.store.release_path(state.active_version).is_dir()
                and not (state.active_wheel_url and state.active_wheel_sha256)
            ):
                # The recorded active release cannot be served and cannot be
                # rebuilt: there is no staged volume release on disk and no
                # downloadable wheel to reconstruct it (an image/mount activation,
                # or a wiped runtime volume). A backward image move lands here too.
                # Revert to the baked image — the known-good runtime — instead of
                # hard-failing into a permanently degraded state by chasing a wheel
                # that never existed.
                next_generation = self.store.read_generation() + 1
                self._reset_to_baked_image(
                    state, baked_version, next_generation,
                    "The recorded DjangoLux release could not be served and was reverted to the baked image.",
                    changed,
                )
                self.store.set_generation(next_generation)
                active = self.store.read_active(baked_version)
                restoration_succeeded = True
                self.restart_worker = True
            else:
                try:
                    self._restore_recorded_active(state)
                    active = self.store.read_active(baked_version)
                    restoration_succeeded = True
                except Exception as exc:
                    active = None
                    state.degraded = True
                    state.degraded_reason = _sanitize(exc)
                    self.store.set_degraded(state.degraded_reason)
                    changed.extend(["degraded", "degraded_reason"])
        if active:
            if self.store.read_generation() != active["generation"]:
                self.store.set_generation(active["generation"])
            if state.active_version != active["version"]:
                state.active_version = active["version"]
                changed.append("active_version")
            if state.generation != active["generation"]:
                state.generation = active["generation"]
                changed.append("generation")
            # Clear a lingering degraded flag once the runtime has demonstrably
            # converged onto a healthy release. That means either a successful
            # restoration just ran, OR the runtime is now serving the baked image
            # (the known-good fallback). A transient degrade must not wedge the
            # runtime permanently once it is healthily back on baked. Volume
            # releases are deliberately excluded: a degrade tied to a failed
            # volume activation/rollback target stays sticky for operator review.
            converged_on_baked = (
                active["version"] == baked_version and active["source"] == "image"
            )
            if (restoration_succeeded or converged_on_baked) and (
                state.degraded or state.degraded_reason
            ):
                state.degraded = False
                state.degraded_reason = ""
                changed.extend(["degraded", "degraded_reason"])
            if not state.degraded:
                self.store.clear_degraded()
            # Safety net for the "stuck on the update screen" outage: a healthy
            # runtime must never sit behind a raised maintenance flag. A failed or
            # interrupted update can converge the app back onto a healthy release
            # (a successful restore, or the baked image) yet leave state/maintenance
            # raised — notably the unsafe-recovery path in _handle_failure, which
            # deliberately keeps the flag up while the app might be broken. Once the
            # runtime is demonstrably healthy again, that flag is just a stale file
            # 503-ing the whole site behind an "update in progress" screen with
            # nothing running (and compose down/up can't clear it — it lives in the
            # runtime volume). If we've healthily converged and no run or image
            # update still owns the flag, lower it. The owner guards ensure we never
            # race an update that is legitimately mid-flight.
            if (
                (restoration_succeeded or converged_on_baked)
                and not state.degraded
                and not state.active_run_token
                and self.store.maintenance_file.exists()
            ):
                from .image_update import active_image_update
                if active_image_update() is None:
                    self.store.set_maintenance(False)
        if changed:
            state.save(update_fields=list(dict.fromkeys(changed + ["updated_at"])))
        return state

    @staticmethod
    def _version_is_newer(candidate, current):
        try:
            return Version(str(candidate)) > Version(str(current))
        except InvalidVersion:
            return False

    def _reset_to_baked_image(self, state, baked_version, generation, reason, changed):
        """Activate the baked image release and clear all volume-update metadata.

        Shared by every path that converges the runtime back onto the immutable
        image package: a project-image rebuild, and the recovery fallback when a
        recorded release can no longer be served. Clears the degraded marker —
        baked is the known-good runtime — but leaves generation bumping and worker
        restart to the caller, since those differ per path.
        """
        self.store.write_active(baked_version, source="image", generation=generation)
        reset_fields = {
            "active_version": baked_version,
            "active_wheel_url": "",
            "active_wheel_sha256": "",
            "active_manifest": {},
            "previous_version": "",
            "previous_wheel_url": "",
            "previous_wheel_sha256": "",
            "previous_manifest": {},
            "latest_version": "",
            "latest_wheel_url": "",
            "latest_wheel_sha256": "",
            "latest_manifest": {},
            "latest_compatible": False,
            "latest_reason": reason,
            "generation": generation,
            "degraded": False,
            "degraded_reason": "",
        }
        for field, value in reset_fields.items():
            if getattr(state, field) != value:
                setattr(state, field, value)
                changed.append(field)
        self.store.clear_degraded()
        self.store.set_maintenance(False)

    def _restore_recorded_active(self, state):
        baked_version = get_baked_version()

        if not state.active_version or state.active_version == baked_version:
            self.store.write_active(baked_version, source="image", generation=state.generation)
            self.store.set_generation(state.generation)
            return
        if not state.active_wheel_url or not state.active_wheel_sha256:
            raise UpdaterError("The active release cannot be reconstructed from verified metadata.")
        candidate = ReleaseCandidate(
            version=state.active_version,
            filename=Path(state.active_wheel_url).name,
            url=state.active_wheel_url,
            sha256=state.active_wheel_sha256,
        )
        wheel = download_wheel(candidate, self.store.wheel_path(candidate))
        verify_pypi_attestation(candidate)
        assessment = assess_wheel(candidate, wheel, baked_version=baked_version)
        if not assessment["compatible"]:
            raise UpdaterError(assessment["reason"])
        release = self.store.release_path(candidate.version)
        if not release.exists():
            stage = self.store.stage_path(f"restore-{candidate.version}")
            RuntimeStore.install_wheel(wheel, stage, runner=self.command_runner)
            self.store.activate_stage(stage, candidate.version)
        self.store.write_active(candidate.version, source="volume", generation=state.generation)
        self.store.set_generation(state.generation)

    def recover_interrupted_run(self):
        """Recover a durable run claimed by a worker that exited unexpectedly."""
        State = _state_model()
        Run = _run_model()
        state = State.load()
        if not state.active_run_token:
            return None
        run = Run.objects.filter(token=state.active_run_token, is_active=True).first()
        if run is None:
            state.active_run_token = ""
            state.save(update_fields=["active_run_token", "updated_at"])
            return None
        if run.status == Run.STATUS_QUEUED:
            return None

        report = {**(run.report or {}), "interrupted": True}
        run.report = report
        run.append_log("The update worker restarted before this operation completed.")
        run.save(update_fields=["report", "progress_log"])
        pointer_switched = bool(report.get("pointer_switched"))
        try:
            if pointer_switched:
                self._restore_interrupted_source(state, run)
                report["pointer_recovered"] = True
                self.restart_worker = True
            elif self.store.maintenance_file.exists():
                active = self.store.read_active(state.baked_version)
                env = (
                    self.store.python_env_for(active["path"])
                    if active["source"] == "volume" else self._image_env()
                )
                self._run_manage(
                    ["collectstatic", "--noinput", "--clear"],
                    env,
                    run,
                    timeout=600,
                )
            self.store.set_maintenance(False)
            self.store.archive_failed_stage(self.store.stage_path(run.token), run.token)
        except Exception as exc:
            report["recovery_failed"] = True
            run.report = report
            run.save(update_fields=["report"])
            self._handle_failure(run, exc)
            return run

        run.report = report
        run.append_log("Interrupted operation recovery completed.")
        run.save(update_fields=["report", "progress_log"])
        status = (
            run.STATUS_ROLLED_BACK
            if pointer_switched and run.action == run.ACTION_APPLY
            else run.STATUS_FAILED
        )
        self._complete(run, status=status, report=report)
        return run

    def _restore_interrupted_source(self, state, run):
        source_version = str(run.source_version or "").strip()
        if not source_version:
            raise UpdaterError("The interrupted update has no recorded source release.")
        if source_version == state.baked_version:
            source = "image"
            env = self._image_env()
        else:
            source_path = self.store.release_path(source_version)
            if not source_path.is_dir():
                raise UpdaterError("The interrupted update's source release is unavailable.")
            source = "volume"
            env = self.store.python_env_for(source_path)

        next_generation = self.store.read_generation() + 1
        self.store.write_active(source_version, source=source, generation=next_generation)
        self._select_state_version(state, source_version, next_generation)
        try:
            self._run_manage(
                ["collectstatic", "--noinput", "--clear"],
                env,
                run,
                timeout=600,
            )
        finally:
            self.store.bump_generation()

    @staticmethod
    def _select_state_version(state, version, generation):
        fields = ("version", "wheel_url", "wheel_sha256", "manifest")
        if state.active_version != version:
            if state.previous_version != version:
                raise UpdaterError("The interrupted update source is absent from runtime state.")
            active = {field: getattr(state, f"active_{field}") for field in fields}
            previous = {field: getattr(state, f"previous_{field}") for field in fields}
            for field in fields:
                setattr(state, f"active_{field}", previous[field])
                setattr(state, f"previous_{field}", active[field])
        state.generation = generation
        state.save()

    def claim_next(self):
        Run = _run_model()
        with transaction.atomic():
            run = Run.objects.select_for_update().filter(
                status=Run.STATUS_QUEUED,
                is_active=True,
            ).order_by("created_at").first()
            if not run:
                return None
            run.started_at = timezone.now()
            run.status = Run.STATUS_CHECKING if run.action == Run.ACTION_CHECK else Run.STATUS_DOWNLOADING
            run.append_log(f"Started {run.action} request.")
            run.save(update_fields=["started_at", "status", "progress_log"])
            return run

    def process_next(self):
        run = self.claim_next()
        if not run:
            return None
        try:
            if run.action == run.ACTION_CHECK:
                self._process_check(run)
            elif run.action == run.ACTION_APPLY:
                self._process_apply(run)
            else:
                self._process_rollback(run)
        except Exception as exc:
            self._handle_failure(run, exc)
        return run

    def _transition(self, run, status, message=""):
        run.status = status
        if message:
            run.append_log(message)
        run.save(update_fields=["status", "progress_log"])
        self._mirror_inline_progress(run)

    def _mirror_inline_progress(self, run):
        """Mirror an inline apply/rollback run's phase to the proxy-served
        deploy-status.json / deploy-log.txt on the shared volume.

        The run's own status API is served by ``web``, which the proxy walls off
        with a 503 the moment the maintenance flag is written — so every phase
        from ``maintenance`` through ``verifying_health`` is invisible to the
        browser polling web. These two files are served straight off the volume
        by the proxy (which stays up), so the live modal and the full-page
        maintenance view keep advancing. Best-effort: a mirror failure must never
        derail the update itself.
        """
        Run = _run_model()
        if run.action not in (Run.ACTION_APPLY, Run.ACTION_ROLLBACK):
            return
        if run.status == Run.STATUS_APPLYING:
            # Composer is executing and publishes its own phases to this file.
            # Mirroring "inline" over them would blank the modal's progress until
            # its next write — and it is the only progress there is to show.
            return
        try:
            from .image_update import write_deploy_log, write_deploy_status

            write_deploy_status(
                self.store,
                run.status,
                kind="inline",
                run_token=run.token,
                action=run.action,
                error=str(run.error or "")[:1000],
            )
            write_deploy_log(self.store, run.progress_log)
        except Exception:
            logger.warning("Failed to mirror inline update progress to the shared volume.", exc_info=True)

    def _complete(self, run, *, report=None, status=None, error=""):
        status = status or run.STATUS_COMPLETED
        with transaction.atomic():
            state = _state_model().objects.select_for_update().get(pk=1)
            run.finish(status, report=report, error=error)
            run.save(update_fields=[
                "status", "is_active", "completed_at", "error", "report", "progress_log",
            ])
            if state.active_run_token == run.token:
                state.active_run_token = ""
                state.save(update_fields=["active_run_token", "updated_at"])
        # Publish the terminal phase to the shared volume too, so a browser still
        # behind the maintenance wall sees the run finish rather than freezing on
        # the last phase before web became reachable again.
        self._mirror_inline_progress(run)
        # The runtime is now durably on the new release — let admins know.
        if run.action == run.ACTION_APPLY and status == run.STATUS_COMPLETED:
            self._notify_admins_app_updated(run)

    def _notify_admins_app_updated(self, run):
        """Post a notification to admins (superusers) that DjangoLux was updated.

        Best-effort and fully isolated: a notification failure must never affect
        the (already durably-committed) update lifecycle.
        """
        try:
            from django.contrib.auth import get_user_model
            from django.urls import NoReverseMatch, reverse

            from ..notifications import notify
            from ..translations import get_strings

            version = str((run.report or {}).get("active_version") or "").strip()
            admins = list(get_user_model().objects.filter(is_active=True, is_superuser=True))
            if not admins:
                return
            try:
                target_url = reverse("options_view")
            except NoReverseMatch:
                target_url = ""
            s = get_strings()
            title = s.get("notif_app_updated_title", "DjangoLux updated")
            template = s.get(
                "notif_app_updated_message",
                "DjangoLux was updated to version {version}.",
            )
            message = template.replace("{version}", version) if version else template
            notify.success(
                message,
                title=title,
                recipients=admins,
                category="system",
                action="dlux_update_applied",
                source="updater",
                target_url=target_url,
                metadata={"version": version, "message_key": "notif_app_updated_message"},
            )
        except Exception:
            logger.warning("Failed to emit the app-updated admin notification.", exc_info=True)

    def _process_check_via_composer(self, run):
        """Read what Composer published instead of reaching PyPI.

        Composer resolves, downloads and verifies the wheel in
        `composer dlux-update --check`, so the manifest — the only authority on
        `inline_safe` — has already been read from the artifact itself. This is
        the last piece that made DjangoLux talk to the network.
        """
        from . import package_request

        state = _state_model().load()
        current = state.active_version or state.baked_version
        report = package_request.read_availability(self.store)
        state.last_checked_at = timezone.now()

        if not report:
            state.last_check_error = (
                "Composer has not reported DjangoLux availability yet. Inline updates "
                "require Composer running as a service in this deployment; run "
                "'composer check' on the host to verify it is installed and wired."
            )
            state.latest_compatible = False
            state.save()
            run.append_log(state.last_check_error)
            run.save(update_fields=["progress_log"])
            self._complete(run, report={"update_available": False, "unknown": True})
            return

        if report.get("error"):
            state.last_check_error = str(report["error"])[:4000]
            state.latest_compatible = False
            state.save()
            run.append_log(f"Composer could not check for updates: {state.last_check_error}")
            run.save(update_fields=["progress_log"])
            self._complete(run, report={"update_available": False, "error": state.last_check_error})
            return

        state.last_check_error = ""
        version = str(report.get("version") or "").strip()
        newer = bool(version) and self._version_is_newer(version, current)
        skipped = version in (state.skipped_versions or [])
        inline_safe = bool(report.get("inline_safe"))

        state.latest_version = version or current
        state.latest_compatible = bool(newer and inline_safe and not skipped)
        if not newer:
            state.latest_reason = "DjangoLux is up to date."
        elif skipped:
            state.latest_reason = f"DjangoLux {version} was skipped for this deployment."
        elif not inline_safe:
            state.latest_reason = report.get("reason") or (
                f"DjangoLux {version} requires a project image rebuild."
            )
        else:
            state.latest_reason = ""
        state.save()

        run.target_version = state.latest_version
        run.append_log(state.latest_reason or f"DjangoLux {version} is available.")
        run.save(update_fields=["target_version", "progress_log"])
        self._complete(run, report={
            "update_available": state.latest_compatible,
            "version": state.latest_version,
            "inline_safe": inline_safe,
        })

    def _process_check(self, run):
        if composer_executes_updates():
            return self._process_check_via_composer(run)
        state = _state_model().load()
        current = state.active_version or state.baked_version
        index = fetch_simple_index()
        candidate = select_latest_candidate(index, current, skip_versions=state.skipped_versions)
        state.last_checked_at = timezone.now()
        state.last_check_error = ""
        if not candidate:
            state.latest_version = current
            state.latest_wheel_url = ""
            state.latest_wheel_sha256 = ""
            state.latest_manifest = {}
            state.latest_compatible = False
            state.latest_reason = "DjangoLux is up to date."
            state.save()
            run.target_version = current
            run.append_log("No newer stable release is available.")
            run.save(update_fields=["target_version", "progress_log"])
            self._complete(run, report={"update_available": False})
            return

        run.target_version = candidate.version
        run.wheel_url = candidate.url
        run.wheel_sha256 = candidate.sha256
        run.save(update_fields=["target_version", "wheel_url", "wheel_sha256"])
        self._transition(run, run.STATUS_DOWNLOADING, f"Downloading DjangoLux {candidate.version}.")
        wheel = download_wheel(candidate, self.store.wheel_path(candidate))
        self._transition(run, run.STATUS_VERIFYING, "Verifying hash, publisher attestation, and compatibility.")
        verify_pypi_attestation(candidate)
        assessment = assess_wheel(candidate, wheel, baked_version=state.baked_version)
        run.manifest = assessment["manifest"]
        run.save(update_fields=["manifest"])
        state.latest_version = candidate.version
        state.latest_wheel_url = candidate.url
        state.latest_wheel_sha256 = candidate.sha256
        state.latest_manifest = assessment["manifest"]
        state.latest_compatible = assessment["compatible"]
        state.latest_reason = assessment["reason"] or "Ready for inline update."
        state.save()
        run.append_log(state.latest_reason)
        run.save(update_fields=["progress_log"])
        self._complete(run, report={
            "update_available": True,
            "compatible": assessment["compatible"],
            "reason": state.latest_reason,
        })

    def _verified_latest_candidate(self, state, run):
        index = fetch_simple_index()
        candidate = select_latest_candidate(
            index, state.active_version or state.baked_version, skip_versions=state.skipped_versions
        )
        if not candidate:
            raise UpdaterError("No verified inline-safe DjangoLux update is available.")
        if candidate.version != state.latest_version:
            # The latest advanced between the check and this apply. Re-verify the
            # new release in place and roll the plan forward instead of dead-ending.
            candidate = self._roll_forward(state, run, candidate)
        elif candidate.sha256 != state.latest_wheel_sha256 or candidate.url != state.latest_wheel_url:
            # Same version, different artifact = a re-published/tampered wheel.
            raise UpdaterError("The PyPI release metadata changed after the update check.")
        run.wheel_url = candidate.url
        run.wheel_sha256 = candidate.sha256
        run.target_version = candidate.version
        run.save(update_fields=["wheel_url", "wheel_sha256", "target_version"])
        return candidate

    def _roll_forward(self, state, run, candidate):
        """The latest release advanced since the check. Re-verify the new
        candidate here (download + attestation + inline-safety) and, if it is
        still inline-safe, roll the plan forward to it — preserving the "only
        install a verified, inline-safe release" guarantee while sparing the admin
        a manual re-check. If the new release is not inline-safe, stop with a
        clear reason instead of a cryptic "no longer the latest"."""
        previous = state.latest_version
        self._transition(
            run,
            run.STATUS_VERIFYING,
            f"A newer release (v{candidate.version}) appeared since the check; re-verifying it.",
        )
        wheel = download_wheel(candidate, self.store.wheel_path(candidate))
        verify_pypi_attestation(candidate)
        assessment = assess_wheel(candidate, wheel, baked_version=state.baked_version)
        state.latest_version = candidate.version
        state.latest_wheel_url = candidate.url
        state.latest_wheel_sha256 = candidate.sha256
        state.latest_manifest = assessment["manifest"]
        state.latest_compatible = assessment["compatible"]
        state.latest_reason = assessment["reason"] or "Ready for inline update."
        state.last_checked_at = timezone.now()
        state.save()
        if not assessment["compatible"]:
            raise UpdaterError(
                f"A newer release (v{candidate.version}) is available but is not inline-safe; "
                f"it needs an image update. {assessment['reason'] or ''}".strip()
            )
        run.append_log(
            f"Available update changed from v{previous} to v{candidate.version}; applying v{candidate.version}."
        )
        run.save(update_fields=["progress_log"])
        return candidate

    def _handoff_to_composer(self, run, mode):
        """Write the intent Composer's executor watches, and wait for its ack.

        The run row stays the source of truth for the admin UI; Composer owns the
        staging, the restart and the rollback decision.
        """
        from . import package_request

        pending = package_request.pending_token(self.store)
        if pending:
            raise UpdaterError("Composer is already performing a DjangoLux update.")
        state = _state_model().load()
        target = "" if mode == package_request.ROLLBACK else (run.target_version or state.latest_version or "")
        # No operation_id: `control_operation_id` belongs to DluxImageUpdate, the
        # row the agent bridge creates for a control-plane `dlux.image_update`.
        # A package run is always local — the bridge accepts no package action —
        # and Composer correlates it by the run's own token. Reading that field
        # off this model raised AttributeError before the request was ever
        # written, so no hand-off could reach Composer at all.
        package_request.write_request(
            self.store,
            mode=mode,
            target_version=target,
            backup_mode=run.backup_mode,
            token=run.token,
        )
        self._transition(
            run,
            run.STATUS_APPLYING,
            f"Handed the {mode} to Composer; it stages, restarts and health-gates it.",
        )
        return True

    def _process_apply(self, run):
        if composer_executes_updates():
            from . import package_request

            return self._handoff_to_composer(run, package_request.APPLY)
        state = _state_model().load()
        if not state.latest_compatible:
            raise UpdaterError("The selected DjangoLux release is not inline-safe.")
        candidate = self._verified_latest_candidate(state, run)
        self._transition(run, run.STATUS_DOWNLOADING, f"Downloading DjangoLux {candidate.version} again.")
        wheel = download_wheel(candidate, self.store.wheel_path(candidate))
        self._transition(run, run.STATUS_VERIFYING, "Re-verifying the release before installation.")
        verify_pypi_attestation(candidate)
        assessment = assess_wheel(candidate, wheel, baked_version=state.baked_version)
        if not assessment["compatible"]:
            raise UpdaterError(assessment["reason"])
        if assessment["manifest"] != state.latest_manifest:
            raise UpdaterError("The signed release manifest changed after the update check.")
        run.manifest = assessment["manifest"]
        run.save(update_fields=["manifest"])

        release = self.store.release_path(candidate.version)
        stage = None
        if not release.exists():
            self._transition(run, run.STATUS_STAGING, "Installing the verified wheel into an isolated staging directory.")
            stage = self.store.stage_path(run.token)
            RuntimeStore.install_wheel(wheel, stage, runner=self.command_runner)
            candidate_path = stage
        else:
            candidate_path = release

        self._transition(run, run.STATUS_PREFLIGHT, "Running project checks and migration planning with the candidate release.")
        candidate_env = self.store.python_env_for(candidate_path)
        self._run_manage(["check"], candidate_env, run)
        self._doctor_preflight(candidate_env, run)
        self._run_manage(["migrate", "--plan"], candidate_env, run)

        self._transition(run, run.STATUS_BACKING_UP, self._backup_phase_message(run, "pre-update"))
        backup = self._create_backup(run)
        if backup is not None:
            run.backup_token = backup.token
            run.save(update_fields=["backup_token"])

        switched = False
        maintenance_started = False
        previous = self.store.read_active(state.baked_version)
        state_snapshot = self._runtime_state_snapshot(state)
        try:
            self._transition(run, run.STATUS_MAINTENANCE, "Entering maintenance mode.")
            self.store.set_maintenance(True, token=run.token)
            maintenance_started = True
            self._transition(run, run.STATUS_MIGRATING, "Applying candidate database migrations.")
            self._run_manage(["migrate", "--noinput"], candidate_env, run)
            self._transition(run, run.STATUS_COLLECTING_STATIC, "Collecting candidate static assets.")
            self._run_manage(["collectstatic", "--noinput", "--clear"], candidate_env, run, timeout=600)
            self._transition(run, run.STATUS_SWITCHING, "Activating the candidate release.")
            if stage is not None:
                release = self.store.activate_stage(stage, candidate.version)
            next_generation = self.store.read_generation() + 1
            self.store.write_active(candidate.version, source="volume", generation=next_generation)
            switched = True
            run.report = {**(run.report or {}), "pointer_switched": True}
            run.save(update_fields=["report"])
            self._update_active_state(state, candidate, assessment["manifest"], next_generation)
            self.store.bump_generation()
            self._transition(run, run.STATUS_RESTARTING, "Restarting DjangoLux application processes.")
            self._transition(run, run.STATUS_VERIFYING_HEALTH, "Waiting for web and Celery health checks.")
            self._verify_health(candidate.version, candidate_env)
        except Exception:
            if switched:
                self._rollback_pointer(state, previous, state_snapshot, run)
                self.store.set_maintenance(False)
                run.append_log("The candidate failed health verification; the previous release was restored.")
                run.save(update_fields=["progress_log"])
                self._complete(run, status=run.STATUS_ROLLED_BACK, report={"automatic": True})
                self.restart_worker = True
                return
            if maintenance_started:
                previous_env = (
                    self.store.python_env_for(previous["path"])
                    if previous["source"] == "volume" else self._image_env()
                )
                try:
                    self._run_manage(
                        ["collectstatic", "--noinput", "--clear"],
                        previous_env,
                        run,
                        timeout=600,
                    )
                except Exception:
                    run.report = {**(run.report or {}), "recovery_failed": True}
                    run.save(update_fields=["report"])
                    raise
            raise
        self.store.set_maintenance(False)
        run.append_log(f"DjangoLux {candidate.version} is active and healthy.")
        run.save(update_fields=["progress_log"])
        self._complete(run, report={"active_version": candidate.version})
        self.restart_worker = True

    def _process_rollback(self, run):
        if composer_executes_updates():
            from . import package_request

            return self._handoff_to_composer(run, package_request.ROLLBACK)
        state = _state_model().load()
        target = state.previous_version
        if not target:
            raise UpdaterError("No previous DjangoLux release is available for rollback.")
        previous_path = self.store.release_path(target)
        source = "volume" if previous_path.is_dir() else "image"
        if source == "image" and target != state.baked_version:
            raise UpdaterError("The previous DjangoLux release is no longer available locally.")
        env = self.store.python_env_for(previous_path) if source == "volume" else self._image_env()
        self._transition(run, run.STATUS_PREFLIGHT, f"Checking rollback target DjangoLux {target}.")
        self._run_manage(["check"], env, run)
        self._doctor_preflight(env, run)
        self._transition(run, run.STATUS_BACKING_UP, self._backup_phase_message(run, "pre-rollback"))
        backup = self._create_backup(run)
        if backup is not None:
            run.backup_token = backup.token
            run.save(update_fields=["backup_token"])
        current_payload = self.store.read_active(state.baked_version)
        current_env = (
            self.store.python_env_for(current_payload["path"])
            if current_payload["source"] == "volume" else self._image_env()
        )
        state_snapshot = self._runtime_state_snapshot(state)
        self._transition(run, run.STATUS_MAINTENANCE, "Entering maintenance mode for rollback.")
        self.store.set_maintenance(True, token=run.token)
        try:
            self._transition(run, run.STATUS_COLLECTING_STATIC, "Collecting previous-release static assets.")
            self._run_manage(["collectstatic", "--noinput", "--clear"], env, run, timeout=600)
            self._transition(run, run.STATUS_SWITCHING, f"Activating DjangoLux {target}.")
            next_generation = self.store.read_generation() + 1
            self.store.write_active(target, source=source, generation=next_generation)
            current_version = state.active_version
            current_url = state.active_wheel_url
            current_sha = state.active_wheel_sha256
            current_manifest = state.active_manifest
            state.active_version = target
            state.active_wheel_url = state.previous_wheel_url
            state.active_wheel_sha256 = state.previous_wheel_sha256
            state.active_manifest = state.previous_manifest
            state.previous_version = current_version
            state.previous_wheel_url = current_url
            state.previous_wheel_sha256 = current_sha
            state.previous_manifest = current_manifest
            state.generation = next_generation
            state.save()
            run.report = {**(run.report or {}), "pointer_switched": True}
            run.save(update_fields=["report"])
            self.store.bump_generation()
            self._transition(run, run.STATUS_RESTARTING, "Restarting DjangoLux application processes.")
            self._transition(run, run.STATUS_VERIFYING_HEALTH, "Waiting for rollback health checks.")
            self._verify_health(target, env)
        except Exception:
            try:
                next_generation = self.store.read_generation() + 1
                self.store.write_active(
                    current_payload["version"],
                    source=current_payload["source"],
                    generation=next_generation,
                )
                self._restore_runtime_state(state, state_snapshot, next_generation)
                try:
                    self._run_manage(
                        ["collectstatic", "--noinput", "--clear"],
                        current_env,
                        run,
                        timeout=600,
                    )
                finally:
                    self.store.bump_generation()
                self._verify_health(current_payload["version"], current_env)
                run.report = {**(run.report or {}), "pointer_recovered": True}
                run.save(update_fields=["report"])
            except Exception:
                run.report = {**(run.report or {}), "recovery_failed": True}
                run.save(update_fields=["report"])
                raise
            raise
        finally:
            if not (run.report or {}).get("recovery_failed"):
                self.store.set_maintenance(False)
        run.append_log(f"DjangoLux {target} was restored successfully.")
        run.save(update_fields=["progress_log"])
        self._complete(run, report={"active_version": target, "manual": True})
        self.restart_worker = True

    @staticmethod
    def _backup_phase_message(run, phase):
        Run = _run_model()
        mode = getattr(run, "backup_mode", Run.BACKUP_DATA) or Run.BACKUP_DATA
        if mode == Run.BACKUP_SKIP:
            return f"Skipping the {phase} backup (operator choice)."
        scope = "full" if mode == Run.BACKUP_FULL else "data-only"
        return f"Creating a {scope} {phase} DjangoLux backup."

    def _create_backup(self, run):
        """Create the pre-update/-rollback backup per the run's backup_mode.

        Returns the SystemBackup, or None when the operator chose to skip it.
        Quick (data-only) is the default; an inline update never touches media on
        disk, so copying unchanged uploads would only slow a quick update. The
        runner reads media_included off the row so the choice is Celery-safe.
        """
        from dlux.backup import run_system_backup

        Run = _run_model()
        mode = getattr(run, "backup_mode", Run.BACKUP_DATA) or Run.BACKUP_DATA
        if mode == Run.BACKUP_SKIP:
            return None
        SystemBackup = apps.get_model("dlux", "SystemBackup")
        backup = SystemBackup.objects.create(
            requested_by_username=run.requested_by_username,
            trigger=SystemBackup.TRIGGER_UPDATE,
            media_included=(mode == Run.BACKUP_FULL),
        )
        run_system_backup(backup.pk)
        backup.refresh_from_db()
        if backup.status != SystemBackup.STATUS_COMPLETED:
            raise UpdaterError("The required pre-update system backup failed.")
        return backup

    # --- image-level (full container) updates ---------------------------------
    # Separate from the inline wheel lifecycle above. Driven from the worker
    # loop via tick_image_update(); the actual pull/recreate is done by the
    # external Composer agent, and finalized by reading its deploy-status.

    def tick_image_update(self):
        """Advance the single active image update, if any. No-op otherwise.

        Never touches DluxUpdateRun / active_run_token, so the inline worker's
        durable-run recovery is unaffected.
        """
        from .image_update import active_image_update

        row = active_image_update()
        if row is None:
            return None
        try:
            if row.status == row.STATUS_PENDING:
                self._begin_image_update(row)
            elif row.status == row.STATUS_AWAITING_RECREATE:
                self._finalize_image_update(row)
        except Exception as exc:
            try:
                self.store.set_maintenance(False)
            except Exception:
                pass
            self._fail_image_update(row, exc)
        return row

    def tick_package_update(self):
        """Finish a run Composer executed. No-op unless one is waiting.

        The hand-off ends at `write_request`: nothing in this process can see
        what Composer then did. Its ack on the shared volume — token plus exit
        code — is the only completion signal there is, and without reading it a
        handed-off run stayed active for ever, which made `queue_run` refuse
        every later update on the deployment.
        """
        from . import package_request

        Run = _run_model()
        state = _state_model().load()
        if not state.active_run_token:
            return None
        run = Run.objects.filter(
            token=state.active_run_token,
            is_active=True,
            status=Run.STATUS_APPLYING,
        ).first()
        if run is None:
            return None

        ack = package_request.read_ack(self.store)
        if str(ack.get("token") or "").strip() != run.token:
            return self._expire_stale_handoff(run)
        try:
            exit_code = int(ack.get("exit_code", 0) or 0)
        except (TypeError, ValueError):
            exit_code = 1

        # Composer changed the release on the volume; the versions this row
        # reports are stale until they are read again.
        try:
            self.reconcile()
        except Exception:
            logger.warning("Could not reconcile state after Composer's update.", exc_info=True)

        detail = package_request.composer_progress(self.store) or {}
        message = str(detail.get("message") or "").strip()
        report = {**(run.report or {}), "composer_exit_code": exit_code}

        if exit_code == 0:
            run.append_log(message or "Composer applied the release.")
            run.save(update_fields=["progress_log"])
            self._complete(run, report=report)
            return run

        if exit_code == 3:
            # Composer's "needs a human": the rollback did not come back healthy
            # either, so nothing automatic should touch this deployment again.
            message = message or (
                "Composer rolled the release back and the previous one did not become "
                "healthy either. The deployment needs an operator."
            )
        elif not message:
            message = f"Composer could not apply the release (exit {exit_code})."

        if detail.get("rolled_back"):
            run.append_log(message)
            self._complete(
                run, status=Run.STATUS_ROLLED_BACK, report=report, error=message,
            )
            return run

        run.report = report
        run.save(update_fields=["report"])
        self._handle_failure(run, UpdaterError(message))
        return run

    def _expire_stale_handoff(self, run):
        """Fail a hand-off Composer never acknowledged, but only well past the
        point where it could still be working.

        Composer's own operation is bounded — download, swap, restart, health
        wait — so an ack this far out means its executor died or never saw the
        request. Leaving the run active instead would be worse than a wrong
        verdict: it blocks every future update, and the release it was applying
        may well be active anyway.
        """
        started = run.started_at or run.created_at
        if not started or timezone.now() - started <= PACKAGE_HANDOFF_TIMEOUT:
            return None
        minutes = int(PACKAGE_HANDOFF_TIMEOUT.total_seconds() // 60)
        self._handle_failure(run, UpdaterError(
            f"Composer did not acknowledge the update within {minutes} minutes. "
            "Check the composer-executor logs — the release may or may not be active; "
            "the Options card reports what is actually installed."
        ))
        return run

    def tick_control_link(self):
        """Apply queued Control Panel pairing actions onto the agent bridge.

        The web tier records intent in ``DluxControlLinkRequest`` because its
        runtime mount is read-only; this worker owns the only read-write mount.
        An applied row is deleted immediately, so the one-use pairing token is at
        rest for at most one tick. A failed row is kept with its token cleared so
        the tile can surface the error.

        Also retires a published request the agent has already confirmed, which
        the read-only web tier cannot clean up itself.
        """
        from ..models import DluxControlLinkRequest
        from . import control_link

        applied = 0
        for row in DluxControlLinkRequest.objects.filter(error="").order_by("created_at"):
            try:
                if row.action == DluxControlLinkRequest.ACTION_CANCEL:
                    control_link.clear_enroll_request(self.store)
                else:
                    control_link.write_enroll_request(
                        self.store,
                        row.control_url,
                        row.pairing_token,
                        operation_id=row.operation_id,
                    )
            except Exception as exc:
                row.pairing_token = ""
                row.error = str(exc)[:500]
                row.save(update_fields=["pairing_token", "error"])
                continue
            row.delete()
            applied += 1

        status = control_link.read_agent_status(self.store) or {}
        published = control_link.read_enroll_request(self.store)
        last = status.get("last_enroll") if isinstance(status.get("last_enroll"), dict) else {}
        if (
            published
            and last.get("operation_id") == published.get("operation_id")
            and last.get("state") == "ok"
        ):
            control_link.clear_enroll_request(self.store)
        self._detect_control_link_disconnect(status)
        return applied

    def _detect_control_link_disconnect(self, status):
        """Alert admins once when a previously-connected Control Panel enrollment
        drops (revoked, or the agent is no longer enrolled).

        The web tier can render the disconnected state on the panel, but a
        superadmin who never opens that page would not know. Detection lives here
        because only the worker has the read-write runtime mount for the dedup
        marker. Fully isolated — a failure never affects the tick.
        """
        from . import control_link

        try:
            control_url = str(status.get("control_url") or "").strip()
            connected = bool(status.get("enrolled")) and not bool(status.get("revoked"))
            notice = control_link.read_link_notice(self.store)
            if connected:
                # Record the live connection and re-arm, so a later drop alerts
                # again (and a move to a different panel re-arms too).
                if notice.get("connected_url") != control_url or notice.get("disconnect_notified"):
                    control_link.write_link_notice(
                        self.store, {"connected_url": control_url, "disconnect_notified": False}
                    )
                return
            # Not connected: only alert if we actually witnessed a prior connection
            # (never for a deployment that was already disconnected on first sight).
            prior = str(notice.get("connected_url") or "").strip()
            if prior and not notice.get("disconnect_notified"):
                self._notify_admins_control_link_disconnected(prior, bool(status.get("revoked")))
                control_link.write_link_notice(
                    self.store, {"connected_url": prior, "disconnect_notified": True}
                )
        except Exception:
            logger.warning("Control-link disconnect detection failed.", exc_info=True)

    def _notify_admins_control_link_disconnected(self, control_url, revoked):
        try:
            from django.contrib.auth import get_user_model
            from django.urls import NoReverseMatch, reverse

            from ..notifications import notify
            from ..translations import get_strings

            admins = list(get_user_model().objects.filter(is_active=True, is_superuser=True))
            if not admins:
                return
            try:
                target_url = reverse("control_panel")
            except NoReverseMatch:
                target_url = ""
            s = get_strings()
            title = s.get("notif_control_link_disconnected_title", "Control Panel disconnected")
            if revoked:
                template = s.get(
                    "notif_control_link_revoked_message",
                    "This deployment's Control Panel enrollment ({url}) was revoked. "
                    "Local updates still work; pair again to reconnect.",
                )
            else:
                template = s.get(
                    "notif_control_link_disconnected_message",
                    "This deployment is no longer connected to its Control Panel ({url}). "
                    "Pair again to reconnect.",
                )
            message = template.replace("{url}", control_url)
            notify.warning(
                message,
                title=title,
                recipients=admins,
                category="system",
                action="control_link_disconnected",
                source="updater",
                target_url=target_url,
                metadata={"control_url": control_url, "revoked": bool(revoked)},
            )
        except Exception:
            logger.warning("Failed to emit the control-link disconnect notification.", exc_info=True)

    def _begin_image_update(self, row):
        from .image_update import write_composer_trigger, write_deploy_status

        # Publish an initial status immediately so the live progress page shows
        # "preparing" (not a stale 'ready' from a previous update) while we back
        # up and enter maintenance, before composer takes over the status file.
        write_deploy_status(self.store, "preparing")
        row.status = row.STATUS_BACKING_UP
        row.append_log("Creating pre-update backup.")
        row.save(update_fields=["status", "progress_log"])
        backup = self._create_backup(row)
        if backup is not None:
            row.backup_token = backup.token
            row.save(update_fields=["backup_token"])
        # Maintenance stays on until composer finishes (success: cleared by the
        # new container's reconcile reset-to-baked; failure/no-recreate: cleared
        # by _finalize_image_update).
        self.store.set_maintenance(True, token=row.token)
        write_composer_trigger(self.store, row)
        row.status = row.STATUS_AWAITING_RECREATE
        row.handoff_at = timezone.now()
        row.append_log("Maintenance enabled; requested image recreate from composer.")
        row.save(update_fields=["status", "handoff_at", "progress_log"])

    def _finalize_image_update(self, row):
        from django.utils.dateparse import parse_datetime

        from .image_update import (
            HANDOFF_START_TIMEOUT_SECONDS,
            HANDOFF_TIMEOUT_SECONDS,
            read_composer_ack,
            read_deploy_status,
        )

        doc = read_deploy_status(self.store)
        dstatus = str(doc.get("status") or "")
        ack = read_composer_ack(self.store)
        ack_matches = str(ack.get("token") or "") == str(row.token)
        try:
            ack_exit_code = int(ack.get("exit_code")) if ack_matches else None
        except (TypeError, ValueError):
            ack_exit_code = None
        # composer rewrites deploy-status every run; only trust one written
        # at/after our hand-off so a stale 'ready' from a prior update is ignored.
        fresh = row.handoff_at is None
        updated = parse_datetime(str(doc.get("updated_at") or ""))
        if updated is not None and row.handoff_at is not None:
            fresh = updated >= row.handoff_at

        status_failed = fresh and dstatus == "failed"
        ack_failed = ack_matches and ack_exit_code not in (None, 0)
        if status_failed or ack_failed:
            error = ""
            if status_failed or str(doc.get("request_token") or "") == str(row.token):
                error = str(doc.get("error") or "").strip()
            if not error:
                error = (
                    f"Composer update process exited with status {ack_exit_code}."
                    if ack_exit_code is not None
                    else "The image update failed."
                )
            self.store.set_maintenance(False)
            self._fail_image_update(row, error)
            return

        status_ready = fresh and dstatus == "ready"
        ack_ready = ack_matches and ack_exit_code == 0
        if status_ready or ack_ready:
            baked = get_baked_version()
            target_ok = True
            try:
                if row.target_version:
                    target_ok = Version(str(baked)) >= Version(str(row.target_version))
            except InvalidVersion:
                target_ok = True
            if target_ok:
                self.store.set_maintenance(False)
                self._complete_image_update(row, baked)
                return

        # Still in progress (or the target isn't live yet). Bail out and lift
        # maintenance only once the hand-off has clearly timed out.
        if row.handoff_at is not None:
            elapsed = (timezone.now() - row.handoff_at).total_seconds()
            acknowledged = fresh or (ack_matches and ack_exit_code is not None)
            if not acknowledged and elapsed > HANDOFF_START_TIMEOUT_SECONDS:
                self.store.set_maintenance(False)
                self._fail_image_update(
                    row, "Composer did not acknowledge the image update request."
                )
                return
            if elapsed > HANDOFF_TIMEOUT_SECONDS:
                self.store.set_maintenance(False)
                self._fail_image_update(
                    row, "The image update did not complete within the expected time."
                )

    def _complete_image_update(self, row, baked):
        row.status = row.STATUS_COMPLETED
        row.is_active = False
        row.completed_at = timezone.now()
        row.append_log(f"Image update to {row.target_version or baked} completed (baked {baked}).")
        row.save(update_fields=["status", "is_active", "completed_at", "progress_log"])

    def _fail_image_update(self, row, error):
        row.status = row.STATUS_FAILED
        row.is_active = False
        row.completed_at = timezone.now()
        row.error = _sanitize(error)
        row.append_log(f"Image update failed: {row.error}")
        row.save(update_fields=["status", "is_active", "completed_at", "error", "progress_log"])

    def _update_active_state(self, state, candidate, manifest, generation):
        state.previous_version = state.active_version or state.baked_version
        state.previous_wheel_url = state.active_wheel_url
        state.previous_wheel_sha256 = state.active_wheel_sha256
        state.previous_manifest = state.active_manifest
        state.active_version = candidate.version
        state.active_wheel_url = candidate.url
        state.active_wheel_sha256 = candidate.sha256
        state.active_manifest = manifest
        state.generation = generation
        state.degraded = False
        state.degraded_reason = ""
        self.store.clear_degraded()
        state.save()

    @staticmethod
    def _runtime_state_snapshot(state):
        fields = (
            "active_version", "active_wheel_url", "active_wheel_sha256", "active_manifest",
            "previous_version", "previous_wheel_url", "previous_wheel_sha256", "previous_manifest",
            "degraded", "degraded_reason",
        )
        return {field: getattr(state, field) for field in fields}

    @staticmethod
    def _restore_runtime_state(state, snapshot, generation):
        for field, value in snapshot.items():
            setattr(state, field, value)
        state.generation = generation
        state.save()

    def _rollback_pointer(self, state, previous, state_snapshot, run):
        source = previous["source"]
        target = previous["version"]
        env = (
            self.store.python_env_for(previous["path"])
            if source == "volume" else self._image_env()
        )
        next_generation = self.store.read_generation() + 1
        self.store.write_active(target, source=source, generation=next_generation)
        self._restore_runtime_state(state, state_snapshot, next_generation)
        try:
            self._run_manage(["collectstatic", "--noinput", "--clear"], env, run, timeout=600)
        finally:
            self.store.bump_generation()
        self._verify_health(target, env)

    def _image_env(self):
        env = os.environ.copy()
        root = str(self.store.root)
        paths = [part for part in env.get("PYTHONPATH", "").split(os.pathsep) if part]
        env["PYTHONPATH"] = os.pathsep.join(part for part in paths if not part.startswith(root))
        return env

    def _manage_py(self):
        path = Path(settings.BASE_DIR) / "manage.py"
        if not path.is_file():
            raise UpdaterError("The generated project's manage.py could not be found.")
        return path

    def _run_manage(self, args, env, run, *, timeout=300, required=True):
        command = [sys.executable, str(self._manage_py()), *args]
        completed = self.command_runner(
            command,
            cwd=str(settings.BASE_DIR),
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = _sanitize(f"{completed.stdout}\n{completed.stderr}")
        if output:
            run.append_log(output)
            run.save(update_fields=["progress_log"])
        if completed.returncode != 0 and required:
            raise UpdaterError(f"Updater command failed: {' '.join(args)}")
        return completed

    def _doctor_preflight(self, env, run):
        """Advisory dlux wiring check for the target release, scoped to the
        settings/urls groups only.

        Deliberately NOT the full doctor and NOT fatal: at preflight the target's
        migrations are unapplied and its static is uncollected (both run later in
        the flow), so the deep doctor checks would report expected "errors" and
        abort the update. The candidate is a released version whose settings.py is
        unchanged, so wiring is confirmation, not a gate — Django's own `check`
        (run just before, and required) is the hard gate. `--group` keeps the
        report to the wiring checks; a target too old to know the flag simply logs
        and is ignored, since this is non-fatal.
        """
        self._run_manage(
            ["dlux_doctor", "--group", "settings", "--group", "urls"],
            env,
            run,
            required=False,
        )

    def _verify_health(self, expected_version, env):
        deadline = time.monotonic() + 120
        last_error = None
        health_url = "http://web:8000/health/"
        version_url = "http://web:8000/sys/api/dlux-update/runtime-health/"
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(health_url, timeout=5) as response:
                    response.read(8192)
                request = urllib.request.Request(
                    version_url,
                    headers={"X-Dlux-Updater-Probe": runtime_probe_token(settings.SECRET_KEY)},
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    import json
                    payload = json.loads(response.read(8192).decode("utf-8"))
                if payload.get("version") == expected_version:
                    break
                last_error = UpdaterError("Web restarted with an unexpected DjangoLux version.")
            except Exception as exc:
                last_error = exc
            time.sleep(2)
        else:
            raise UpdaterError("The updated web service did not become healthy.") from last_error

        last_celery_error = "Celery has not answered a health probe yet."
        while time.monotonic() < deadline:
            last_celery_error = self._celery_health_error(expected_version, env)
            if not last_celery_error:
                return
            time.sleep(2)
        raise UpdaterError(
            f"The updated Celery service did not become healthy. Last probe: {last_celery_error}"
        )

    def _celery_health_error(self, expected_version, env):
        """Return an empty string only when Celery answers and runs the expected release."""
        settings_module = str(os.environ.get("DJANGO_SETTINGS_MODULE") or "config.settings")
        celery_app = settings_module.split(".", 1)[0]
        try:
            completed = self.command_runner(
                [sys.executable, "-m", "celery", "-A", celery_app, "inspect", "ping", "--timeout", "5"],
                cwd=str(settings.BASE_DIR),
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except Exception as exc:
            return f"Celery ping failed: {_sanitize(exc)}"
        if completed.returncode != 0 or "pong" not in completed.stdout.lower():
            diagnostic = _sanitize(f"{completed.stdout}\n{completed.stderr}")[-500:]
            return f"Celery ping returned no worker response{': ' + diagnostic if diagnostic else '.'}"

        version_probe = (
            "import importlib,sys;"
            f"app=importlib.import_module({(celery_app + '.celery')!r}).app;"
            "replies=app.control.broadcast('dlux_version',reply=True,timeout=5) or [];"
            "versions=[payload.get('version') for reply in replies "
            "for payload in reply.values() if isinstance(payload,dict)];"
            f"sys.exit(0 if versions and all(v == {str(expected_version)!r} for v in versions) else 1)"
        )
        try:
            completed = self.command_runner(
                [sys.executable, "-c", version_probe],
                cwd=str(settings.BASE_DIR),
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except Exception as exc:
            return f"Celery version probe failed: {_sanitize(exc)}"
        if completed.returncode != 0:
            diagnostic = _sanitize(f"{completed.stdout}\n{completed.stderr}")[-500:]
            return f"Celery has not reported DjangoLux {expected_version}{': ' + diagnostic if diagnostic else '.'}"
        return ""

    def _handle_failure(self, run, exc):
        report = run.report or {}
        recovery_unsafe = bool(
            report.get("recovery_failed")
            or (report.get("pointer_switched") and not report.get("pointer_recovered"))
        )
        if not recovery_unsafe:
            try:
                self.store.set_maintenance(False)
            except Exception:
                pass
        try:
            self.store.archive_failed_stage(self.store.stage_path(run.token), run.token)
        except Exception:
            pass
        message = _sanitize(exc)
        run.append_log(message)
        with transaction.atomic():
            state = _state_model().objects.select_for_update().get(pk=1)
            run.finish(run.STATUS_FAILED, error=message)
            run.save(update_fields=[
                "status", "is_active", "completed_at", "error", "report", "progress_log",
            ])
            if state.active_run_token == run.token:
                state.active_run_token = ""
            if run.action == run.ACTION_CHECK:
                state.last_checked_at = timezone.now()
                state.last_check_error = message
                state.latest_compatible = False
                state.latest_reason = message
            elif recovery_unsafe:
                state.degraded = True
                state.degraded_reason = message
                self.store.set_degraded(message)
                self.restart_worker = True
            state.save()
        # Surface a failure that struck while the maintenance flag was up.
        self._mirror_inline_progress(run)
