import contextlib
import threading

from django.db import models
from django.apps import apps
from .middleware import get_current_user

# When set, ScopedManager hides soft-deleted rows even in the superadmin
# "show soft-deleted" review mode. Used to keep the paths that must never see
# deleted rows safe — uniqueness validation and (via the form patch) related
# pickers — while list/detail reads stay transparent.
_hide_deleted_local = threading.local()


def _force_hide_deleted():
    return getattr(_hide_deleted_local, 'on', False)


@contextlib.contextmanager
def force_hide_deleted():
    prev = getattr(_hide_deleted_local, 'on', False)
    _hide_deleted_local.on = True
    try:
        yield
    finally:
        _hide_deleted_local.on = prev


def _is_scope_enabled():
    """
    Helper to check if scopes are globally enabled.
    """
    try:
        ScopeSettings = apps.get_model('dlux', 'ScopeSettings')
        if not ScopeSettings.load().is_enabled:
            return False
        return True
    except (LookupError, Exception):
        return False

class ScopedQuerySet(models.QuerySet):
    """Bulk operations for ``ScopedModel`` rows.

    ``delete()`` soft-deletes, like ``ScopedModel.delete()`` does for one row, so
    the Django admin's "delete selected" and any ``filter(...).delete()`` keep
    the rows (and the history pointing at them) recoverable. Rows already in the
    recycle bin keep their original ``deleted_at``/``deleted_by``.
    ``hard_delete()`` is the explicit escape hatch for maintenance paths that
    must really remove rows (log pruning, Reset data's permanent mode).
    """

    def delete(self):
        from django.utils import timezone

        from .files.registry import document_file_fields

        user = get_current_user()
        actor = user if user is not None and getattr(user, 'is_authenticated', False) else None
        live = self.filter(deleted_at__isnull=True)
        cascade = bool(document_file_fields(self.model))
        pks = list(live.values_list('pk', flat=True)) if cascade else ()
        deleted_at = timezone.now()
        count = live.update(deleted_at=deleted_at, deleted_by=actor)
        if cascade:
            from .files.history import cascade_soft_delete

            cascade_soft_delete(self.model, pks, deleted_at, getattr(actor, 'pk', None))
        return count, {self.model._meta.label: count}

    delete.alters_data = True
    delete.queryset_only = True

    def hard_delete(self):
        return super().delete()

    hard_delete.alters_data = True
    hard_delete.queryset_only = True

    def restore(self):
        from .files.registry import document_file_fields

        cascade = bool(document_file_fields(self.model))
        deleted = dict(self.filter(deleted_at__isnull=False).values_list('pk', 'deleted_at')) if cascade else {}
        count = self.update(deleted_at=None, deleted_by=None)
        if cascade:
            from .files.history import cascade_restore

            cascade_restore(self.model, deleted)
        return count

    restore.alters_data = True
    restore.queryset_only = True


class ScopedManager(models.Manager.from_queryset(ScopedQuerySet)):
    """
    A manager that automatically filters queries by the current user's scope.
    Automatically excludes soft-deleted records (deleted_at is built into ScopedModel).
    """
    
    def apply_scoping(self, queryset):
        """
        Apply scoping logic to an existing queryset.
        Can be used to "refresh" querysets that were created before the user was known.
        """
        # 1. Skip if scopes are disabled
        if not _is_scope_enabled():
            return queryset

        from .middleware import get_current_user
        user = get_current_user()
        
        # 2. If no user or user is superuser, return all
        if not user or not user.is_authenticated or user.is_superuser:
            return queryset

        # 3. Filter by scope
        try:
            self.model._meta.get_field('scope')
            user_scope = getattr(getattr(user, 'profile', None), 'scope', None) or getattr(user, 'scope', None)
            
            if user_scope:
                # Scoped users see only their own scoped data
                return queryset.filter(scope=user_scope)
            else:
                # Non-scoped users see only the Centralized (un-scoped) archive
                return queryset.filter(scope__isnull=True)
        except Exception:
            return queryset

    def get_queryset(self):
        qs = super().get_queryset()

        # Hide soft-deleted rows, EXCEPT when a superadmin has enabled the
        # "show soft-deleted" review mode — then reads/lists include them
        # transparently (custom views' `objects.all()` show them too, no view
        # change). `force_hide_deleted()` overrides that for the paths that must
        # never surface deleted rows (uniqueness validation, related pickers).
        if hasattr(self.model, 'deleted_at'):
            hide = _force_hide_deleted()
            if not hide:
                from .utils.authorization import soft_deleted_visible
                hide = not soft_deleted_visible()
            if hide:
                qs = qs.filter(deleted_at__isnull=True)

        return self.apply_scoping(qs)
