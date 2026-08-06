from django.conf import settings
from django.core.management.base import BaseCommand

from dlux.updater import get_baked_version
from dlux.updater.runtime import RuntimeStore
from dlux.updater.supervisor import _is_newer


class Command(BaseCommand):
    help = (
        "File-level runtime pointer reconcile, safe to run BEFORE migrations. "
        "Resets the active runtime pointer to the baked image whenever a "
        "volume-pinned release is not strictly newer than baked, so a stale "
        "pinned release can never wedge the boot chain (migrator/web) behind a "
        "maintenance screen. Touches only the runtime volume, never the "
        "database, and always exits 0 so it cannot block startup."
    )

    def handle(self, *args, **options):
        try:
            root = getattr(settings, "DLUX_UPDATE_RUNTIME_ROOT", "/opt/dlux-runtime")
            store = RuntimeStore(root).ensure()
            baked = get_baked_version()
            try:
                active = store.read_active(baked)
            except Exception:
                # Corrupt/unreadable pointer: the supervisor already falls back to
                # baked on its own, so there is nothing to reset here.
                return
            if active.get("source") == "volume" and not _is_newer(active.get("version"), baked):
                # The pinned release is older-or-equal to the baked image, so the
                # image supersedes it. Point the runtime at baked (the always-
                # servable, app-consistent release) so the very next boot runs the
                # migrator and web against baked instead of the stale release.
                store.write_active(baked, source="image", generation=store.read_generation())
                self.stdout.write(
                    self.style.WARNING(
                        f"Runtime pointer reset to baked {baked} "
                        f"(pinned {active.get('version')} is not newer than baked)."
                    )
                )
        except Exception as exc:  # never block the boot chain
            self.stderr.write(f"dlux_reconcile skipped (non-fatal): {exc}")
