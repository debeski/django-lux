"""Dlux strong-password validator.

Enforces strict password rules — minimum length, upper- and lower-case letters,
a digit, and a symbol — but ONLY when the ``SystemSettings.auth_config``
``enforce_strong_passwords`` toggle is on. It is a no-op otherwise, so it is safe
to register globally in ``AUTH_PASSWORD_VALIDATORS`` (dlux_settings() does this);
every set-password path that runs Django's ``validate_password()`` (registration,
user creation, password change/reset, admin) is covered.

The rule set is mirrored client-side by the live password-rules UI
(``dlux/static/dlux/helpers/password_rules/js/main.js``); keep them in sync.
"""

import re

from django.core.exceptions import ValidationError

STRONG_PASSWORD_MIN_LENGTH = 12


def strong_password_min_length():
    """Resolve the admin-configured minimum length (auth_config, clamped 8–64)."""
    try:
        from dlux.utils import get_system_config
        value = int(get_system_config().get('strong_password_min_length', STRONG_PASSWORD_MIN_LENGTH))
        if 8 <= value <= 64:
            return value
    except Exception:
        pass
    return STRONG_PASSWORD_MIN_LENGTH


def _min_length_label(strings, min_length):
    template = strings.get('password_rule_min_length', 'At least {count} characters')
    return template.replace('{count}', str(min_length))


def strong_password_failures(password):
    """Return a list of translated requirement labels the password fails.

    Empty list means the password satisfies every rule.
    """
    from dlux.translations import get_strings
    s = get_strings()
    password = password or ''
    min_length = strong_password_min_length()
    failures = []
    if len(password) < min_length:
        failures.append(_min_length_label(s, min_length))
    if not re.search(r'[A-Z]', password):
        failures.append(s.get('password_rule_upper', 'An uppercase letter'))
    if not re.search(r'[a-z]', password):
        failures.append(s.get('password_rule_lower', 'A lowercase letter'))
    if not re.search(r'\d', password):
        failures.append(s.get('password_rule_digit', 'A digit'))
    if not re.search(r'[^A-Za-z0-9]', password):
        failures.append(s.get('password_rule_symbol', 'A symbol'))
    return failures


class DluxStrongPasswordValidator:
    """AUTH_PASSWORD_VALIDATORS entry; active only when the toggle is enabled."""

    @staticmethod
    def _enabled():
        try:
            from dlux.utils import get_system_config
            return bool(get_system_config().get('enforce_strong_passwords', False))
        except Exception:
            return False

    def validate(self, password, user=None):
        if not self._enabled():
            return
        failures = strong_password_failures(password)
        if failures:
            from dlux.translations import get_strings
            s = get_strings()
            raise ValidationError(
                '%(intro)s %(rules)s' % {
                    'intro': s.get('password_rules_error', 'Password does not meet the requirements:'),
                    'rules': ', '.join(failures),
                },
                code='dlux_weak_password',
            )

    def get_help_text(self):
        if not self._enabled():
            return ''
        from dlux.translations import get_strings
        s = get_strings()
        template = s.get(
            'password_rules_help',
            'At least {count} characters with upper and lower case letters, a digit, and a symbol.',
        )
        return template.replace('{count}', str(strong_password_min_length()))
