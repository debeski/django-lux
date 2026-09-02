# Ribbon

The ribbon is the band at the top of a list page carrying its **title**, its
**filters** and its **actions**.

It is page chrome, like the navbar and the titlebar: the administrator chooses
how it looks in *System Settings → Ribbon*, and a view gets a correct one
without configuring anything. It replaces `advanced_filter_helper`, which
required a hand-written `advanced_config` dict per FilterSet and had a fixed
layout no administrator could change (removed in v1.9.0 — see
[Deprecation Countdown](deprecation-countdown.md)).

## Using it

```python
from dlux.ribbon import RibbonMixin


class AssetListView(RibbonMixin, ScopedListView):
    filterset_class = AssetFilter
```

```django
{% load dlux_tags %}
{% dlux_ribbon %}
```

That is the whole integration. The ribbon is derived from the FilterSet.

A page with no FilterSet can still use it — `build_ribbon(None, ...)` returns a
band carrying just the title, subtitle and actions, which is how the Reports
page renders its header. An action can be `type='submit'` with `form` and
`formaction` in `attrs`, so a button in the ribbon can submit a form living
elsewhere on the page; `{'html': ...}` passes rendered markup through for a
composite control.

Keep page-owned POST workflows out of the action rail when they need several
fields. The Backup & Restore page renders its passphrase, scope, and create
button as a row immediately under `{% dlux_ribbon %}`, leaving the ribbon actions
for navigation, filters, and compact triggers.

## What is derived, and how

| Rule | Result |
|---|---|
| A filter named `keyword`, `q` or `search` | Leads the primary row and takes the leftover width |
| A filter named `year` | Sits beside the search |
| `<name>_gte` + `<name>_lte` (or `__gte`/`__lte`) | Collapse into one From/To range control |
| A `_gte` with no `_lte` sibling | Stays a plain field — a half-range is still a real filter |
| Everything else | The advanced panel, in declaration order |

Labels resolve through dlux translations in this order, so a project that is
already translated needs no new strings:

`label_<model>_<field>` → `label_<field>` → `filter_<field>` → the field's own
label → the field name, title-cased.

The field's own label is skipped for a range, because django_filters generates
it from the lookup and it reads as a sentence ("Date joined is greater than or
equal to"); it is also skipped when django_filters could not resolve the field
path and produced `[invalid name]`.

The advanced panel opens on load when an advanced filter is actually filtering,
so a filter in effect is never hidden behind a collapsed toggle.

## Overriding

Each attribute works on its own — a view never has to specify all of them to
correct one:

```python
class AssetListView(RibbonMixin, ScopedListView):
    filterset_class = AssetFilter
    ribbon_primary = ['keyword', 'year', 'category']
    ribbon_actions = [
        {'url': reverse_lazy('asset_add'), 'label': 'Add', 'icon': 'bi bi-plus-lg',
         'permission': 'storage.add_asset'},
    ]
```

| Attribute | Default | Meaning |
|---|---|---|
| `ribbon_primary` | inferred | Filter names for the primary row |
| `ribbon_advanced` | everything not primary | Filter names for the advanced panel |
| `ribbon_actions` | none | Action dicts; `permission` drops the action when the user lacks it |
| `ribbon_title` | the view's `page_title` | Heading text |
| `ribbon_title_icon` | none | Bootstrap-icon class for the title, e.g. `bi bi-people`; renders as a tinted tile beside the copy |
| `ribbon_subtitle` | none | A line under the title, in the same column |
| `ribbon_preserve_keys` | none | Query keys that are not filters but must survive a filter submit and a Clear |

A list split by nav tabs carries its tab in the query string. The ribbon is a
GET form, so those keys have to be resubmitted as hidden inputs and kept in the
Clear URL, or the first filter throws the reader back to the first tab. Name
them in `ribbon_preserve_keys` — or better, derive them, as
`TabbedListMixin.get_ribbon_preserve_keys()` does downstream. `page` is never
carried: applying or clearing a filter changes what the list holds, so the old
page number is meaningless.

An action renders as a link when it has a `url` and as a `<button>` otherwise,
because the commonest dlux list action opens a dynamic modal and has no href:

```python
ribbon_actions = [
    {'label': 'Add User', 'icon': 'bi bi-person-plus-fill',
     'css_class': 'btn btn-primary rounded-pill',
     'attrs': {'data-dynamic-modal': reverse('modal_user')}},
]
```

`{'html': '...'}` passes markup through untouched for anything neither shape
covers.

A name that the FilterSet does not define is skipped rather than raising, so a
filter renamed out from under a view degrades to a missing control instead of a
500 on the list page.

For finer control, override `get_ribbon_actions()`, `get_ribbon_title()`,
`get_ribbon_subtitle()`, `get_ribbon_clear_url()`, or `get_ribbon()` itself.

## Field normalisation and the Clear control

`build_ribbon` applies `set_field_attrs` to the filter form — the same
normalisation the old helpers applied — so widgets get their Bootstrap classes,
their RTL `dir`, and the shared `dlux-datepicker` hook. It runs **after**
derivation, not before: `set_field_attrs` folds a select's label into its empty
choice and blanks `field.label`, so normalising first would destroy the labels
the derivation reads.

The Clear control reflects **filter** state, not table presentation state.
`page`, `per_page`, `sort` and `export_type` never activate it, and a Clear
preserves them — except `page`, which is dropped because page 7 of a different
result set is meaningless. This is the same contract `advanced_filter_helper`
was fixed to honour in v1.8.2.

## Tabs

A tab is not a filter. A filter narrows a set the reader has already chosen; a
tab *chooses* the set. That is why the strip sits between the heading and the
filter row — it decides what the filters are about — and why switching one keeps
the filters rather than clearing them.

One rule divides the header, and it sits **under the title**: the title says
what the page is, while the tabs and the filters both say which records, so
that is where the boundary falls. A page with no strip keeps the same rule
above its filter row.

Declare a strip and the ribbon renders it, narrows the queryset by it, and keeps
its key through a filter submit and a Clear:

```python
class PartyListView(RibbonMixin, ScopedListView):
    ribbon_tabs = {
        'param': 'kind',
        'sources': [
            {'type': 'all'},
            {'type': 'field', 'field': 'kind'},
            {'type': 'flag', 'field': 'is_archived'},
        ],
    }
```

| source | gives |
|---|---|
| `all` | the leading "everything" tab; no lookup |
| `field` | one tab per choice, or per row of a related table |
| `flag` | one tab for a boolean, showing the rows where it is true |
| `static` | one tab with a lookup you write |

One strip can mix them, because a real list often splits more than one way — a
choice field alongside a couple of booleans is the case the design was built
around. Each tab carries its own lookup, so `field` narrows to a value while
`flag` narrows to `True`.

**A source can follow a relation path.** When the list is one step from what it
splits by, name the path and the tabs come from the far end:

```python
{'type': 'field', 'field': 'zone__warehouse'}   # tabs are warehouses
```

The lookup narrows through the path while `param` stays whatever short key you
want in the URL. Labels resolve against the field's own name, so this still reads
`tab_warehouse_<value>`, not the whole path.

**A lookup can be a `Q`.** Some conditions are an OR and no dict can say one:

```python
{'type': 'static', 'key': 'active', 'label': 'Active Fleet',
 'lookup': Q(disposition__isnull=True) | Q(disposition__deleted_at__isnull=False)}
```

`filter()` takes either, so a tab may too. A `Q` cannot be stored in
`ribbon_config`, so a strip using one is code-only — declare it with
`ribbon_tabs_fixed` if losing the condition would break the page.

**A source's icons.** `icon` applies to every tab the source makes; `icons` maps
one value to its own, which is what a type strip wants — an inbound arrow on
Imports, an outbound one on Exports:

```python
{'type': 'field', 'field': 'doc_type',
 'icons': {'import': 'bi bi-box-arrow-in-down', 'export': 'bi bi-box-arrow-up'}}
```

**A source can carry a scope.** Give any source a `lookup` and every tab it
produces applies it too, so a strip can split *within* a scope while one tab
steps outside:

```python
ribbon_tabs_fixed = {
    'param': 'category',
    'sources': [
        {'type': 'all', 'lookup': {'is_active': True}},
        {'type': 'field', 'field': 'category', 'lookup': {'is_active': True},
         'queryset': lambda request: categories_for(request.user)},
        {'type': 'static', 'key': 'retired', 'label': 'Retired',
         'lookup': {'is_active': False}},
    ],
}
```

That last tab is the reason the scope belongs on the source rather than in the
view's `get_queryset()`: narrowing is additive, so a tab that must escape the
scope could never do it from there. Where a tab's own lookup names the same key,
the tab wins — it is the more specific statement.

A relation source's `queryset` may be a **callable taking the request**, for the
rows this particular reader may pick from. A config read once at import cannot
know that, and offering a tab whose rows the reader cannot see is a worse page.

Options: `default` for a strip with no "All" (the reader always stands in one
tab); `only` / `exclude` to narrow the offered choices, which is how a
privileged tab stays hidden; `drop` to clear a dependent key when the tab
changes; `items` to hand tabs in directly.

`get_ribbon_tabs()` is the escape hatch for a strip no source expresses, and
`get_ribbon_tab_counts()` returns `{key: count}` for badges — counting is the
view's job, because only it knows whether the number should respect the current
filters. Counts are taken over the **un-narrowed** list, or every badge would
read the active tab's total.

Duplicate keys raise at build time: two tabs answering to one URL means the
second is unreachable.

### Editing strips in Settings

*Settings → Ribbon → Tab Strips* writes `SystemSettings.ribbon_config`. Normal
list views keep the existing `"app_label.ModelName"` storage key, while direct
page ribbons can use route keys such as `"route.reports_overview"`. A ribbon
host can gain extra tab strips and administrator-owned buttons without a
developer, and declared strips can be re-dressed or removed.

The builder lists URL views that actually render a ribbon, including no-tab
hosts and explicit function-based pages that set `view.dlux_ribbon_host = True`.
Reading the model registry instead would offer every table in the project,
sessions and permissions included, none of which have a page. Within a model it
offers only fields that can populate a strip — a choices field, a relation, or a
boolean, minus the audit relations every scoped model carries — so an extra
strip cannot raise on render, and a malformed one is dropped when it is saved
rather than when a page loads. Dlux system hosts are hidden in the builder until
the administrator enables **Show system items**.

### Re-dressing a strip: the overlay

Re-dressing a strip does not change what its tabs mean. Settings can reorder,
rename, re-icon and hide the tabs of any strip, including one it could never
create from JSON:

```json
{"storage.VehicleProfile": {"strips": [{
    "index":  0,
    "param":  "state",
    "order":  ["disposed", "active"],
    "labels": {"disposed": "Retired"},
    "icons":  {"active": "bi bi-truck"},
    "hidden": []
}]}}
```

It applies to the **built** tabs, not to the config that builds them. That is
why it works everywhere: Fleet's strip narrows by `Q(disposition__isnull=True) |
Q(disposition__deleted_at__isnull=False)`, which no stored config can express —
but once it is a list of tabs, reordering it is trivial and touches no lookup.
Nothing an overlay does can change what a tab *means*.

So `ribbon_tabs_fixed` does not mean "invisible in Settings". It means "not
removable and no extra strips": a locked strip takes the cosmetic half — order,
label, icon — and keeps its tabs, because which tabs exist is the developer's
call and how they read is not.

Two behaviours worth knowing:

- Hiding the default tab falls back to the first tab still standing. Hiding a
  tab is an ordinary thing to do, and a list page is the wrong place to discover
  it was the default.
- A tab the saved order never mentioned keeps its declared position, after the
  ones it names — otherwise a strip that gains a tab in code would disappear
  behind an order saved months earlier.

### What Settings shows

The builder lists **every** model with a ribbon, locked ones included, and
resolves each declared strip into its actual tabs — it used to know only the
*sources* that generate them, which is why a page's real tabs were invisible and
a locked model had no presence in Settings at all.

Each model card separates the two kinds of strip:

| group | does | action wording |
|---|---|---|
| **Pre-defined strips** | re-dress tabs, or remove the declared strip from the page | **Restore** discards edits/removal; **Remove** suppresses the declared strip |
| **Extra strips** | add a new strip, change its split field or relation, then re-dress its tabs | **Remove** deletes the admin-made strip |

Restore is only used for pre-defined strips. An admin-made strip is not restored
to code, because there is no code version of it; removing it deletes that extra
strip from the saved config.

A declared strip may carry a callable `queryset` or a `Q` lookup, neither of
which survives the JSON the builder reads. Those parts are dropped from the
catalog and the rest of the declaration stays visible — so such a strip can
still be re-dressed without rewriting its lookup.

### More than one strip

`ribbon_tabs` takes a list. The first is the primary; each after it says how it
stands to the one before:

```python
ribbon_tabs = [
    {"param": "warehouse", "drop": ("zone",), "sources": [...]},
    {"param": "zone", "relation": "child", "label": _("Zones here"), "sources": [...]},
    {"param": "condition", "relation": "axis", "label": _("Condition"), "sources": [...]},
]
```

| `relation` | means | drawn as |
|---|---|---|
| *(none)* | the primary — chooses the set | filled pills |
| `child` | narrows **within** its parent | attached to it, per *Nested tabs* |
| `axis` | cuts **across** everything above | a segmented control, always |

That last row is the point. Depth means containment and nothing else: a row
under another row claims the second lives inside the first. Zones do live inside
a warehouse; condition does not — damaged stock exists in every zone at once. Two
rows that look alike while meaning different things is what makes a stack read as
assembled rather than designed, so an axis is deliberately not a pill.

A child only shows while its parent is active, and builds its tabs from the
parent-filtered queryset. That means a Settings-created second strip such as
Party `Type` under Party `Kind` only shows child tabs that actually have rows
under the active parent tab. If no child value remains, the child strip drops
out. `when` is different: it gates the whole child strip to one parent tab, as
with export types under Exports:

```python
{"param": "export_type", "relation": "child", "when": "export", "sources": [...]}
```

Every strip's key is preserved through a filter submit and a Clear without the
view restating it.

`get_ribbon_tabs()` still returns the **primary** strip and is still the escape
hatch for a strip no source expresses; `get_ribbon_strips()` returns them all.

### Choosing how a nested strip attaches

*Settings → Ribbon → Nested tabs*: **Inline chain** (default), **Nested rail**,
**Tier by weight**. Named for nesting because a single-strip list renders all
three identically — it is not a setting for how tabs look.

The axis control is not one of the choices, on purpose: styling it like a child
would configure away the distinction that keeps three rows readable.

### Saved config shape

`ribbon_config` keeps declared-strip edits, admin-created strips, and
admin-created buttons separately:

```json
{
  "storage.Asset": {
    "strips": [
      {"index": 0, "param": "category", "enabled": false}
    ],
    "extra_strips": [
      {
        "param": "condition",
        "relation": "axis",
        "sources": [
          {"type": "all"},
          {"type": "field", "field": "condition"}
        ]
      }
    ],
    "custom_actions": {
      "asset_list": [
        {
          "id": "custom-inspection",
          "labels": {"en": "Inspection"},
          "icon": "bi bi-clipboard-check",
          "destination": {
            "kind": "modal",
            "route_name": "inspection_modal",
            "url": "/inspections/modal/",
            "permissions": ["storage.add_inspection"]
          },
          "attrs": {
            "data-dynamic-modal": "/inspections/modal/",
            "data-modal-title": "Inspection"
          },
          "permissions": ["storage.add_inspection"]
        }
      ]
    }
  }
}
```

`strips` entries are overlays/removals for what the view declared. Each entry
must name the declared strip by `param` or `index`. `extra_strips` entries are
complete strip configs created in Settings, and each one must carry usable
`sources`. `custom_actions` is grouped by ribbon host route, so two views over
the same model can have different administrator-owned buttons. Developer-defined
actions are listed as locked in the builder; administrators can add, edit, and
remove only their own buttons. Button destinations come from context-free,
permission-described URL views classified as page, form, or modal destinations.

A ribbon button *is* its destination. Two buttons reaching the same endpoint are
the same button however they were declared — a view's own, one dlux supplies, one
an administrator added — and whichever attribute carries it: `data-dynamic-modal`,
dlux's own `data-url`, a composite control's `data-start-url`, a submit button's
`formaction`, or an href. The ribbon draws
the first and drops the rest. That identity (`dest:<endpoint>`) is also what
administrator edits to a code-declared button are keyed by, in
`ribbon_config[<host>].actions`: `enabled: false` removes it, `labels` renames it
per language, `icon` re-glyphs it, and dropping the entry restores it — the same
overlay model the declared tab strips use. A button that is raw `html` has no
destination, so it can be neither deduped nor edited.

The builder gets a class-based host's buttons by asking it — `get_ribbon_actions()`
is where a real view builds them, since which buttons it shows usually depends on
the reader's permissions. That runs the view's own code, so it happens inside a
rolled-back transaction: building a catalog must not change anything. A
function-based host has no instance to ask and declares its buttons on the
function instead:

    reports_overview_view.dlux_ribbon_host = True
    reports_overview_view.dlux_ribbon_actions = _reports_action_specs

    system_backup_page.dlux_ribbon_host = True
    system_backup_page.dlux_ribbon_actions = _backup_action_specs

`dlux_ribbon_actions` is a list of action specs, or a callable taking the request
when the buttons depend on it. Share one list with the view rather than restating
it, so what an administrator renames is the button the page actually draws.

A control that is rendered markup — a start button with its own progress bar and
download link — cannot be described as a label and an icon. Declare a stand-in for
it with `kind: 'html'` and an `attrs` entry naming its endpoint; the builder lists
it for removal and offers no rename, and `_actions.html` renders `html` and nothing
else so those attrs never reach the page. Keep the stand-in out of the list the
view renders: sharing one list puts it ahead of the markup it stands for, and the
duplicate check then drops the markup.

`ribbon_destination_catalog()` walks the route catalog itself, so it applies the
`ribbon_destination` discovery profile and the hidden `dlux` group rule by hand —
the same rules the sidebar and navbar catalogs use, so a view excluded from those
is excluded here too, the usual way (`dlux_exclude = True`, or naming profiles).
Skipping that is what once offered sign-up and session pages, settings
import/export endpoints, and `global_search` — which answers with JSON — as
destinations. Two things do come out of the hidden group: the configurable system
pages, and every dynamic-modal manager whoever registered it. Everything dlux owns
is labelled `System · …` in the picker so it reads apart from a project's own pages.

A function view that answers `{"html": ...}` is a modal endpoint no matter how it
is named or routed, and only it can say so — declare `dlux_modal = True` on it.
Without that it is catalogued as a page, and a button pointing at it navigates to
raw JSON instead of opening a modal.

A view that should stay out of the navigation catalogs but remain a destination
names the profiles it opts out of (`dlux_exclude = ('sidebar', 'navbar', …)`)
rather than using `sidebar_exclude = True`, which means every profile.

The page builds visible strips in this order:

| declared as | an administrator may | use it when |
|---|---|---|
| `ribbon_tabs` | re-dress it, remove it, and append extra strips | almost always |
| `ribbon_tabs_fixed` | re-dress it only | the tabs are part of how the page works |
| *(nothing)* | append extra strips | the split is entirely their call |

`ribbon_tabs` is the one to reach for. What a view declares there is a
**starting point**, not a floor: the page renders it from the first request with
nothing stored, and the builder opens with it under **Pre-defined strips**.

The short name belongs to the adjustable form on purpose. Locking a strip is the
exception, so it is the one that has to be spelled out — a developer reaching for
the obvious name gets the behaviour that is right nearly every time, and
`ribbon_tabs_fixed` reads at the call site as the deliberate choice it is.

```python
class PartyListView(RibbonMixin, ScopedListView):
    ribbon_tabs = {                      # a good default; theirs to dress or remove
        'param': 'kind',
        'sources': [{'type': 'all'}, {'type': 'field', 'field': 'kind'}],
    }

class AuditLogView(RibbonMixin, ListView):
    ribbon_tabs_fixed = {                # the audit tab is permission-gated
        'param': 'category',
        'sources': [{'type': 'field', 'field': 'category', 'exclude': ['audit']}],
    }
```

Use `ribbon_tabs_fixed` when the strip carries a rule — a permission-gated tab,
a split the rest of the view depends on — not merely when you would rather keep
your version. Overriding `get_ribbon_tabs()` locks the model the same way, since
a Settings-created strip drawn against it would be ignored.

For a direct function-based page that builds a `Ribbon` without a model-backed
`RibbonMixin`, mark the callable and pass the route storage key when rendering
custom actions:

```python
def reports_overview_view(request):
    ...

reports_overview_view.dlux_ribbon_host = True

ribbon = build_ribbon(
    request=request,
    title="Reports",
    actions=[...],
    custom_actions_key="route.reports_overview",
    custom_actions_host="reports_overview",
)
```

### Off is a state, not an absence

Removing a pre-defined strip stores `{"enabled": false}` on that declared strip's
entry. This outranks what the view declares — otherwise removing a page-provided
strip would do nothing.

| stored | the page shows |
|---|---|
| nothing | whatever `ribbon_tabs` declares |
| `{"strips": [{"param": "category", "enabled": false}]}` | the declared `category` strip is suppressed |
| `{"extra_strips": [...]}` | the declared strips, followed by those extra strips |

`normalize_ribbon_config` keeps the disabled record even though it has no
sources — the one exception to dropping sourceless strips, because discarding it
would silently restore the strip it was saved to suppress. Restoring a
pre-defined strip deletes that entry, so the page returns to the declaration. A
locked strip ignores removal.

## Administrator settings

*System Settings → Ribbon*. All `layout_config` keys; see
[Reference](reference.md).

**Layout** is the arrangement. **Style** is the look. They are separate settings
so a new skin never has to reason about where the actions sit, and a new
arrangement never has to restate a palette.

| Setting | Values |
|---|---|
| `ribbon_layout` | `default`, `stacked`, `compact` |
| `ribbon_style` | `accent`, `panel`, `flat` |
| `ribbon_title` | on (default) / off — **decided by** `compact` |
| `ribbon_advanced_trigger` | `button` (default), `always`, `off` |

Where the actions sit is the layout's decision alone — title row for `default`,
below the filters for `stacked`, inline for `compact` — so there is no separate
setting for it.

A layout can also answer another setting outright: `compact` is a single row, so
it has no title. That setting is greyed out in the Ribbon step by
`ribbon/js/ribbon_settings.js` rather than hidden, so the reader can see what
the layout decided. A disabled input is not submitted, so the stored value
survives untouched and returns when a layout that uses it is chosen again — the
server enforces the same rule through `Ribbon.shows_title`, so the behaviour does
not depend on the script running.

## Layouts

`default` is the standard list header, and it emits the **same markup as the
list header it generalises** — `header-row` / `heading` / `actions` above a
`dlux-ribbon-filter` block whose form is the familiar
`py-3 row g-2 no-print m-0 dlux-form dlux-filter` crispy grid: fields as
`form-group col-auto` (the search one `flex-fill`), then
`col-sm-12 col-md-2 col-lg-auto` for the pill chip controls and
`col-sm-12 col-md-3 col-lg-auto` for the advanced toggle, with the advanced
fields as `col-auto flex-fill` inside a `collapse m-0`.

That is deliberate, not incidental: the form keeps the `dlux-filter` class
because `form_fields.css` **and all seven themes** style filter rows through it.
Sharing the class means a page moving to the ribbon renders identically under
every theme, with no per-theme selector to duplicate. The ribbon's own script
keys off `data-dlux-ribbon-autosubmit` and the helper's off
`data-dlux-filter-autosubmit`, so the two can coexist on a page without
double-submitting.

The one class the ribbon must **not** borrow is `dlux-filter-toggle`: the
helper's script binds advanced-panel state to it, so sharing it would leave two
scripts restoring one panel from two different `localStorage` keys. The ribbon
uses `dlux-ribbon-toggle` and carries the three pressed-state rules itself.

`stacked` moves the actions to their own row under the filters, for a list with
more actions than fit beside a title. `compact` pulls everything into one row:
no title, and the actions become the last column of the filter row.

Each renders from `_<layout>.html` and carries `dlux-ribbon-layout-<layout>`.

## Styles

The style is a skin class on the root, `dlux-ribbon-skin-<style>`, and it only
ever sets chrome — padding, border, radius, background, heading weight. Every
style works with every layout.

| Style | Look |
|---|---|
| `accent` | A coloured edge down the side of a bordered header (the default; unchanged). |
| `panel` | A softly rounded, raised panel. |
| `flat` | No panel at all: a single dividing rule under the band, for pages where the list should lead. |

The panel skin also carries `glass-profile` (a dlux-wide class name, not the skin's label), and every layout carries
`data-dlux-card-surface`. Both are existing dlux chrome hooks, not decoration:
all seven themes restyle `.glass-profile`, so the dark themes replace the panel
surface with their own rather than tinting a light one, and
`base/css/card_edges.css` keys off `data-dlux-card-surface`, so the **Card edges**
setting reaches the ribbon at every style. The skins set their radius from
`--dlux-card-edge-radius` with their designed value as the fallback, so `curved`
keeps each skin's own corners and `normal` flattens them all to the standard
radius.

Adding a fourth is a block of CSS under a new `dlux-ribbon-skin-*` class plus a
choice in `RIBBON_STYLE_CHOICES` and a matching `option_meta` entry — no
template and no Python branch.

## Files

```
dlux/ribbon/                       build.py (derivation), mixin.py, spec.py
dlux/templates/dlux/ribbon/        ribbon.html + one template per style
dlux/static/dlux/ribbon/{css,js}   layout, and autosubmit + panel-state memory
```

Every style fills the same four regions — title, actions, primary filters,
advanced panel — so **a new style is a template, not a branch in Python**.
Individual fields render through crispy, so widgets, choice translation and
error display are unchanged.

The ribbon's JS hooks (`form.dlux-ribbon[data-dlux-ribbon-autosubmit]`,
`button.dlux-ribbon-toggle`) are deliberately distinct from the old helper's
(`form.dlux-filter[data-dlux-filter-autosubmit]`, `button.dlux-filter-toggle`)
so both scripts can be on one page during migration without a select change
submitting the form twice.
