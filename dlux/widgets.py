from django import forms
from django.forms import widgets
from django.forms.utils import flatatt
from django.utils.html import conditional_escape, format_html
from django.utils.safestring import mark_safe


class DluxFileInput(forms.ClearableFileInput):
    template_name = 'dlux/forms/file_input.html'

    def __init__(self, attrs=None, *, field_label='', show_scan=False):
        self.field_label = field_label
        self.show_scan = show_scan
        widget_attrs = dict(attrs or {})
        existing_class = str(widget_attrs.get('class', '') or '').strip()
        widget_attrs['class'] = f"{existing_class} archive-file-input".strip()
        super().__init__(attrs=widget_attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        data = context['widget']
        try:
            from .translations import get_strings
            strings = get_strings()
        except Exception:
            strings = {}
        data['field_label'] = self.field_label
        # A caller asking for a scan button only gets one where the deployment
        # has turned ScanLink on; otherwise the button is the thing that fires
        # the localhost probe.
        from .utils import scanlink_enabled
        data['show_scan'] = bool(self.show_scan and scanlink_enabled())
        data['empty_title'] = strings.get('archive_file_empty_title', 'No file selected')
        data['empty_meta'] = strings.get('archive_file_empty_meta', 'Drop a file here or use the actions.')
        data['current_meta'] = strings.get('archive_file_current_meta', 'Current file on this record.')
        data['selected_meta'] = strings.get('archive_file_selected_meta', 'Ready to save with this form.')
        data['too_large_template'] = strings.get('archive_file_too_large', 'File exceeds the maximum allowed size ({limit} MB).')
        data['open_action'] = strings.get('archive_file_open_action', 'Open file')
        data['upload_action'] = strings.get('archive_file_upload_action', 'Upload file')
        data['clear_action'] = strings.get('archive_file_clear_action', 'Clear file')
        if value and hasattr(value, 'url'):
            data['file_url'] = value.url
            data['display_name'] = getattr(value, 'name', '').split('/')[-1] or str(value)
            display_name = data['display_name'].lower()
            if display_name.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico')):
                data['icon_class'] = 'bi bi-file-earmark-image-fill'
            else:
                data['icon_class'] = 'bi bi-file-earmark-fill'
        else:
            data['file_url'] = ''
            data['display_name'] = ''
            data['icon_class'] = 'bi bi-file-earmark-arrow-up-fill'
        return context


class _DluxSelectorMixin:
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
        disabled_values=(),
    ):
        self.selector_variant = variant or 'card'
        self.disabled_values = {str(value) for value in (disabled_values or ())}
        self.option_meta = {
            str(key): dict(value or {})
            for key, value in (option_meta or {}).items()
        }
        self.searchable = bool(searchable)
        self.search_placeholder = str(search_placeholder or '').strip()
        super().__init__(attrs=attrs, choices=choices)

    def create_option(self, *args, **kwargs):
        option = super().create_option(*args, **kwargs)
        value = str(option.get('value'))
        option['meta'] = self.option_meta.get(value, {})
        if value in self.disabled_values:
            option['attrs'] = {**(option.get('attrs') or {}), 'disabled': True}
        return option

    def render(self, name, value, attrs=None, renderer=None):
        value = self.format_value(value)
        final_attrs = self.build_attrs(self.attrs, attrs)
        container_classes = [
            'dlux-choice-selector',
            f'dlux-choice-selector--{self.selector_variant}',
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
            'data-dlux-selector': 'true',
            'data-dlux-selector-variant': self.selector_variant,
        }
        if self.searchable:
            container_attrs['data-dlux-selector-searchable'] = 'true'
        if final_attrs.get('id'):
            container_attrs['id'] = final_attrs['id']

        output = [format_html('<div{}>', flatatt(container_attrs))]

        if self.searchable:
            output.append(
                format_html(
                    (
                        '<div class="dlux-choice-selector__search">'
                        '<input type="search" class="form-control glass-input" '
                        'placeholder="{}" data-dlux-selector-search>'
                        '</div>'
                    ),
                    self.search_placeholder or 'Search',
                )
            )

        output.append(mark_safe('<div class="dlux-choice-selector__options" data-dlux-selector-options>'))
        for group_name, group_options, _index in self.optgroups(name, value, final_attrs):
            if group_name:
                output.append(
                    format_html(
                        '<div class="dlux-choice-selector__group-label">{}</div>',
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
        option_attrs['class'] = 'dlux-choice-option__input'
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
            'dlux-choice-option',
            f'dlux-choice-option--{self.selector_variant}',
        ]
        if option_attrs.get('disabled'):
            option_classes.append('is-disabled')

        indicator = ''
        preview_class = str(meta.get('preview_class') or '').strip()
        if preview_class:
            indicator = format_html(
                '<span class="dlux-choice-option__swatch {}"></span>',
                preview_class,
            )
        elif meta.get('icon'):
            indicator = format_html(
                '<span class="dlux-choice-option__icon"><i class="bi {}"></i></span>',
                meta.get('icon'),
            )

        meta_lines = []
        if description:
            meta_lines.append(format_html('<span class="dlux-choice-option__meta">{}</span>', description))
        if secondary:
            meta_lines.append(format_html('<span class="dlux-choice-option__meta dlux-choice-option__meta--secondary">{}</span>', secondary))

        return format_html(
            (
                '<label class="{}" data-dlux-selector-option data-dlux-selector-text="{}">'
                '<input{}>'
                '<span class="dlux-choice-option__surface">{}'
                '<span class="dlux-choice-option__copy">'
                '<span class="dlux-choice-option__label">{}</span>{}'
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
        option_attrs['class'] = 'dlux-choice-option__input'
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
            'dlux-choice-option',
            'dlux-choice-option--toggle',
        ]
        if option_attrs.get('disabled'):
            option_classes.append('is-disabled')

        surface_classes = [
            'lang-option',
            'dlux-choice-option__surface',
            'dlux-choice-option__surface--toggle',
        ]
        if option.get('selected'):
            surface_classes.append('lang-active')

        surface_bits = []
        if meta.get('icon'):
            surface_bits.append(
                format_html(
                    '<span class="dlux-choice-option__icon"><i class="bi {}"></i></span>',
                    meta.get('icon'),
                )
            )
        if surface_label:
            surface_bits.append(
                format_html(
                    '<span class="dlux-choice-toggle__surface-label">{}</span>',
                    surface_label,
                )
            )
        if not surface_bits:
            surface_bits.append(
                format_html(
                    '<span class="dlux-choice-toggle__surface-label">{}</span>',
                    label,
                )
            )

        caption_bits = [
            format_html('<span class="dlux-choice-toggle__caption-label">{}</span>', label),
        ]
        if description:
            caption_bits.append(
                format_html('<span class="dlux-choice-toggle__caption-meta">{}</span>', description)
            )
        if secondary:
            caption_bits.append(
                format_html('<span class="dlux-choice-toggle__caption-meta">{}</span>', secondary)
            )

        return format_html(
            (
                '<label class="{}" data-dlux-selector-option data-dlux-selector-text="{}">'
                '<input{}>'
                '<span class="dlux-choice-toggle">'
                '<span class="{}" data-dlux-selector-surface>'
                '<span class="dlux-choice-toggle__surface-content">{}</span>'
                '</span>'
                '<span class="dlux-choice-toggle__caption">{}</span>'
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


class DluxChoiceSelectorWidget(_DluxSelectorMixin, widgets.ChoiceWidget):
    input_type = 'radio'
    allow_multiple_selected = False
    use_fieldset = False


class DluxMultipleChoiceSelectorWidget(_DluxSelectorMixin, widgets.ChoiceWidget):
    input_type = 'checkbox'
    allow_multiple_selected = True
    use_fieldset = False
