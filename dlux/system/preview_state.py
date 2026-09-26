"""The draft a settings-preview request renders with. A leaf: imports nothing.

`SystemSettings.load()` asks this module, so it must not pull in forms, options
or views — `dlux.system.preview` owns everything else about a preview.
"""

from contextvars import ContextVar

draft_settings = ContextVar('dlux_settings_preview_draft', default=None)


def current_draft():
    """The draft `SystemSettings` this request previews, or ``None``."""
    return draft_settings.get()
