"""Password-reset (forgot-password) support for the Dlux login flow.

Wraps Django's built-in password-reset machinery so it (a) is gated behind the
admin ``forgot_password_enabled`` toggle *and* verified email readiness, and
(b) delivers the reset email through Dlux's own transport (``send_dlux_mail``)
instead of Django's default ``send_mail`` — the same path used by the public
registration verification email (``registration.py``).
"""

import logging

from django.contrib.auth.forms import PasswordResetForm
from django.template import loader

from .utils import (
    build_config_groups,
    get_email_service_status,
    get_system_config,
    send_dlux_mail,
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


class DluxPasswordResetForm(PasswordResetForm):
    """Password-reset form that sends through Dlux's own mail transport.

    Django's ``PasswordResetForm.save`` renders the subject/body templates and
    then calls ``send_mail``; we override only ``send_mail`` so the message is
    handed to :func:`send_dlux_mail` (direct/relay, encrypted secrets, failure
    alerts) rather than Django's default connection.
    """

    def send_mail(self, subject_template_name, email_template_name, context,
                  from_email, to_email, html_email_template_name=None):
        subject = loader.render_to_string(subject_template_name, context)
        # Email subject *must not* contain newlines.
        subject = ''.join(subject.splitlines())
        body = loader.render_to_string(email_template_name, context)
        send_dlux_mail(
            subject,
            body,
            [to_email],
            from_email=from_email,
            fail_silently=False,
        )
