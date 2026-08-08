"""Registry of dismissible dialogs and their per-user "don't show again" state.

A dialog that can be permanently dismissed needs a way back, or the opt-out is a
one-way door. Registering it here puts it behind the Options page's *Reset dialog
prompts* action, which clears every registered dismissal in one go.

Downstream projects register their own prompts the same way Dlux registers its
built-ins::

    from dlux.dialogs import register_dismissible_dialog

    register_dismissible_dialog(
        id='archive.install_app',
        label='Install as app prompt',
        app_namespace='archive.pwa',
        app_preference_key='dismissed',
    )

Dismissal state lives in one of three places:

``preference_key``
    A top-level key in ``Profile.preferences`` (Dlux-owned keys).
``app_namespace`` + ``app_preference_key``
    A key inside ``Profile.preferences['app'][<namespace>]`` — the reserved,
    project-owned namespace, and the right home for downstream prompts.
``profile_field``
    A boolean field on ``Profile``. Dlux-internal: projects cannot add fields to
    Dlux's ``Profile``, so this exists for built-ins such as the Initial User
    Setup completion flag.
"""
import re

from .system.constants import PREFERENCES_APP_NAMESPACE

_ID_RE = re.compile(r'^[A-Za-z0-9._-]{1,128}$')

_REGISTRY = {}


def register_dismissible_dialog(*, id, label, preference_key=None,
                                app_namespace=None, app_preference_key=None,
                                profile_field=None, description=''):
    """Register one dismissible dialog. Raises ``ValueError`` on invalid input.

    Registering the same ``id`` twice replaces the earlier entry, so a module
    imported more than once does not accumulate duplicates.
    """
    dialog_id = str(id or '').strip()
    if not _ID_RE.match(dialog_id):
        raise ValueError(
            'register_dismissible_dialog: id must be 1-128 chars of [A-Za-z0-9._-]'
        )

    label = str(label or '').strip()
    if not label:
        raise ValueError('register_dismissible_dialog: label is required')

    if app_namespace and not app_preference_key:
        raise ValueError(
            'register_dismissible_dialog: app_namespace requires app_preference_key'
        )
    if app_preference_key and not app_namespace:
        raise ValueError(
            'register_dismissible_dialog: app_preference_key requires app_namespace'
        )
    if not any([preference_key, app_namespace, profile_field]):
        raise ValueError(
            'register_dismissible_dialog: one of preference_key, '
            'app_namespace/app_preference_key, or profile_field is required'
        )

    _REGISTRY[dialog_id] = {
        'id': dialog_id,
        'label': label,
        'description': str(description or '').strip(),
        'preference_key': str(preference_key).strip() if preference_key else None,
        'app_namespace': str(app_namespace).strip() if app_namespace else None,
        'app_preference_key': str(app_preference_key).strip() if app_preference_key else None,
        'profile_field': str(profile_field).strip() if profile_field else None,
    }
    return _REGISTRY[dialog_id]


def get_dismissible_dialogs():
    """Every registered dialog, sorted by id."""
    return [dict(spec) for _, spec in sorted(_REGISTRY.items())]


def _clear_preference(preferences, key):
    if key in preferences:
        preferences.pop(key, None)
        return True
    return False


def _clear_app_preference(preferences, namespace, key):
    bag = preferences.get(PREFERENCES_APP_NAMESPACE)
    if not isinstance(bag, dict):
        return False
    namespace_bag = bag.get(namespace)
    if not isinstance(namespace_bag, dict) or key not in namespace_bag:
        return False
    namespace_bag.pop(key, None)
    # Drop the namespace once it holds nothing, so resetting does not leave
    # empty scaffolding behind in the preferences blob.
    if not namespace_bag:
        bag.pop(namespace, None)
    if not bag:
        preferences.pop(PREFERENCES_APP_NAMESPACE, None)
    return True


def reset_dismissible_dialogs(profile):
    """Clear every registered dialog's dismissal state for one profile.

    Saves the profile only when something actually changed, and returns the
    number of dialogs reset. Preferences unrelated to dialogs are untouched —
    that is the whole point of this being separate from the full preferences
    reset.
    """
    if profile is None:
        return 0

    preferences = profile.preferences
    if not isinstance(preferences, dict):
        preferences = {}
    else:
        preferences = dict(preferences)
        app_bag = preferences.get(PREFERENCES_APP_NAMESPACE)
        if isinstance(app_bag, dict):
            preferences[PREFERENCES_APP_NAMESPACE] = {
                namespace: dict(value) if isinstance(value, dict) else value
                for namespace, value in app_bag.items()
            }

    reset_count = 0
    profile_fields_changed = False

    for spec in _REGISTRY.values():
        cleared = False
        if spec['preference_key']:
            cleared = _clear_preference(preferences, spec['preference_key']) or cleared
        if spec['app_namespace']:
            cleared = _clear_app_preference(
                preferences, spec['app_namespace'], spec['app_preference_key'],
            ) or cleared
        field = spec['profile_field']
        if field and hasattr(profile, field) and bool(getattr(profile, field)):
            setattr(profile, field, False)
            profile_fields_changed = True
            cleared = True
        if cleared:
            reset_count += 1

    if reset_count:
        profile.preferences = preferences
        update_fields = ['preferences']
        if profile_fields_changed:
            update_fields.extend(
                spec['profile_field'] for spec in _REGISTRY.values() if spec['profile_field']
            )
        profile.save(update_fields=sorted(set(update_fields)))

    return reset_count


def register_builtin_dialogs():
    """Dlux's own dismissible dialogs. Called once from ``DluxConfig.ready()``."""
    register_dismissible_dialog(
        id='dlux.unsaved_changes',
        label='Unsaved changes warning',
        description='The prompt shown when a settings modal is closed with pending edits.',
        preference_key='skip_unsaved_settings_prompt',
    )
    register_dismissible_dialog(
        id='dlux.initial_user_setup',
        label='Initial user setup',
        description='The first-login welcome modal, shown once per user.',
        profile_field='is_configured',
    )
