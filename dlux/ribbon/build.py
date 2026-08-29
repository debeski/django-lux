"""Deriving a ribbon from a FilterSet.

The point of the feature: a view that declares a `filterset_class` and nothing
else gets a correct band. Everything below is inference from what the FilterSet
already says, using the naming conventions dlux already relies on elsewhere —
`set_field_attrs` (dlux/utils/crud.py) reads the same `_gte`/`_lte` suffixes to
label a pair From/To, so the pairing here is that convention reused, not a
second one invented.
"""

from .spec import KIND_FIELD, KIND_RANGE, KIND_SEARCH, Ribbon, RibbonAction, RibbonField

# A filter under one of these names is the list's free-text search: it leads the
# primary row and takes the leftover width.
SEARCH_NAMES = ('keyword', 'q', 'search')
# Filters that belong beside the search rather than behind the toggle, because
# every list that has them filters by them constantly.
PROMOTED_NAMES = ('year',)
# Both spellings occur: `date__gte` from a declared filter, `date_gte` from a
# hand-named one.
RANGE_SUFFIXES = (('__gte', '__lte'), ('_gte', '_lte'))
# Query parameters that control how the list is presented, not what it contains.
# Changing a page or a sort must not light up the Clear control — that contract
# is shared with `advanced_filter_helper` (see the v1.8.2 changelog) and is
# preserved across a Clear.
PRESENTATION_KEYS = ('page', 'per_page', 'sort', 'export_type')


def split_range_suffix(name):
    """('date__gte') -> ('date', 'from'); ('x') -> (None, None)."""
    for low, high in RANGE_SUFFIXES:
        if name.endswith(low):
            return name[: -len(low)], 'from'
        if name.endswith(high):
            return name[: -len(high)], 'to'
    return None, None


def _model_name(filterset):
    meta = getattr(filterset, '_meta', None)
    model = getattr(meta, 'model', None)
    return model.__name__.lower() if model is not None else ''


# django_filters generates a label from the lookup when a filter declares none.
# For a range that reads as a sentence ("Date joined is greater than or equal
# to"), and it is this marker when the field path cannot be resolved. Neither
# belongs on a ribbon control.
AUTO_LABEL_MARKER = '[invalid name]'


def _label_for(base, form, strings, model_name, fallback_field=None, allow_field_label=True):
    """Model-specific translation, then generic, then the filter namespace, then
    the field's own label.

    `filter_<name>` is in the chain because that is where dlux already keeps
    filter labels (`filter_year`, `filter_date`, `filter_all`), so a project
    that translated its filters for the old helper needs no new strings.
    """
    keys = (
        f'label_{model_name}_{base}' if model_name else None,
        f'label_{base}',
        f'filter_{base}',
    )
    for key in keys:
        if key and strings.get(key):
            return strings[key]
    if allow_field_label and fallback_field is not None:
        label = getattr(fallback_field, 'label', None)
        if label and str(label) != AUTO_LABEL_MARKER:
            return str(label)
    return base.replace('__', ' ').replace('_', ' ').strip().title()


def _pair_ranges(names, form, strings, model_name):
    """Collapse from/to siblings into one slot, keeping declaration order.

    A `_gte` with no matching `_lte` (or the reverse) stays a plain field — a
    half-range is a real filter, and dropping it would silently lose it.
    """
    bases = {}
    for name in names:
        base, direction = split_range_suffix(name)
        if base:
            bases.setdefault(base, {})[direction] = name

    slots = []
    consumed = set()
    for name in names:
        if name in consumed:
            continue
        base, direction = split_range_suffix(name)
        pair = bases.get(base) if base else None
        if pair and 'from' in pair and 'to' in pair:
            ordered = (pair['from'], pair['to'])
            consumed.update(ordered)
            slots.append(RibbonField(
                names=ordered,
                kind=KIND_RANGE,
                label=_label_for(
                    base, form, strings, model_name,
                    form.fields.get(ordered[0]), allow_field_label=False,
                ),
            ))
            continue
        consumed.add(name)
        if base:
            # A half-range: the auto-label is the same lookup sentence a full
            # range gets, but dropping to the bare base name would lose the
            # from/to sense. Suffix it the way `set_field_attrs` already does.
            sense = strings.get(f'filter_{direction}') or direction.title()
            label = '{} ({})'.format(
                _label_for(base, form, strings, model_name, allow_field_label=False),
                sense.strip(),
            )
        else:
            label = _label_for(name, form, strings, model_name, form.fields.get(name))
        slots.append(RibbonField(names=(name,), kind=KIND_FIELD, label=label))
    return slots


def _bound_value(form, name):
    if name not in form.fields:
        return None
    if form.is_bound:
        return (form.data.get(name) or '').strip() if hasattr(form.data, 'get') else None
    return None


def build_ribbon(
    filterset=None,
    *,
    request=None,
    title='',
    title_icon='',
    subtitle='',
    primary=None,
    advanced=None,
    actions=None,
    hidden=None,
    tabs=None,
    preserve_keys=(),
    clear_url='',
    layout=None,
    strings=None,
    panel_id='dlux-ribbon-advanced',
):
    """Build a `Ribbon` from a FilterSet, honouring any explicit overrides.

    `primary` and `advanced`, when given, are lists of filter names; a name that
    the FilterSet does not define is skipped rather than raising, so a view that
    keeps a stale name after a filter is renamed degrades to a missing control
    instead of a 500 on a list page.
    """
    from dlux.translations import get_current_language_code, get_strings

    if strings is None:
        strings = get_strings(get_current_language_code(request))
    if layout is None:
        from dlux.utils import get_system_config

        layout = get_system_config()

    # One strip or several: a caller that has only ever had one keeps passing it.
    if tabs is None:
        strips = []
    elif isinstance(tabs, (list, tuple)):
        strips = [strip for strip in tabs if strip]
    else:
        strips = [tabs]
    # Every strip's key survives a filter submit and a Clear without the view
    # restating them — which is what a hand-drawn second strip always had to do.
    for strip in strips:
        if getattr(strip, 'param', None):
            preserve_keys = tuple(preserve_keys or ()) + (strip.param,)

    form = getattr(filterset, 'form', None)
    ribbon = Ribbon(
        form=form,
        title=title,
        title_icon=title_icon,
        subtitle=subtitle,
        actions=list(actions or []),
        strips=strips,
        nesting=layout.get('ribbon_nesting') or 'chain',
        hidden=list(hidden or []),
        clear_url=clear_url,
        panel_id=panel_id,
        strings=strings,
        layout=layout.get('ribbon_layout') or 'default',
        style=layout.get('ribbon_style') or 'accent',
        show_title=bool(layout.get('ribbon_title', True)),
        advanced_trigger=layout.get('ribbon_advanced_trigger') or 'button',
    )
    if form is None:
        return ribbon

    model_name = _model_name(filterset)
    all_names = [n for n in form.fields]

    if primary is not None or advanced is not None:
        chosen = [n for n in (primary or []) if n in form.fields]
        rest = [n for n in (advanced if advanced is not None else all_names)
                if n in form.fields and n not in chosen]
    else:
        chosen = [n for n in all_names if n in SEARCH_NAMES]
        chosen += [n for n in all_names if n in PROMOTED_NAMES and n not in chosen]
        rest = [n for n in all_names if n not in chosen]

    ribbon.primary = _pair_ranges(chosen, form, strings, model_name)
    ribbon.advanced = _pair_ranges(rest, form, strings, model_name)

    for slot in ribbon.primary:
        if slot.name in SEARCH_NAMES:
            slot.kind = KIND_SEARCH
            slot.placeholder = strings.get('search_placeholder') or slot.label
            # Set it on the widget rather than passing it at render time:
            # `set_field_attrs` fills a placeholder with `setdefault`, so one
            # placed here wins, and the field is never given two.
            field = form.fields.get(slot.name)
            if field is not None and slot.placeholder:
                field.widget.attrs['placeholder'] = slot.placeholder

    ribbon.advanced_active = any(
        _bound_value(form, name)
        for slot in ribbon.advanced
        for name in slot.names
    )
    # Deliberately after derivation: `set_field_attrs` folds a select's label
    # into its empty choice and blanks `field.label`, so normalising first would
    # destroy the labels the derivation reads.
    from dlux.utils.crud import set_field_attrs

    set_field_attrs(form, request, inline_labels=True)

    ribbon.has_active_filters = _has_active_filters(request, form)
    if not clear_url:
        ribbon.clear_url = _clear_url(request, preserve_keys)
    if not hidden:
        ribbon.hidden = _carried_keys(request, preserve_keys)
    return ribbon


def _carried_keys(request, preserve_keys):
    """Keys the filter form must resubmit, as hidden inputs.

    A list split by tabs carries its tab in the query string, and the ribbon is
    a GET form: without these, the first filter submission drops the reader back
    to the first tab. Presentation keys ride along for the same reason.
    """
    if request is None:
        return []
    keys = tuple(preserve_keys or ()) + PRESENTATION_KEYS
    return [
        (key, value)
        for key, value in request.GET.items()
        # `page` is not carried: applying a filter changes what the list holds,
        # so the old page number is meaningless.
        if key in keys and key != 'page' and value
    ]


def _has_active_filters(request, form):
    """True when a real filter is set — presentation keys do not count."""
    if request is None:
        return False
    return any(
        key in form.fields and value
        for key, value in request.GET.items()
    )


def _clear_url(request, preserve_keys=()):
    """The list with its filters dropped but its presentation kept.

    `preserve_keys` survives a Clear too: a tab is not a filter, so clearing the
    filters must not also throw the reader back to the first tab.
    """
    if request is None:
        return ''
    import urllib.parse

    keys = tuple(preserve_keys or ()) + PRESENTATION_KEYS
    kept = [
        (key, value)
        for key, value in request.GET.items()
        # `page` is deliberately dropped: clearing a filter changes what the
        # list contains, so page 7 of the old result set is meaningless.
        if key in keys and key != 'page' and value
    ]
    query = urllib.parse.urlencode(kept, doseq=True)
    return f'{request.path}?{query}' if query else request.path


def build_action(spec, request=None):
    """Turn an action dict into a `RibbonAction`, or None if not permitted."""
    if isinstance(spec, RibbonAction):
        return spec
    spec = dict(spec or {})
    permission = spec.pop('permission', None)
    if permission and request is not None:
        user = getattr(request, 'user', None)
        if user is None or not user.has_perm(permission):
            return None
    from django.utils.safestring import mark_safe

    raw_html = spec.get('html', '')
    return RibbonAction(
        url=spec.get('url', '') or '',
        label=spec.get('label', ''),
        icon=spec.get('icon', ''),
        css_class=spec.get('css_class') or spec.get('btn_class') or 'btn btn-primary',
        type=spec.get('type') or 'button',
        attrs=dict(spec.get('attrs') or {}),
        # Developer-supplied markup from view code, not user input.
        html=mark_safe(raw_html) if raw_html else '',
    )
