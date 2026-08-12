"""Force every non-superuser to change password at next login.

Irreversible, superuser-only and audit-logged — the same class of action as
:mod:`dlux.admin_actions.data_reset`, which is why they sit together. It lived
as a private helper inside `views/general.py` until 1.8.0, where the only way to
exercise it was an HTTP POST; here it can be tested directly.
"""
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction


def force_password_change_for_all_non_superusers():
    """Set the existing first-login password-change marker on every non-superuser."""
    User = get_user_model()
    Profile = apps.get_model('dlux', 'Profile')
    users = User.objects.filter(is_superuser=False).only('pk')
    updated_count = 0

    with transaction.atomic():
        for user in users.iterator():
            profile, _created = Profile.all_objects.get_or_create(user=user)
            preferences = dict(profile.preferences or {})
            if preferences.get('force_password_change') is True:
                continue
            preferences['force_password_change'] = True
            profile.preferences = preferences
            profile.save(update_fields=['preferences'])
            updated_count += 1

    return updated_count, users.count()
