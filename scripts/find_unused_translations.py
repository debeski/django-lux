#!/usr/bin/env python3
"""Find (and optionally remove) unused DLUX_STRINGS translation keys.

A translation key is considered **unused** when its exact string does not appear
anywhere in the scanned source tree (templates, Python, JS, email/text). It is
reported per key, and with ``--apply`` the matching lines are removed from both
the ``ar`` and ``en`` blocks of ``dlux/translations.py``.

Safety
------
* **Dry-run by default.** Nothing is written unless you pass ``--apply``; a
  unified diff of the proposed removal is always printed for review.
* **Runtime-built keys are protected.** Many keys are looked up dynamically
  (``s.get(f"model_{name}")``, ``f"action_{key}"``, …) so their literal string
  never appears in source. The script auto-detects such prefixes from the code
  (f-strings / concatenation / ``%`` formatting) and never flags a key whose
  name starts with one; add more with ``--protect-prefix``.
* **Conservative matching.** A key counts as "used" on any substring hit, so the
  script errs toward *keeping* keys — false "unused" is far less likely than
  false "used".

Usage
-----
    python scripts/find_unused_translations.py                 # report + diff only
    python scripts/find_unused_translations.py --apply         # actually remove
    python scripts/find_unused_translations.py --protect-prefix foo_ --protect-prefix bar_
    python scripts/find_unused_translations.py --list          # just print the keys
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS = ROOT / "dlux" / "translations.py"

SCAN_EXTS = {".py", ".html", ".js", ".txt", ".md", ".json"}
SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", ".xpose", "__pycache__",
    "migrations", "staticfiles", "static_root", "dist", "build",
    "django_lux.egg-info", ".mypy_cache", ".pytest_cache",
}

# Always keep keys starting with one of these (belt-and-braces on top of the
# auto-detected prefixes below).
DEFAULT_PROTECTED_PREFIXES = [
    "model_", "models_", "app_", "action_", "perm_", "user_report_",
]

# Detect literal prefixes that are completed at runtime:
#   f"model_{name}"  ->  model_
#   "action_" + key  ->  action_
#   "user_report_%s" % k  ->  user_report_
_DYNAMIC_PATTERNS = [
    re.compile(r"""f["']([A-Za-z0-9_]*?_)\{"""),          # f"prefix{...}"
    re.compile(r"""["']([A-Za-z0-9_]*?_)["']\s*\+"""),     # "prefix" + var
    re.compile(r"""["']([A-Za-z0-9_]*?_)%[sd]"""),         # "prefix%s"
]


def load_key_positions(path: Path):
    """Return (source, {lang: {key: (start_line, end_line)}}) via AST.

    Comment-only lines never appear (AST ignores comments), so commented-out
    keys are naturally excluded.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    langs: dict[str, dict[str, tuple[int, int]]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "DLUX_STRINGS" for t in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for lang_key, lang_val in zip(node.value.keys, node.value.values):
            if not (isinstance(lang_key, ast.Constant) and isinstance(lang_key.value, str)):
                continue
            if not isinstance(lang_val, ast.Dict):
                continue
            entries: dict[str, tuple[int, int]] = {}
            for k, v in zip(lang_val.keys, lang_val.values):
                if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                    continue
                start = k.lineno
                end = getattr(v, "end_lineno", None) or v.lineno
                entries[k.value] = (start, end)
            langs[lang_key.value] = entries
    return source, langs


def iter_scan_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SCAN_EXTS:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.resolve() == TRANSLATIONS.resolve():
            continue  # don't count a key's own definition as usage
        if path.resolve() == Path(__file__).resolve():
            continue
        yield path


def build_corpus_and_prefixes():
    """One big text blob of all scanned source + auto-detected dynamic prefixes."""
    chunks = []
    prefixes: set[str] = set()
    for path in iter_scan_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        chunks.append(text)
        if path.suffix == ".py":
            for pat in _DYNAMIC_PATTERNS:
                for m in pat.findall(text):
                    if len(m) >= 3 and m.endswith("_"):
                        prefixes.add(m)
    return "\n".join(chunks), prefixes


def main(argv=None):
    parser = argparse.ArgumentParser(description="Find/remove unused DLUX_STRINGS keys.")
    parser.add_argument("--apply", action="store_true",
                        help="Rewrite dlux/translations.py, removing unused keys (default: dry-run).")
    parser.add_argument("--protect-prefix", action="append", default=[],
                        help="Never flag keys starting with this prefix (repeatable).")
    parser.add_argument("--list", action="store_true",
                        help="Only print the unused keys (no diff).")
    args = parser.parse_args(argv)

    source, langs = load_key_positions(TRANSLATIONS)
    all_keys = set()
    for entries in langs.values():
        all_keys.update(entries)

    corpus, auto_prefixes = build_corpus_and_prefixes()
    protected_prefixes = sorted(
        set(DEFAULT_PROTECTED_PREFIXES) | auto_prefixes | set(args.protect_prefix)
    )

    def is_protected(key: str) -> bool:
        return any(key.startswith(p) for p in protected_prefixes)

    unused, protected_unused = [], []
    for key in sorted(all_keys):
        if key in corpus:
            continue
        if is_protected(key):
            protected_unused.append(key)
        else:
            unused.append(key)

    langs_present = ", ".join(sorted(langs))
    print(f"Scanned {TRANSLATIONS.relative_to(ROOT)} — {len(all_keys)} keys across [{langs_present}].")
    print(f"Protected prefixes ({len(protected_prefixes)}): {', '.join(protected_prefixes)}")
    if protected_unused:
        print(f"Kept {len(protected_unused)} literal-absent key(s) matched by a dynamic prefix "
              f"(e.g. {', '.join(protected_unused[:5])}{'…' if len(protected_unused) > 5 else ''}).")
    print(f"\nUnused candidates: {len(unused)}")
    for key in unused:
        print(f"  - {key}")

    if args.list or not unused:
        return 0

    # Build the rewritten source (drop each unused key's line range in every lang).
    drop_lines: set[int] = set()
    for key in unused:
        for entries in langs.values():
            if key in entries:
                start, end = entries[key]
                drop_lines.update(range(start, end + 1))

    original_lines = source.splitlines(keepends=True)
    new_lines = [ln for i, ln in enumerate(original_lines, start=1) if i not in drop_lines]
    new_source = "".join(new_lines)

    import difflib
    diff = difflib.unified_diff(
        original_lines, new_lines,
        fromfile=f"a/{TRANSLATIONS.relative_to(ROOT)}",
        tofile=f"b/{TRANSLATIONS.relative_to(ROOT)}",
    )
    print("\n--- proposed diff " + "-" * 40)
    sys.stdout.writelines(diff)

    if args.apply:
        TRANSLATIONS.write_text(new_source, encoding="utf-8")
        print(f"\nAPPLIED: removed {len(unused)} key(s), {len(drop_lines)} line(s) from "
              f"{TRANSLATIONS.relative_to(ROOT)}.")
        print("Re-run your test suite to confirm nothing dynamic broke.")
    else:
        print(f"\nDRY-RUN: {len(unused)} key(s), {len(drop_lines)} line(s) would be removed. "
              f"Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
