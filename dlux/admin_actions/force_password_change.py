"""Force every non-superuser to change password at next login.

Irreversible, superuser-only and audit-logged — the same class of action as
:mod:`dlux.admin_actions.data_reset`, which is why they sit together. It lived
as a private helper inside the system-options views until 1.8.0, where the only
way to exercise it was an HTTP POST; here it can be tested directly.
"""
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction


BATCH_SIZE = 500


def force_password_change_for_all_non_superusers():
    """Set the existing first-login password-change marker on every non-superuser.

    Works in batches of ``BATCH_SIZE`` profiles (two queries each), so the
    request stays short however many accounts exist. Returns
    ``(newly_marked, non_superusers)``.
    """
    User = get_user_model()
    Profile = apps.get_model('dlux', 'Profile')
    users = User.objects.filter(is_superuser=False)
    updated_count = 0

    with transaction.atomic():
        profiles = Profile.all_objects.filter(user__in=users.values('pk'))
        for user in users.exclude(pk__in=profiles.values('user_id')).only('pk'):
            Profile.all_objects.get_or_create(user=user)
        profile_ids = list(profiles.order_by('pk').values_list('pk', flat=True))
        for start in range(0, len(profile_ids), BATCH_SIZE):
            batch = []
            for profile in Profile.all_objects.filter(pk__in=profile_ids[start:start + BATCH_SIZE]).only('pk', 'preferences'):
                preferences = dict(profile.preferences or {})
                if preferences.get('force_password_change') is True:
                    continue
                preferences['force_password_change'] = True
                profile.preferences = preferences
                batch.append(profile)
            if batch:
                Profile.all_objects.bulk_update(batch, ['preferences'])
                updated_count += len(batch)

    return updated_count, users.count()
