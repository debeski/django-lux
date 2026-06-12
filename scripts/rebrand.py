#!/usr/bin/env python3
"""Throwaway rebrand tool: microsys -> django-lux (import token `dlux`).

Content replacement only (path/dir renames are done separately via `git mv`).
Ordered, longest-match-first so `django-microsys` -> `django-lux` (not `django-dlux`).
Binary-safe (decode-guard). Run from the repo root.

    python3 scripts/rebrand.py --dry-run     # show what would change
    python3 scripts/rebrand.py --apply        # rewrite files in place
"""
import argparse
import difflib
import os
import re
import sys

# Directories never traversed.
SKIP_DIRS = {
    ".git", "__pycache__", "build", ".venv", "venv", "node_modules",
    ".xpose", ".sonar", ".pytest_cache", ".claude", "dist", ".dist",
    "scripts",  # don't rewrite this script's own patterns
}
SKIP_DIR_SUFFIXES = (".egg-info",)

# Only these extensions (or exact names) are treated as text and rewritten.
TEXT_EXTS = {
    ".py", ".go", ".js", ".css", ".html", ".md", ".toml", ".txt", ".cfg",
    ".in", ".yml", ".yaml", ".json", ".mod", ".po", ".tmpl", ".gitignore",
    ".gitattributes", ".sh", ".env", ".dockerfile",
}
TEXT_NAMES = {"Makefile", "Dockerfile", "MANIFEST.in", "LICENSE"}

# Third-party vendored asset dirs to leave alone entirely.
SKIP_PATH_PARTS = ("static/bootstrap", "static/chart.js", "static/vanillajs-datepicker")

# Ordered literal replacements (applied top to bottom). Longest/most specific first.
LITERAL_RULES = [
    # 0 compound brand prose ("Django <brand>") -> the clean display name, so we
    # don't produce redundant "Django DjangoLux" / "Django-Dlux".
    ("Django microSYS", "DjangoLux"),
    ("Django-Microsys", "DjangoLux"),
    # 1-4 distribution / hyphenated + underscore dist names
    ("django-microsys-sso-client", "django-lux-sso-client"),
    ("django-microsys-sso", "django-lux-sso"),
    ("django-microsys", "django-lux"),
    ("django_microsys", "django_lux"),
    # 5 backup format identifiers (case-kept)
    ("MSB1", "DLB1"),
    ("MSB_", "DLB_"),
    ("MSB", "DLB"),
    (".msb", ".dlb"),
    ("msb", "dlb"),
    ("Msb", "Dlb"),
    # (CSS regex rule runs between here — see REGEX_RULES)
    # 7 brand prose variants
    ("microSYS", "DjangoLux"),
    ("MicroSys", "DjangoLux"),
    ("microSys", "DjangoLux"),
    # 8 case-mapped core token
    ("MICROSYS", "DLUX"),
    ("Microsys", "Dlux"),
    ("microsys", "dlux"),
]

# CSS prefix: ms-<word> -> dl-<word>, but NOT Bootstrap utilities
# (ms-1, ms-auto, ms-n1, ms-sm-*, ms-md-*, ...).
CSS_RE = re.compile(r"\bms-(?!auto\b|sm-|md-|lg-|xl-|xxl-|n?\d)([a-z])")


def transform(text):
    # backup-format + brand literals, then CSS regex inserted at rule 6 position.
    # We split LITERAL_RULES around the CSS pass: run the first 9 (dist+backup),
    # then CSS, then the brand/core rules — matching the plan's ordering.
    backup_end = LITERAL_RULES.index(("microSYS", "DjangoLux"))
    for old, new in LITERAL_RULES[:backup_end]:
        text = text.replace(old, new)
    text = CSS_RE.sub(r"dl-\1", text)
    for old, new in LITERAL_RULES[backup_end:]:
        text = text.replace(old, new)
    return text


def is_text_file(path):
    name = os.path.basename(path)
    if name in TEXT_NAMES:
        return True
    _, ext = os.path.splitext(name)
    return ext in TEXT_EXTS


def iter_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.endswith(SKIP_DIR_SUFFIXES)
        ]
        rel = os.path.relpath(dirpath, root).replace(os.sep, "/")
        if any(part in rel for part in SKIP_PATH_PARTS):
            continue
        for fn in filenames:
            yield os.path.join(dirpath, fn)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--root", default=".")
    ap.add_argument("--show-diff", action="store_true", help="print unified diffs (dry-run)")
    args = ap.parse_args()

    changed, total_files, css_hits = [], 0, 0
    for path in iter_files(args.root):
        if not is_text_file(path):
            continue
        total_files += 1
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
            if b"\x00" in raw:
                continue  # binary guard
            src = raw.decode("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        dst = transform(src)
        if dst == src:
            continue
        css_hits += len(CSS_RE.findall(src))
        changed.append(path)
        if args.show_diff:
            diff = difflib.unified_diff(
                src.splitlines(True), dst.splitlines(True),
                fromfile=path, tofile=path, n=1,
            )
            sys.stdout.writelines(diff)
        if args.apply:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(dst)

    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"\n[{mode}] scanned {total_files} text files; "
          f"{len(changed)} would change; ~{css_hits} ms-> dl- CSS hits.")
    for p in changed:
        print("  ", p)


if __name__ == "__main__":
    sys.exit(main())
