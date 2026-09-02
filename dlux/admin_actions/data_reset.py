"""Superuser "Reset data" admin command.

Clears row data from selected models, in one of two modes.

**Soft** (the default) respects Dlux semantics:

- ``ScopedModel`` subclasses are **soft-deleted** (the same recoverable
  ``deleted_at`` mechanism the app uses everywhere) via a bulk ``update()`` —
  ``QuerySet.delete()`` would bypass the model's soft-delete override. Their
  media files are always kept (the rows are recoverable).
- Non-scoped models are **hard-deleted** via ``QuerySet.delete()``, which honours
  each incoming relation's ``on_delete`` (CASCADE cascades, SET_NULL nulls,
  PROTECT blocks — that model is skipped and reported). Their FileField/ImageField
  blobs are removed only when the caller opts into deleting media.

**Permanent** is for starting over: every selected model is hard-deleted,
scoped ones included, and for those it also empties the recycle bin — rows soft-
deleted by any earlier action go too. Media follows the same opt-in. There is no
undo, so the endpoint requires an explicit typed confirmation on top of the
password gate.

A model that exists only as a line of another record — an invoice's items, a
product's variants — is never offered: see ``cascade_parent``.

Bulk operations do not run ``save()``/``delete()``, so a denormalized figure a
project maintains there (a stock balance, a cached total) is left standing when
the rows behind it go. Projects repair theirs from the ``data_reset_finished``
signal.

Hard guards (never selectable, never touched): System Settings, the updater state
rows, permission groups/permissions, and Django internals. ``auth.User`` is
selectable but superusers and the acting user are always protected.
"""
import django.dispatch
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

#: Soft-delete what can be soft-deleted; hard-delete the rest. Recoverable.
RESET_MODE_SOFT = 'soft'
#: Hard-delete everything selected, recycle bin included. Not recoverable.
RESET_MODE_PERMANENT = 'permanent'
RESET_MODES = (RESET_MODE_SOFT, RESET_MODE_PERMANENT)
#: Typed on top of the password before permanent mode will run. The UI shows
#: the localized `data_reset_confirm_word`; both are accepted.
DATA_RESET_CONFIRM_WORD = 'DELETE'

#: Sent once a reset run has finished, with ``actor``, ``mode``, ``models``
#: (the label_lower keys that were selected) and ``results``.
#:
#: A reset writes in bulk, so no ``save()`` or ``delete()`` runs and anything a
#: project derives in those methods goes stale. Connect a receiver to rebuild it
#: — the canonical case being a running balance kept on a parent row while the
#: ledger rows that moved it are what the operator just cleared.
data_reset_finished = django.dispatch.Signal()


def normalize_mode(value):
    """Anything unrecognized is the safe mode."""
    mode = str(value or '').strip().lower()
    return mode if mode in RESET_MODES else RESET_MODE_SOFT

# label_lower of models that must never be cleared from here.
HARD_EXCLUDED_MODELS = frozenset({
    'dlux.systemsettings',
    'dlux.dluxupdatestate',
    'dlux.dluxupdaterun',
    'dlux.dluximageupdate',
    'auth.group',
    'auth.permission',
    'contenttypes.contenttype',
    'sessions.session',
    'admin.logentry',
})
HARD_EXCLUDED_APPS = frozenset({'contenttypes', 'sessions', 'admin', 'migrations', 'authtoken'})

_EXCLUDE_MEDIA_FIELD_HINTS = ('password', 'secret', 'token', 'hash', 'encrypted')


def _scoped_model_cls():
    from ..models import ScopedModel
    return ScopedModel


def is_scoped(model):
    try:
        return issubclass(model, _scoped_model_cls())
    except TypeError:
        return False


def _structurally_eligible(model):
    meta = model._meta
    if meta.abstract or not meta.managed or meta.auto_created or meta.proxy:
        return False
    if meta.app_label in HARD_EXCLUDED_APPS:
        return False
    if meta.label_lower in HARD_EXCLUDED_MODELS:
        return False
    return True


def cascade_parent(model):
    """The record this model is a *line* of, or None.

    An invoice's items, a product's variants, a count's lines: rows that have no
    life of their own, and that nobody resets on their own. Offering them
    separately is actively harmful — soft-deleting the invoices leaves their
    items behind, and clearing the items after that permanently strands a parent
    that was supposed to be recoverable. So a line model is kept out of the
    catalog entirely: in permanent mode its parent's delete already takes it
    through CASCADE, and in soft mode leaving it alone is what keeps the parent
    restorable.

    Detected as a required CASCADE foreign key to another resettable model. Two
    deliberate exemptions:

    - A ``ScopedModel`` is never a line. It carries its own soft-delete
      lifecycle, which is what makes it a record rather than a row.
    - The user model is never a parent. Devices, sessions and memberships do
      cascade from a user, but clearing users is not how an operator clears
      those, so they stay selectable in their own right.
    """
    if is_scoped(model):
        return None
    user_model = get_user_model()
    for field in model._meta.get_fields():
        if not isinstance(field, models.ForeignKey) or field.null:
            continue
        if getattr(field.remote_field, 'on_delete', None) is not models.CASCADE:
            continue
        parent = field.remote_field.model
        if parent is model or parent is user_model:
            continue
        if _structurally_eligible(parent):
            return parent
    return None


def is_reset_eligible(model):
    return _structurally_eligible(model) and cascade_parent(model) is None


def _file_fields(model):
    fields = []
    for field in model._meta.get_fields():
        if not isinstance(field, (models.FileField, models.ImageField)):
            continue
        if any(hint in field.name.lower() for hint in _EXCLUDE_MEDIA_FIELD_HINTS):
            continue
        fields.append(field.name)
    return fields


def _deletion_queryset(model, actor, mode=RESET_MODE_SOFT):
    """Rows that a reset would remove — protected rows are excluded up front."""
    User = get_user_model()
    if model is User:
        # Never delete superusers or the operator running the command.
        qs = model._base_manager.filter(is_superuser=False)
        if actor is not None and getattr(actor, 'pk', None) is not None:
            qs = qs.exclude(pk=actor.pk)
        return qs
    if is_scoped(model):
        qs = model.all_objects.all()
        if mode != RESET_MODE_PERMANENT:
            # Soft mode touches live rows only: what is already in the recycle
            # bin is "gone" as far as the app is concerned. Permanent mode is
            # the one that empties the bin as well.
            qs = qs.filter(deleted_at__isnull=True)
        return qs
    return model._base_manager.all()


def _trashed_count(model):
    """Rows already soft-deleted — what permanent mode would additionally purge."""
    if not is_scoped(model):
        return 0
    try:
        return model.all_objects.filter(deleted_at__isnull=False).count()
    except Exception:
        return 0


def _model_label(model, strings=None):
    from ..utils.activity_log import translate_activity_log_model_name
    key = model._meta.label_lower
    if strings is not None:
        label = translate_activity_log_model_name(key, strings)
        # translate_* echoes the raw "app.model" key when there is no translation;
        # never show that — fall back to the model's readable verbose name.
        if label and label != key:
            return str(label)
    return str(model._meta.verbose_name_plural).strip().title()


def build_reset_catalog(actor, strings=None):
    """[{key, label, app, count, trashed, scoped, has_media}] for eligible models.

    ``count`` is what soft mode would clear; ``trashed`` is what permanent mode
    would take on top of it.
    """
    catalog = []
    for model in apps.get_models():
        if not is_reset_eligible(model):
            continue
        try:
            count = _deletion_queryset(model, actor).count()
        except Exception:
            continue
        catalog.append({
            'key': model._meta.label_lower,
            'label': _model_label(model, strings),
            'app': model._meta.app_label,
            'count': count,
            'trashed': _trashed_count(model),
            'scoped': is_scoped(model),
            'has_media': bool(_file_fields(model)),
        })
    catalog.sort(key=lambda item: (not item['scoped'], item['app'], item['label'].lower()))
    return catalog


def _delete_media_files(model, queryset):
    from django.core.files.storage import default_storage
    field_names = _file_fields(model)
    if not field_names:
        return 0
    removed = 0
    for obj in queryset.iterator(chunk_size=200):
        for name in field_names:
            file_field = getattr(obj, name, None)
            stored = getattr(file_field, 'name', '') or ''
            if not stored:
                continue
            try:
                if default_storage.exists(stored):
                    default_storage.delete(stored)
                    removed += 1
            except Exception:
                continue
    return removed


def execute_reset(actor, selected_keys, *, delete_media=False, mode=RESET_MODE_SOFT):
    """Clear the selected models. Each model runs in its own savepoint so a
    PROTECT block (or any error) on one does not roll back the others. Returns a
    list of per-model result dicts.

    ``mode`` is ``RESET_MODE_SOFT`` (scoped models are soft-deleted) or
    ``RESET_MODE_PERMANENT`` (everything hard-deleted, recycle bin included).
    """
    mode = normalize_mode(mode)
    results = []
    selected = [str(k).strip().lower() for k in (selected_keys or []) if str(k).strip()]
    for key in selected:
        model = _resolve_model(key)
        if model is None or not is_reset_eligible(model):
            results.append({'key': key, 'label': key, 'status': 'skipped', 'reason': 'not_eligible', 'deleted': 0})
            continue
        label = _model_label(model)
        scoped = is_scoped(model)
        # Scoped rows survive as recoverable ones only in soft mode.
        soft = scoped and mode != RESET_MODE_PERMANENT
        qs = _deletion_queryset(model, actor, mode)
        try:
            with transaction.atomic():
                count = qs.count()
                if count == 0:
                    results.append({'key': key, 'label': label, 'status': 'empty', 'deleted': 0,
                                    'scoped': scoped, 'media_deleted': 0})
                    continue
                if soft:
                    # Bulk soft-delete — QuerySet.delete() bypasses the soft-delete
                    # override, so update() the recoverable markers directly.
                    qs.update(deleted_at=timezone.now(), deleted_by=actor)
                    results.append({'key': key, 'label': label, 'status': 'soft_deleted',
                                    'deleted': count, 'scoped': True, 'media_deleted': 0})
                else:
                    # Media goes with the rows now that nothing can bring them back.
                    media_deleted = _delete_media_files(model, qs) if delete_media else 0
                    qs.delete()
                    results.append({'key': key, 'label': label, 'status': 'deleted',
                                    'deleted': count, 'scoped': scoped, 'media_deleted': media_deleted})
        except ProtectedError:
            results.append({'key': key, 'label': label, 'status': 'protected', 'deleted': 0,
                            'scoped': scoped})
        except Exception as exc:  # noqa: BLE001 — surface the failure per model
            results.append({'key': key, 'label': label, 'status': 'error', 'deleted': 0,
                            'reason': str(exc)[:200]})

    # After the writes, never between them: a receiver rebuilding a derived
    # figure has to see the final state of every model in the run.
    try:
        data_reset_finished.send(
            sender=None, actor=actor, mode=mode, models=selected, results=results,
        )
    except Exception:  # noqa: BLE001 — a project's repair must not fail the reset
        import logging
        logging.getLogger(__name__).exception("data_reset_finished receiver failed.")
    return results


def _resolve_model(key):
    try:
        return apps.get_model(str(key))
    except Exception:
        return None
