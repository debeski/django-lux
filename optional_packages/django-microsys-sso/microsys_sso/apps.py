from django.apps import AppConfig


class MicrosysSSOConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "microsys_sso"
    verbose_name = "Microsys SSO"

    def ready(self):
        from . import signals  # noqa: F401

