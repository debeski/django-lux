from pathlib import Path


_VERSION_FILE = Path(__file__).with_name("VERSION")


def get_version():
    return _VERSION_FILE.read_text(encoding="utf-8").strip()


__version__ = get_version()
