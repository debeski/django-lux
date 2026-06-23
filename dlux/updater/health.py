import os
import hashlib
import hmac
import sys
import time
from pathlib import Path


def runtime_probe_token(secret_key):
    return hmac.new(
        str(secret_key).encode("utf-8"),
        b"django-lux-runtime-version-probe-v1",
        hashlib.sha256,
    ).hexdigest()


def main():
    root = Path(os.getenv("DLUX_UPDATE_RUNTIME_ROOT", "/opt/dlux-runtime"))
    if (root / "state" / "degraded").exists():
        return 1
    heartbeat = root / "state" / "updater-heartbeat"
    try:
        age = time.time() - float(heartbeat.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 1
    return 0 if 0 <= age <= 45 else 1


if __name__ == "__main__":
    sys.exit(main())
