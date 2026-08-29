"""Row-level access hooks a project can add without patching dlux.

Django permissions are model-level ("can view invoices"). Which *rows* a user
may see is the project's business — ownership, territory, department — and dlux
does not model it. What dlux owns is the choke points: the dynamic modal
resolves the object it is about to show, edit or delete through one queryset,
and scope filtering is applied there.

Before this, a project needing ownership had to reach into
`dlux.views.sections` and wrap that helper by hand. That worked, but it meant
importing `dlux.views` from `AppConfig.ready()` — which triggers section
discovery, a database query during startup — so the patch had to be deferred to
the first request instead. A registry avoids both: this module imports nothing,
so registering is cheap and safe at app-init.

    # myapp/apps.py
    def ready(self):
        from dlux.access import register_modal_queryset_filter
        from myapp.access import apply_ownership

        register_modal_queryset_filter(apply_ownership)

A filter is called as `filter(queryset, user)` and must return a queryset. It
runs *after* scope filtering, so it narrows an already-scoped set and can never
widen one — a filter that returns something larger than it was given still
cannot reveal a row from another scope, because that row was gone before it was
called.
"""

_MODAL_QUERYSET_FILTERS = []


def register_modal_queryset_filter(filter_fn):
    """Narrow the queryset the dynamic modal resolves its object from.

    Registering the same callable twice is a no-op, so an `AppConfig.ready()`
    that runs more than once — which Django permits — does not stack filters.
    """
    if not callable(filter_fn):
        raise ValueError('dlux.access: a modal queryset filter must be callable')
    if filter_fn not in _MODAL_QUERYSET_FILTERS:
        _MODAL_QUERYSET_FILTERS.append(filter_fn)
    return filter_fn


def unregister_modal_queryset_filter(filter_fn):
    """Remove a registered filter (mainly for tests)."""
    try:
        _MODAL_QUERYSET_FILTERS.remove(filter_fn)
    except ValueError:
        pass


def get_modal_queryset_filters():
    return tuple(_MODAL_QUERYSET_FILTERS)


def apply_modal_queryset_filters(queryset, user):
    """Run every registered filter over `queryset`, in registration order.

    A filter that raises is skipped rather than allowed to take down the modal —
    but it is skipped *closed*: the queryset it was given is kept, which is the
    narrower of the two possible answers, so a broken filter cannot widen what
    the reader sees.
    """
    import logging

    logger = logging.getLogger('dlux')

    for filter_fn in _MODAL_QUERYSET_FILTERS:
        try:
            narrowed = filter_fn(queryset, user)
        except Exception:
            logger.exception(
                'dlux.access: modal queryset filter %r raised; keeping the '
                'un-narrowed queryset for this filter.',
                getattr(filter_fn, '__name__', filter_fn),
            )
            continue
        if narrowed is not None:
            queryset = narrowed
    return queryset
