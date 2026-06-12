from django.db import models
from django.apps import apps
from .middleware import get_current_user

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

class ScopedManager(models.Manager):
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
        
        # Skip if soft-deleted (standard behavior)
        if hasattr(self.model, 'deleted_at'):
            qs = qs.filter(deleted_at__isnull=True)

        return self.apply_scoping(qs)
