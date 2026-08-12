"""Catalogs derived from discovery: loggable models, home-page URL options."""

from django.apps import apps
from django.urls import NoReverseMatch, reverse
from ..system.constants import DISCOVERY_PROFILE_LANDING

from .render import _user_has_sidebar_permission
from .routes import discover_routes_for


def _is_section_model(model):
    """True for auxiliary 'section' content models (is_section=True) — project content,
    not dlux framework machinery."""
    try:
        from ..utils.sections import _model_is_section
        return bool(_model_is_section(model))
    except Exception:
        return False


_BASE_LOG_ACTIONS = ('create', 'update', 'delete')


def _model_log_actions(model):
    """Loggable actions for a model: the CRUD base plus any custom actions the model declares
    via `dlux_log_actions = ['download', 'approve', ...]`. Unknown actions are still logged at
    runtime by default; declaring them here surfaces a toggle in the settings grid."""
    actions = list(_BASE_LOG_ACTIONS)
    declared = getattr(model, 'dlux_log_actions', None)
    if isinstance(declared, (list, tuple, set)):
        for raw in declared:
            act = str(raw or '').strip().lower()
            if act and act not in actions:
                actions.append(act)
    return actions


def build_log_model_catalog(lang_code=None):
    """Return loggable concrete models grouped for the Logging settings UI.

    Shape: {'user': [{'key','label','actions'}], 'system': [...]}.
    - Excludes models that never produce meaningful logs (Django framework internals, dlux
      operational/identity/self/dummy models — see is_model_loggable) plus auto/through/proxy.
    - 'user' (project) = non-dlux app models and auxiliary section models. 'system' = the
      synthetic "User accounts" identity entry (users are a core dlux component) plus the
      remaining dlux framework/config models.
    - Each item's `actions` = create/update/delete plus any declared `dlux_log_actions`.
    """
    from ..translations import get_strings
    from ..utils.activity_log import (
        LOG_IDENTITY_MODEL_KEY,
        is_model_loggable,
        translate_activity_log_model_name,
    )

    strings = get_strings(lang_code) if lang_code else get_strings()
    user_items = []
    system_items = []
    for model in apps.get_models():
        meta = model._meta
        if meta.auto_created or meta.proxy:
            continue
        key = meta.label_lower  # "app_label.model"
        if not is_model_loggable(key, meta.app_label):
            continue
        label = translate_activity_log_model_name(key, strings) or str(meta.verbose_name)
        item = {'key': key, 'label': str(label), 'actions': _model_log_actions(model)}
        is_project = (meta.app_label != 'dlux') or _is_section_model(model)
        (user_items if is_project else system_items).append(item)
    user_items.sort(key=lambda i: i['label'].lower())
    system_items.sort(key=lambda i: i['label'].lower())
    # Pin the unified user-identity (User + Profile) toggle to the top of the system list —
    # user accounts are a core dlux component.
    system_items.insert(0, {
        'key': LOG_IDENTITY_MODEL_KEY,
        'label': str(strings.get('log_model_user_accounts', 'User accounts')),
        'actions': list(_BASE_LOG_ACTIONS),
    })
    return {'user': user_items, 'system': system_items}


def build_user_home_url_options(user, lang_code=None):
    """Reversible pages the given user may access, as a list of {'value', 'label'} for a
    landing-page picker. Permission-filtered with the same rules as the sidebar (superusers
    see all; system items included so profile/options/reports appear when accessible)."""
    catalog = discover_routes_for(
        DISCOVERY_PROFILE_LANDING,
        lang_code=lang_code,
        include_system_items=True,
    )
    seen = set()
    options = []
    for entry in catalog:
        url_name = entry.get('url_name')
        if not url_name:
            continue
        if not _user_has_sidebar_permission(user, entry.get('permissions'), entry.get('permissions_explicit', False)):
            continue
        try:
            resolved = reverse(url_name)
        except NoReverseMatch:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        label = str(entry.get('label') or entry.get('group_label') or url_name).strip()
        options.append({'value': resolved, 'label': label})
    options.sort(key=lambda o: o['label'].lower())
    return options
