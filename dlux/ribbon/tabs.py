"""Tabs: the strip that chooses *which* records the page is about.

A tab is not a filter. A filter narrows a set the reader has already chosen; a
tab chooses the set. That is why the strip belongs above the filter row and why
switching one resets the page rather than adding to it.

One strip can mix sources, because a real list often splits more than one way:

    ribbon_tabs = {
        'param': 'kind',
        'sources': [
            {'type': 'all'},
            {'type': 'field', 'field': 'kind'},          # one tab per choice
            {'type': 'flag', 'field': 'is_archived'},    # rows where it is True
        ],
    }

The same shape is what a settings builder edits, so a strip declared in code and
one drawn in Settings are the same object by the time anything renders it.
"""

from dataclasses import dataclass, field

from django.db.models import Q
from typing import Any, List, Optional

#: A tab's query value identifies it. For a field source that is the field's own
#: value, so `?kind=employee` keeps working; for a flag it is the field name.
#: Keys must be unique across sources — `validate` says so rather than letting
#: two tabs quietly answer to the same URL.
SOURCE_ALL = 'all'
SOURCE_FIELD = 'field'
SOURCE_FLAG = 'flag'
SOURCE_STATIC = 'static'


@dataclass
class RibbonTab:
    """One tab. `key` is its query value; empty means "everything"."""

    key: str = ''
    label: str = ''
    url: str = ''
    active: bool = False
    count: Optional[int] = None
    icon: str = ''
    #: How to narrow a queryset for this tab, set by the source that made it.
    lookup: Optional[dict] = None

    @property
    def is_all(self):
        return not self.key


@dataclass
class RibbonTabs:
    """A strip of tabs and the query key that carries the active one."""

    param: str = 'tab'
    items: List[RibbonTab] = field(default_factory=list)
    active: str = ''
    #: How this strip stands to the one before it. '' is the primary strip;
    #: 'child' narrows *within* it and is drawn attached to it; 'axis' cuts
    #: across everything above and is deliberately drawn as a different control,
    #: so an orthogonal row is never mistaken for a nested one.
    relation: str = ''
    #: Parent tab keys that reveal a child strip. Empty means any active parent —
    #: zones appear once a warehouse is picked, whichever warehouse it is —
    #: while a value names the one tab it belongs under, the way export types
    #: belong under Exports and nowhere else.
    when: tuple = ()
    #: Shown beside an axis strip, which needs saying what it is asking.
    label: str = ''

    @property
    def is_child(self):
        return self.relation == 'child'

    @property
    def is_axis(self):
        return self.relation == 'axis'

    def reveals_for(self, parent_active):
        """Whether this child strip belongs under the parent's active tab."""
        if not self.is_child:
            return True
        if not parent_active:
            return False
        return not self.when or parent_active in self.when

    def __bool__(self):
        return bool(self.items)

    def __iter__(self):
        return iter(self.items)

    @property
    def active_tab(self):
        for tab in self.items:
            if tab.key == self.active:
                return tab
        return None

    def narrow(self, queryset):
        """Apply the active tab to a queryset.

        A tab with no lookup narrows nothing — "All", or a strip whose view
        does its own filtering.
        """
        tab = self.active_tab
        if tab is None or not tab.lookup:
            return queryset
        # A dict covers most tabs, but a real condition is sometimes an OR —
        # "no disposition, or a cancelled one" — which no dict can say. `filter()`
        # already takes either, so the strip may too. A `Q` cannot survive the
        # settings builder's JSON, so it is a code-only declaration.
        if isinstance(tab.lookup, Q):
            return queryset.filter(tab.lookup)
        return queryset.filter(**tab.lookup)

    def validate(self):
        """Duplicate keys mean two tabs answer to one URL, so the second is
        unreachable. Worth failing loudly at build time rather than shipping a
        strip with a dead tab in it."""
        seen = set()
        for tab in self.items:
            if tab.key in seen:
                raise ValueError(
                    f'ribbon tabs: duplicate key {tab.key!r} on param {self.param!r}; '
                    'give the source an explicit key or rename the field'
                )
            seen.add(tab.key)
        return self


def _tab_url(request, param, key, *, drop=()):
    """This tab, keeping the query it was reached with.

    A tab is not a filter, so it keeps the filters. `page` always goes: page 4
    of one tab is rarely a valid page of another.
    """
    if request is None:
        return f'?{param}={key}' if key else '?'
    query = request.GET.copy()
    query.pop('page', None)
    for name in drop:
        query.pop(name, None)
    if key:
        query[param] = key
    else:
        query.pop(param, None)
    encoded = query.urlencode()
    return f'?{encoded}' if encoded else '?'


def _resolve_field(model, path):
    """The field at a lookup path, following relations the way `filter()` does.

    A strip often splits by something one step away — balances by the warehouse
    their *zone* belongs to — where the tabs come from `Warehouse` but the lookup
    has to read `zone__warehouse`. One name for both keeps the two from drifting.
    """
    parts = path.split('__')
    current = model
    for index, part in enumerate(parts):
        field = current._meta.get_field(part)
        if index == len(parts) - 1:
            return field
        related = getattr(field, 'related_model', None)
        if related is None:
            raise ValueError(
                f'ribbon tabs: {model.__name__}.{path} traverses {part!r}, '
                'which is not a relation'
            )
        current = related
    return None


def _relation_label(obj, source):
    """A related row's tab label: `label_attr` if the source names one.

    `__str__` is written for a global context and often qualifies itself — a zone
    reads "Main - A1" so it means something in a dropdown. Inside a strip nested
    under Main, that prefix is on every tab and says nothing; `label_attr` lets
    the strip ask for the short form its parent already qualifies.
    """
    attr = source.get('label_attr')
    if attr:
        value = getattr(obj, attr, None)
        if callable(value):
            value = value()
        if value:
            return str(value)
    return str(obj)


def _icon_for(value, source):
    """One source makes many tabs, so an icon can be per value or shared.

    `icons` maps a value to its own icon — import, export and return each read
    at a glance — and `icon` covers the rest. Without this a field source's
    `icon` was accepted and then dropped, which the settings builder still
    offered an input for.
    """
    icons = source.get('icons') or {}
    return icons.get(value) or icons.get(str(value)) or source.get('icon', '')


def _with_scope(lookup, source):
    """Merge a source's shared `lookup` into one tab's own.

    A strip is often a split *within* a scope rather than over the whole table —
    categories of the working register, with retired items on their own tab. The
    scope belongs on the source, not repeated on every tab it generates, and not
    hidden in the view's `get_queryset()` where a tab that must escape it (the
    retired one) then cannot.
    """
    scope = source.get('lookup')
    if not scope:
        return lookup
    merged = dict(scope)
    merged.update(lookup or {})
    return merged


def _label_for_choice(value, label, strings, model_name, field_name):
    """A tab names a group, so it reads plural where a form field reads
    singular. `tab_<field>_<value>` first, then the form's own `choice_<value>`.
    """
    for key in (f'tab_{field_name}_{value}', f'tab_{value}', f'choice_{value}'):
        if strings.get(key):
            return strings[key]
    return str(label)


def _lookup_available(queryset, lookup):
    if queryset is None:
        return True
    narrowed = queryset
    if lookup:
        if isinstance(lookup, Q):
            narrowed = narrowed.filter(lookup)
        else:
            narrowed = narrowed.filter(**lookup)
    return narrowed.exists()


def _field_tabs(model, source, strings, request=None):
    """One tab per choice on a field, or per row of a related table."""
    name = source['field']
    django_field = _resolve_field(model, name)
    # Labels resolve against the field's own name, not the whole path: a strip on
    # `zone__warehouse` still reads `tab_warehouse_<value>`.
    label_name = name.split('__')[-1]
    # A strip is often narrower than the field: a category the reader may not
    # see should not be offered as a tab.
    only = source.get('only')
    exclude = set(source.get('exclude') or ())

    def wanted(value):
        if only is not None and value not in only and str(value) not in {str(o) for o in only}:
            return False
        return value not in exclude and str(value) not in {str(e) for e in exclude}

    tabs = []
    if getattr(django_field, 'choices', None):
        for value, label in django_field.choices:
            if not wanted(value):
                continue
            tabs.append(RibbonTab(
                key=str(value),
                label=_label_for_choice(value, label, strings, model._meta.model_name, label_name),
                icon=_icon_for(value, source),
                lookup=_with_scope({name: value}, source),
            ))
        return tabs
    if django_field.is_relation:
        # A related table's rows are the tabs — warehouses, categories.
        queryset = source.get('queryset')
        if callable(queryset):
            # The rows a *this* reader may pick from — scoped, active-only —
            # which a config written once at import time cannot know.
            queryset = queryset(request)
        if queryset is None:
            queryset = django_field.related_model._default_manager.all()
        for obj in queryset:
            if not wanted(obj.pk):
                continue
            tabs.append(RibbonTab(
                key=str(obj.pk),
                label=_relation_label(obj, source),
                icon=_icon_for(obj.pk, source),
                lookup=_with_scope({name: obj.pk}, source),
            ))
        return tabs
    raise ValueError(
        f'ribbon tabs: {model.__name__}.{name} has neither choices nor a relation, '
        'so it cannot populate a strip; use a flag source or hand the tabs in'
    )


def _flag_tabs(model, source, strings):
    """One tab for a boolean, showing the rows where it is true."""
    name = source['field']
    label = source.get('label') or strings.get(f'tab_{name}') or strings.get(f'label_{name}')
    if not label:
        label = str(model._meta.get_field(name).verbose_name).title()
    return [RibbonTab(
        key=source.get('key') or name,
        label=label,
        icon=source.get('icon', ''),
        # `True` rather than the field name alone: a flag tab shows what is set.
        lookup=_with_scope({name: source.get('value', True)}, source),
    )]


def build_ribbon_tabs(config, *, model=None, request=None, strings=None, counts=None,
                      overlay=None, locked=False, scope_queryset=None):
    """Turn a tab config into a `RibbonTabs`.

    `config` is the declarative shape a view sets or a settings builder writes.
    A view wanting something no source expresses hands `items` straight through
    instead — the escape hatch is part of the design, not an afterthought.
    """
    if not config:
        return RibbonTabs()
    if isinstance(config, RibbonTabs):
        return config

    from dlux.translations import get_current_language_code, get_strings

    if strings is None:
        strings = get_strings(get_current_language_code(request))

    param = config.get('param') or 'tab'
    drop = tuple(config.get('drop') or ())
    relation = str(config.get('relation') or '')
    when = config.get('when')
    when = (when,) if isinstance(when, str) else tuple(when or ())
    strip_label = config.get('label') or ''
    items = []

    for source in (config.get('sources') or []):
        kind = source.get('type', SOURCE_FIELD)
        if kind == SOURCE_ALL:
            items.append(RibbonTab(
                key='',
                label=source.get('label') or strings.get('ui_all', 'All'),
                icon=source.get('icon', ''),
                # "All" of whatever this strip is about, which is not always the
                # whole table — see `_with_scope`.
                lookup=source.get('lookup'),
            ))
        elif kind == SOURCE_STATIC:
            items.append(RibbonTab(
                key=str(source.get('key', '')),
                label=source.get('label', ''),
                icon=source.get('icon', ''),
                lookup=source.get('lookup'),
            ))
        elif kind == SOURCE_FLAG:
            items.extend(_flag_tabs(model, source, strings))
        elif kind == SOURCE_FIELD:
            items.extend(_field_tabs(model, source, strings, request))
        else:
            raise ValueError(f'ribbon tabs: unknown source type {kind!r}')

    for item in config.get('items') or []:
        items.append(item if isinstance(item, RibbonTab) else RibbonTab(**item))

    # Looked up here rather than by each caller, so a view that builds its strip
    # by hand — the sections screen does — is re-dressed like any other.
    if overlay is None and model is not None:
        stored = configured_strip_for(model, param)
        overlay = {key: stored[key] for key in OVERLAY_KEYS if stored and key in stored}
    items = _apply_overlay(items, overlay, locked=locked,
                           language=get_current_language_code(request))
    if scope_queryset is not None:
        items = [tab for tab in items if _lookup_available(scope_queryset, tab.lookup)]

    tabs = RibbonTabs(param=param, items=items, relation=relation, when=when,
                      label=strip_label).validate()

    requested = (request.GET.get(param, '') if request is not None else '').strip()
    # `default` is for a strip with no "All": the reader always stands in one
    # tab, so an unknown value falls back to the first meaningful one rather
    # than to an unfiltered page the strip never offers.
    fallback = str(config.get('default') or '')
    if fallback and not any(t.key == fallback for t in items):
        # Hiding the default is an ordinary thing to do in Settings, so it falls
        # back to the first tab still standing rather than raising on a list page.
        # A default naming a tab the strip never had is still a developer error.
        declared = config.get('items') or config.get('sources')
        if declared is not None and (overlay or scope_queryset is not None):
            fallback = items[0].key if items else ''
        else:
            raise ValueError(
                f'ribbon tabs: default {fallback!r} is not one of the tabs on param {param!r}'
            )
    tabs.active = requested if any(t.key == requested for t in tabs.items) else fallback
    for tab in tabs.items:
        tab.active = tab.key == tabs.active
        tab.url = _tab_url(request, param, tab.key, drop=drop)
        if counts is not None:
            # Supplying counts at all means badges are wanted, so a tab with no
            # rows reads 0 rather than losing its badge — "User 0" is a fact,
            # a missing badge is an absence the reader has to interpret.
            tab.count = counts.get(tab.key, 0)
    return tabs


OVERLAY_KEYS = ('order', 'labels', 'icons', 'hidden')


def _overlay_label(value, language):
    """A renamed tab's label in this reader's language.

    A dict is per-language, with a blank entry meaning "leave it alone" so an
    operator can rename a tab in Arabic without inventing an English name for
    it. A bare string is one name for every language.
    """
    if isinstance(value, dict):
        return value.get(language) or value.get('') or ''
    return value or ''


def _apply_overlay(items, overlay, *, locked=False, language=''):
    """Re-dress an already-built strip: order, names, icons, what shows.

    Deliberately applied to the *built* tabs rather than to the config that
    builds them. That is the whole reason it works everywhere: a strip whose
    lookups are `Q` objects or come from a request-scoped queryset can never be
    expressed in settings JSON, so rebuilding it from Settings is impossible —
    but by the time it is a list of tabs, reordering and renaming it is trivial
    and can break nothing, because none of this touches a lookup.

    A locked strip (`ribbon_tabs_fixed`) takes the cosmetic half only: which tabs
    exist is the developer's call, how they read is not.
    """
    if not overlay:
        return items

    if not locked:
        hidden = set(overlay.get('hidden') or ())
        if hidden:
            items = [tab for tab in items if tab.key not in hidden]

    labels = overlay.get('labels') or {}
    icons = overlay.get('icons') or {}
    for tab in items:
        if tab.key in labels:
            renamed = _overlay_label(labels[tab.key], language)
            if renamed:
                tab.label = renamed
        if tab.key in icons:
            tab.icon = icons[tab.key]

    order = overlay.get('order')
    if order:
        rank = {key: index for index, key in enumerate(order)}
        # A tab the order forgot keeps its declared position, after the ones it
        # names — so a strip that gains a tab in code does not vanish from view
        # because an older saved order never mentioned it.
        items = sorted(
            enumerate(items),
            key=lambda pair: (rank.get(pair[1].key, len(rank)), pair[0]),
        )
        items = [tab for _index, tab in items]
    return items


def _stored_ribbon_entry(model):
    """The normalized settings entry for one model."""
    if model is None:
        return {}
    return _stored_ribbon_entry_key(f'{model._meta.app_label}.{model.__name__}')


def _stored_ribbon_entry_key(key):
    """The normalized settings entry for one model or synthetic route key."""
    if not key:
        return {}

    from django.apps import apps as django_apps

    from dlux.system.normalizers import normalize_ribbon_config

    try:
        SystemSettings = django_apps.get_model('dlux', 'SystemSettings')
        config = normalize_ribbon_config(SystemSettings.load().ribbon_config)
    except Exception:
        # A list page must render even if settings are unreadable — mid-migration,
        # say. No strip is a worse page, not a broken one.
        return {}
    return config.get(str(key)) or {}


def configured_strips_for(model):
    """Stored overlays/removals for strips the view declares."""
    return list(_stored_ribbon_entry(model).get('strips') or ())


def configured_extra_strips_for(model):
    """Stored strips created in System Settings."""
    return list(_stored_ribbon_entry(model).get('extra_strips') or ())


def configured_custom_actions_for(model, host_key=None):
    """Stored administrator-created actions for one ribbon host."""
    if model is None:
        return []
    return configured_custom_actions_for_key(f'{model._meta.app_label}.{model.__name__}', host_key)


def configured_custom_actions_for_key(key, host_key=None):
    """Stored administrator-created actions for a model or route storage key."""
    stored = _stored_ribbon_entry_key(key).get('custom_actions') or {}
    if isinstance(stored, (list, tuple)):
        return list(stored)
    if not isinstance(stored, dict):
        return []
    actions = []
    actions.extend(stored.get('*') or [])
    if host_key:
        actions.extend(stored.get(str(host_key)) or [])
    return actions


def configured_action_overlays_for_key(key):
    """Stored administrator edits to the buttons a view declares in code."""
    stored = _stored_ribbon_entry_key(key).get('actions') or {}
    return stored if isinstance(stored, dict) else {}


def configured_strip_for(model, param=None, index=0):
    """The stored overlay/removal for one declared strip."""
    strips = configured_strips_for(model)
    if not strips:
        return None
    if param:
        for strip in strips:
            if strip.get('param') == param:
                return strip
        for strip in strips:
            if strip.get('index') == index and not strip.get('param'):
                return strip
        return None
    return strips[index] if 0 <= index < len(strips) else None


def configured_tabs_for(model):
    """The first strip created in System Settings, or None."""
    strips = configured_extra_strips_for(model)
    return strips[0] if strips else None
