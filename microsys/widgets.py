from django import forms
from django.forms import widgets
from django.forms.utils import flatatt
from django.utils.html import conditional_escape, format_html
from django.utils.safestring import mark_safe


class _MicrosysSelectorMixin:
    selector_variant = 'card'
    searchable = False
    search_placeholder = ''

    def __init__(
        self,
        attrs=None,
        choices=(),
        *,
        variant='card',
        option_meta=None,
        searchable=False,
        search_placeholder='',
    ):
        self.selector_variant = variant or 'card'
        self.option_meta = {
            str(key): dict(value or {})
            for key, value in (option_meta or {}).items()
        }
        self.searchable = bool(searchable)
        self.search_placeholder = str(search_placeholder or '').strip()
        super().__init__(attrs=attrs, choices=choices)

    def create_option(self, *args, **kwargs):
        option = super().create_option(*args, **kwargs)
        option['meta'] = self.option_meta.get(str(option.get('value')), {})
        return option

    def render(self, name, value, attrs=None, renderer=None):
        value = self.format_value(value)
        final_attrs = self.build_attrs(self.attrs, attrs)
        container_classes = [
            'ms-choice-selector',
            f'ms-choice-selector--{self.selector_variant}',
        ]
        extra_class = str(final_attrs.pop('class', '') or '').strip()
        if extra_class:
            filtered_classes = [
                css_class
                for css_class in extra_class.split()
                if css_class not in {'form-control', 'form-select'}
            ]
            if filtered_classes:
                container_classes.extend(filtered_classes)
        if self.searchable:
            container_classes.append('is-searchable')

        container_attrs = {
            'class': ' '.join(container_classes),
            'data-ms-selector': 'true',
            'data-ms-selector-variant': self.selector_variant,
        }
        if self.searchable:
            container_attrs['data-ms-selector-searchable'] = 'true'
        if final_attrs.get('id'):
            container_attrs['id'] = final_attrs['id']

        output = [format_html('<div{}>', flatatt(container_attrs))]

        if self.searchable:
            output.append(
                format_html(
                    (
                        '<div class="ms-choice-selector__search">'
                        '<input type="search" class="form-control glass-input" '
                        'placeholder="{}" data-ms-selector-search>'
                        '</div>'
                    ),
                    self.search_placeholder or 'Search',
                )
            )

        output.append(mark_safe('<div class="ms-choice-selector__options" data-ms-selector-options>'))
        for group_name, group_options, _index in self.optgroups(name, value, final_attrs):
            if group_name:
                output.append(
                    format_html(
                        '<div class="ms-choice-selector__group-label">{}</div>',
                        group_name,
                    )
                )
            for option in group_options:
                output.append(self._render_option(option))
        output.append(mark_safe('</div></div>'))
        return mark_safe(''.join(str(part) for part in output))

    def _render_option(self, option):
        if self.selector_variant == 'toggle':
            return self._render_toggle_option(option)

        option_attrs = dict(option.get('attrs') or {})
        option_attrs['class'] = 'ms-choice-option__input'
        option_attrs['type'] = self.input_type
        option_attrs['name'] = option.get('name')
        option_attrs['value'] = option.get('value')

        meta = option.get('meta') or {}
        label = conditional_escape(option.get('label') or option.get('value') or '')
        description = conditional_escape(meta.get('description') or '')
        secondary = conditional_escape(meta.get('secondary') or '')
        search_text = ' '.join(
            part
            for part in [
                str(option.get('label') or ''),
                str(meta.get('description') or ''),
                str(meta.get('secondary') or ''),
                str(meta.get('search_text') or ''),
                str(option.get('value') or ''),
            ]
            if part
        ).strip()

        option_classes = [
            'ms-choice-option',
            f'ms-choice-option--{self.selector_variant}',
        ]
        if option_attrs.get('disabled'):
            option_classes.append('is-disabled')

        indicator = ''
        preview_class = str(meta.get('preview_class') or '').strip()
        if preview_class:
            indicator = format_html(
                '<span class="ms-choice-option__swatch {}"></span>',
                preview_class,
            )
        elif meta.get('icon'):
            indicator = format_html(
                '<span class="ms-choice-option__icon"><i class="bi {}"></i></span>',
                meta.get('icon'),
            )

        meta_lines = []
        if description:
            meta_lines.append(format_html('<span class="ms-choice-option__meta">{}</span>', description))
        if secondary:
            meta_lines.append(format_html('<span class="ms-choice-option__meta ms-choice-option__meta--secondary">{}</span>', secondary))

        return format_html(
            (
                '<label class="{}" data-ms-selector-option data-ms-selector-text="{}">'
                '<input{}>'
                '<span class="ms-choice-option__surface">{}'
                '<span class="ms-choice-option__copy">'
                '<span class="ms-choice-option__label">{}</span>{}'
                '</span>'
                '</span>'
                '</label>'
            ),
            ' '.join(option_classes),
            search_text,
            flatatt(option_attrs),
            mark_safe(str(indicator)),
            label,
            mark_safe(''.join(str(line) for line in meta_lines)),
        )

    def _render_toggle_option(self, option):
        option_attrs = dict(option.get('attrs') or {})
        option_attrs['class'] = 'ms-choice-option__input'
        option_attrs['type'] = self.input_type
        option_attrs['name'] = option.get('name')
        option_attrs['value'] = option.get('value')

        meta = option.get('meta') or {}
        label_text = option.get('label') or option.get('value') or ''
        label = conditional_escape(label_text)
        description = conditional_escape(meta.get('description') or '')
        secondary = conditional_escape(meta.get('secondary') or '')
        surface_label = conditional_escape(meta.get('surface_label') or '')
        search_text = ' '.join(
            part
            for part in [
                str(label_text or ''),
                str(meta.get('description') or ''),
                str(meta.get('secondary') or ''),
                str(meta.get('search_text') or ''),
                str(option.get('value') or ''),
            ]
            if part
        ).strip()

        option_classes = [
            'ms-choice-option',
            'ms-choice-option--toggle',
        ]
        if option_attrs.get('disabled'):
            option_classes.append('is-disabled')

        surface_classes = [
            'lang-option',
            'ms-choice-option__surface',
            'ms-choice-option__surface--toggle',
            'rounded',
            'border',
            'shadow-sm',
            'p-2',
            'mb-1',
        ]
        if option.get('selected'):
            surface_classes.append('lang-active')

        surface_bits = []
        if meta.get('icon'):
            surface_bits.append(
                format_html(
                    '<span class="ms-choice-option__icon"><i class="bi {}"></i></span>',
                    meta.get('icon'),
                )
            )
        if surface_label:
            surface_bits.append(
                format_html(
                    '<span class="ms-choice-toggle__surface-label">{}</span>',
                    surface_label,
                )
            )
        if not surface_bits:
            surface_bits.append(
                format_html(
                    '<span class="ms-choice-toggle__surface-label">{}</span>',
                    label,
                )
            )

        caption_bits = [
            format_html('<span class="ms-choice-toggle__caption-label">{}</span>', label),
        ]
        if description:
            caption_bits.append(
                format_html('<span class="ms-choice-toggle__caption-meta">{}</span>', description)
            )
        if secondary:
            caption_bits.append(
                format_html('<span class="ms-choice-toggle__caption-meta">{}</span>', secondary)
            )

        return format_html(
            (
                '<label class="{}" data-ms-selector-option data-ms-selector-text="{}">'
                '<input{}>'
                '<span class="ms-choice-toggle">'
                '<span class="{}" data-ms-selector-surface>'
                '<span class="ms-choice-toggle__surface-content">{}</span>'
                '</span>'
                '<span class="ms-choice-toggle__caption">{}</span>'
                '</span>'
                '</label>'
            ),
            ' '.join(option_classes),
            search_text,
            flatatt(option_attrs),
            ' '.join(surface_classes),
            mark_safe(''.join(str(bit) for bit in surface_bits)),
            mark_safe(''.join(str(bit) for bit in caption_bits)),
        )


class MicrosysChoiceSelectorWidget(_MicrosysSelectorMixin, widgets.ChoiceWidget):
    input_type = 'radio'
    allow_multiple_selected = False
    use_fieldset = False


class MicrosysMultipleChoiceSelectorWidget(_MicrosysSelectorMixin, widgets.ChoiceWidget):
    input_type = 'checkbox'
    allow_multiple_selected = True
    use_fieldset = False
