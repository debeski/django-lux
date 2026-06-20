"""Prune old activity-log rows per the System Settings ``log_config`` retention policy.

- ``user`` and ``system`` categories are pruned when their section ``retention_days`` > 0.
- ``audit`` is privileged: it is pruned ONLY when ``audit.retention_days`` > 0 (the
  app-level immutability guard is intentionally bypassed here via a bulk delete, because the
  operator explicitly configured an audit retention window).

Usage:
    manage.py dlux_prune_activity_log [--dry-run]
"""
from datetime import timedelta

from django.apps import apps
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Delete activity-log rows older than the configured per-category retention."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Report what would be deleted without deleting anything.",
        )

    def handle(self, *args, **options):
        from dlux.utils.activity_log import get_active_log_config

        ActivityLog = apps.get_model('dlux', 'ActivityLog')
        log_config = get_active_log_config()
        now = timezone.now()
        dry_run = options.get('dry_run')
        total = 0

        for category in ('user', 'system', 'audit'):
            section = log_config.get(category) if isinstance(log_config, dict) else None
            if not isinstance(section, dict):
                continue
            try:
                retention_days = int(section.get('retention_days', 0) or 0)
            except (TypeError, ValueError):
                retention_days = 0
            if retention_days <= 0:
                self.stdout.write(f"  • {category}: keep forever (retention_days=0) — skipped")
                continue

            cutoff = now - timedelta(days=retention_days)
            qs = ActivityLog.all_objects.filter(category=category, created_at__lt=cutoff)
            count = qs.count()
            total += count
            verb = "would delete" if dry_run else "deleted"
            self.stdout.write(
                f"  • {category}: {verb} {count} row(s) older than {retention_days} day(s) "
                f"(before {cutoff.isoformat()})"
            )
            if count and not dry_run:
                qs.delete()

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}Activity-log prune complete: {total} row(s)."))
