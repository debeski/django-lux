"""
Management command to seed UserActivityLog with random entries for pagination testing.

Usage:
    python manage.py seed_activity_log --count 250
    python manage.py seed_activity_log --count 500 --user-id 1
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from microsys.models import UserActivityLog, Scope
import random

User = get_user_model()


class Command(BaseCommand):
    help = "Seed UserActivityLog with random entries for pagination testing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=200,
            help="Number of activity log entries to create (default: 200)",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            help="Specific user ID to use as the actor (default: random existing user)",
        )
        parser.add_argument(
            "--scope-id",
            type=int,
            help="Specific scope ID to assign (default: random or None)",
        )

    def handle(self, *args, **options):
        count = options["count"]
        user_id = options.get("user_id")
        scope_id = options.get("scope_id")

        # Resolve user
        if user_id:
            try:
                user = User.objects.get(pk=user_id)
                self.stdout.write(f"Using specified user: {user.username} (ID: {user.pk})")
            except User.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"User with ID {user_id} not found"))
                return
        else:
            users = list(User.objects.all()[:10])
            if not users:
                self.stderr.write(self.style.ERROR("No users found. Create a user first."))
                return
            user = random.choice(users)
            self.stdout.write(f"Using random user: {user.username} (ID: {user.pk})")

        # Resolve scope
        scope = None
        if scope_id:
            try:
                scope = Scope.objects.get(pk=scope_id)
                self.stdout.write(f"Using specified scope: {scope.name} (ID: {scope.pk})")
            except Scope.DoesNotExist:
                self.stderr.write(self.style.WARNING(f"Scope with ID {scope_id} not found, using None"))
        else:
            scopes = list(Scope.objects.all())
            if scopes:
                scope = random.choice(scopes)
                self.stdout.write(f"Using random scope: {scope.name} (ID: {scope.pk})")

        # Sample data pools
        actions = [
            "create", "update", "delete", "view", "login", "logout",
            "export", "import", "approve", "reject", "assign", "unassign",
            "activate", "deactivate", "publish", "unpublish", "archive", "restore",
        ]

        model_names = [
            "User", "Profile", "Product", "Order", "Customer", "Invoice",
            "Payment", "Category", "Tag", "Comment", "Review", "Session",
            "Document", "Attachment", "Notification", "Setting", "Log",
        ]

        ip_addresses = [
            "192.168.1.100", "10.0.0.50", "172.16.0.25",
            "203.0.113.45", "198.51.100.22", "192.0.2.10",
        ] + [f"192.168.{random.randint(0, 255)}.{random.randint(1, 254)}" for _ in range(20)]

        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.0",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.0",
            "Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X) AppleWebKit/605.0",
        ]

        # Create entries in batches
        batch_size = 100
        created = 0

        self.stdout.write(f"Creating {count} activity log entries...")

        for i in range(count):
            # Vary timestamps over the last 90 days
            days_ago = random.randint(0, 90)
            hours_ago = random.randint(0, 23)
            minutes_ago = random.randint(0, 59)
            created_at = timezone.now() - timezone.timedelta(
                days=days_ago, hours=hours_ago, minutes=minutes_ago
            )

            # Randomize fields
            action = random.choice(actions)
            model_name = random.choice(model_names)
            object_id = random.randint(1, 10000)
            number = f"DOC-{random.randint(1000, 99999)}" if random.random() > 0.3 else None
            ip_address = random.choice(ip_addresses)
            user_agent = random.choice(user_agents) if random.random() > 0.2 else None

            # Build varied details payload
            details = {
                "action": action,
                "model": model_name,
                "id": object_id,
            }
            if random.random() > 0.5:
                details["changes"] = {
                    "field": random.choice(["name", "status", "price", "quantity"]),
                    "old": f"old_value_{random.randint(1, 100)}",
                    "new": f"new_value_{random.randint(1, 100)}",
                }
            if random.random() > 0.7:
                details["metadata"] = {
                    "source": random.choice(["web", "api", "mobile", "import"]),
                    "version": f"1.{random.randint(0, 20)}.{random.randint(0, 9)}",
                }

            entry = UserActivityLog(
                created_by=user,
                action=action,
                model_name=model_name,
                object_id=object_id,
                number=number,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details,
                scope=scope,
            )

            # Override the auto_now_add timestamp
            entry.save()
            UserActivityLog.objects.filter(pk=entry.pk).update(created_at=created_at)

            created += 1
            if created % batch_size == 0:
                self.stdout.write(f"  ... created {created}/{count}")

        self.stdout.write(self.style.SUCCESS(f"Successfully created {created} activity log entries"))
        self.stdout.write(f"View them in the admin or activity log UI to test pagination.")
