import random
import signal
import threading
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from dlux import __version__
from dlux.updater import UpdaterError
from dlux.updater.service import (
    UpdateService,
    queue_daily_check_if_due,
    record_worker_volume_report,
    updates_enabled,
)
from dlux.updater.agent_bridge import (
    consume_agent_requests,
    publish_agent_results,
    publish_agent_snapshot,
)


class Command(BaseCommand):
    help = "Run the isolated DjangoLux update queue worker."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process at most one queued operation.")
        parser.add_argument("--no-jitter", action="store_true", help="Disable daily-check startup jitter.")
        parser.add_argument("--poll-seconds", type=float, default=2.0)

    def handle(self, *args, **options):
        stopping = False

        def stop(_signum, _frame):
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)

        try:
            service = UpdateService()
        except UpdaterError as exc:
            # This process owns the write side, so its verdict is the one the
            # panel and the queue guard read. Record it before dying, or the
            # deployment shows nothing but a worker that keeps restarting.
            record_worker_volume_report(str(exc))
            raise
        record_worker_volume_report()
        state = service.reconcile()
        if state.degraded:
            # Never wedge the site behind a maintenance screen on a degraded
            # reconcile. The baked image is always servable — its app code and dlux
            # shipped together — so fall back to it, clear the flags, and restart
            # clean instead of crash-looping. The failure stays in the archived
            # state and logs for operator review.
            from dlux.updater import get_baked_version

            baked = get_baked_version()
            service.store.write_active(baked, source="image", generation=service.store.read_generation())
            service.store.clear_degraded()
            service.store.set_maintenance(False)
            service.store.invalidate_heartbeat()
            self.stdout.write(self.style.WARNING(
                f"Degraded runtime ({state.degraded_reason or 'reconstruction failed'}); "
                f"reconciled to baked {baked} and restarting the update worker."
            ))
            return
        if state.active_version and state.active_version != __version__:
            service.store.invalidate_heartbeat()
            self.stdout.write("Selected runtime release differs from this interpreter; restarting the update worker.")
            return
        service.store.write_heartbeat()
        heartbeat_stop = threading.Event()

        def keep_heartbeat_fresh():
            while not heartbeat_stop.wait(10):
                service.store.write_heartbeat()

        heartbeat = threading.Thread(
            target=keep_heartbeat_fresh,
            name="dlux-updater-heartbeat",
            daemon=True,
        )
        heartbeat.start()
        try:
            recovered = service.recover_interrupted_run()
            if recovered and service.restart_worker:
                self.stdout.write("Interrupted update recovered; restarting update worker.")
                return
            if options["once"]:
                consume_agent_requests(service)
                service.process_next()
                service.tick_image_update()
                service.tick_control_link()
                publish_agent_results(service.store)
                publish_agent_snapshot(service.store, force=True)
                return

            jitter = 0 if options["no_jitter"] else random.randint(0, 1800)
            daily_check_after = time.monotonic() + jitter
            poll_seconds = max(0.5, min(float(options["poll_seconds"]), 30.0))
            self.stdout.write(self.style.SUCCESS("DjangoLux update worker is ready."))

            while not stopping:
                record_worker_volume_report()
                consume_agent_requests(service)
                processed = service.process_next()
                if service.restart_worker:
                    self.stdout.write("Active release changed; restarting update worker.")
                    return
                # Advance any in-flight image-level update (composer hand-off).
                # Independent of the inline run queue above.
                service.tick_image_update()
                # Publish any Control Panel pairing request the read-only web
                # tier queued for us.
                service.tick_control_link()
                publish_agent_results(service.store)
                publish_agent_snapshot(service.store)
                if not processed and updates_enabled() and time.monotonic() >= daily_check_after:
                    queue_daily_check_if_due()
                    daily_check_after = time.monotonic() + max(
                        300,
                        int(getattr(settings, "DLUX_UPDATE_CHECK_INTERVAL", 86400) or 86400),
                    )
                time.sleep(poll_seconds)
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=2)
