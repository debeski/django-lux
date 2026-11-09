"""Run DjangoLux's task worker: queued tasks and ``DLUX_TASK_SCHEDULE``."""

import signal

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run queued and scheduled tasks from the DjangoLux task queue."

    def add_arguments(self, parser):
        parser.add_argument("--threads", type=int, default=None, help="Tasks run at once (default DLUX_TASK_RUNNER['threads']).")
        parser.add_argument("--queue", action="append", dest="queues", help="Queue to take work from; repeat for several.")
        parser.add_argument("--no-schedule", action="store_true", help="Run queued work only; leave DLUX_TASK_SCHEDULE to other workers.")
        parser.add_argument("--burst", action="store_true", help="Run what is due now in this thread, then exit.")
        parser.add_argument("--check", action="store_true",
                            help="Exit 0 when a worker on this host has a fresh heartbeat (a container healthcheck).")

    def handle(self, *args, **options):
        from dlux.taskrunner.worker import Worker

        if options["check"]:
            import socket

            from dlux.taskrunner.queue import live_dlux_workers

            if not live_dlux_workers().filter(hostname=socket.gethostname()[:255]).exists():
                raise CommandError("No dlux_worker on this host has a fresh heartbeat.")
            self.stdout.write("ok")
            return
        worker = Worker(threads=options["threads"], queues=options["queues"], schedule=not options["no_schedule"])
        if options["burst"]:
            done = worker.run_burst()
            self.stdout.write(f"Ran {done} task(s).")
            return
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, worker.stop)
        worker.run()
