import json

from django import template
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

from dlux.translations import get_strings
from dlux.utils import (
    SENSITIVE_ACTIVITY_MASK,
    is_sensitive_activity_field_name,
    translate_activity_log_model_name,
)

register = template.Library()

from dlux.middleware import get_current_request

@register.filter
def translate_log(value, prefix=''):
    """
    Translates a log value (action, model_name) using the dlux translation system.
    Usage: {{ log.action|translate_log:'action' }} -> looks for 'action_LOGIN' (lowercase)
    Usage: {{ log.model_name|translate_log:'model' }} -> looks for 'model_user' (lowercase)
    """
    if not value:
        return ""
        
    request = get_current_request()
    dlux_strings = get_strings()
        
    if prefix == 'model':
        return translate_activity_log_model_name(value, strings=dlux_strings)

    # Construct key: e.g. 'action_login'
    key = f"{prefix}_{str(value).lower()}" if prefix else str(value).lower()
    
    # Look up
    return dlux_strings.get(key, value)

@register.simple_tag
def format_log_details(details):
    """
    Format the details JSON into a readable HTML string.
    """
    if not details or not isinstance(details, dict):
        return ""

    dlux_strings = get_strings()
    html_parts = []

    # Check for specific types
    if 'filename' in details:
        # Download/Export
        fname = details.get('filename')
        count = details.get('count', 1)
        html_parts.append(format_html(
            '<i class="bi bi-file-earmark-arrow-down me-1"></i> {} <span class="badge bg-light text-dark ms-1">{} {}</span>',
            fname,
            count,
            dlux_strings.get('label_items', 'items'),
        ))
    else:
        # Update Diffs
        for field, changes in details.items():
            field_label = _format_detail_label(field)

            if isinstance(changes, dict) and 'old' in changes and 'new' in changes:
                old_val = _prepare_log_value(field, changes['old'])
                new_val = _prepare_log_value(field, changes['new'])

                # Truncate long values
                if old_val and len(str(old_val)) > 20: old_val = str(old_val)[:20] + "..."
                if new_val and len(str(new_val)) > 20: new_val = str(new_val)[:20] + "..."

                if not old_val:
                    # Set
                    html_parts.append(format_html(
                        '<span class="badge bg-success me-1 text-white">{}: {}</span>',
                        field_label,
                        new_val,
                    ))
                elif not new_val:
                    # Unset
                    html_parts.append(format_html(
                        '<span class="badge bg-danger me-1 text-white">{}: {} <i class="bi bi-x"></i></span>',
                        field_label,
                        old_val,
                    ))
                else:
                    # Change
                    html_parts.append(format_html(
                        '<span class="badge bg-light text-dark border me-1">{}: <span class="text-secondary">{}</span> <i class="bi bi-arrow-right mx-1"></i> <strong>{}</strong></span>',
                        field_label,
                        old_val,
                        new_val,
                    ))
            else:
                # Generic key-value
                html_parts.append(format_html(
                    '<span class="badge bg-secondary me-1">{}: {}</span>',
                    field_label,
                    _prepare_log_value(field, changes),
                ))

    return mark_safe("".join(str(part) for part in html_parts))


def _format_detail_label(field_name):
    return str(field_name).replace("_", " ").strip() or str(field_name)


def _prepare_log_value(field_name, value):
    if is_sensitive_activity_field_name(field_name):
        return SENSITIVE_ACTIVITY_MASK
    if value is None or value == "":
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _render_detail_value(kind, label, value):
    return format_html(
        '<div class="dlux-log-detail-value dlux-log-detail-value--{}">'
        '<div class="dlux-log-detail-value-label">{}</div>'
        '<div class="dlux-log-detail-value-body">{}</div>'
        '</div>',
        kind,
        label,
        escape(value),
    )


@register.simple_tag
def render_log_details_panel(details):
    """Render a structured activity-log details panel for the detail modal."""
    if not details or not isinstance(details, dict):
        return ""

    dlux_strings = get_strings()
    items = []

    if 'filename' in details:
        filename = _prepare_log_value('filename', details.get('filename'))
        count = details.get('count', 1)
        values_html = _render_detail_value(
            'single',
            dlux_strings.get('label_file', 'File'),
            filename,
        )
        if count is not None:
            values_html += _render_detail_value(
                'single',
                dlux_strings.get('label_count', 'Count'),
                str(count),
            )
        items.append(format_html(
            '<div class="dlux-log-detail-item">'
            '<div class="dlux-log-detail-head">'
            '<div class="dlux-log-detail-field">{}</div>'
            '<span class="dlux-log-detail-status is-info"><i class="bi bi-info-circle"></i>{}</span>'
            '</div>'
            '<div class="dlux-log-detail-values">{}</div>'
            '</div>',
            dlux_strings.get('label_download', 'Download'),
            dlux_strings.get('log_change_info', 'Info'),
            mark_safe(values_html),
        ))
    else:
        for field, changes in details.items():
            field_label = _format_detail_label(field)

            if isinstance(changes, dict) and 'old' in changes and 'new' in changes:
                old_val = _prepare_log_value(field, changes.get('old'))
                new_val = _prepare_log_value(field, changes.get('new'))

                if old_val and not new_val:
                    status_label = dlux_strings.get('log_change_cleared', 'Cleared')
                    status_class = 'is-cleared'
                    status_icon = 'bi-dash-circle'
                    values_html = _render_detail_value(
                        'old',
                        dlux_strings.get('label_previous_value', 'Previous Value'),
                        old_val,
                    )
                elif new_val and not old_val:
                    status_label = dlux_strings.get('log_change_set', 'Set')
                    status_class = 'is-set'
                    status_icon = 'bi-plus-circle'
                    values_html = _render_detail_value(
                        'new',
                        dlux_strings.get('label_new_value', 'New Value'),
                        new_val,
                    )
                else:
                    status_label = dlux_strings.get('log_change_changed', 'Changed')
                    status_class = 'is-changed'
                    status_icon = 'bi-arrow-left-right'
                    values_html = (
                        _render_detail_value(
                            'old',
                            dlux_strings.get('label_previous_value', 'Previous Value'),
                            old_val or dlux_strings.get('log_value_empty', 'Empty'),
                        )
                        + _render_detail_value(
                            'new',
                            dlux_strings.get('label_new_value', 'New Value'),
                            new_val or dlux_strings.get('log_value_empty', 'Empty'),
                        )
                    )
            else:
                status_label = dlux_strings.get('log_change_info', 'Info')
                status_class = 'is-info'
                status_icon = 'bi-info-circle'
                values_html = _render_detail_value(
                    'single',
                    dlux_strings.get('label_value', 'Value'),
                    _prepare_log_value(field, changes) or dlux_strings.get('log_value_empty', 'Empty'),
                )

            items.append(format_html(
                '<div class="dlux-log-detail-item">'
                '<div class="dlux-log-detail-head">'
                '<div class="dlux-log-detail-field">{}</div>'
                '<span class="dlux-log-detail-status {}"><i class="bi {}"></i>{}</span>'
                '</div>'
                '<div class="dlux-log-detail-values">{}</div>'
                '</div>',
                field_label,
                status_class,
                status_icon,
                status_label,
                mark_safe(values_html),
            ))

    return mark_safe('<div class="dlux-log-details">{}</div>'.format("".join(str(item) for item in items)))
