"""The shape a ribbon takes once it has been derived.

These are plain data: `build_ribbon` produces them by inspecting a FilterSet,
and the templates read them. Nothing here renders, and nothing here reaches
back into a request — which is what lets a ribbon be built and asserted on in
a test without a view.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

# What a slot in the ribbon carries. A range is two form fields presented as
# one control, so the kind travels with the slot rather than being re-derived
# from the field name in every template.
KIND_SEARCH = 'search'
KIND_RANGE = 'range'
KIND_FIELD = 'field'


@dataclass
class RibbonField:
    """One control in the ribbon: a single filter, or a from/to pair."""

    names: Tuple[str, ...]
    kind: str = KIND_FIELD
    label: str = ''
    placeholder: str = ''
    col_class: str = ''

    @property
    def name(self):
        return self.names[0]

    @property
    def is_range(self):
        return self.kind == KIND_RANGE

    @property
    def is_search(self):
        return self.kind == KIND_SEARCH


@dataclass
class RibbonAction:
    """A control at the end of the ribbon — usually Add, sometimes an export.

    Renders as a link when it has a `url`, and as a button otherwise: the most
    common list action in dlux opens a dynamic modal from `data-dynamic-modal`
    with no href at all, so a link-only action would have forced every such page
    to fall back to raw `html`.
    """

    url: str = ''
    label: str = ''
    icon: str = ''
    css_class: str = 'btn btn-primary'
    # `submit` for a button that posts a form elsewhere on the page — an export
    # or a print, which carry the current filters by submitting the form that
    # holds them via `form=` and `formaction=` in `attrs`.
    type: str = 'button'
    attrs: dict = field(default_factory=dict)
    html: str = ''

    @property
    def is_html(self):
        return bool(self.html)

    @property
    def is_link(self):
        return bool(self.url)


@dataclass
class Ribbon:
    """A list page's band: its title, its filters, and its actions."""

    form: Any = None
    title: str = ''
    title_icon: str = ''
    subtitle: str = ''
    primary: List[RibbonField] = field(default_factory=list)
    advanced: List[RibbonField] = field(default_factory=list)
    actions: List[RibbonAction] = field(default_factory=list)
    #: The strips that choose which records the page is about, in order, parents
    #: before their children. Between the heading and the filters, because they
    #: govern both. A list, because a page can split more than one way at once.
    strips: List[Any] = field(default_factory=list)
    #: How a nested strip attaches to its parent: 'chain', 'rail' or 'tiered'.
    #: Only ever visible on a page carrying more than one strip.
    nesting: str = 'chain'
    hidden: List[Tuple[str, str]] = field(default_factory=list)
    clear_url: str = ''
    panel_id: str = 'dlux-ribbon-advanced'
    # Resolved from layout_config at build time so a template never has to.
    # `layout` is the arrangement (which template renders); `style` is the look
    # (which skin class the root carries). Keeping them apart means a new skin
    # never has to reason about where the actions sit, and a new arrangement
    # never has to restate a palette.
    layout: str = 'default'
    style: str = 'accent'
    show_title: bool = True
    advanced_trigger: str = 'button'
    # True when an advanced field is actually filtering, so the panel opens
    # even if the reader last left it shut.
    advanced_active: bool = False
    # Whether a real filter is set, which is what the Clear control reflects.
    has_active_filters: bool = False
    strings: dict = field(default_factory=dict)

    @property
    def tabs(self):
        """The primary strip. Named for what it was when there was only one, and
        kept because templates and views read it that way."""
        return self.strips[0] if self.strips else None

    @property
    def has_tabs(self):
        return bool(self.strips)

    @property
    def nested_strips(self):
        """Everything after the primary: the children and the axes."""
        return self.strips[1:]

    @property
    def nesting_class(self):
        return f'dlux-ribbon-nesting-{self.nesting}'

    @property
    def has_advanced(self):
        return bool(self.advanced) and self.advanced_trigger != 'off'

    @property
    def advanced_open(self):
        return self.advanced_trigger == 'always' or self.advanced_active

    @property
    def template_name(self):
        return f'dlux/ribbon/_{self.layout}.html'

    @property
    def skin_class(self):
        """The skin class, plus any shared chrome class the skin piggybacks on.

The panel skin also carries `glass-profile` — a dlux-wide class name,
        not this skin's label — because every theme already restyles it, so the
        dark themes replace its surface instead of tinting a light one.
        Decided here rather than in the template: a `ribbon.style ==` comparison
        in markup trips the inline-style policy check, and the templates should
        not be branching on a value anyway.
        """
        classes = [f'dlux-ribbon-skin-{self.style}']
        if self.style == 'panel':
            classes.append('glass-profile')
        return ' '.join(classes)

    @property
    def shows_title(self):
        """Compact has no room for a title, whatever the toggle says."""
        return self.show_title and self.layout != 'compact'

    @property
    def actions_below(self):
        """Where the actions sit is the layout's decision and nothing else's.

        There was briefly a separate `ribbon_actions_position` setting. It was
        redundant: its only live value, `default` + `below`, rendered byte for
        byte what `stacked` already rendered, and it was greyed out under the
        other two layouts. Removed before v1.8.2 shipped.
        """
        return self.layout == 'stacked'

    def field_names(self):
        names = []
        for slot in list(self.primary) + list(self.advanced):
            names.extend(slot.names)
        return names

    def string(self, key: str, default: str = '') -> str:
        return self.strings.get(key) or default


def blank_ribbon(**kwargs) -> Optional[Ribbon]:
    """A ribbon with no filter form — a list page that only needs its actions."""
    return Ribbon(**kwargs)
