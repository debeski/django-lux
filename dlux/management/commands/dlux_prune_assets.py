"""Delete managed assets nothing points at any more.

An asset outlives the record that used it: replace a product image and the old
one stays in the library and in storage. Nothing collected them, so a long-lived
deployment accumulates files no page can reach.

Deliberately conservative, because deleting a file is not undoable:

* **Dry run by default.** `--apply` is the only thing that deletes.
* **Referenced assets are never touched.** "Referenced" is every relation to the
  asset model (`referenced_asset_ids`: plain foreign keys such as the branding
  fields, font variants and ScanLink releases, one-to-ones, many-to-manys) plus
  the `ManagedAssetField` registry, read through each model's base manager so
  soft-deleted and out-of-scope records count too.
* **The shared namespace is never pruned.** It is a curated pool any field may
  read, so "nothing points at it" is not evidence it is unused.
* A relation or declaration that cannot be read makes the run **refuse**, never
  guess.
* **The row goes first.** Each delete runs in its own transaction, and the file
  is removed by `ManagedAsset.delete` only once that row delete has committed.
  A delete the database refuses (a reference that appeared since the scan)
  leaves both the row and its file as they were.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError, RestrictedError

from dlux.assets import referenced_asset_ids
from dlux.models.asset_field import registered_asset_fields
from dlux.models.assets import SHARED_ASSET_NAMESPACE


class Command(BaseCommand):
    help = "Report (or with --apply, delete) managed assets nothing references."

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually delete. Without it nothing is written and the report is a preview.',
        )
        parser.add_argument(
            '--namespace', action='append', default=[], metavar='NS',
            help='Restrict to this namespace. Repeatable. Default: every namespace except the shared pool.',
        )
        parser.add_argument(
            '--kind', default='', help='Restrict to one asset kind (image, font, ...).',
        )
        parser.add_argument(
            '--include-shared', action='store_true',
            help=f'Also consider {SHARED_ASSET_NAMESPACE}. Off by default: it is a curated pool.',
        )

    def handle(self, *args, **options):
        from dlux.models import ManagedAsset

        referenced = self._referenced_ids()
        queryset = ManagedAsset.objects.all()

        if options['kind']:
            queryset = queryset.filter(kind=options['kind'])
        if options['namespace']:
            queryset = queryset.filter(namespace__in=options['namespace'])
        elif not options['include_shared']:
            queryset = queryset.exclude(namespace=SHARED_ASSET_NAMESPACE)

        orphans = queryset.exclude(pk__in=referenced) if referenced else queryset
        orphans = list(orphans.order_by('namespace', 'pk'))

        self.stdout.write(
            f"Declared asset fields: {len(registered_asset_fields())} "
            f"| referenced assets: {len(referenced)} | candidates: {len(orphans)}"
        )
        if not orphans:
            self.stdout.write(self.style.SUCCESS('Nothing to prune.'))
            return

        by_namespace = {}
        for asset in orphans:
            by_namespace.setdefault(asset.namespace or '(default)', []).append(asset)
        for namespace, assets in sorted(by_namespace.items()):
            self.stdout.write(f"\n  {namespace} — {len(assets)}")
            for asset in assets[:20]:
                self.stdout.write(f"    #{asset.pk} {asset.kind} {getattr(asset.file, 'name', '') or '(no file)'}")
            if len(assets) > 20:
                self.stdout.write(f"    … and {len(assets) - 20} more")

        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                f"\nDry run — nothing deleted. Re-run with --apply to remove {len(orphans)}."
            ))
            return

        deleted = 0
        for asset in orphans:
            pk = asset.pk
            try:
                # The file is scheduled by ManagedAsset.delete for after this
                # commits, so a refused or rolled-back delete keeps it.
                with transaction.atomic():
                    asset.delete()
            except (ProtectedError, RestrictedError):
                self.stderr.write(f"    kept #{pk}: it is referenced")
                continue
            except Exception as exc:
                # One failure must not abandon the rest of the run.
                if ManagedAsset.objects.filter(pk=pk).exists():
                    self.stderr.write(f"    could not delete #{pk}: {exc}")
                    continue
                self.stderr.write(f"    deleted #{pk}, but its file could not be removed: {exc}")
            deleted += 1
        self.stdout.write(self.style.SUCCESS(f"\nDeleted {deleted} of {len(orphans)}."))

    def _referenced_ids(self):
        """Every asset id any relation or declared field currently points at."""
        referenced = referenced_asset_ids()
        for declaration in registered_asset_fields().values():
            column = f'{declaration.field_name}_id'
            try:
                values = (
                    declaration.model._base_manager
                    .filter(~Q(**{column: None}))
                    .values_list(column, flat=True)
                )
                referenced.update(v for v in values if v is not None)
            except Exception as exc:
                # A model whose table is missing (an app mid-migration) must make
                # the run refuse to delete, not silently widen the orphan set.
                raise RuntimeError(
                    f"Could not read {declaration.identity}; refusing to prune: {exc}"
                ) from exc
        return referenced
