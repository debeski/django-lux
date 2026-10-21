"""Resolve settings-field ownership from the layout that renders the controls."""

from html.parser import HTMLParser


class _NamedControls(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.names = set()
        self.feed(str(markup))

    def handle_starttag(self, tag, attrs):
        if tag in {'input', 'select', 'textarea'}:
            name = dict(attrs).get('name')
            if name:
                self.names.add(name)


def _field_names(node):
    if isinstance(node, str):
        yield node
        return
    if hasattr(node, 'html'):
        yield from _NamedControls(node.html).names
    for child in getattr(node, 'fields', ()):
        yield from _field_names(child)


def settings_field_steps(form):
    from ...system.constants import SETUP_STEP_APPEARANCE, SETUP_STEP_TITLEBAR

    # These builders render their transport inputs only on the active section.
    template_fields = {
        'allowed_fonts': SETUP_STEP_APPEARANCE,
        'allowed_themes': SETUP_STEP_APPEARANCE,
        'titlebar_config': SETUP_STEP_TITLEBAR,
    }
    owners = {}
    step = 0
    for node in form.helper.layout.fields:
        if 'wizard-step' not in str(getattr(node, 'css_class', '')).split():
            continue
        for name in _field_names(node):
            if name in form.fields:
                previous = owners.setdefault(name, step)
                if previous != step:
                    raise ValueError(f'Settings field {name} belongs to multiple steps.')
        step += 1
    for name, owner in template_fields.items():
        if name in form.fields and owners.setdefault(name, owner) != owner:
            raise ValueError(f'Settings builder {name} renders outside its declared step.')
    return owners


def protect_inactive_settings(form):
    form.field_steps = settings_field_steps(form)
    if not form.is_bound or not form.single_step_mode or form.mode == 'setup':
        return
    data = form.data.copy()
    files = form.files.copy()
    for name, owner in form.field_steps.items():
        if owner != form.single_step_index:
            form.fields[name].disabled = True
            data.pop(name, None)
            files.pop(name, None)
    if form.single_step_index != form.field_steps.get('default_language'):
        import json
        form.initial['default_language'] = form.instance.default_language
        form.initial['languages'] = json.dumps(form.instance.languages)
    form.data = data
    form.files = files
