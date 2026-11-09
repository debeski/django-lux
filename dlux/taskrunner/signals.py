"""Worker lifecycle signals (the dlux backend's counterpart of Celery's ``worker_ready``)."""

from django.dispatch import Signal

# Sent once by ``dlux_worker`` after its heartbeat row exists and before it claims anything.
worker_started = Signal()
# Sent when the worker stops claiming work, before it waits for running tasks.
worker_stopping = Signal()
