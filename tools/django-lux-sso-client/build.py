from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def main():
    subprocess.check_call([sys.executable, "-m", "build"], cwd=ROOT)


if __name__ == "__main__":
    main()

