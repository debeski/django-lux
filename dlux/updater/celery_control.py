"""Optional Celery inspect command used to confirm the worker's active Dlux release."""

try:
    from celery.worker.control import inspect_command
except ImportError:  # pragma: no cover - Celery is optional outside generated projects.
    inspect_command = None


if inspect_command is not None:  # pragma: no branch
    @inspect_command()
    def dlux_version(state, **kwargs):
        from dlux import __version__

        return {"version": __version__}
