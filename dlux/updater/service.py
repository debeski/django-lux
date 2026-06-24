from __future__ import annotations

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


TERMINAL_STATUSES = frozenset({"completed", "failed", "rolled_back"})
_SECRET_KEY_PATTERN = r"[A-Za-z0-9_.-]*(?:password|secret|token|authorization)[A-Za-z0-9_.-]*"
_SECRET_VALUE_PATTERN = r'''(?:(?:bearer|basic)\s+\S+|"(?:\\.|[^"])*"|'(?:\\.|[^'])*'|[^\s,;]+)'''
SECRET_RE = re.compile(
    rf'''(?ix)(["']?{_SECRET_KEY_PATTERN}["']?\s*[:=]\s*){_SECRET_VALUE_PATTERN}'''
)
SECRET_FLAG_RE = re.compile(rf"(?i)(--?{_SECRET_KEY_PATTERN}\s+)(\S+)")


def updates_enabled():
    return bool(getattr(settings, "DLUX_INLINE_UPDATES_ENABLED", False))


def runtime_store():
    return RuntimeStore(getattr(settings, "DLUX_UPDATE_RUNTIME_ROOT", "/opt/dlux-runtime")).ensure()


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
    return {
        "enabled": updates_enabled(),
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
        }
    return serialize_state(state)


def queue_run(action, username=""):
    if not updates_enabled():
        raise UpdaterError("Inline DjangoLux updates are disabled for this project.")
    Run = _run_model()
    if action not in {Run.ACTION_CHECK, Run.ACTION_APPLY, Run.ACTION_ROLLBACK}:
        raise UpdaterError("The requested updater action is invalid.")
    State = _state_model()
    State.load()
    with transaction.atomic():
        state = State.objects.select_for_update().get(pk=1)
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
        )
        state.active_run_token = run.token
        state.save(update_fields=["active_run_token", "updated_at"])
    return run


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
        if active and active["source"] == "volume" and self._version_is_newer(
            baked_version, active["version"]
        ):
            next_generation = self.store.read_generation() + 1
            self.store.write_active(baked_version, source="image", generation=next_generation)
            self.store.set_generation(next_generation)
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
                "latest_reason": "A newer project-image DjangoLux release was activated.",
                "generation": next_generation,
                "degraded": False,
                "degraded_reason": "",
            }
            for field, value in reset_fields.items():
                if getattr(state, field) != value:
                    setattr(state, field, value)
                    changed.append(field)
            self.store.clear_degraded()
            self.store.set_maintenance(False)
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
                "latest_reason": "A newer project-image DjangoLux release was activated.",
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
            active = self.store.read_active(baked_version)
        if active is None or (
            not self.store.active_file.exists()
            and state.active_version
            and state.active_version != baked_version
        ):
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
            if restoration_succeeded and (state.degraded or state.degraded_reason):
                state.degraded = False
                state.degraded_reason = ""
                changed.extend(["degraded", "degraded_reason"])
            if not state.degraded:
                self.store.clear_degraded()
        if changed:
            state.save(update_fields=list(dict.fromkeys(changed + ["updated_at"])))
        return state

    @staticmethod
    def _version_is_newer(candidate, current):
        try:
            return Version(str(candidate)) > Version(str(current))
        except InvalidVersion:
            return False

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
        assessment = assess_wheel(candidate, wheel)
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

    def _complete(self, run, *, report=None, status=None):
        status = status or run.STATUS_COMPLETED
        with transaction.atomic():
            state = _state_model().objects.select_for_update().get(pk=1)
            run.finish(status, report=report)
            run.save(update_fields=[
                "status", "is_active", "completed_at", "error", "report", "progress_log",
            ])
            if state.active_run_token == run.token:
                state.active_run_token = ""
                state.save(update_fields=["active_run_token", "updated_at"])

    def _process_check(self, run):
        state = _state_model().load()
        current = state.active_version or state.baked_version
        index = fetch_simple_index()
        candidate = select_latest_candidate(index, current)
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
        assessment = assess_wheel(candidate, wheel)
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
        candidate = select_latest_candidate(index, state.active_version or state.baked_version)
        if not candidate or candidate.version != state.latest_version:
            raise UpdaterError("The previously checked release is no longer the latest stable update.")
        if candidate.sha256 != state.latest_wheel_sha256 or candidate.url != state.latest_wheel_url:
            raise UpdaterError("The PyPI release metadata changed after the update check.")
        run.wheel_url = candidate.url
        run.wheel_sha256 = candidate.sha256
        run.target_version = candidate.version
        run.save(update_fields=["wheel_url", "wheel_sha256", "target_version"])
        return candidate

    def _process_apply(self, run):
        state = _state_model().load()
        if not state.latest_compatible:
            raise UpdaterError("The selected DjangoLux release is not inline-safe.")
        candidate = self._verified_latest_candidate(state, run)
        self._transition(run, run.STATUS_DOWNLOADING, f"Downloading DjangoLux {candidate.version} again.")
        wheel = download_wheel(candidate, self.store.wheel_path(candidate))
        self._transition(run, run.STATUS_VERIFYING, "Re-verifying the release before installation.")
        verify_pypi_attestation(candidate)
        assessment = assess_wheel(candidate, wheel)
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
        self._run_manage(["dlux_check"], candidate_env, run)
        self._run_manage(["migrate", "--plan"], candidate_env, run)

        self._transition(run, run.STATUS_BACKING_UP, "Creating a full pre-update DjangoLux backup.")
        backup = self._create_backup(run)
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
        self._run_manage(["dlux_check"], env, run)
        self._transition(run, run.STATUS_BACKING_UP, "Creating a full pre-rollback DjangoLux backup.")
        backup = self._create_backup(run)
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

    def _create_backup(self, run):
        from dlux.backup import run_system_backup

        SystemBackup = apps.get_model("dlux", "SystemBackup")
        backup = SystemBackup.objects.create(
            requested_by_username=run.requested_by_username,
            trigger=SystemBackup.TRIGGER_UPDATE,
        )
        run_system_backup(backup.pk)
        backup.refresh_from_db()
        if backup.status != SystemBackup.STATUS_COMPLETED:
            raise UpdaterError("The required pre-update system backup failed.")
        return backup

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

    def _run_manage(self, args, env, run, *, timeout=300):
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
        if completed.returncode != 0:
            raise UpdaterError(f"Updater command failed: {' '.join(args)}")
        return completed

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
