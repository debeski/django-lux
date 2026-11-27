"""Password-reset (forgot-password) support for the Dlux login flow.

Wraps Django's built-in password-reset machinery so it (a) is gated behind the
admin ``forgot_password_enabled`` toggle *and* verified email readiness, and
(b) delivers the reset email through Dlux's own transport, queued for the task
worker (``queue_dlux_mail``), instead of Django's default ``send_mail`` — the
same path used by the public registration verification email
(``registration.py``). Queueing keeps the response time the same whether or not
the address has an account.
"""

import hashlib
import logging

from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.cache import cache
from django.template import loader
from django.utils.http import base36_to_int

from ..utils import (
    build_config_groups,
    get_email_service_status,
    get_system_config,
    queue_dlux_mail,
)

logger = logging.getLogger('dlux')


def forgot_password_config():
    """Resolved forgot-password settings from the auth config."""
    config = get_system_config()
    return {
        'enabled': bool(config.get('forgot_password_enabled', False)),
    }


def forgot_password_available():
    """The reset flow is usable only when enabled AND email delivery is ready.

    Mirrors ``registration.public_registration_available`` — a self-gating link
    that never appears (and whose views 404) unless mail can actually be sent.
    """
    if not forgot_password_config()['enabled']:
        return False
    return bool(get_email_service_status().get('available'))


def reset_email_system_name():
    """Display name used in the reset email, falling back to 'DjangoLux'."""
    identity = build_config_groups(get_system_config()).get('identity', {})
    return identity.get('display_name') or 'DjangoLux'


# Clock tolerance for a token stamped slightly ahead of this server.
RESET_TOKEN_FUTURE_LEEWAY_SECONDS = 300
RESET_MAIL_ADDRESS_COOLDOWN_SECONDS = 60
RESET_REQUEST_IP_LIMIT = 10
RESET_REQUEST_IP_WINDOW_SECONDS = 3600


class DluxPasswordResetTokenGenerator(PasswordResetTokenGenerator):
    """Django's generator, also refusing tokens stamped in the future.

    Django rejects only tokens that are too old. A token minted while the clock
    ran ahead would otherwise stay valid for its timeout counted from that
    future time.
    """

    def check_token(self, user, token):
        if not super().check_token(user, token):
            return False
        try:
            ts = base36_to_int(str(token).split('-')[0])
        except (ValueError, IndexError):
            return False
        return ts <= self._num_seconds(self._now()) + RESET_TOKEN_FUTURE_LEEWAY_SECONDS


reset_token_generator = DluxPasswordResetTokenGenerator()


def _throttle_key(kind, value):
    digest = hashlib.sha256(str(value or '').strip().lower().encode('utf-8')).hexdigest()[:32]
    return f'dlux:pwreset:{kind}:{digest}'


def reset_request_ip_limited(ip_address):
    """Count a reset request from ``ip_address``; True once the hourly limit is passed."""
    if not ip_address:
        return False
    key = _throttle_key('ip', ip_address)
    cache.add(key, 0, timeout=RESET_REQUEST_IP_WINDOW_SECONDS)
    try:
        count = cache.incr(key)
    except ValueError:
        return False
    return count > RESET_REQUEST_IP_LIMIT


class DluxPasswordResetForm(PasswordResetForm):
    """Password-reset form that sends through Dlux's own mail transport.

    Django's ``PasswordResetForm.save`` renders the subject/body templates and
    then calls ``send_mail``; we override only ``send_mail`` so the message is
    queued through :func:`queue_dlux_mail` (direct/relay, encrypted secrets,
    failure alerts) rather than sent on Django's default connection.
    """

    def send_mail(self, subject_template_name, email_template_name, context,
                  from_email, to_email, html_email_template_name=None):
        subject = loader.render_to_string(subject_template_name, context)
        # Email subject *must not* contain newlines.
        subject = ''.join(subject.splitlines())
        body = loader.render_to_string(email_template_name, context)
        # One reset mail per address per cooldown; the page answers the same either way.
        if not cache.add(_throttle_key('mail', to_email), 1, timeout=RESET_MAIL_ADDRESS_COOLDOWN_SECONDS):
            logger.info("Password reset mail skipped: address cooldown active")
            return
        queue_dlux_mail(subject, body, [to_email], from_email=from_email)
