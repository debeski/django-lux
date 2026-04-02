from django.db import models
from django.apps import apps
from .middleware import get_current_user

class ScopedManager(models.Manager):
    """
    A manager that automatically filters queries by the current user's scope.
    Automatically excludes soft-deleted records (deleted_at is built into ScopedModel).
    """
    
    def get_queryset(self):
        qs = super().get_queryset()
        
        # 1. Soft Delete Check — deleted_at is built into every ScopedModel
        qs = qs.filter(deleted_at__isnull=True)

        # 2. Scope Filtering
        # Check if Scope system is globally enabled
        try:
            ScopeSettings = apps.get_model('microsys', 'ScopeSettings')
            if not ScopeSettings.load().is_enabled:
                return qs
        except (LookupError, Exception):
            # If ScopeSettings table doesn't exist yet (e.g. migration), skip
            return qs

        user = get_current_user()
        
        # If no user or user is superuser, return all
        if not user or not user.is_authenticated or user.is_superuser:
            return qs

        # If user has a scope, filter by it
        # Note: We use 'scope' string, assuming the field name on the model is 'scope'
        if hasattr(user, 'profile') and user.profile.scope:
             # Check if the model actually has a 'scope' field
             try:
                 self.model._meta.get_field('scope')
                 qs = qs.filter(scope=user.profile.scope)
             except Exception:
                 pass
        elif hasattr(user, 'scope') and user.scope: # Layout for old CustomUser (will be removed later)
             try:
                 self.model._meta.get_field('scope')
                 qs = qs.filter(scope=user.scope)
             except Exception:
                 pass
                 
        return qs
