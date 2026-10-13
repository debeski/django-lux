# Imports of the required python modules and libraries
######################################################
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.apps import apps

User = get_user_model()

UserActivityLog = apps.get_model('dlux', 'ActivityLog')
Scope = apps.get_model('dlux', 'Scope')

class CustomUserAdmin(UserAdmin):
    model = User
    # Access related profile fields via methods if needed, or stick to User fields for now.
    # To properly show profile fields, we should probably use an Inline.
    list_display = ['username', 'email', 'is_staff', 'is_active'] 
    list_filter = ['is_staff', 'is_active']
    search_fields = ['username', 'email']
    ordering = ['username']

    # A user that history points at (created_by, logs, reviews…) is only ever
    # soft-deleted, the same way User Management deletes; a hard delete would
    # blank or orphan that history. Users with no history delete normally.
    def delete_model(self, request, obj):
        from .utils import delete_user_preserving_history

        delete_user_preserving_history(obj)

    def delete_queryset(self, request, queryset):
        for user in queryset:
            self.delete_model(request, user)

@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ('created_by', 'category', 'action', 'model_name', 'object_id', 'created_at', 'ip_address')
    list_filter = ('category', 'action', 'model_name', 'created_at')
    search_fields = ('created_by__username', 'model_name', 'object_id', 'ip_address')
    readonly_fields = ('created_by', 'category', 'action', 'model_name', 'object_id', 'number', 'ip_address', 'user_agent', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

admin.site.register(User, CustomUserAdmin)
admin.site.register(Scope)
admin.site.unregister(Group)
