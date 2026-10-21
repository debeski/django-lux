"""Boolean parsing shared by configuration normalizers and import boundaries."""


def parse_boolean(value, default=False):
    """Accept booleans, 0/1 and known text tokens; otherwise retain the default."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {'1', 'true', 'yes', 'y', 'on'}:
            return True
        if token in {'', '0', 'false', 'no', 'n', 'off'}:
            return False
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    return default
