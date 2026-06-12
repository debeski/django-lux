import json
from pathlib import Path

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

from dlux.models import SystemSettings
from dlux.utils import apply_system_settings_import, export_system_settings_payload


class Command(BaseCommand):
    help = "Manage the Dlux SystemSettings singleton for development and portable setup workflows."

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            choices=("status", "unconfigure", "configure", "delete", "reset", "export", "import"),
            help="Action to run against the SystemSettings singleton.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Confirm destructive actions such as delete and reset.",
        )
        parser.add_argument(
            "--input",
            dest="input_path",
            help="JSON file to import for the import action.",
        )
        parser.add_argument(
            "--output",
            dest="output_path",
            help="JSON file to write for the export action. Omit to print JSON to stdout.",
        )
        parser.add_argument(
            "--leave-unconfigured",
            action="store_true",
            help="When importing, apply settings but keep is_configured=False.",
        )

    def _existing(self):
        return SystemSettings._default_manager.filter(pk=1).first()

    def _clear_cache(self):
        cache.delete(SystemSettings.__name__)

    def _require_yes(self, action):
        if not action:
            raise CommandError("This action requires --yes.")

    def _status(self):
        instance = self._existing()
        if not instance:
            self.stdout.write("SystemSettings singleton: missing")
            self.stdout.write("Next SystemSettings.load() will recreate it.")
            return

        self.stdout.write("SystemSettings singleton: present")
        self.stdout.write(f"pk: {instance.pk}")
        self.stdout.write(f"is_configured: {bool(instance.is_configured)}")
        self.stdout.write(f"home_url: {instance.home_url or ''}")
        self.stdout.write(f"default_language: {instance.default_language or ''}")
        self.stdout.write(f"default_theme: {instance.default_theme or ''}")
        self.stdout.write(f"prevent_multiple_active_sessions: {bool(getattr(instance, 'prevent_multiple_active_sessions', False))}")
        self.stdout.write(f"sidebar_enabled: {bool((instance.sidebar_config or {}).get('enabled', True))}")
        self.stdout.write(f"navbar_enabled: {bool((instance.navbar_config or {}).get('enabled', False))}")

    def _set_configured(self, value):
        instance = SystemSettings.load()
        instance.is_configured = bool(value)
        instance.save(update_fields=["is_configured"])
        state = "configured" if value else "unconfigured"
        self.stdout.write(self.style.SUCCESS(f"SystemSettings marked {state}."))

    def _delete(self):
        deleted, _ = SystemSettings._default_manager.filter(pk=1).delete()
        self._clear_cache()
        self.stdout.write(self.style.SUCCESS(f"Deleted SystemSettings singleton rows: {deleted}."))

    def _reset(self):
        SystemSettings._default_manager.filter(pk=1).delete()
        instance = SystemSettings(is_configured=False)
        instance.save()
        self._clear_cache()
        instance.refresh_cache()
        self.stdout.write(self.style.SUCCESS("SystemSettings reset to model defaults and marked unconfigured."))

    def _export(self, output_path):
        payload = export_system_settings_payload(SystemSettings.load())
        raw = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        if output_path:
            path = Path(output_path)
            path.write_text(f"{raw}\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Exported SystemSettings to {path}."))
            return
        self.stdout.write(raw)

    def _import(self, input_path, leave_unconfigured):
        if not input_path:
            raise CommandError("The import action requires --input.")
        path = Path(input_path)
        if not path.exists() or not path.is_file():
            raise CommandError(f"Import file not found: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8") or "{}")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CommandError(f"Invalid import JSON: {exc}") from exc

        instance = SystemSettings.load()
        apply_system_settings_import(
            instance,
            payload,
            mark_configured=not leave_unconfigured,
            preserve_email_secret=True,
        )
        state = "unconfigured" if leave_unconfigured else "configured"
        self.stdout.write(self.style.SUCCESS(f"Imported SystemSettings from {path} and marked {state}."))

    def handle(self, *args, **options):
        action = options["action"]
        if action == "status":
            self._status()
        elif action == "unconfigure":
            self._set_configured(False)
        elif action == "configure":
            self._set_configured(True)
        elif action == "delete":
            self._require_yes(options["yes"])
            self._delete()
        elif action == "reset":
            self._require_yes(options["yes"])
            self._reset()
        elif action == "export":
            self._export(options.get("output_path"))
        elif action == "import":
            self._import(options.get("input_path"), options["leave_unconfigured"])
