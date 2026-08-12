"""Activity log and section registry."""

from django.db import models
from datetime import timedelta

from .base import ScopedModel


class ActivityLog(ScopedModel):
    """
    Activity log model — the single source of truth for all logs (user/system/audit).
    Uses inherited ScopedModel fields:
    - created_by → the user who performed the action (was 'user')
    - created_at → when the action occurred (was 'timestamp')

    Renamed from ``UserActivityLog`` (the "User" prefix is obsolete now that this stores
    system and audit entries too). ``UserActivityLog`` remains a module alias for
    backward-compatible imports.
    """
    CATEGORY_USER = 'user'
    CATEGORY_SYSTEM = 'system'
    CATEGORY_AUDIT = 'audit'
    CATEGORY_CHOICES = (
        (CATEGORY_USER, "User"),
        (CATEGORY_SYSTEM, "System"),
        (CATEGORY_AUDIT, "Audit"),
    )

    # created_by (inherited) → replaces old 'user' field
    # created_at (inherited) → replaces old 'timestamp' field
    action = models.CharField(max_length=50, verbose_name="Action")
    # Log category: 'user' (project work / dev-invoked), 'system' (dlux-internal), or
    # 'audit' (security events). Derived at log time by resolve_log_category(); audit rows
    # are privileged (append-only, never auto-pruned by default).
    category = models.CharField(
        max_length=10, choices=CATEGORY_CHOICES, default=CATEGORY_USER,
        verbose_name="Category",
    )
    # Human-readable label (the model's translated verbose name at log time). Used for
    # display. NOTE: this is locale-dependent, so never key reports/grouping off it.
    model_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Model Name")
    # Stable, locale-independent identity ("app_label.model_name", e.g. "documents.decree").
    # This is what reports/eligibility should group and resolve on. Null for legacy rows
    # and for non-model events (login, password, session, ...).
    model_key = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="Model Key")
    object_id = models.IntegerField(blank=True, null=True, verbose_name="Object ID")
    number = models.CharField(max_length=50, null=True, blank=True, verbose_name="Document Number")
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="IP Address")
    user_agent = models.TextField(blank=True, null=True, verbose_name="User Agent")
    details = models.JSONField(default=dict, blank=True, null=True, verbose_name="Details")

    # Backward-compat properties for templates and tables
    @property
    def user(self):
        """Alias for created_by (backward compat)."""
        return self.created_by

    @property
    def timestamp(self):
        """Alias for created_at (backward compat)."""
        return self.created_at

    def __str__(self):
        return f"{self.created_by} {self.action} {self.model_name or 'General'} at {self.created_at}"

    def save(self, *args, **kwargs):
        # Audit entries are append-only: block in-app mutation of an existing audit row.
        # (Inserts have no pk yet and are allowed.) Bulk QuerySet.update() bypasses this by
        # design; app code must not target audit rows for updates.
        if self.pk and self.category == self.CATEGORY_AUDIT:
            raise ValueError("Audit activity-log entries are immutable and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Audit entries cannot be deleted through the app (never auto-pruned by default).
        # Bulk QuerySet.delete() bypasses this; the prune command excludes audit explicitly.
        if self.category == self.CATEGORY_AUDIT:
            return None
        return super().delete(*args, **kwargs)

    class Meta:
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"
        default_permissions = ()
        indexes = [
            models.Index(fields=['created_at'], name='dlux_ual_created_idx'),
            models.Index(fields=['scope', 'created_at'], name='dlux_ual_scope_created_idx'),
            models.Index(fields=['created_by', 'created_at'], name='dlux_ual_actor_created_idx'),
            models.Index(fields=['model_key', 'created_at'], name='dlux_ual_model_created_idx'),
            models.Index(fields=['action', 'created_at'], name='dlux_ual_action_created_idx'),
            models.Index(fields=['category', 'created_at'], name='dlux_ual_cat_created_idx'),
        ]
        permissions = [
            ("view_activitylog", "View activity log"),
        ]

    @classmethod
    def safe_log(cls, user, action, model_name=None, object_id=None, number=None, details=None, ip_address=None, user_agent=None, scope=None, model_key=None, category=None):
        """
        Log an action only if a duplicate entry hasn't been created in the last 2 seconds.

        ``category`` is the log type ('user'/'system'/'audit'); when omitted it is derived
        from (action, model_key, model_name) via resolve_log_category. It is NOT part of the
        dedupe key — it is a pure function of fields already in the key.
        """
        from django.utils.timezone import now
        from datetime import timedelta

        # Debounce window
        time_threshold = now() - timedelta(seconds=2)

        # Check for duplicates
        duplicate = cls.objects.filter(
            created_by=user,
            action=action,
            model_name=model_name,
            object_id=object_id,
            created_at__gte=time_threshold
        )

        if details:
             duplicate = duplicate.filter(details=details)

        if duplicate.exists():
            return None

        # Automatically use actor's scope if not provided
        if not scope and user:
            from ..utils import get_user_scope
            scope = get_user_scope(user)

        if category is None:
            from ..utils.activity_log import resolve_log_category
            category = resolve_log_category(action, model_key=model_key, model_name=model_name)

        return cls.objects.create(
            created_by=user,
            action=action,
            category=category,
            model_name=model_name,
            model_key=(str(model_key).strip().lower() or None) if model_key else None,
            object_id=object_id,
            number=number,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            scope=scope,
        )

    def get_modal_context(self):
        """Auto-resolve related object for dynamic modal detail view."""
        related_object = None
        if (self.model_key or self.model_name) and self.object_id:
            from ..utils import resolve_model_by_name
            try:
                target_model = resolve_model_by_name(self.model_key or self.model_name)
                if target_model:
                    try:
                        related_object = target_model._default_manager.get(pk=self.object_id)
                    except (target_model.DoesNotExist, ValueError, TypeError):
                        pass
            except Exception:
                pass
        return {
            'related_object': related_object,
            'related_object_model': related_object._meta.verbose_name if related_object else (self.model_name or "-"),
        }


UserActivityLog = ActivityLog


class Section(models.Model):
    """Dummy Model for section permissions."""
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("view_sections", "View sections"),
            ("manage_sections", "Manage sections"),
        ]
