# Imports of the required python modules and libraries
######################################################
from django.apps import AppConfig
from django.apps import apps
from .system.constants import DEFAULT_HOME_URL


def custom_permission_str(self):
    """Custom translations for Django permissions based on active language"""
    from dlux.translations import get_strings
    
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

class DluxConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dlux'
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
        import dlux.signals
        import dlux.discovery
        try:
            import dlux.updater.celery_control
        except ImportError:
            pass

        # Auto-inject scope handling into ModelForm / FilterSet / Table
        from dlux.patches import apply_scoped_patches, apply_global_translation_patches
        apply_scoped_patches()
        apply_global_translation_patches()
        
        # Lazy str patch for Permission
        try:
            from django.contrib.auth.models import Permission
            Permission.add_to_class("__str__", custom_permission_str)
        except (LookupError, ImportError):
            pass

        # Autodiscover Options cards: import each installed app's optional
        # `dlux_options` module so it can call dlux.options.register_card(...).
        self._autodiscover_option_cards()

    def _autodiscover_option_cards(self):
        """Import ``<app>.dlux_options`` for every installed app, if present.

        Registration is trusted code run once at startup — this is the only path
        by which an Options card can enter the registry. A broken options module
        in one app is logged and skipped so it can't take down site startup.
        """
        import logging
        from importlib import import_module
        from importlib.util import find_spec
        from django.apps import apps as django_apps

        logger = logging.getLogger('dlux')
        for app_config in django_apps.get_app_configs():
            module_name = f"{app_config.name}.dlux_options"
            try:
                if find_spec(module_name) is None:
                    continue
            except (ImportError, AttributeError, ValueError):
                continue
            try:
                import_module(module_name)
            except Exception:
                logger.exception("Failed to import Options cards from '%s'; skipping.", module_name)

    def _validate_configuration(self):
        """Validate dlux configuration at startup and emit warnings."""
        import warnings
        from django.conf import settings

        # Check Middleware
        new_path = 'dlux.middleware.DluxMiddleware'
        old_path = 'dlux.middleware.ActivityLogMiddleware'
        configured_path = getattr(settings, 'DLUX_MIDDLEWARE', new_path)
        configured_middleware = getattr(settings, 'MIDDLEWARE', [])
        
        if configured_path not in configured_middleware and old_path not in configured_middleware:
            warnings.warn(
                f"\n⚠️  dlux: '{configured_path}' not found in MIDDLEWARE.\n"
                "   Activity logging will not work. Run 'python manage.py dlux_check' for details.",
                UserWarning
            )

        # Check Context Processors
        context_proc = 'dlux.context_processors.dlux_context'
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
                f"\n⚠️  dlux: '{context_proc}' not found in TEMPLATES context_processors.\n"
                "   Sidebar and branding will not work. Run 'python manage.py dlux_check' for details.",
                UserWarning
            )
