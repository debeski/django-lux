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


_registered = False


def register_pdf_options():
    """Show the PDF tools controls in System Settings > Extra Features."""
    global _registered
    _registered = True


def pdf_tools_registered():
    return _registered
