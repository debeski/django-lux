"""OCR's Extra Features controls and save policy (``extra_config['ocr']``)."""

from crispy_forms.layout import Div, Field, HTML, Row
from django.urls import reverse
from django.utils.html import escape

from ..ocr import CONFIG_KEY, MODES, normalize_ocr_config
from ..system.constants import SETUP_STEP_EXTRAS
from ..widgets import DluxChoiceSelectorWidget
from .builders import _bind_choice_selector_widget, build_settings_toggle_field

FIELDS = ('enabled', 'auto_on_save', 'search', 'mode', 'service_url', 'timeout', 'max_file_mb', 'threads')
MODE_ICONS = {'auto': 'bi-layers-half', 'ocr': 'bi-eye'}
LABELS = {
    'enabled': ('form_sys_ocr_enabled', 'Enable OCR'),
    'auto_on_save': ('form_sys_ocr_auto_on_save', 'Read new and replaced files automatically'),
    'search': ('form_sys_ocr_search', 'Include extracted text in search'),
    'mode': ('form_sys_ocr_mode', 'Reading mode'),
    'service_url': ('form_sys_ocr_service_url', 'OCR service address'),
    'timeout': ('form_sys_ocr_timeout', 'Time limit per file (seconds)'),
    'max_file_mb': ('form_sys_ocr_max_file_mb', 'Largest file (MB)'),
    'threads': ('form_sys_ocr_threads', 'CPU threads per file'),
}
MODE_LABELS = {
    'auto': ('ocr_mode_auto', 'Use the PDF text layer when sound, OCR the rest'),
    'ocr': ('ocr_mode_ocr', 'Always OCR every page'),
}


def configure_ocr_fields(form, strings):
    config = normalize_ocr_config((form.instance.extra_config or {}).get(CONFIG_KEY))
    active_step = not form.single_step_mode or form.single_step_index == SETUP_STEP_EXTRAS
    for key in FIELDS:
        form.initial['ocr_' + key] = config[key]
        field = form.fields['ocr_' + key]
        field.label = strings.get(*LABELS[key])
        field.disabled = not active_step
    choices = [(mode, strings.get(*MODE_LABELS[mode])) for mode in MODES]
    form.fields['ocr_mode'].choices = choices
    _bind_choice_selector_widget(
        form.fields['ocr_mode'],
        DluxChoiceSelectorWidget(choices=choices, variant='toggle', option_meta={k: {'icon': v} for k, v in MODE_ICONS.items()}),
    )
    form.fields['ocr_enabled'].help_text = strings.get(
        'help_sys_ocr_enabled',
        "Reads the text of registered document files with the stack's ocr service. Start or stop that service from the Operations panel.",
    )
    form.fields['ocr_threads'].help_text = strings.get('help_sys_ocr_threads', 'CPU threads used for each file.')


def _service_status(strings):
    from ..ocr.client import service_health

    health = service_health()
    if health:
        text = strings.get('ocr_service_connected', 'Service connected: {engine} {version}').format(
            engine=health.get('engine', ''), version=health.get('engine_version', ''))
        css = 'text-success'
    else:
        text = strings.get('ocr_service_unreachable', 'The OCR service does not answer at the configured address.')
        css = 'text-warning-emphasis'
    return f"<p class='small {css} mb-2' role='status'>{escape(text)}</p>"


def ocr_settings_layout(form, strings):
    panel_url = reverse('dlux_operations_panel')
    status = _service_status(strings) if normalize_ocr_config((form.instance.extra_config or {}).get(CONFIG_KEY))['enabled'] else ''
    return Div(
        HTML('<h6 class="fw-bold my-3">' + escape(strings.get('ocr_settings_title', 'OCR text extraction')) + '</h6>'),
        build_settings_toggle_field(form, 'ocr_enabled', css_class='col-12'),
        Div(
            HTML(status),
            Row(
                Div(build_settings_toggle_field(form, 'ocr_auto_on_save', css_class='col-12'), css_class='col-lg-6'),
                Div(build_settings_toggle_field(form, 'ocr_search', css_class='col-12'), css_class='col-lg-6'),
                css_class='g-3 mb-3',
            ),
            Field('ocr_mode'),
            Row(
                Div(Field('ocr_service_url'), css_class='col-12'),
                Div(Field('ocr_timeout'), css_class='col-12 col-md-4'),
                Div(Field('ocr_max_file_mb'), css_class='col-12 col-md-4'),
                Div(Field('ocr_threads'), css_class='col-12 col-md-4'),
                css_class='g-3 mb-3',
            ),
            HTML(
                "<div class='mt-2'>"
                f"<button type='button' class='btn btn-outline-primary rounded-pill px-4' data-dynamic-modal='{panel_url}'"
                f" data-modal-title=\"{escape(strings.get('dlux_ops_panel_title', 'Operations'))}\">"
                f"<i class='bi bi-hdd-stack me-1'></i> {escape(strings.get('ocr_manage_service', 'Start or stop the OCR service'))}</button>"
                f"<div class='form-text'>{escape(strings.get('ocr_manage_service_help', 'The ocr service is listed in the Operations panel with the other auxiliary services.'))}</div>"
                "</div>"
            ),
        ),
        **{'data-ocr-settings': ''},
    )


def apply_ocr(form, instance):
    if 'ocr_enabled' not in form.cleaned_data:
        return
    if form.single_step_mode and form.single_step_index != SETUP_STEP_EXTRAS:
        return
    extra = dict(instance.extra_config or {})
    config = normalize_ocr_config(extra.get(CONFIG_KEY))
    for key in FIELDS:
        value = form.cleaned_data.get('ocr_' + key)
        if value not in (None, ''):
            config[key] = value
    config['enabled'] = bool(form.cleaned_data.get('ocr_enabled'))
    for key in ('auto_on_save', 'search'):
        config[key] = bool(form.cleaned_data.get('ocr_' + key))
    extra[CONFIG_KEY] = normalize_ocr_config(config)
    instance.extra_config = extra
