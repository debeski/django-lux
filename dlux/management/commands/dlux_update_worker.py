import random
import signal
import threading
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from dlux import __version__
from dlux.updater.service import UpdateService, queue_daily_check_if_due, updates_enabled


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

        service = UpdateService()
        state = service.reconcile()
        if state.degraded:
            raise CommandError(state.degraded_reason or "DjangoLux runtime reconstruction failed.")
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
                service.process_next()
                return

            jitter = 0 if options["no_jitter"] else random.randint(0, 1800)
            daily_check_after = time.monotonic() + jitter
            poll_seconds = max(0.5, min(float(options["poll_seconds"]), 30.0))
            self.stdout.write(self.style.SUCCESS("DjangoLux update worker is ready."))

            while not stopping:
                processed = service.process_next()
                if service.restart_worker:
                    self.stdout.write("Active release changed; restarting update worker.")
                    return
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
