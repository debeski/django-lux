import logging

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)
User = get_user_model()


def _revoke_provider_tokens(user):
    try:
        from oauth2_provider.models import AccessToken, RefreshToken
    except ImportError:
        return

    AccessToken.objects.filter(user=user).delete()
    RefreshToken.objects.filter(user=user).delete()

    try:
        from .models import SSOSessionState

        for session in SSOSessionState.objects.filter(user=user, revoked_at__isnull=True):
            session.revoke()
    except Exception:
        logger.exception("Failed to update Microsys SSO session state for user %s", user.pk)


@receiver(pre_delete, sender=User)
def revoke_tokens_on_user_delete(sender, instance, **kwargs):
    _revoke_provider_tokens(instance)


@receiver(post_save, sender=User)
def revoke_tokens_on_user_deactivate(sender, instance, **kwargs):
    if not getattr(instance, "is_active", True):
        _revoke_provider_tokens(instance)

