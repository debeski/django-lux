"""Backup and restore errors whose message an operator reads.

A leaf module: ``crypto`` and ``chain`` raise these, and both sit below
``_shared`` in the backup package's import order.
"""


class BackupError(ValueError):
    """A ``ValueError`` that also knows its translation key.

    ``str()`` stays the English text, so logs and callers that compare messages
    are unchanged; ``translated()`` is what a restore row stores.
    """

    def __init__(self, string_key, default, /, **params):
        self.key = string_key
        self.default = default
        self.params = params
        super().__init__(default.format(**params))

    def translated(self):
        try:
            from ..translations import get_strings

            template = get_strings().get(self.key) or self.default
            return template.format(**self.params)
        except Exception:
            return str(self)
