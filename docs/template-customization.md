# Template and Form Customization

Project template extensions belong under `templates/dlux/includes/`:

- `custom_head.html` for additional head markup;
- `custom_scripts.html` for project scripts; and
- `custom_footer.html` for the global footer content.

These are extension points, not replacements for `dlux/base.html` assets. Avoid
duplicating the framework form asset partials: `dlux/base.html` loads them once
for dynamic-modal forms.

## Page bases

Use `dlux/form_base.html` for a full-page form and `dlux/list_base.html` for a
list/filter surface. Both extend `dlux/base.html` and load the supported assets.

For a submit rail outside a form, use the opt-in `form_content` and `form_footer`
blocks and associate footer buttons through the HTML `form` attribute:

```django
{% extends "dlux/form_base.html" %}

{% block form_content %}
<form id="invoice-form" method="post">
    {% csrf_token %}
    {% crispy form %}
</form>
{% endblock %}

{% block form_footer %}
<footer class="dlux-form-footer">
    <button type="submit" form="invoice-form" class="dlux-form-action dlux-form-action-primary">Save</button>
</footer>
{% endblock %}
```

The footer is page-local at desktop width and returns to normal flow below 768px.
Existing templates that override `content` remain compatible.

Place page-specific Bootstrap modals in `dlux/base.html`'s `page_modals` block,
preserving `{{ block.super }}`. It renders directly under `body`, outside content
containers whose containment, transforms or stacking contexts can trap a modal
below Bootstrap's backdrop. Backup Details uses this block while retaining the
backup page's layout containment and inner scrolling.

## Forms and filters

Use `DluxFileInput` or `AssetPickerField` for files, not a raw file input. The
shared base already wires the file, scan-link, double-submit, and form styles.
For a ForeignKey with more rows than a dropdown should hold, use a
[search-and-add field](ui-integration.md#search-and-add-fields). For filters, see
[UI Integration](ui-integration.md#tables-filters-and-row-actions).

If a page must combine list and form behavior, extend one base and include only
the complementary asset partial it genuinely needs. Use `{% include_once %}` when
a reusable partial may be included from multiple paths.

Password inputs need a preceding username autocomplete field in the DOM to
prevent browsers from filling unrelated titlebar controls with saved credentials.

## Public Page And Layout Behavior

Anonymous public page presentation is configured in System Settings: its theme,
title, description, sidebar, and titlebar are category-owned controls beneath the
public-homepage configuration. Do not hand-code a second public page chrome; the
shared context flags drive the normal base template.

Use logical CSS properties and framework classes so layout mirrors in RTL. In
particular, do not position title actions, back links, or rails with physical
left/right assumptions. See [Translations](translation-guide.md) for validation.

Component templates require no theme-specific markup. Mono, for example, supplies
its column-builder control surfaces in `mono.css`, including hover and
keyboard-focus states. Disclosure controls retain link styling without a rounded
button border.

## Assisted entry

Two independent aids for repetitive data entry, each a user preference:

| Preference | Default | Behaviour |
| --- | --- | --- |
| `autofill_from_related` | on | Choosing a ForeignKey copies that record's matching-named fields into the form. Reacts only to a deliberate selection. |
| `sticky_forms` | off | A new form starts pre-filled from the last record the user created. Off by default because it changes a form nobody touched. |

Neither feature gates the other. Only sticky forms gets an inline switch, on the
forms that support it; filling from a related record reacts to a deliberate
selection and is configured from Options alone. Turning sticky off clears the
remembered record id.

The cookie-based `enable_prefill` switch is removed (see
[Deprecation Countdown](deprecation-countdown.md#removed-in-v180)); read the
preference through the helpers below instead.

### How a form opts in

A form advertises what it supports:

- **Fill from related** — FK selects carrying `data-autofill-source`, which
  `resolve_form_class_for_model` adds automatically.
- **Sticky forms** — `data-model-name` + `data-app-label` on the `<form>`. The
  dynamic modal emits them on **create** forms only, since pre-filling an existing
  record from a different one would be data loss. A project rendering its own form
  templates must emit them itself for sticky forms to apply there; the attributed
  `<form>` may be the root element the modal inserts.

Forms that support sticky forms get a thin `dlux-assist-bar` at the top, with the
switch at its end. That switch is the shared `dlux-settings-toggle-field` control
— `helpers/toggle/css/main.css` (loaded on every page) and the themes style it by
those exact class names, so JS building it must use them and `type="checkbox"`, or
it renders as a bare browser checkbox. With the [entry clipboard](entry-clipboard.md)
enabled, its popover button shares this row.

### Server-side sticky prefill

Sticky prefill is a **server-side** concern when the initial data has to be in
the form before it renders, so dlux owns the gate rather than a cookie:

```python
from dlux.utils import sticky_forms_enabled, sticky_form_initial

# either read the gate directly...
if request.method == 'GET' and sticky_forms_enabled(request):
    ...

# ...or let dlux build the initial dict
initial = sticky_form_initial(request, Decree, {
    'category': 'category',
    'number': lambda last: increment_number(last.number),
})
form = DecreeForm(initial=initial, request=request)
```

`sticky_form_initial(request, model, fields, *, order_by='-pk', transform=None)`
maps each form field to a model attribute name or a callable taking the last
record — the first row of the model's default manager in `order_by` order.
`transform(initial, last)` can post-process the whole dict. It returns `{}` when
the preference is off, on a POST, or when the model has no rows, so a call site
never has to branch.

A form that calculates its own sticky initial values must set
`dlux_sticky_server = True` on the form class. The shared dynamic-modal form then
emits `data-sticky-server` alongside `data-app-label`/`data-model-name`;
handwritten templates must emit it themselves. This preserves server
transformations such as an incremented reference number and bound validation
input, instead of copying the old number back from the last-entry API: Dlux skips
its own client-side fill on such a form. Keep the declaration even when sticky
entry is switched off or the form is bound after a validation error — the server
owns both the blank defaults and submitted values.

Flipping the switch on a `data-sticky-server` form saves the preference and then
reloads, since only a reload can apply or undo work that happened before render;
Save and add more reopens a fresh GET form.
