"""OCR's Extra Features controls and save policy (``extra_config['ocr']``)."""

from crispy_forms.layout import Div, Field, HTML, Row
from django.urls import reverse
from django.utils.html import escape

from ..ocr import CONFIG_KEY, MODES, normalize_ocr_config
from ..system.constants import SETUP_STEP_EXTRAS
from ..widgets import DluxChoiceSelectorWidget, DluxMultipleChoiceSelectorWidget
from .builders import _bind_choice_selector_widget, build_settings_toggle_field

FIELDS = ('enabled', 'auto_on_save', 'search', 'mode', 'service_url', 'timeout', 'max_file_mb', 'threads',
          'background_enabled', 'background_interval', 'background_batch_size', 'background_queue_limit', 'automatic_models')
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
    'background_enabled': ('form_sys_ocr_background_enabled', 'Read older files in the background'),
    'background_interval': ('form_sys_ocr_background_interval', 'Background scan interval (seconds)'),
    'background_batch_size': ('form_sys_ocr_background_batch_size', 'Files queued per background scan'),
    'background_queue_limit': ('form_sys_ocr_background_queue_limit', 'Pause catch-up at this many active files'),
    'automatic_models': ('form_sys_ocr_automatic_models', 'Models included in automatic OCR'),
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
        "Reads the text of registered document files with the stack's ocr service. Saving a change here also starts or stops that service (current password required).",
    )
    form.fields['ocr_threads'].help_text = strings.get('help_sys_ocr_threads', 'CPU threads used for each file.')
    from ..files.specs import registered_document_files
    from ..utils.activity_log import translate_activity_log_model_name
    models = {spec.model._meta.label_lower: spec.model for spec in registered_document_files() if spec.ocr}
    choices = []
    for key, model in sorted(models.items()):
        label = translate_activity_log_model_name(key, strings)
        choices.append((key, str(model._meta.verbose_name_plural) if label == key else label))
    form.fields['ocr_automatic_models'].choices = choices
    form.initial['ocr_automatic_models'] = list(models) if config['automatic_models'] is None else config['automatic_models']
    _bind_choice_selector_widget(form.fields['ocr_automatic_models'], DluxMultipleChoiceSelectorWidget(choices=choices, variant='card', searchable=True))
    form.fields['ocr_automatic_models'].help_text = strings.get('help_sys_ocr_automatic_models', 'Excluded models receive no automatic or background OCR. Manual Run OCR remains available.')
    form.fields['ocr_background_enabled'].help_text = strings.get('help_sys_ocr_background_enabled', 'Catch up on older files that have no OCR result. Finished and failed files are skipped; manual reads take priority.')
    form.fields['ocr_current_password'].label = strings.get('form_sys_ocr_current_password', 'Current password')
    form.fields['ocr_current_password'].help_text = strings.get(
        'help_sys_ocr_current_password',
        'Needed only when you turn OCR on or off: saving then starts or stops the ocr service through Composer.',
    )
    form.fields['ocr_current_password'].disabled = not active_step


def _stored_enabled(form):
    return normalize_ocr_config((form.instance.extra_config or {}).get(CONFIG_KEY))['enabled']


def clean_ocr(form, cleaned):
    """A changed Enable OCR switch needs the current password: saving it starts or stops the ocr service."""
    from ..translations import get_strings
    from ..ocr.control import operation_for
    from ..ocr import valid_service_url

    form._ocr_service_operation = ''
    if form.single_step_mode and form.single_step_index != SETUP_STEP_EXTRAS:
        return
    if cleaned.get('ocr_service_url') and not valid_service_url(cleaned['ocr_service_url']):
        form.add_error('ocr_service_url', get_strings().get('ocr_service_internal_only', 'Use an internal service name or a private LAN address.'))
    if 'ocr_enabled' not in cleaned or bool(cleaned.get('ocr_enabled')) == _stored_enabled(form):
        return
    strings = get_strings()
    request = getattr(form, 'request', None)
    user = getattr(request, 'user', None) or getattr(form, '_user', None)
    password = cleaned.get('ocr_current_password') or ''
    if not user or not getattr(user, 'is_superuser', False):
        form.add_error('ocr_enabled', strings.get('permission_denied', 'Permission denied.'))
    elif not password:
        form.add_error('ocr_current_password', strings.get('current_password_required', 'Please enter your current password.'))
    elif not user.check_password(password):
        form.add_error('ocr_current_password', strings.get('current_password_incorrect', 'Current password is incorrect.'))
        if request is not None:
            from ..utils import log_audit_event
            log_audit_event(request, 'permission_denied', 'PERMISSION_DENIED', instance=user, model_name='password')
    else:
        form._ocr_service_operation = operation_for(bool(cleaned.get('ocr_enabled')))


def _service_status(strings, enabled):
    from ..ocr.client import service_health
    from ..ocr.control import service_status

    lines = []
    if enabled:
        health = service_health()
        if health:
            text = strings.get('ocr_service_connected', 'Service connected: {engine} {version}').format(
                engine=health.get('engine', ''), version=health.get('engine_version', ''))
            lines.append(('text-success', text))
        else:
            lines.append(('text-warning-emphasis', strings.get('ocr_service_unreachable', 'The OCR service does not answer at the configured address.')))
    status = service_status()
    if status:
        start = status['operation'] == 'service-start'
        if status['state'] == 'unavailable':
            lines.append(('text-warning-emphasis', status['message']))
        elif status['state'] in ('queued', 'running'):
            lines.append(('text-body-secondary', strings.get('ocr_service_start_requested', 'Starting the ocr service through Composer.') if start
                          else strings.get('ocr_service_stop_requested', 'Stopping the ocr service through Composer.')))
        elif status['state'] == 'completed':
            lines.append(('text-success', strings.get('ocr_service_started', 'Composer started the ocr service.') if start
                          else strings.get('ocr_service_stopped', 'Composer stopped the ocr service.')))
        else:
            lines.append(('text-danger', strings.get('ocr_service_request_failed', 'Composer could not change the ocr service: {error}').format(error=status['message'])))
    return ''.join(f"<p class='small {css} mb-2' role='status'>{escape(text)}</p>" for css, text in lines)


def ocr_settings_layout(form, strings):
    panel_url = reverse('dlux_operations_panel')
    status = _service_status(strings, _stored_enabled(form))
    from django.core.cache import cache
    from ..ocr.background import STATE_KEY
    background = cache.get(STATE_KEY)
    if background and normalize_ocr_config((form.instance.extra_config or {}).get(CONFIG_KEY))['background_enabled']:
        states = {
            'idle': strings.get('ocr_background_state_idle', 'Idle'),
            'queued': strings.get('ocr_background_state_queued', 'Files queued'),
            'paused_queue': strings.get('ocr_background_state_paused_queue', 'Paused: OCR queue is busy'),
            'paused_service': strings.get('ocr_background_state_paused_service', 'Paused: OCR service is unavailable'),
        }
        label = states.get(background.get('state'), states['idle'])
        text = strings.get('ocr_background_progress', 'Background: {state}. Last scan: {scanned} checked, {queued} queued.').format(
            state=label, scanned=background.get('scanned', 0), queued=background.get('queued', 0))
        status += f"<p class='small text-body-secondary mb-2' role='status'>{escape(text)}</p>"
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
            Field('ocr_automatic_models'),
            build_settings_toggle_field(form, 'ocr_background_enabled', css_class='col-12'),
            Row(
                Div(Field('ocr_background_interval'), css_class='col-12 col-lg-4'),
                Div(Field('ocr_background_batch_size'), css_class='col-12 col-lg-4'),
                Div(Field('ocr_background_queue_limit'), css_class='col-12 col-lg-4'),
                css_class='g-3 mb-3',
            ),
            Row(
                Div(Field('ocr_service_url'), css_class='col-12'),
                Div(Field('ocr_timeout'), css_class='col-12 col-md-4'),
                Div(Field('ocr_max_file_mb'), css_class='col-12 col-md-4'),
                Div(Field('ocr_threads'), css_class='col-12 col-md-4'),
                css_class='g-3 mb-3',
            ),
            Field('ocr_current_password'),
            HTML(
                "<div class='mt-2'>"
                f"<button type='button' class='btn btn-outline-primary rounded-pill px-4' data-dynamic-modal='{panel_url}'"
                f" data-modal-title=\"{escape(strings.get('dlux_ops_panel_title', 'Operations'))}\">"
                f"<i class='bi bi-hdd-stack me-1'></i> {escape(strings.get('ocr_manage_service', 'Open the Operations panel'))}</button>"
                f"<div class='form-text'>{escape(strings.get('ocr_manage_service_help', 'The ocr service is listed in the Operations panel with the other auxiliary services.'))}</div>"
                "</div>"
            ),
        ),
        **{
            'data-ocr-settings': '',
            'data-ocr-initial-enabled': 'true' if _stored_enabled(form) else 'false',
            'data-ocr-confirm-title': strings.get('ocr_settings_title', 'OCR text extraction'),
            'data-ocr-confirm-description': strings.get('help_sys_ocr_current_password', 'Needed only when you turn OCR on or off: saving then starts or stops the ocr service through Composer.'),
        },
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
    for key in ('auto_on_save', 'search', 'background_enabled'):
        config[key] = bool(form.cleaned_data.get('ocr_' + key))
    extra[CONFIG_KEY] = normalize_ocr_config(config)
    instance.extra_config = extra
    operation = getattr(form, '_ocr_service_operation', '')
    request = getattr(form, 'request', None)
    if operation and request is not None:
        # Sent by dlux.ocr.control.settings_saved only when this row is really
        # written: Preview builds the same instance and never saves it.
        instance._dlux_ocr_service_request = (request, operation)
