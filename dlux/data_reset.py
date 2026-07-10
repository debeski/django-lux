"""Superuser "Reset data" admin command.

Clears row data from selected models. Respects Dlux semantics:

- ``ScopedModel`` subclasses are **soft-deleted** (the same recoverable
  ``deleted_at`` mechanism the app uses everywhere) via a bulk ``update()`` —
  ``QuerySet.delete()`` would bypass the model's soft-delete override. Their
  media files are always kept (the rows are recoverable).
- Non-scoped models are **hard-deleted** via ``QuerySet.delete()``, which honours
  each incoming relation's ``on_delete`` (CASCADE cascades, SET_NULL nulls,
  PROTECT blocks — that model is skipped and reported). Their FileField/ImageField
  blobs are removed only when the caller opts into deleting media.

Hard guards (never selectable, never touched): System Settings, the updater state
rows, permission groups/permissions, and Django internals. ``auth.User`` is
selectable but superusers and the acting user are always protected.
"""
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

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
    from .models import ScopedModel
    return ScopedModel


def is_scoped(model):
    try:
        return issubclass(model, _scoped_model_cls())
    except TypeError:
        return False


def is_reset_eligible(model):
    meta = model._meta
    if meta.abstract or not meta.managed or meta.auto_created or meta.proxy:
        return False
    if meta.app_label in HARD_EXCLUDED_APPS:
        return False
    if meta.label_lower in HARD_EXCLUDED_MODELS:
        return False
    return True


def _file_fields(model):
    fields = []
    for field in model._meta.get_fields():
        if not isinstance(field, (models.FileField, models.ImageField)):
            continue
        if any(hint in field.name.lower() for hint in _EXCLUDE_MEDIA_FIELD_HINTS):
            continue
        fields.append(field.name)
    return fields


def _deletion_queryset(model, actor):
    """Rows that a reset would remove — protected rows are excluded up front."""
    User = get_user_model()
    if model is User:
        # Never delete superusers or the operator running the command.
        qs = model._base_manager.filter(is_superuser=False)
        if actor is not None and getattr(actor, 'pk', None) is not None:
            qs = qs.exclude(pk=actor.pk)
        return qs
    if is_scoped(model):
        # All scopes' still-active rows (soft-deleted rows are already "gone").
        return model.all_objects.filter(deleted_at__isnull=True)
    return model._base_manager.all()


def _model_label(model, strings=None):
    from .utils.activity_log import translate_activity_log_model_name
    key = model._meta.label_lower
    if strings is not None:
        label = translate_activity_log_model_name(key, strings)
        # translate_* echoes the raw "app.model" key when there is no translation;
        # never show that — fall back to the model's readable verbose name.
        if label and label != key:
            return str(label)
    return str(model._meta.verbose_name_plural).strip().title()


def build_reset_catalog(actor, strings=None):
    """[{key, label, app, count, scoped, has_media}] for eligible models, sorted."""
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


def execute_reset(actor, selected_keys, *, delete_media=False):
    """Clear the selected models. Each model runs in its own savepoint so a
    PROTECT block (or any error) on one does not roll back the others. Returns a
    list of per-model result dicts."""
    results = []
    selected = [str(k).strip().lower() for k in (selected_keys or []) if str(k).strip()]
    for key in selected:
        model = _resolve_model(key)
        if model is None or not is_reset_eligible(model):
            results.append({'key': key, 'label': key, 'status': 'skipped', 'reason': 'not_eligible', 'deleted': 0})
            continue
        label = _model_label(model)
        qs = _deletion_queryset(model, actor)
        try:
            with transaction.atomic():
                count = qs.count()
                if count == 0:
                    results.append({'key': key, 'label': label, 'status': 'empty', 'deleted': 0,
                                    'scoped': is_scoped(model), 'media_deleted': 0})
                    continue
                if is_scoped(model):
                    # Bulk soft-delete — QuerySet.delete() bypasses the soft-delete
                    # override, so update() the recoverable markers directly.
                    qs.update(deleted_at=timezone.now(), deleted_by=actor)
                    results.append({'key': key, 'label': label, 'status': 'soft_deleted',
                                    'deleted': count, 'scoped': True, 'media_deleted': 0})
                else:
                    media_deleted = _delete_media_files(model, qs) if delete_media else 0
                    qs.delete()
                    results.append({'key': key, 'label': label, 'status': 'deleted',
                                    'deleted': count, 'scoped': False, 'media_deleted': media_deleted})
        except ProtectedError:
            results.append({'key': key, 'label': label, 'status': 'protected', 'deleted': 0,
                            'scoped': is_scoped(model)})
        except Exception as exc:  # noqa: BLE001 — surface the failure per model
            results.append({'key': key, 'label': label, 'status': 'error', 'deleted': 0,
                            'reason': str(exc)[:200]})
    return results


def _resolve_model(key):
    try:
        return apps.get_model(str(key))
    except Exception:
        return None
