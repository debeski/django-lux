from django.apps import AppConfig


class DluxSSOConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dlux_sso"
    verbose_name = "Dlux SSO"

    def ready(self):
        from . import signals  # noqa: F401

