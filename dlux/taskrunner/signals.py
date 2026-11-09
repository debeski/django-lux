"""Worker lifecycle signals: ``worker_started`` (sent when a worker is ready, like Celery's ``worker_ready``) and ``worker_stopping``."""

from django.dispatch import Signal

# Sent once by ``dlux_worker`` after its heartbeat row exists and before it claims anything.
worker_started = Signal()
# Sent when the worker stops claiming work, before it waits for running tasks.
worker_stopping = Signal()
