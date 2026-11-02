"""Activity rows for records that predate activity logging.

Reports count the activity log. A record saved before its deployment logged
activity (an import, a seed, a project that adopted DjangoLux reports later) has
no CREATE row, so it is never counted. ``backfill_report_activity`` writes the
missing CREATE rows from what the record itself holds: when it was created (the
same timestamp field reports window a model's rows by), who created it, its scope
and its number. Each row carries ``details={"backfilled": True}``, so it reads as
reconstructed rather than observed. A record that already has a CREATE row, under
its model key or a legacy model name, is skipped, so a second run writes nothing.
"""

from django.apps import apps
from django.db import models as django_models, transaction

from .eligibility import get_report_eligible_models
from .queries import _backup_timestamp_field, _iter_queryset_by_pk, report_model_key

BACKFILL_ACTION = "CREATE"
BACKFILL_DETAILS = {"backfilled": True, "source": "record"}


def _created_object_ids(model):
    """Primary keys of ``model`` records that already have a CREATE row."""
    ActivityLog = apps.get_model("dlux", "ActivityLog")
    label = model._meta.label_lower
    rows = (
        ActivityLog._base_manager.filter(action=BACKFILL_ACTION, object_id__isnull=False)
        .values_list("model_key", "model_name", "object_id")
        .order_by()
        .distinct()
    )
    return {
        object_id for model_key, model_name, object_id in rows
        if report_model_key(model_key, model_name) == label
    }


def _user_field(model):
    try:
        field = model._meta.get_field("created_by")
    except Exception:
        return None
    return field.attname if getattr(field, "is_relation", False) else None


def _has_field(model, name):
    try:
        model._meta.get_field(name)
    except Exception:
        return False
    return True


def backfill_report_activity(models=None, *, apply=False, batch_size=500):
    """Count, and with ``apply`` write, the missing CREATE rows.

    Returns ``[{"model", "missing", "written", "skipped"}]``, one per eligible
    model; ``skipped`` names why a model was left out: ``no_timestamp`` (nothing
    to place the row in time) or ``non_integer_pk`` (``ActivityLog.object_id`` is
    an integer, so the row could not be matched to its record on a later run).
    """
    ActivityLog = apps.get_model("dlux", "ActivityLog")
    results = []
    for model in models or get_report_eligible_models():
        label = model._meta.label_lower
        timestamp = _backup_timestamp_field(model)
        if not timestamp:
            results.append({"model": label, "missing": 0, "written": 0, "skipped": "no_timestamp"})
            continue
        if not isinstance(model._meta.pk, (django_models.AutoField, django_models.BigAutoField, django_models.IntegerField)):
            results.append({"model": label, "missing": 0, "written": 0, "skipped": "non_integer_pk"})
            continue
        user_field = _user_field(model)
        has_scope = _has_field(model, "scope")
        has_number = _has_field(model, "number")
        logged = _created_object_ids(model)
        missing = written = 0
        pending = []

        def flush():
            nonlocal written
            if not pending:
                return
            with transaction.atomic():
                created = ActivityLog._base_manager.bulk_create([row for row, _ in pending])
                # `created_at` is auto_now_add, so bulk_create stamps it with now;
                # set the record's own creation time afterwards.
                for row, (_, when) in zip(created, pending):
                    row.created_at = when
                ActivityLog._base_manager.bulk_update(created, ["created_at"])
            written += len(pending)
            pending.clear()

        for record in _iter_queryset_by_pk(model._base_manager.all(), chunk_size=batch_size):
            when = getattr(record, timestamp, None)
            if record.pk in logged or when is None:
                continue
            missing += 1
            if not apply:
                continue
            number = str(getattr(record, "number", "") or "")[:50] if has_number else ""
            row = ActivityLog(
                action=BACKFILL_ACTION,
                category=ActivityLog.CATEGORY_USER,
                model_name=str(model._meta.verbose_name),
                model_key=label,
                object_id=record.pk,
                number=number or None,
                details=dict(BACKFILL_DETAILS),
                created_by_id=getattr(record, user_field, None) if user_field else None,
                scope_id=getattr(record, "scope_id", None) if has_scope else None,
            )
            pending.append((row, when))
            if len(pending) >= batch_size:
                flush()
        flush()
        results.append({"model": label, "missing": missing, "written": written, "skipped": ""})
    return results
