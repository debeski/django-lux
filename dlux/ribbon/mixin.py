"""The view side of the ribbon.

`RibbonMixin` adds `ribbon` to a list view's context. A view that already has a
`filterset_class` needs nothing else; the attributes below exist for the cases
where inference guesses wrong, and each can be set on its own.
"""


class RibbonMixin:
    # Filter names to keep in the primary row. None means "infer".
    ribbon_primary = None
    # Filter names for the advanced panel. None means "everything not primary".
    ribbon_advanced = None
    # Action dicts: {'url', 'label', 'icon', 'css_class', 'permission'} or
    # {'html': ...}. Resolved per request so a permission check is honoured.
    ribbon_actions = None
    # Page title. Falls back to whatever the view already puts in the context.
    ribbon_title = ''
    # Bootstrap-icon class for the title, e.g. 'bi bi-people'.
    ribbon_title_icon = ''
    ribbon_subtitle = ''
    # The tab strip: a declarative config — the same shape a settings builder
    # writes — or a ready `RibbonTabs`. This is the one to reach for. An
    # administrator may reshape it, or switch it off, in Settings -> Ribbon;
    # what is declared here is the starting point they are handed.
    ribbon_tabs = None
    # The same thing, locked. The builder skips the model entirely, so the
    # strip cannot be reshaped or switched off. For a strip the page needs to
    # work — a permission-gated tab, say — not merely one you would rather keep.
    # `get_ribbon_tabs()` is the escape hatch for a strip no source expresses.
    ribbon_tabs_fixed = None
    # Query keys that are not filters but must survive a filter submit and a
    # Clear. A strip's own key is added automatically.
    ribbon_preserve_keys = ()
    ribbon_context_key = 'ribbon'

    def get_ribbon_filterset(self):
        """The FilterSet the ribbon describes.

        Prefers an instance the view has already built, so the ribbon reflects
        the same bound form the list was filtered with rather than a second one
        built from the same GET.
        """
        for attr in ('filterset', 'object_list_filter', '_ribbon_filterset'):
            existing = getattr(self, attr, None)
            if existing is not None:
                return existing
        filterset_class = getattr(self, 'filterset_class', None)
        if filterset_class is None:
            return None
        getter = getattr(self, 'get_filterset', None)
        if callable(getter):
            return getter(filterset_class)
        return filterset_class(self.request.GET or None, request=self.request)

    def get_ribbon_title(self):
        return self.ribbon_title or getattr(self, 'page_title', '') or ''

    def get_ribbon_subtitle(self):
        return self.ribbon_subtitle or ''

    def get_ribbon_actions(self):
        from .build import build_action

        resolved = []
        for spec in (self.ribbon_actions or []):
            action = build_action(spec, request=self.request)
            if action is not None:
                resolved.append(action)
        return resolved

    def get_ribbon_host_key(self):
        match = getattr(getattr(self, 'request', None), 'resolver_match', None)
        view_name = str(getattr(match, 'view_name', '') or '').strip()
        if view_name:
            return view_name
        url_name = str(getattr(match, 'url_name', '') or '').strip()
        namespace = str(getattr(match, 'namespace', '') or '').strip()
        return f'{namespace}:{url_name}' if namespace and url_name else url_name

    def get_custom_ribbon_actions(self):
        from .build import build_action
        from .tabs import configured_custom_actions_for

        model = getattr(self, 'model', None) or getattr(getattr(self, 'queryset', None), 'model', None)
        resolved = []
        for spec in configured_custom_actions_for(model, self.get_ribbon_host_key()):
            action = build_action(spec, request=self.request)
            if action is not None:
                resolved.append(action)
        return resolved

    def get_ribbon_tab_counts(self):
        """`{tab key: count}`, or None for no badges.

        Counting is the view's job: only it knows whether the number should
        respect the current filters, and a per-tab COUNT is a query the ribbon
        has no business issuing on its own.
        """
        return None

    def _declared_strips(self):
        declared = self.ribbon_tabs_fixed or self.ribbon_tabs
        if isinstance(declared, (list, tuple)):
            return list(declared)
        return [declared] if declared else []

    def get_ribbon_tabs(self):
        """The **primary** strip: first declared strip, else first extra strip.

        Still one strip, and still the escape hatch a view overrides when no
        source expresses what it needs. A page splitting more than one way
        declares the rest alongside it; `get_ribbon_strips()` returns them all.
        """
        strips = self._build_configured_strips()
        return strips[0] if strips else None

    def get_ribbon_strips(self):
        """Every strip this page splits by, in order.

        A list can split more than one way at once — balances by warehouse, then
        by zone within it, then by condition across all of them. The first is the
        primary and comes from `get_ribbon_tabs()`, so a view that overrides that
        keeps working; each strip after it says how it stands to the one before
        through `relation`.
        """
        primary_override_locked = self.__class__.get_ribbon_tabs is not RibbonMixin.get_ribbon_tabs
        if primary_override_locked:
            primary = self.get_ribbon_tabs()
            return [primary] if primary else []
        return self._build_configured_strips()

    def _ribbon_base_queryset(self):
        if not hasattr(self, '_ribbon_base_queryset_cache'):
            getter = getattr(super(), 'get_queryset', None)
            if callable(getter):
                self._ribbon_base_queryset_cache = getter()
            else:
                model = getattr(self, 'model', None) or getattr(getattr(self, 'queryset', None), 'model', None)
                self._ribbon_base_queryset_cache = model._default_manager.all() if model is not None else None
        return self._ribbon_base_queryset_cache

    def _build_configured_strips(self):
        """Declared strips followed by Settings-created extras."""
        model = getattr(self, 'model', None) or getattr(getattr(self, 'queryset', None), 'model', None)
        fixed = bool(self.ribbon_tabs_fixed)
        strips = []

        base_queryset = None
        parent_queryset = None
        parent_active = ''

        def current_queryset():
            nonlocal base_queryset
            if parent_queryset is not None:
                return parent_queryset
            if base_queryset is None:
                base_queryset = self._ribbon_base_queryset()
            return base_queryset

        def remember_visible(strip):
            nonlocal parent_queryset, parent_active
            if strip.is_axis:
                return
            if strip.is_child and not strip.reveals_for(parent_active):
                return
            parent_queryset = strip.narrow(current_queryset())
            parent_active = strip.active

        def child_scope(config):
            if isinstance(config, dict) and config.get('relation') == 'child' and parent_active:
                return current_queryset()
            return None

        for index, config in enumerate(self._declared_strips()):
            scope_queryset = child_scope(config)
            strip = self._build_declared_strip(
                config, model, index, fixed, use_counts=not strips,
                scope_queryset=scope_queryset,
            )
            if strip:
                if strip.is_child and scope_queryset is not None and not any(not tab.is_all for tab in strip):
                    continue
                strips.append(strip)
                remember_visible(strip)
        if fixed:
            return strips
        from .tabs import configured_extra_strips_for

        for config in configured_extra_strips_for(model):
            scope_queryset = child_scope(config)
            strip = self._build_extra_strip(
                config, model, use_counts=not strips, scope_queryset=scope_queryset,
            )
            if strip:
                if strip.is_child and scope_queryset is not None and not any(not tab.is_all for tab in strip):
                    continue
                strips.append(strip)
                remember_visible(strip)
        return strips

    def _build_declared_strip(self, declared, model, index, locked, *, use_counts=False,
                              scope_queryset=None):
        """One strip declared by the view, after Settings overlays/removals."""
        from .tabs import OVERLAY_KEYS, build_ribbon_tabs, configured_strip_for

        param = declared.get('param') if isinstance(declared, dict) else None
        stored = configured_strip_for(model, param, index=index)

        if not locked and stored and stored.get('enabled') is False:
            return None

        overlay = {key: stored[key] for key in OVERLAY_KEYS if stored and key in stored}
        return build_ribbon_tabs(
            declared,
            model=model,
            request=self.request,
            counts=self.get_ribbon_tab_counts() if use_counts else None,
            overlay=overlay,
            locked=locked,
            scope_queryset=scope_queryset,
        )

    def _build_extra_strip(self, config, model, *, use_counts=False, scope_queryset=None):
        """One strip created in System Settings."""
        from .tabs import OVERLAY_KEYS, build_ribbon_tabs

        overlay = {key: config[key] for key in OVERLAY_KEYS if key in config}
        return build_ribbon_tabs(
            config,
            model=model,
            request=self.request,
            counts=self.get_ribbon_tab_counts() if use_counts else None,
            overlay=overlay,
            scope_queryset=scope_queryset,
        )

    def get_ribbon_preserve_keys(self):
        return tuple(self.ribbon_preserve_keys or ())

    def get_ribbon_clear_url(self):
        return ''

    def get_ribbon(self, context=None):
        from .build import build_ribbon

        filterset = (context or {}).get('filter') if context else None
        if filterset is None:
            filterset = self.get_ribbon_filterset()
        actions = list(self.get_ribbon_actions() or [])
        actions.extend(self.get_custom_ribbon_actions())
        return build_ribbon(
            filterset,
            request=self.request,
            title=self.get_ribbon_title(),
            title_icon=self.ribbon_title_icon,
            subtitle=self.get_ribbon_subtitle(),
            primary=self.ribbon_primary,
            advanced=self.ribbon_advanced,
            actions=actions,
            tabs=self.visible_ribbon_strips(),
            preserve_keys=self.get_ribbon_preserve_keys(),
            clear_url=self.get_ribbon_clear_url(),
        )

    def _ribbon_tabs(self):
        """The primary strip, built once per request.

        `get_queryset` narrows by the active tab and the ribbon renders the same
        strip; building it twice would issue the count queries twice.

        The cache is primed with `None` before building, so a `get_queryset()`
        reached *while* the strip is being built sees no strip and returns the
        un-narrowed set. That is both the recursion guard and the correct
        answer: tab counts are counts of the whole list, and counting through
        the active tab would make every badge read the active tab's total.
        """
        strips = self._ribbon_strips()
        return strips[0] if strips else None

    def _ribbon_strips(self):
        """Every strip, built once per request. See `_ribbon_tabs`."""
        if not hasattr(self, '_ribbon_tabs_cache'):
            self._ribbon_tabs_cache = []
            built = self.get_ribbon_strips()
            if built is None:
                built = []
            elif not isinstance(built, (list, tuple)):
                # `get_ribbon_strips()` is an override point too, and a view that
                # returns one strip from it means the obvious thing.
                built = [built]
            self._ribbon_tabs_cache = [strip for strip in built if strip]
        return self._ribbon_tabs_cache

    def visible_ribbon_strips(self):
        """The strips actually on show, parents before their children.

        A child strip is only meaningful under an active parent — zones say
        nothing until a warehouse is picked — so it drops out rather than
        rendering an empty row, and its lookup drops with it.
        """
        strips = self._ribbon_strips()
        visible = []
        parent_active = ''
        for strip in strips:
            if strip.is_child and not strip.reveals_for(parent_active):
                continue
            visible.append(strip)
            if not strip.is_axis:
                parent_active = strip.active
        return visible

    def get_queryset(self):
        """Narrow by every strip on show.

        Each strip knows its own lookup, so a view declaring them gets the
        filtering for free — which is the point of declaring them rather than
        hand-rolling a third tab implementation. A strip that is not on show
        does not narrow, or a stale sub-tab key would quietly empty the page.
        """
        queryset = self._ribbon_base_queryset()
        for strip in self.visible_ribbon_strips():
            queryset = strip.narrow(queryset)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context[self.ribbon_context_key] = self.get_ribbon(context)
        return context
