# Template and Form Customization

Project template extensions belong under `templates/dlux/includes/`:

- `custom_head.html` for additional head markup;
- `custom_scripts.html` for project scripts; and
- `custom_footer.html` for the global footer content.

These are extension points, not replacements for `dlux/base.html` assets. Avoid duplicating the framework form asset partials: `dlux/base.html` loads them once for dynamic-modal forms.

## Page bases

Use `dlux/form_base.html` for a full-page form and `dlux/list_base.html` for a list/filter surface. Both extend `dlux/base.html` and load the supported assets.

For a submit rail outside a form, use the opt-in `form_content` and `form_footer` blocks and associate footer buttons through the HTML `form` attribute:

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

The footer is page-local at desktop width and returns to normal flow below 768px. Existing templates that override `content` remain compatible.

## Forms and filters

Use `DluxFileInput` or `AssetPickerField` for files, not a raw file input. The shared base already wires the file, scan-link, double-submit, and form styles. For filters, see [UI Integration](ui-integration.md#tables-filters-and-row-actions).

If a page must combine list and form behavior, extend one base and include only the complementary asset partial it genuinely needs. Use `{% include_once %}` when a reusable partial may be included from multiple paths.

## Public root and layout behavior

Anonymous public-root presentation is configured in System Settings: its theme, title, description, sidebar, and titlebar are category-owned controls beneath the public-homepage configuration. Do not hand-code a second public root chrome; the shared context flags drive the normal base template.

Use logical CSS properties and framework classes so layout mirrors in RTL. In particular, do not position title actions, back links, or rails with physical left/right assumptions. See [Translations](translation-guide.md) for validation.

## Assisted entry

Autofill and sticky forms are separate user preferences. Read them through `sticky_forms_enabled()` and `sticky_form_initial()` rather than the retired cookie-based `enable_prefill` switch. Password inputs need a preceding username autocomplete field in the DOM to prevent browsers from filling unrelated titlebar controls with saved credentials.
