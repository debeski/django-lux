"""The ribbon: a list page's title, filters and actions as one band.

Page chrome, like the navbar and the titlebar: the administrator picks how it
looks in Settings -> Layout, and a view declaring a `filterset_class` gets a
correct one without configuring anything.

    from dlux.ribbon import RibbonMixin

    class AssetListView(RibbonMixin, ScopedListView):
        filterset_class = AssetFilter

and in the template:

    {% load dlux_tags %}
    {% dlux_ribbon %}

Replaces `dlux.utils.advanced_filter_helper`, which stays available until
v1.9.0 (see docs/deprecation-countdown.md).
"""

from .build import build_action, build_ribbon, split_range_suffix
from .tabs import (RibbonTab, RibbonTabs, build_ribbon_tabs, configured_extra_strips_for,
                   configured_strip_for, configured_strips_for, configured_tabs_for)
from .mixin import RibbonMixin
from .spec import KIND_FIELD, KIND_RANGE, KIND_SEARCH, Ribbon, RibbonAction, RibbonField

__all__ = [
    'Ribbon',
    'RibbonTab',
    'RibbonTabs',
    'build_ribbon_tabs',
    'configured_extra_strips_for',
    'configured_strip_for',
    'configured_strips_for',
    'configured_tabs_for',
    'RibbonAction',
    'RibbonField',
    'RibbonMixin',
    'build_action',
    'build_ribbon',
    'split_range_suffix',
    'KIND_FIELD',
    'KIND_RANGE',
    'KIND_SEARCH',
]
