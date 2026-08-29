"""Notification records, per-user state, rules and watches."""

from django.db import models
from django.conf import settings

from .base import ScopedModel


class DluxNotification(ScopedModel):
    """Durable user-facing notification event."""

    LEVEL_INFO = 'info'
    LEVEL_SUCCESS = 'success'
    LEVEL_WARNING = 'warning'
    LEVEL_ERROR = 'error'
    LEVEL_CHOICES = (
        (LEVEL_INFO, 'Info'),
        (LEVEL_SUCCESS, 'Success'),
        (LEVEL_WARNING, 'Warning'),
        (LEVEL_ERROR, 'Error'),
    )

    AUDIENCE_ACTOR = 'actor'
    AUDIENCE_WATCHERS = 'watchers'
    AUDIENCE_USERS = 'users'
    AUDIENCE_BROADCAST = 'broadcast'
    AUDIENCE_CHOICES = (
        (AUDIENCE_ACTOR, 'Actor'),
        (AUDIENCE_WATCHERS, 'Watchers'),
        (AUDIENCE_USERS, 'Specific Users'),
        (AUDIENCE_BROADCAST, 'Broadcast'),
    )

    title = models.CharField(max_length=180, blank=True, verbose_name="Title")
    message = models.TextField(verbose_name="Message")
    level = models.CharField(max_length=16, choices=LEVEL_CHOICES, default=LEVEL_INFO, db_index=True, verbose_name="Level")
    category = models.CharField(max_length=64, default='general', db_index=True, verbose_name="Category")
    source = models.CharField(max_length=64, default='manual', db_index=True, verbose_name="Source")
    action = models.CharField(max_length=64, blank=True, db_index=True, verbose_name="Action")
    source_model = models.CharField(max_length=120, blank=True, verbose_name="Source Model")
    source_model_key = models.CharField(max_length=120, blank=True, db_index=True, verbose_name="Source Model Key")
    source_object_id = models.CharField(max_length=64, blank=True, db_index=True, verbose_name="Source Object ID")
    source_label = models.CharField(max_length=255, blank=True, verbose_name="Source Label")
    target_url = models.CharField(max_length=512, blank=True, verbose_name="Target URL")
    request_path = models.CharField(max_length=512, blank=True, verbose_name="Request Path")
    event_key = models.CharField(max_length=255, unique=True, null=True, blank=True, verbose_name="Event Key")
    audience_type = models.CharField(max_length=24, choices=AUDIENCE_CHOICES, default=AUDIENCE_ACTOR, verbose_name="Audience Type")
    badge_enabled = models.BooleanField(default=True, db_default=True, verbose_name="Badge Enabled")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="Metadata")
    expires_at = models.DateTimeField(blank=True, null=True, db_index=True, verbose_name="Expires At")

    class Meta:
        verbose_name = "Dlux Notification"
        verbose_name_plural = "Dlux Notifications"
        default_permissions = ()
        indexes = [
            models.Index(fields=['created_at'], name='dlux_notif_created_idx'),
            models.Index(fields=['scope', 'created_at'], name='dlux_notif_scope_created_idx'),
            models.Index(fields=['level', 'created_at'], name='dlux_notif_level_created_idx'),
            models.Index(fields=['source_model_key', 'created_at'], name='dlux_notif_model_created_idx'),
            models.Index(fields=['action', 'created_at'], name='dlux_notif_action_created_idx'),
        ]
        permissions = [
            ('view_notification', 'View notifications'),
            ('manage_notifications', 'Manage notification rules and watches'),
        ]

    def __str__(self):
        return self.title or self.message[:80]


class DluxNotificationState(models.Model):
    """Per-user state for a notification."""

    notification = models.ForeignKey(
        'dlux.DluxNotification',
        related_name='states',
        on_delete=models.CASCADE,
        verbose_name="Notification",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='dlux_notification_states',
        on_delete=models.CASCADE,
        verbose_name="User",
    )
    read_at = models.DateTimeField(blank=True, null=True, db_index=True, verbose_name="Read At")
    dismissed_at = models.DateTimeField(blank=True, null=True, db_index=True, verbose_name="Dismissed At")
    emailed_at = models.DateTimeField(blank=True, null=True, verbose_name="Emailed At")
    email_status = models.CharField(max_length=32, blank=True, verbose_name="Email Status")
    email_error = models.TextField(blank=True, verbose_name="Email Error")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        verbose_name = "Dlux Notification State"
        verbose_name_plural = "Dlux Notification States"
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=['notification', 'user'], name='dlux_notif_state_user_uniq'),
        ]
        indexes = [
            models.Index(fields=['user', 'read_at'], name='dlux_ns_read_idx'),
            models.Index(fields=['user', 'dismissed_at'], name='dlux_ns_dismiss_idx'),
            models.Index(fields=['user', 'created_at'], name='dlux_ns_created_idx'),
        ]

    def __str__(self):
        return f"{self.user} / {self.notification_id}"


class DluxNotificationRule(ScopedModel):
    """Admin-configured routing rule for notification events."""

    name = models.CharField(max_length=120, verbose_name="Name")
    enabled = models.BooleanField(default=True, db_index=True, verbose_name="Enabled")
    priority = models.IntegerField(default=100, db_index=True, verbose_name="Priority")
    match_config = models.JSONField(default=dict, blank=True, verbose_name="Match Configuration")
    delivery_config = models.JSONField(default=dict, blank=True, verbose_name="Delivery Configuration")
    stop_processing = models.BooleanField(default=False, verbose_name="Stop Processing")

    class Meta:
        verbose_name = "Dlux Notification Rule"
        verbose_name_plural = "Dlux Notification Rules"
        default_permissions = ()
        ordering = ['priority', 'name']
        indexes = [
            models.Index(fields=['enabled', 'priority'], name='dlux_notif_rule_enabled_idx'),
            models.Index(fields=['scope', 'priority'], name='dlux_notif_rule_scope_idx'),
        ]

    def __str__(self):
        return self.name


class DluxNotificationWatch(ScopedModel):
    """Model-level notification watch for a user and optional scope."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='dlux_notification_watches',
        on_delete=models.CASCADE,
        verbose_name="User",
    )
    model_key = models.CharField(max_length=120, db_index=True, verbose_name="Model Key")
    enabled = models.BooleanField(default=True, db_index=True, verbose_name="Enabled")
    email_enabled = models.BooleanField(default=False, verbose_name="Email Enabled")

    class Meta:
        verbose_name = "Dlux Notification Watch"
        verbose_name_plural = "Dlux Notification Watches"
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=['user', 'scope', 'model_key'], name='dlux_nw_user_scope_model'),
        ]
        indexes = [
            models.Index(fields=['model_key', 'enabled'], name='dlux_nw_model_idx'),
            models.Index(fields=['scope', 'model_key'], name='dlux_nw_scope_model_idx'),
        ]

    def __str__(self):
        return f"{self.user} watches {self.model_key}"
