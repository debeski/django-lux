import base64
import random
import string
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management import call_command, get_commands, load_command_class
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from dlux.utils.sections import _is_child_model, _model_is_section


BUILTIN_APP_LABELS = {
    "admin",
    "auth",
    "contenttypes",
    "dlux",
    "messages",
    "sessions",
    "staticfiles",
}
AUDIT_FIELD_NAMES = {
    "created_at",
    "updated_at",
    "deleted_at",
    "created_by",
    "updated_by",
    "deleted_by",
}
IMAGE_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
    "AScY42YAAAAASUVORK5CYII="
)


def build_seed_pdf(label):
    escaped_label = (
        str(label)
        .encode("ascii", "replace")
        .replace(b"\\", b"\\\\")
        .replace(b"(", b"\\(")
        .replace(b")", b"\\)")
    )
    stream = (
        b"BT\n/F1 12 Tf\n72 720 Td\n(Seeded document: "
        + escaped_label
        + b") Tj\nET\n"
    )
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        (
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"endstream"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    )

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


class SeedModelError(Exception):
    pass


class MissingRelatedRows(SeedModelError):
    pass


def model_label(model):
    return model._meta.label_lower


def normalize_model_label(value):
    return str(value or "").strip().lower()


def is_seedable_project_model(model, app_labels=None):
    meta = model._meta
    if (
        meta.abstract
        or meta.auto_created
        or meta.proxy
        or not meta.managed
        or meta.swapped
        or meta.app_label in BUILTIN_APP_LABELS
        or getattr(model, "dlux_seed", None) is False
    ):
        return False

    if app_labels and meta.app_label not in app_labels:
        return False
    if getattr(model, "dlux_seed", None) is True:
        return True

    app_config = meta.app_config
    base_dir = getattr(settings, "BASE_DIR", None)
    if app_config and base_dir:
        try:
            Path(app_config.path).resolve().relative_to(Path(base_dir).resolve())
            return True
        except (OSError, ValueError):
            return False
    return not model.__module__.startswith(("django.", "dlux."))


def discover_seed_models(app_labels=None):
    labels = {
        str(label).strip().lower()
        for label in app_labels or ()
        if str(label).strip()
    }
    return sorted(
        (
            model
            for model in apps.get_models()
            if is_seedable_project_model(model, labels or None)
        ),
        key=model_label,
    )


def resolve_requested_models(tokens, candidates):
    if not tokens:
        return list(candidates)

    indexes = {}
    for model in candidates:
        keys = {
            model_label(model),
            model._meta.model_name.lower(),
            model._meta.object_name.lower(),
        }
        for key in keys:
            indexes.setdefault(key, []).append(model)

    resolved = []
    for token in tokens:
        matches = indexes.get(normalize_model_label(token), [])
        if not matches:
            raise CommandError(f"Unknown or ineligible model: {token}")
        if len(matches) > 1:
            labels = ", ".join(model_label(model) for model in matches)
            raise CommandError(f"Ambiguous model '{token}'; use one of: {labels}")
        if matches[0] not in resolved:
            resolved.append(matches[0])
    return resolved


def get_populate_command():
    owner = get_commands().get("populate")
    if not owner or owner == "dlux":
        return None
    try:
        app_config = next(
            config
            for config in apps.get_app_configs()
            if owner in {config.label, config.name}
        )
        Path(app_config.path).resolve().relative_to(Path(settings.BASE_DIR).resolve())
    except (LookupError, OSError, StopIteration, TypeError, ValueError):
        return None
    return load_command_class(owner, "populate")


def declared_populate_labels(command):
    return {
        normalize_model_label(label)
        for label in getattr(command, "dlux_populate_models", ())
        if normalize_model_label(label)
    }


def related_models(models_to_seed):
    related = set()
    for model in models_to_seed:
        for field in model._meta.get_fields():
            target = getattr(field, "related_model", None)
            if not field.is_relation or field.auto_created or target is None or target is model:
                continue
            related.add(target)
    return related


def is_lookup_model(model):
    return _model_is_section(model) or _is_child_model(model, model._meta.app_label)


def command_accepts_option(command, option_name):
    parser = command.create_parser("manage.py", "populate")
    return any(action.dest == option_name for action in parser._actions)


class MetadataSeeder:
    def __init__(self, *, database, rng, batch_label):
        self.database = database
        self.rng = rng
        self.batch_label = batch_label

    def seed_model(self, model, count):
        created = []
        with transaction.atomic(using=self.database):
            for index in range(1, count + 1):
                instance = self._create_instance(model, index)
                created.append(instance)
        return created

    def _create_instance(self, model, index):
        last_error = None
        for attempt in range(1, 6):
            try:
                with transaction.atomic(using=self.database):
                    values = self._model_values(model, index, attempt)
                    instance = model(**values)
                    instance.full_clean()
                    instance.save(using=self.database)
                    self._assign_many_to_many(instance)
                    return instance
            except MissingRelatedRows:
                raise
            except (IntegrityError, ValidationError, ValueError, TypeError) as exc:
                last_error = exc
        raise SeedModelError(
            f"could not create a valid row after 5 attempts: {last_error}"
        )

    def _model_values(self, model, index, attempt):
        values = {}
        for field in model._meta.concrete_fields:
            if self._skip_field(field):
                continue
            value = self._field_value(model, field, index, attempt)
            if value is not models.NOT_PROVIDED:
                values[field.name] = value
        return values

    @staticmethod
    def _skip_field(field):
        if isinstance(field, (models.AutoField, models.BigAutoField, models.SmallAutoField)):
            return True
        if field.name in AUDIT_FIELD_NAMES or not field.editable:
            return True
        if getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False):
            return True
        if field.has_default() and not field.choices:
            default = field.get_default()
            return field.blank or default not in field.empty_values
        return False

    def _field_value(self, model, field, index, attempt):
        if isinstance(field, (models.ForeignKey, models.OneToOneField)):
            return self._related_value(model, field)

        required = not field.blank
        if isinstance(field, models.FileField) and not required:
            return None if field.null else ""
        if field.null and not required and self.rng.random() < 0.15:
            return None
        if field.choices:
            values = [
                value
                for value, _label in field.flatchoices
                if value not in (None, "") or not required
            ]
            if values:
                return self.rng.choice(values)

        token = self._token(model, field, index, attempt)
        if isinstance(field, models.BooleanField):
            return bool(self.rng.getrandbits(1))
        if isinstance(field, models.UUIDField):
            return uuid.UUID(int=self.rng.getrandbits(128))
        if isinstance(field, models.EmailField):
            return self._fit(f"{token}@example.test", field.max_length)
        if isinstance(field, models.URLField):
            return self._fit(f"https://example.test/{token}", field.max_length)
        if isinstance(field, models.SlugField):
            return self._fit(token.lower(), field.max_length)
        if isinstance(field, models.GenericIPAddressField):
            return f"192.0.2.{self.rng.randint(1, 254)}"
        if isinstance(field, models.TextField):
            if field.blank and self.rng.random() < 0.15:
                return ""
            return f"Seeded {field.verbose_name} {token}"
        if isinstance(field, models.CharField):
            if field.blank and self.rng.random() < 0.15:
                return ""
            return self._fit(f"{field.name}-{token}", field.max_length)
        if isinstance(field, models.DateTimeField):
            return timezone.now() - timedelta(
                days=self.rng.randint(0, 365),
                seconds=self.rng.randint(0, 86399),
            )
        if isinstance(field, models.DateField):
            return date(
                timezone.now().year - self.rng.randint(0, 5),
                self.rng.randint(1, 12),
                self.rng.randint(1, 28),
            )
        if isinstance(field, models.TimeField):
            return time(
                self.rng.randint(0, 23),
                self.rng.randint(0, 59),
                self.rng.randint(0, 59),
            )
        if isinstance(field, models.DurationField):
            return timedelta(minutes=self.rng.randint(1, 10080))
        if isinstance(field, models.DecimalField):
            scale = Decimal(10) ** -field.decimal_places
            whole_digits = max(1, field.max_digits - field.decimal_places)
            maximum = (10 ** min(whole_digits, 6)) - 1
            fraction = scale if field.decimal_places else Decimal(0)
            return (Decimal(self.rng.randint(0, maximum)) + fraction).quantize(scale)
        if isinstance(field, models.FloatField):
            return round(self.rng.uniform(1, 10000), 3)
        if isinstance(field, models.IntegerField):
            minimum, maximum = 1, 10_000
            for validator in field.validators:
                limit = getattr(validator, "limit_value", None)
                if callable(limit):
                    limit = limit()
                if limit is None:
                    continue
                if getattr(validator, "code", "") == "min_value":
                    minimum = max(minimum, int(limit))
                elif getattr(validator, "code", "") == "max_value":
                    maximum = min(maximum, int(limit))
            if minimum > maximum:
                raise SeedModelError(
                    f"no valid integer range for {model_label(model)}.{field.name}"
                )
            return self.rng.randint(minimum, maximum)
        if isinstance(field, models.JSONField):
            return {"seed": self.batch_label, "token": token}
        if isinstance(field, models.BinaryField):
            return token.encode("utf-8")
        if isinstance(field, models.ImageField):
            return ContentFile(IMAGE_BYTES, name=f"{token}.png")
        if isinstance(field, models.FileField):
            extension = self._file_extension(field)
            content = (
                build_seed_pdf(token)
                if extension == "pdf"
                else f"Seeded file {token}\n".encode("utf-8")
            )
            return ContentFile(
                content,
                name=f"{token}.{extension}",
            )
        raise SeedModelError(
            f"unsupported required field {model_label(model)}.{field.name} "
            f"({field.get_internal_type()})"
        )

    def _related_value(self, model, field):
        target = field.remote_field.model
        rows = list(target._default_manager.using(self.database).all()[:500])
        required = not field.null and not field.has_default()
        if isinstance(field, models.OneToOneField) and rows:
            used = set(
                model._default_manager.using(self.database)
                .exclude(**{f"{field.name}__isnull": True})
                .values_list(field.attname, flat=True)
            )
            rows = [row for row in rows if row.pk not in used]
        if not rows:
            if required:
                raise MissingRelatedRows(
                    f"{model_label(model)} requires rows in {model_label(target)}"
                )
            return None
        if not required and self.rng.random() < 0.20:
            return None
        return self.rng.choice(rows)

    def _assign_many_to_many(self, instance):
        for field in instance._meta.many_to_many:
            if not field.remote_field.through._meta.auto_created:
                continue
            rows = list(
                field.remote_field.model._default_manager.using(self.database).all()[:100]
            )
            if not rows:
                if not field.blank:
                    raise MissingRelatedRows(
                        f"{model_label(instance.__class__)} requires rows in "
                        f"{model_label(field.remote_field.model)}"
                    )
                continue
            minimum = 0 if field.blank else 1
            maximum = min(3, len(rows))
            size = self.rng.randint(minimum, maximum)
            getattr(instance, field.name).set(self.rng.sample(rows, size))

    def _token(self, model, field, index, attempt):
        random_part = "".join(self.rng.choices(string.ascii_lowercase + string.digits, k=6))
        return (
            f"{self.batch_label}-{model._meta.model_name}-{field.name}-"
            f"{index}-{attempt}-{random_part}"
        )

    @staticmethod
    def _fit(value, max_length):
        if not max_length:
            return value
        if len(value) <= max_length:
            return value
        return value[-max_length:]

    @staticmethod
    def _file_extension(field):
        for validator in field.validators:
            allowed = getattr(validator, "allowed_extensions", None)
            if allowed:
                return str(sorted(allowed)[0]).lower()
        return "txt"


class Command(BaseCommand):
    help = (
        "Discover project models and generate valid random development rows from "
        "their field metadata."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "models",
            nargs="*",
            help="Optional app.Model labels or unambiguous model names.",
        )
        parser.add_argument(
            "--app",
            action="append",
            default=[],
            dest="apps",
            help="Limit auto-discovery to an app label; repeatable.",
        )
        parser.add_argument(
            "--exclude",
            action="append",
            default=[],
            help="Exclude an app.Model label; repeatable.",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=10,
            help="Rows to create per seeded model. Default: 10.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Deterministic random seed.",
        )
        parser.add_argument(
            "--batch-label",
            default="",
            help="Value embedded in generated text. Defaults to a timestamp.",
        )
        parser.add_argument(
            "--database",
            default="default",
            help="Database alias. Default: default.",
        )
        parser.add_argument(
            "--no-populate",
            action="store_true",
            help="Do not invoke a project-owned populate command for empty dependencies.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Create rows. Without this flag the command only prints its plan.",
        )

    def handle(self, *args, **options):
        if options["count"] < 1:
            raise CommandError("--count must be at least 1.")

        candidates = discover_seed_models(options["apps"])
        selected = resolve_requested_models(options["models"], candidates)
        excluded = {normalize_model_label(value) for value in options["exclude"]}
        selected = [model for model in selected if model_label(model) not in excluded]
        if not selected:
            raise CommandError("No eligible project models were selected.")

        populate_command = get_populate_command()
        populate_labels = (
            declared_populate_labels(populate_command) if populate_command else set()
        )
        if populate_command and not populate_labels:
            populate_labels = {
                model_label(model) for model in candidates if is_lookup_model(model)
            }
        populate_models = [
            model for model in selected if model_label(model) in populate_labels
        ]
        seed_models = [
            model for model in selected if model_label(model) not in populate_labels
        ]

        owned_relations = {
            model
            for model in related_models(seed_models)
            if model_label(model) in populate_labels
        }
        populate_models.extend(
            model
            for model in sorted(owned_relations, key=model_label)
            if model not in populate_models
        )
        missing_populate_models = [
            model
            for model in populate_models
            if not model._default_manager.using(options["database"]).exists()
        ]

        self._write_plan(seed_models, missing_populate_models, options)
        if not options["apply"]:
            self.stdout.write(self.style.WARNING(
                "Dry run only; re-run with --apply to create rows."
            ))
            return

        batch_label = options["batch_label"] or datetime.now().strftime("%Y%m%d%H%M%S")
        rng = random.Random(options["seed"])
        seeder = MetadataSeeder(
            database=options["database"],
            rng=rng,
            batch_label=batch_label,
        )

        created = {}
        skipped = {}
        with transaction.atomic(using=options["database"]):
            if missing_populate_models and not options["no_populate"]:
                self._run_populate(
                    populate_command,
                    missing_populate_models,
                    options["database"],
                    options["verbosity"],
                )

            pending = list(seed_models)
            while pending:
                progress = False
                for model in list(pending):
                    try:
                        rows = seeder.seed_model(model, options["count"])
                    except MissingRelatedRows:
                        continue
                    except SeedModelError as exc:
                        skipped[model_label(model)] = str(exc)
                        pending.remove(model)
                        progress = True
                    else:
                        created[model_label(model)] = len(rows)
                        pending.remove(model)
                        progress = True
                if not progress:
                    for model in pending:
                        skipped[model_label(model)] = self._missing_relation_reason(
                            model,
                            options["database"],
                        )
                    break

        for label, count in created.items():
            self.stdout.write(self.style.SUCCESS(f"Created {count} row(s): {label}"))
        for label, reason in skipped.items():
            self.stderr.write(self.style.WARNING(f"Skipped {label}: {reason}"))
        self.stdout.write(self.style.SUCCESS(
            f"Seed complete: {sum(created.values())} row(s) across "
            f"{len(created)} model(s); {len(skipped)} model(s) skipped."
        ))

    def _write_plan(self, seed_models, populate_models, options):
        mode = "APPLY" if options["apply"] else "DRY RUN"
        self.stdout.write(f"DjangoLux seed plan ({mode})")
        if populate_models:
            label = (
                "Empty canonical dependencies (--no-populate): "
                if options["no_populate"]
                else "Populate empty dependencies: "
            )
            self.stdout.write(label + ", ".join(
                model_label(model) for model in populate_models
            ))
        else:
            self.stdout.write("Populate empty dependencies: none")
        self.stdout.write(
            f"Seed {options['count']} row(s) each: "
            + (", ".join(model_label(model) for model in seed_models) or "none")
        )

    def _run_populate(self, command, models_to_populate, database, verbosity):
        if command is None:
            return
        labels = [model_label(model) for model in models_to_populate]
        kwargs = {
            "verbosity": max(0, verbosity - 1),
            "stdout": self.stdout,
            "stderr": self.stderr,
        }
        if command_accepts_option(command, "models"):
            kwargs["models"] = labels
        if command_accepts_option(command, "database"):
            kwargs["database"] = database
        self.stdout.write("Running local populate for: " + ", ".join(labels))
        call_command("populate", **kwargs)

    @staticmethod
    def _missing_relation_reason(model, database):
        missing = []
        for field in model._meta.concrete_fields:
            if not isinstance(field, (models.ForeignKey, models.OneToOneField)):
                continue
            if field.blank or field.null or field.has_default():
                continue
            target = field.remote_field.model
            if not target._default_manager.using(database).exists():
                missing.append(model_label(target))
        for field in model._meta.many_to_many:
            if field.blank or not field.remote_field.through._meta.auto_created:
                continue
            target = field.remote_field.model
            if not target._default_manager.using(database).exists():
                missing.append(model_label(target))
        if missing:
            return "missing required related rows: " + ", ".join(sorted(set(missing)))
        return "unresolved required relation cycle"
