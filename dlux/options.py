"""Options-page card registry — the *only* supported way for a downstream app to
add a card to ``/sys/options/``.

Security model (firm, Dlux-first):

* **Code-only registration.** Cards are registered from trusted Python at
  startup (an app's ``dlux_options`` module or ``AppConfig.ready``). There is no
  HTTP, database, or settings path to register a card, so a card can never be
  *injected* by a request, a stored value, or a compromised non-superuser.
* **Server-side visibility.** ``superuser_only`` / ``permission`` are enforced in
  :func:`get_visible_cards` *before* a card's builder runs or its template
  renders — not merely hidden in the template.
* **Sandboxed rendering.** Each card renders in isolation inside a ``try/except``
  (:func:`render_cards`); a card that raises is logged and skipped so one bad
  app card can never blank the Options page.
* **Auto-escaping preserved.** A card's template is rendered by Django (its data
  auto-escaped) and Dlux only marks the *already-rendered* trusted-template HTML
  safe. Dlux never marks app-supplied *data* safe. App card templates must not
  ``|safe`` untrusted values themselves.
"""

import logging
import re

from .system.constants import SAFE_NAMESPACE_RE

logger = logging.getLogger('dlux')

_SAFE_ID = re.compile(SAFE_NAMESPACE_RE)
# One or more Bootstrap-Icons classes, e.g. "bi-grid" or "bi-grid text-primary".
_SAFE_ICON = re.compile(r'^[A-Za-z0-9 _-]+$')
_MAX_ID_LEN = 128

# id -> card dict. Insertion order is irrelevant; render order is (order, id).
_REGISTRY = {}


def register_card(*, id, title, template_name, icon='bi-puzzle', order=100,
                  superuser_only=False, permission=None, context_builder=None,
                  visible=None):
    """Register one Options-page card. Raises ``ValueError`` on invalid input.

    Args:
        id: Stable unique slug ([A-Za-z0-9._-], <=128). Also the card's
            ``data-options-card`` value, so keep it namespaced (``myapp.thing``).
        title: The card heading — a plain string, or a ``callable(request)->str``
            for per-request localization.
        template_name: A template (resolved by the normal loader) rendered as the
            card *body*. Dlux supplies the surrounding card chrome.
        icon: Bootstrap-Icons class(es) for the heading.
        order: Sort weight (lower first); ties break by ``id``.
        superuser_only: Only render for superusers (enforced server-side).
        permission: Optional ``"app_label.codename"``; only users with it see it.
        context_builder: Optional ``callable(request)->dict`` producing the
            template context. Runs sandboxed with the current request/user.
        visible: Optional ``callable(request)->bool`` for config-driven
            visibility (e.g. show the card only when a feature is enabled in
            ``extra_config``). Evaluated server-side *after* the static gates and
            **fail-closed** — if it raises, the card is hidden.
    """
    if not isinstance(id, str) or not id or len(id) > _MAX_ID_LEN or not _SAFE_ID.match(id):
        raise ValueError(f"register_card: invalid id {id!r} (must match {SAFE_NAMESPACE_RE}, <= {_MAX_ID_LEN} chars)")
    if not (isinstance(title, str) and title) and not callable(title):
        raise ValueError(f"register_card[{id}]: title must be a non-empty string or a callable")
    if not isinstance(template_name, str) or not template_name:
        raise ValueError(f"register_card[{id}]: template_name must be a non-empty string")
    if not isinstance(icon, str) or not _SAFE_ICON.match(icon):
        raise ValueError(f"register_card[{id}]: invalid icon {icon!r}")
    if not isinstance(order, int) or isinstance(order, bool):
        raise ValueError(f"register_card[{id}]: order must be an int")
    if permission is not None and not (isinstance(permission, str) and permission):
        raise ValueError(f"register_card[{id}]: permission must be a non-empty string or None")
    if context_builder is not None and not callable(context_builder):
        raise ValueError(f"register_card[{id}]: context_builder must be callable or None")
    if visible is not None and not callable(visible):
        raise ValueError(f"register_card[{id}]: visible must be callable or None")

    if id in _REGISTRY:
        # Overwrite (dev autoreload re-imports the module) but make it visible.
        logger.debug("register_card: overwriting already-registered Options card '%s'", id)

    _REGISTRY[id] = {
        'id': id,
        'title': title,
        'template_name': template_name,
        'icon': icon,
        'order': int(order),
        'superuser_only': bool(superuser_only),
        'permission': permission,
        'context_builder': context_builder,
        'visible': visible,
    }


def unregister_card(id):
    """Remove a card (mainly for tests)."""
    _REGISTRY.pop(id, None)


def clear_registry():
    """Drop all registered cards (test helper)."""
    _REGISTRY.clear()


def get_visible_cards(request):
    """Cards the requesting user may see, sorted by (order, id).

    Permission/superuser gating is enforced here, server-side, so an ineligible
    card's ``context_builder`` never runs and its template never renders.
    """
    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False):
        return []
    visible = []
    for card in _REGISTRY.values():
        if card['superuser_only'] and not user.is_superuser:
            continue
        if card['permission'] and not user.has_perm(card['permission']):
            continue
        predicate = card['visible']
        if predicate is not None:
            try:
                if not predicate(request):
                    continue
            except Exception:
                # Fail closed: a broken visibility check hides the card rather
                # than exposing it.
                logger.exception("Options card '%s' visible() raised; hiding it (fail-closed).", card['id'])
                continue
        visible.append(card)
    return sorted(visible, key=lambda c: (c['order'], c['id']))


def render_cards(request):
    """Render visible cards to a list of ``{id, title, icon, html}``.

    Every card is rendered inside its own ``try/except`` — a failing card is
    logged and dropped, never propagated, so the Options page always renders.
    """
    from django.template.loader import render_to_string
    from .translations import get_current_language_code, get_strings

    strings = get_strings(get_current_language_code(request))
    rendered = []
    for card in get_visible_cards(request):
        try:
            context = {'request': request, 'user': request.user, 'DLUX_STRINGS': strings}
            builder = card['context_builder']
            if builder is not None:
                extra = builder(request)
                if isinstance(extra, dict):
                    context.update(extra)
            title = card['title']
            if callable(title):
                title = title(request)
            html = render_to_string(card['template_name'], context, request=request)
        except Exception:
            logger.exception("Options card '%s' failed to render; skipping it.", card['id'])
            continue
        rendered.append({
            'id': card['id'],
            'title': title,
            'icon': card['icon'],
            'html': html,
        })
    return rendered
