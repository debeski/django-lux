from django.contrib import admin

from .models import SSOIdentity


@admin.register(SSOIdentity)
class SSOIdentityAdmin(admin.ModelAdmin):
    list_display = ("user", "issuer", "subject", "role", "last_login_at")
    search_fields = ("user__username", "user__email", "issuer", "subject", "role")
    readonly_fields = ("claims", "created_at", "updated_at", "last_login_at")

