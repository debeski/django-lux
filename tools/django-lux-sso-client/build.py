from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent


def main():
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "build",
            str(ROOT),
            "--outdir",
            str(ROOT / "dist"),
        ],
        cwd=REPO_ROOT,
    )


if __name__ == "__main__":
    main()
