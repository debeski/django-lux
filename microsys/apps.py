# Imports of the required python modules and libraries
######################################################
from django.apps import AppConfig
from django.apps import apps
from .constants import DEFAULT_HOME_URL


def custom_permission_str(self):
    """Custom translations for Django permissions based on active language"""
    from microsys.translations import get_strings
    
    permission_name = str(self.name)
    strings = get_strings()

    # Translation map for keywords
    replacements = {
        "Can add": strings.get("can_add", "إضافة"),
        "Can change": strings.get("can_change", "تعديل"),
        "Can delete": strings.get("can_delete", "حذف"),
        "Can view": strings.get("can_view", "عرض"),
        "permission": strings.get("permission_word", "الصلاحيات"),
    }

    for en, target in replacements.items():
        permission_name = permission_name.replace(en, target)

    return permission_name.strip()

class MicrosysConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'microsys'
    verbose_name = "System Management"

    def ready(self):
        # Runtime configuration validation
        self._validate_configuration()

        # Provide sane default auth redirects if user didn't set them
        try:
            from django.conf import settings
            if not getattr(settings, 'LOGIN_REDIRECT_URL', None):
                settings.LOGIN_REDIRECT_URL = DEFAULT_HOME_URL
            if not getattr(settings, 'LOGOUT_REDIRECT_URL', None):
                settings.LOGOUT_REDIRECT_URL = '/accounts/login/'
        except Exception:
            pass
        
        # Patch models and signals
        import microsys.signals
        import microsys.discovery

        # Auto-inject scope handling into ModelForm / FilterSet / Table
        from microsys.patches import apply_scoped_patches, apply_global_translation_patches
        apply_scoped_patches()
        apply_global_translation_patches()
        
        # Lazy str patch for Permission
        try:
            from django.contrib.auth.models import Permission
            Permission.add_to_class("__str__", custom_permission_str)
        except (LookupError, ImportError):
            pass

    def _validate_configuration(self):
        """Validate microsys configuration at startup and emit warnings."""
        import warnings
        from django.conf import settings

        # Check Middleware
        new_path = 'microsys.middleware.MicrosysMiddleware'
        old_path = 'microsys.middleware.ActivityLogMiddleware'
        configured_middleware = getattr(settings, 'MIDDLEWARE', [])
        
        if new_path not in configured_middleware and old_path not in configured_middleware:
            warnings.warn(
                f"\n⚠️  microsys: '{new_path}' not found in MIDDLEWARE.\n"
                "   Activity logging will not work. Run 'python manage.py microsys_check' for details.",
                UserWarning
            )

        # Check Context Processors
        context_proc = 'microsys.context_processors.microsys_context'
        context_ok = False
        try:
            for template in getattr(settings, 'TEMPLATES', []):
                processors = template.get('OPTIONS', {}).get('context_processors', [])
                if context_proc in processors:
                    context_ok = True
                    break
        except (AttributeError, TypeError):
            pass

        if not context_ok:
            warnings.warn(
                f"\n⚠️  microsys: '{context_proc}' not found in TEMPLATES context_processors.\n"
                "   Sidebar and branding will not work. Run 'python manage.py microsys_check' for details.",
                UserWarning
            )
