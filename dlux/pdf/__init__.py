"""Optional PDF interface. Projects own documents, permissions and persistence."""

NAMESPACE = 'dlux.pdf'
DEFAULTS = {'editing_enabled': True, 'history_enabled': True, 'max_pages': 500, 'max_source_mb': 100}


def get_pdf_features():
    from dlux.utils import get_app_system_config

    config = get_app_system_config(NAMESPACE, {})
    if not isinstance(config, dict):
        config = {}
    result = {key: config.get(key, DEFAULTS[key]) is True for key in ('editing_enabled', 'history_enabled')}
    for key, maximum in [('max_pages', 5000), ('max_source_mb', 500)]:
        try:
            value = int(config.get(key, DEFAULTS[key]))
        except (TypeError, ValueError):
            value = DEFAULTS[key]
        result[key] = max(1, min(maximum, value))
    return result


def register_pdf_options():
    from dlux.options import register_app_settings
    from dlux.translations import lazy_translator

    register_app_settings(
        namespace=NAMESPACE,
        title=lazy_translator('pdf_options_title', 'PDF tools'),
        description=lazy_translator('pdf_options_description', 'Disable tools without removing documents or file history.'),
        icon='bi-file-earmark-pdf', setup=False,
        fields=[
            {'name': key, 'type': 'boolean', 'default': True,
             'label': lazy_translator('pdf_option_' + key, label)}
            for key, label in [('editing_enabled', 'Enable page editing'), ('history_enabled', 'Enable file history')]
        ] + [
            {'name': 'max_pages', 'type': 'integer', 'default': 500, 'min_value': 1, 'max_value': 5000,
             'label': lazy_translator('pdf_option_max_pages', 'Maximum editable pages')},
            {'name': 'max_source_mb', 'type': 'integer', 'default': 100, 'min_value': 1, 'max_value': 500,
             'label': lazy_translator('pdf_option_max_source_mb', 'Maximum combined PDF size (MB)')},
        ],
    )
