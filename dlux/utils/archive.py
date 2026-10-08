"""Model-to-zip archive primitives.

Shared by the system backup (`dlux.backup`) and the report archive
(`dlux.reports.archive`). It lives in `utils` because it belongs to neither
feature: before the split, `dlux.backup` imported it from `dlux.reports`, which
made the system backup depend on the reports feature for its serialization.

`stream_model_into_zip` takes a `label_field_resolver` so the caller decides how
a record folder is named. The reports archive passes its config-driven resolver;
the system backup passes nothing and gets flat pk folders.
"""

import io
import json
import re
import shutil
import unicodedata

from django.core.files.storage import default_storage
from django.core.serializers.json import Serializer as JsonSerializer
from django.db import models

from .common import _iter_queryset_by_pk

class _CursorlessJSONSerializer(JsonSerializer):
    """Backup serializer variant that avoids QuerySet.iterator() entirely.

    Natural keys are memoised per related row in ``natural_key_cache`` (shared
    across every model of one backup run). Without it each FK to a natural-key
    model costs one query per serialized row — 60k queries for 20k audited rows.
    M2M values read from the prefetch cache that ``_serialization_queryset``
    arranges instead of issuing a query per row.
    """

    natural_key_cache = None
    # ``row_observer(pk, text) -> bool`` sees each record's exact JSON and says
    # whether to write it; incremental backups digest every row this way and
    # keep only the ones that changed.
    row_observer = None
    _written = False

    def end_object(self, obj):
        if self.row_observer is None:
            return super().end_object(obj)
        dump = self.get_dump_object(obj)
        text = json.dumps(dump, **self.json_kwargs)
        self._current = None
        if not self.row_observer(dump.get("pk"), text):
            return
        if self._written:
            self.stream.write(", ")
        self.stream.write(text)
        self._written = True

    def _cached_natural_key(self, model, key, loader):
        cache = self.natural_key_cache
        if cache is None:
            return loader()
        cache_key = (model, key)
        if cache_key not in cache:
            cache[cache_key] = loader()
        return cache[cache_key]

    def _resolve_fk_natural_key(self, obj, field):
        related_model = field.remote_field.model
        if not self._model_supports_natural_key(related_model):
            return None
        value = getattr(obj, field.attname, None)
        if value is None:
            return None

        def load():
            related = getattr(obj, field.name, None)
            try:
                return related.natural_key()
            except AttributeError:
                return None

        return self._cached_natural_key(related_model, (field.target_field.attname, value), load)

    def handle_m2m_field(self, obj, field):
        if not field.remote_field.through._meta.auto_created:
            return
        related_model = field.remote_field.model
        related = list(getattr(obj, field.name).all())
        related.sort(key=lambda value: value.pk)
        if self.use_natural_foreign_keys and hasattr(related_model, "natural_key"):
            self._current[field.name] = [
                self._cached_natural_key(related_model, ("pk", value.pk), value.natural_key)
                or self._value_from_field(value, value._meta.pk)
                for value in related
            ]
            return
        self._current[field.name] = [
            self._value_from_field(value, value._meta.pk) for value in related
        ]


def _serialization_queryset(qs, *, natural_foreign_keys):
    """Join natural-key FK targets and prefetch auto M2M links for serialization."""
    meta = qs.model._meta
    joins = []
    if natural_foreign_keys:
        for field in meta.concrete_fields:
            related = getattr(field, "related_model", None)
            if field.is_relation and related is not None and callable(getattr(related, "natural_key", None)):
                joins.append(field.name)
    prefetches = [
        field.name for field in meta.many_to_many
        if field.remote_field.through._meta.auto_created
    ]
    if joins:
        qs = qs.select_related(*joins)
    if prefetches:
        qs = qs.prefetch_related(*prefetches)
    return qs


# Media that is already compressed gains nothing from DEFLATE and costs ~20x the
# time of a plain copy, so those archive members are stored as-is.
_STORED_EXTENSIONS = frozenset({
    "7z", "avif", "bz2", "docx", "gif", "gz", "heic", "jpeg", "jpg", "m4a", "m4v",
    "mov", "mp3", "mp4", "ogg", "pdf", "png", "pptx", "rar", "webm", "webp",
    "xlsx", "xz", "zip", "zst",
})


def _file_member(name):
    import time
    import zipfile

    info = zipfile.ZipInfo(name, date_time=time.localtime()[:6])
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    info.compress_type = zipfile.ZIP_STORED if extension in _STORED_EXTENSIONS else zipfile.ZIP_DEFLATED
    return info


def _model_natural_key_fields(model):
    """Best-effort field list composing a model's natural key, or ``[]``.

    System backups serialize foreign keys with ``use_natural_foreign_keys=True``,
    so an FK to a model that defines ``natural_key()`` is stored as that natural
    key (e.g. ``["alice"]``) rather than a PK. Only confidently-derivable cases
    are reported — currently models exposing ``USERNAME_FIELD`` (the auth user) —
    so the viewer can map such references to a label. When this returns ``[]``
    the viewer falls back to displaying the raw natural key, which is itself
    already human-readable.
    """
    if not callable(getattr(model, "natural_key", None)):
        return []
    username_field = getattr(model, "USERNAME_FIELD", None)
    if username_field:
        try:
            model._meta.get_field(username_field)
        except Exception:
            return []
        return [username_field]
    return []


def _safe_archive_segment(value, *, max_length=80):
    value = unicodedata.normalize("NFKC", str(value or "")).strip()
    value = re.sub(r"[\\/\x00-\x1f\x7f]+", "-", value)
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"-+", "-", value).strip(" .-")
    return value[:max_length].rstrip(" .-")


def build_relation_schema(models_list, *, label_field_resolver=None):
    """Per-model relation + label metadata baked into the backup manifest.

    Lets the standalone ``.dlb`` viewer resolve FK/O2O/M2M references to readable
    labels without the originating project. Shape::

        {"app.model": {"label_field": "name",
                       "natural_key_fields": ["username"],   # omitted when empty
                       "relations": {"field": {"kind": "fk|o2o|m2m",
                                               "to": "app.target"}}}}

    Only relations that ``dumpdata`` actually serializes are recorded (concrete
    FK/O2O fields and M2M fields backed by an auto-created through table), keyed
    by the same name the serializer uses in each record's ``fields`` map.
    Defensive: any per-model failure is skipped rather than breaking the backup,
    since this is a viewer convenience, not restore data.
    """
    schema = {}
    for model in models_list:
        try:
            meta = model._meta
            relations = {}
            for field in meta.concrete_fields:
                if not field.is_relation or field.related_model is None:
                    continue
                kind = "o2o" if field.one_to_one else "fk" if field.many_to_one else ""
                if not kind:
                    continue
                relations[field.name] = {
                    "kind": kind,
                    "to": field.related_model._meta.label_lower,
                }
            for field in meta.local_many_to_many:
                if field.related_model is None:
                    continue
                # Only auto-created through tables are serialized by dumpdata.
                if not field.remote_field.through._meta.auto_created:
                    continue
                relations[field.name] = {
                    "kind": "m2m",
                    "to": field.related_model._meta.label_lower,
                }
            label_field = label_field_resolver(model) if label_field_resolver else ""
            if not label_field:
                # User-like models rarely have a name/title field but read well
                # by their login identifier (e.g. username).
                username_field = getattr(model, "USERNAME_FIELD", None)
                if username_field:
                    try:
                        meta.get_field(username_field)
                        label_field = username_field
                    except Exception:
                        pass
            entry = {
                "label_field": label_field,
                "relations": relations,
            }
            natural_key_fields = _model_natural_key_fields(model)
            if natural_key_fields:
                entry["natural_key_fields"] = natural_key_fields
            schema[meta.label_lower] = entry
        except Exception:
            continue
    return schema


def backup_record_folder(record, *, label_field=None, label_field_resolver=None):
    """Human-readable base folder for one report-backup record."""
    if label_field is not None:
        field_name = label_field
    elif label_field_resolver is not None:
        field_name = label_field_resolver(record.__class__)
    else:
        field_name = ""
    label = _safe_archive_segment(getattr(record, field_name, "")) if field_name else ""
    if label:
        field_label = _safe_archive_segment(field_name.replace("_", "-"), max_length=30)
        return f"{field_label}-{label}"
    object_label = _safe_archive_segment(str(record))
    if object_label and object_label != _safe_archive_segment(record.pk, max_length=80):
        return f"record-{object_label}"
    return "record"


def stream_model_into_zip(
    zf,
    model,
    qs,
    manifest,
    *,
    serialize_kwargs=None,
    object_transform=None,
    human_record_folders=False,
    label_field_resolver=None,
    include_files=True,
    include_records=True,
    step_callback=None,
    natural_key_cache=None,
    row_observer=None,
    file_filter=None,
):
    """Stream one model's records (JSON) and its file-field contents into an
    open backup ZipFile, recording everything in ``manifest``.

    Shared by the reports backup and the full system backup: the serializer
    writes straight into the zip entry and storage files are chunk-copied, so
    peak memory stays flat no matter how many records/PDFs are covered.

    ``include_files=False`` produces a data-only export: record JSON is still
    written (FileField *names* are preserved in the data), but the referenced
    media blobs are not copied into the archive. A restore then leaves existing
    media on disk untouched (``_restore_files`` only touches files the manifest
    lists). This is what the inline updater's pre-update backup uses so a quick
    code/schema update is not gated on copying gigabytes of unchanged uploads.

    ``include_records=False`` is the mirror image: copy the media and record the
    manifest entries, but write no ``data/`` JSON. The periodic reports ZIP uses
    it because that archive is a deliverable read by people — its data ships as
    the entries workbook — and is never restored. The restorable ``.dlb`` always
    keeps the JSON.

    ``natural_key_cache`` is a dict shared across the models of one run, so a
    user referenced by every audited table is resolved once, not once per row.

    ``row_observer(pk, text) -> bool`` receives every record's serialized JSON
    and decides whether it is written; the manifest count is then the number
    written. ``file_filter(storage_name) -> bool`` decides whether a media file
    is copied. Incremental backups use both to keep only what changed.

    ``step_callback(stage, done, total)`` — ``stage`` being ``"rows"`` or
    ``"files"`` — reports movement *inside* one model. Without it a model holding
    thousands of uploads looks frozen for as long as it takes to copy them, which
    is indistinguishable from a dead worker.
    """
    meta = model._meta
    model_key = meta.label_lower
    total_rows = qs.count()
    model_entry = {"model": model_key, "count": total_rows}
    manifest["models"].append(model_entry)

    def report(stage, done, total):
        if step_callback:
            step_callback(stage, done, total)

    serialize_kwargs = serialize_kwargs or {}
    rows_qs = _serialization_queryset(
        qs, natural_foreign_keys=bool(serialize_kwargs.get("use_natural_foreign_keys")),
    )

    def serialized_objects():
        for position, obj in enumerate(_iter_queryset_by_pk(rows_qs, chunk_size=1000), start=1):
            report("rows", position, total_rows)
            yield object_transform(obj) if object_transform else obj

    if include_records:
        with zf.open(f"data/{meta.app_label}/{meta.model_name}.json", mode="w") as raw_stream:
            text_stream = io.TextIOWrapper(raw_stream, encoding="utf-8")
            serializer = _CursorlessJSONSerializer()
            serializer.natural_key_cache = natural_key_cache
            written = [0]
            if row_observer is not None:
                def observe(pk, text):
                    keep = row_observer(pk, text)
                    written[0] += 1 if keep else 0
                    return keep
                serializer.row_observer = observe
            serializer.serialize(
                serialized_objects(),
                stream=text_stream,
                **serialize_kwargs,
            )
            text_stream.flush()
            text_stream.detach()
        if row_observer is not None:
            model_entry["count"] = written[0]
            model_entry["total"] = total_rows
    if not include_files:
        return
    file_fields = [
        field for field in meta.get_fields()
        if isinstance(field, (models.FileField, models.ImageField))
    ]
    if not file_fields:
        return
    # Human folders may name a record by ``str(record)``, which can read any
    # field, so only the flat-pk layout narrows the columns it loads.
    files_qs = qs if human_record_folders else qs.only(
        meta.pk.attname, *(field.attname for field in file_fields),
    )
    record_label_field = (
        label_field_resolver(model) if human_record_folders and label_field_resolver else ""
    )
    folder_counts = {}
    for position, record in enumerate(_iter_queryset_by_pk(files_qs, chunk_size=500), start=1):
        report("files", position, total_rows)
        if human_record_folders:
            base_folder = backup_record_folder(record, label_field=record_label_field)
            folder_counts[base_folder] = folder_counts.get(base_folder, 0) + 1
            occurrence = folder_counts[base_folder]
            record_folder = base_folder if occurrence == 1 else f"{base_folder}--{occurrence}"
        else:
            record_folder = str(record.pk)
        for field in file_fields:
            file_value = getattr(record, field.name, None)
            if not file_value or not getattr(file_value, "name", ""):
                continue
            if file_filter is not None and not file_filter(file_value.name):
                continue
            archive_name = f"files/{meta.app_label}/{meta.model_name}/{record_folder}/{field.name}/{file_value.name.split('/')[-1]}"
            try:
                with default_storage.open(file_value.name, "rb") as fh, \
                        zf.open(_file_member(archive_name), mode="w") as dest:
                    shutil.copyfileobj(fh, dest, 256 * 1024)
                manifest["files"].append({
                    "model": model_key,
                    "pk": record.pk,
                    "record_folder": record_folder,
                    "record_label_field": record_label_field,
                    "field": field.name,
                    "path": archive_name,
                    # Original storage name — what a restore writes the file back as.
                    "name": file_value.name,
                })
            except Exception:
                manifest["missing_files"].append({
                    "model": model_key,
                    "pk": record.pk,
                    "field": field.name,
                    "name": file_value.name,
                })
