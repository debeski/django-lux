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


def strong_password_failures(password):
    """Return a list of translated requirement labels the password fails.

    Empty list means the password satisfies every rule.
    """
    from dlux.translations import get_strings
    s = get_strings()
    password = password or ''
    failures = []
    if len(password) < STRONG_PASSWORD_MIN_LENGTH:
        failures.append(s.get('password_rule_length', 'At least 12 characters'))
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
        return s.get(
            'password_rules_help',
            'At least 12 characters with upper and lower case letters, a digit, and a symbol.',
        )
