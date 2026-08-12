"""Scopes and permission-preset groups."""

from django.db import models
from django.conf import settings


class Scope(models.Model):
    name = models.CharField(max_length=100, verbose_name="Scope")
    description = models.TextField(blank=True, null=True, verbose_name="Description")
    default_theme = models.CharField(
        max_length=50,
        blank=True,
        default='',
        db_default='',
        verbose_name="Default Theme",
    )
    is_public_registration_default = models.BooleanField(
        default=False,
        db_default=False,
        verbose_name="Default for Public Registration",
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Scope"
        verbose_name_plural = "Scopes"


class ScopeSettings(models.Model):
    is_enabled = models.BooleanField(default=False, verbose_name="Enable Scopes")
    auto_create_user_scope = models.BooleanField(default=False, verbose_name="Auto-create scope for each user")

    class Meta:
        verbose_name = "Scope Settings"
        verbose_name_plural = "Scope Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super(ScopeSettings, self).save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Scope Settings"


class GroupProfile(models.Model):
    """
    Metadata sidecar for a Django auth ``Group`` used as a reusable permission
    PRESET. The Group itself owns the name + permissions bundle (and therefore
    feeds ``user.has_perm`` via native group inheritance); this model only adds
    the description, optional scope binding, active flag, and audit trail that
    the native Group lacks. Purely additive — a Group without a profile still
    works as a plain preset.
    """
    group = models.OneToOneField(
        'auth.Group', on_delete=models.CASCADE, related_name='dlux_profile',
        verbose_name="Group",
    )
    description = models.CharField(max_length=255, blank=True, verbose_name="Description")
    # A preset may be global (scope NULL) or bound to a single Scope. Plain FK
    # (not ScopeForeignKey) so a preset's scope is chosen explicitly on the
    # preset form rather than auto-derived from the acting admin's own scope.
    scope = models.ForeignKey(
        'dlux.Scope', on_delete=models.PROTECT, null=True, blank=True,
        related_name='group_presets', verbose_name="Scope",
    )
    is_active = models.BooleanField(default=True, verbose_name="Active")
    is_public_registration_default = models.BooleanField(
        default=False,
        db_default=False,
        verbose_name="Default for Public Registration",
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, editable=False, verbose_name="Updated At")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name='+',
        on_delete=models.SET_NULL, editable=False, verbose_name="Created By",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name='+',
        on_delete=models.SET_NULL, editable=False, verbose_name="Updated By",
    )

    class Meta:
        verbose_name = "Group Preset"
        verbose_name_plural = "Group Presets"
        default_permissions = ()
        # Host the manage_groups permission on this NEW model (not the existing
        # Profile) so it ships inside CreateModel.options — keeping the release
        # migration inline-safe (no AlterModelOptions). Codename resolves as
        # `dlux.manage_groups` either way (both models are in the dlux app).
        permissions = [
            ("manage_groups", "Can manage permission groups"),
        ]

    def __str__(self):
        return self.group.name


class GroupMembership(models.Model):
    """
    Audit/history record of a user's membership in a permission-preset Group.
    Django's implicit ``user_groups`` M2M carries no timestamp or actor; this
    parallel row records WHO assigned the user to WHICH preset and WHEN, and
    backs the "users assigned to groups" view. The Group's ``user_set`` stays
    the source of truth for permission resolution — this table is kept in sync
    by ``dlux.utils.users.set_user_group_presets``.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='group_memberships', verbose_name="User",
    )
    group = models.ForeignKey(
        'auth.Group', on_delete=models.CASCADE,
        related_name='dlux_memberships', verbose_name="Group",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name='+',
        on_delete=models.SET_NULL, verbose_name="Assigned By",
    )
    assigned_at = models.DateTimeField(auto_now_add=True, verbose_name="Assigned At")

    class Meta:
        verbose_name = "Group Membership"
        verbose_name_plural = "Group Memberships"
        default_permissions = ()
        unique_together = ('user', 'group')
        ordering = ['-assigned_at']

    def __str__(self):
        return f"{self.user} → {self.group}"
