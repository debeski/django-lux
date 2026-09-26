"""Draft previews of System Settings: real pages rendered with unsaved values.

A preview is two requests. The settings form POSTs its unsaved state to
``system_settings_preview_draft``, which validates it the way a save would and
parks the raw form data in the session under a short-lived token. A frame then
GETs an ordinary page with ``?_dlux_preview=<token>``; `DluxMiddleware` calls
`begin()` before the view runs, and for that one request `SystemSettings.load()`
answers with the draft instead of the stored row. Every template, context
processor and view reads settings through `load()`, so the page renders exactly
as it would after a save — the project's own pages included — without a line of
per-field preview code.

A preview request can never write. It is GET-only, runs inside a transaction
that is always rolled back, restores the session it found, and the markup it
returns carries a guard that swallows clicks and submits. The reader's personal
preferences are blanked for the request, so the page shows the system defaults
being edited rather than the admin's own theme or density.
"""

from __future__ import annotations

import copy
import secrets
import time
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from django.http import QueryDict

PREVIEW_PARAM = '_dlux_preview'
AS_PARAM = '_dlux_preview_as'
LANG_PARAM = '_dlux_preview_lang'
SESSION_KEY = 'dlux_settings_previews'
MAX_DRAFTS = 6
DRAFT_TTL_SECONDS = 30 * 60
KIND_SYSTEM = 'system'
KIND_APP = 'app'
REQUEST_MEMOS = ('_dlux_system_config', '_dlux_language_config', '_dlux_scope_enabled')

from .preview_state import current_draft, draft_settings as _draft_settings  # noqa: F401


class DraftInvalid(Exception):
    """The unsaved form would not save, so there is nothing truthful to render."""

    def __init__(self, errors):
        super().__init__('The settings draft is not valid.')
        self.errors = errors


def is_preview_request(request):
    return bool(getattr(request, 'dlux_preview', None))


# ── Draft storage ──────────────────────────────────────────────────────────


def _querydict_payload(data):
    if isinstance(data, QueryDict):
        return {key: data.getlist(key) for key in data.keys()}
    return {str(key): list(value) if isinstance(value, (list, tuple)) else [value] for key, value in dict(data).items()}


def _payload_querydict(payload):
    query = QueryDict('', mutable=True)
    for key, values in (payload or {}).items():
        query.setlist(key, [str(value) for value in values])
    query._mutable = False
    return query


def store_draft(request, *, kind=KIND_SYSTEM, data=None, mode='', namespace='', step=None):
    """Park a draft in the session and return its token. Oldest drafts expire."""
    now = time.time()
    drafts = {
        token: entry
        for token, entry in (request.session.get(SESSION_KEY) or {}).items()
        if isinstance(entry, dict) and now - float(entry.get('created', 0)) < DRAFT_TTL_SECONDS
    }
    token = secrets.token_urlsafe(18)
    drafts[token] = {
        'kind': kind,
        'mode': mode,
        'namespace': namespace,
        'step': step,
        'user_id': getattr(request.user, 'pk', None),
        'created': now,
        'data': _querydict_payload(data or {}),
    }
    if len(drafts) > MAX_DRAFTS:
        for stale in sorted(drafts, key=lambda key: drafts[key]['created'])[:-MAX_DRAFTS]:
            drafts.pop(stale, None)
    request.session[SESSION_KEY] = drafts
    request.session.modified = True
    return token


def _stored_draft(request, token):
    if not token or not hasattr(request, 'session'):
        return None
    entry = (request.session.get(SESSION_KEY) or {}).get(token)
    if not isinstance(entry, dict):
        return None
    if time.time() - float(entry.get('created', 0)) >= DRAFT_TTL_SECONDS:
        return None
    if entry.get('user_id') != getattr(request.user, 'pk', None):
        return None
    return entry


# ── Building the draft ─────────────────────────────────────────────────────


def _fresh_settings():
    """A private copy of the stored row — never the cached singleton."""
    from django.apps import apps

    SystemSettings = apps.get_model('dlux', 'SystemSettings')
    instance = SystemSettings.objects.order_by('pk').first()
    return instance if instance is not None else SystemSettings(pk=1)


def _form_errors(form):
    return {
        field: [str(message) for message in messages]
        for field, messages in form.errors.items()
    }


def _step_request(request, step):
    """`request` as the settings form sees it when one Options step is posted.

    The form reads the step from ``request.GET['step']`` and, in single-step
    mode, keeps every other step's stored values — exactly what the modal's own
    save does. A preview frame is a different request, so it is replayed here.
    """
    if step is None:
        return request
    stepped = copy.copy(request)
    stepped.GET = QueryDict(urlencode({'step': step}))
    return stepped


def build_system_draft(request, data, *, mode='', step=None):
    """Bind the settings form to `data` and return what it would save, unsaved."""
    from django.utils.module_loading import import_string

    SystemSettingsForm = import_string('dlux.forms.SystemSettingsForm')
    request = _step_request(request, step if mode != 'setup' else None)
    kwargs = {'data': data, 'instance': _fresh_settings(), 'request': request, 'user': request.user}
    if mode == 'setup':
        kwargs['mode'] = 'setup'
    form = SystemSettingsForm(**kwargs)
    if not form.is_valid():
        raise DraftInvalid(_form_errors(form))
    draft = form.save(commit=False)
    for field_name in ('logo', 'favicon', 'login_logo', 'login_background'):
        current = getattr(draft, f'{field_name}_asset', None)
        try:
            resolved = form._resolve_asset_selection(field_name, current, commit=False)
        except TypeError:
            resolved = current
        setattr(draft, f'{field_name}_asset', resolved)
    draft.is_configured = True
    return draft


def build_app_draft(request, data, *, namespace):
    """The stored settings with one app namespace replaced by the unsaved form."""
    # Resolved by name: the middleware reaches this module, and a static import
    # of dlux.options (forms, ribbon) would couple it to their import cluster.
    from django.utils.module_loading import import_string

    get_visible_app_setting = import_string('dlux.options.get_visible_app_setting')
    build_app_settings_form = import_string('dlux.options.build_app_settings_form')
    get_app_settings_form_value = import_string('dlux.options.get_app_settings_form_value')

    definition = get_visible_app_setting(request, namespace)
    if definition is None:
        raise DraftInvalid({'__all__': ['Unknown settings namespace.']})
    form = build_app_settings_form(definition, request, data=data)
    if not form.is_valid():
        raise DraftInvalid(_form_errors(form))
    draft = _fresh_settings()
    extra = copy.deepcopy(draft.extra_config) if isinstance(draft.extra_config, dict) else {}
    apps_config = extra.get('app') if isinstance(extra.get('app'), dict) else {}
    apps_config[definition['namespace']] = get_app_settings_form_value(definition, form)
    extra['app'] = apps_config
    draft.extra_config = extra
    return draft


def build_draft(request, entry):
    data = _payload_querydict(entry.get('data'))
    if entry.get('kind') == KIND_APP:
        return build_app_draft(request, data, namespace=entry.get('namespace') or '')
    return build_system_draft(request, data, mode=entry.get('mode') or '', step=entry.get('step'))


# ── The preview request ────────────────────────────────────────────────────


def _draft_language(draft, requested):
    from dlux.system.normalizers import normalize_language_catalog

    try:
        languages = normalize_language_catalog(getattr(draft, 'languages', None) or {})
    except Exception:
        languages = getattr(draft, 'languages', None) or {}
    if requested and requested in languages:
        return requested
    default = getattr(draft, 'default_language', '') or 'en'
    return default if not languages or default in languages else next(iter(languages))


def begin(request):
    """Turn `request` into a preview of its token's draft, or leave it alone.

    Returns a callable that undoes the activation, or ``None`` when the request
    is not a (permitted) preview.
    """
    token = request.GET.get(PREVIEW_PARAM) if hasattr(request, 'GET') else None
    if not token:
        return None
    user = getattr(request, 'user', None)
    if request.method not in ('GET', 'HEAD') or not getattr(user, 'is_superuser', False):
        return None
    entry = _stored_draft(request, token)
    if entry is None:
        return None
    try:
        draft = build_draft(request, entry)
    except DraftInvalid:
        return None

    session_snapshot = dict(request.session.items()) if hasattr(request, 'session') else None
    reset = _draft_settings.set(draft)
    # Anything earlier in the stack that already read settings memoised them on
    # the request; those copies describe the stored row, not the draft.
    for memo in REQUEST_MEMOS:
        if hasattr(request, memo):
            try:
                delattr(request, memo)
            except AttributeError:
                pass
    audience = request.GET.get(AS_PARAM) or ''
    request.dlux_preview = {'token': token, 'audience': audience, 'kind': entry.get('kind')}
    request.dlux_preview_language = _draft_language(draft, request.GET.get(LANG_PARAM) or '')

    profile = getattr(user, 'profile', None) if getattr(user, 'is_authenticated', False) else None
    if profile is not None:
        profile.preferences = {}
    if audience == 'anonymous':
        from django.contrib.auth.models import AnonymousUser

        request.user = AnonymousUser()

    def end():
        _draft_settings.reset(reset)
        if session_snapshot is not None:
            current = dict(request.session.items())
            if current != session_snapshot:
                for key in list(current):
                    if key not in session_snapshot:
                        del request.session[key]
                for key, value in session_snapshot.items():
                    request.session[key] = value

    return end


def preview_params(request):
    """The query parameters that keep a follow-up request inside this preview."""
    state = getattr(request, 'dlux_preview', None) or {}
    params = {PREVIEW_PARAM: state.get('token', '')}
    if state.get('audience'):
        params[AS_PARAM] = state['audience']
    requested = request.GET.get(LANG_PARAM)
    if requested:
        params[LANG_PARAM] = requested
    return params


def carry_preview(url, request):
    """`url` with the preview parameters added, for same-site URLs only."""
    parts = urlsplit(url or '')
    if parts.scheme or parts.netloc:
        host = request.get_host()
        if parts.netloc and parts.netloc != host:
            return url
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(preview_params(request))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


GUARD_SCRIPT_PATH = 'dlux/system/js/preview_guard.js'


def _guard_tag(request):
    """The guard, as a static script: dlux pages carry no executable inline code."""
    from django.utils.module_loading import import_string

    # By name, like the form and options helpers: the middleware reaches here.
    dlux_static = import_string('dlux.templatetags.dlux_tags.dlux_static')
    nonce = str(getattr(request, 'csp_nonce', '') or '')
    nonce_attr = f' nonce="{nonce}"' if nonce else ''
    return f'<script src="{dlux_static(GUARD_SCRIPT_PATH)}" data-dlux-preview-guard{nonce_attr}></script>'


def finish(request, response):
    """Mark a preview response: uncached, frameable by us only, inert, redirects kept inside."""
    response['Cache-Control'] = 'no-store'
    response['X-Frame-Options'] = 'SAMEORIGIN'
    location = response.get('Location')
    if location and 300 <= response.status_code < 400:
        response['Location'] = carry_preview(location, request)
    content_type = response.get('Content-Type', '')
    if 'text/html' in content_type and not getattr(response, 'streaming', False):
        body = response.content.decode(response.charset or 'utf-8', errors='replace')
        marker = body.lower().rfind('</body>')
        if marker != -1:
            body = body[:marker] + _guard_tag(request) + body[marker:]
            # Marked before first paint, so page-load animations never replay in a
            # preview frame and a re-render reads as the page changing in place.
            html_at = body.lower().find('<html')
            if html_at != -1:
                insert_at = html_at + len('<html')
                body = body[:insert_at] + ' data-dlux-preview' + body[insert_at:]
            response.content = body.encode(response.charset or 'utf-8')
            if response.has_header('Content-Length'):
                response['Content-Length'] = str(len(response.content))
    return response
