from django.contrib import admin

from .models import (
    SSOAdminInvitation,
    SSOAuditEvent,
    SSOClientMembership,
    SSOClientPolicy,
    SSOSessionState,
)


class SSOClientMembershipInline(admin.TabularInline):
    model = SSOClientMembership
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(SSOClientPolicy)
class SSOClientPolicyAdmin(admin.ModelAdmin):
    list_display = ("display_name", "slug", "is_active", "allow_all_authenticated", "require_pkce")
    search_fields = ("display_name", "slug", "application__name", "application__client_id")
    inlines = (SSOClientMembershipInline,)


@admin.register(SSOAdminInvitation)
class SSOAdminInvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "policy", "role", "expires_at", "accepted_at")
    search_fields = ("email", "policy__display_name", "policy__slug")
    readonly_fields = ("token_hash", "created_at", "accepted_at")


@admin.register(SSOAuditEvent)
class SSOAuditEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "client_id", "user", "actor", "role", "created_at")
    search_fields = ("event_type", "client_id", "user__username", "actor__username")
    readonly_fields = ("created_at",)


@admin.register(SSOSessionState)
class SSOSessionStateAdmin(admin.ModelAdmin):
    list_display = ("user", "policy", "role", "created_at", "expires_at", "revoked_at")
    search_fields = ("user__username", "policy__display_name", "token_identifier")
    readonly_fields = ("created_at",)

