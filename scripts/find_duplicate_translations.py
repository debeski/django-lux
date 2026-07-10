#!/usr/bin/env python3
"""Find duplicate DLUX_STRINGS values — keys that could be unified into one.

Groups translation keys by identical **English** value and reports each group as
a consolidation candidate, tiered by how safe the merge is:

* **Tier 1** — identical EN *and* identical AR → safe to unify.
* **Tier 2** — identical EN but the AR wording differs → unify only after picking
  one Arabic form (a wording decision, not mechanical).

Report-only by design: unifying keys means updating every call site (templates,
forms, dynamic lookups), which is not safe to automate — this regenerates a
fresh, accurate version of ``.xpose/trans_audit.md`` for you to act on.

Keys looked up by computed name (``f"model_{name}"``, ``f"action_{v}"``, …) are
detected from the code and flagged **[dynamic]** — never unify those by deleting;
they need an alias map in ``get_strings()``.

Usage:
    python scripts/find_duplicate_translations.py            # text report
    python scripts/find_duplicate_translations.py --tier1     # only the safe merges
    python scripts/find_duplicate_translations.py --md        # markdown (refresh the audit)
    python scripts/find_duplicate_translations.py --md > .xpose/trans_audit.md
"""

from __future__ import annotations

import argparse
import ast
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS = ROOT / "dlux" / "translations.py"

SCAN_EXTS = {".py"}
SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", ".xpose", "__pycache__",
    "migrations", "staticfiles", "dist", "build", "django_lux.egg-info",
}
_DYNAMIC_PATTERNS = [
    re.compile(r"""f["']([A-Za-z0-9_]*?_)\{"""),
    re.compile(r"""["']([A-Za-z0-9_]*?_)["']\s*\+"""),
    re.compile(r"""["']([A-Za-z0-9_]*?_)%[sd]"""),
]
DEFAULT_PROTECTED_PREFIXES = ["model_", "models_", "app_", "action_", "perm_", "user_report_"]


def load_lang_values(path: Path):
    """{lang: {key: value}} for simple string entries, via AST (ignores comments)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    langs: dict[str, dict[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "DLUX_STRINGS" for t in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for lk, lv in zip(node.value.keys, node.value.values):
            if not (isinstance(lk, ast.Constant) and isinstance(lk.value, str) and isinstance(lv, ast.Dict)):
                continue
            entries = {}
            for k, v in zip(lv.keys, lv.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str) \
                        and isinstance(v, ast.Constant) and isinstance(v.value, str):
                    entries[k.value] = v.value
            langs[lk.value] = entries
    return langs


def detect_dynamic_prefixes():
    prefixes = set(DEFAULT_PROTECTED_PREFIXES)
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.resolve() == TRANSLATIONS.resolve():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat in _DYNAMIC_PATTERNS:
            for m in pat.findall(text):
                if len(m) >= 3 and m.endswith("_"):
                    prefixes.add(m)
    return sorted(prefixes)


def canonical(keys):
    """Suggested key to keep: shortest name, ties broken alphabetically."""
    return sorted(keys, key=lambda k: (len(k), k))[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Find duplicate DLUX_STRINGS values.")
    ap.add_argument("--tier1", action="store_true", help="Only groups with identical EN and AR.")
    ap.add_argument("--md", action="store_true", help="Emit markdown (keep -> retire) tables.")
    ap.add_argument("--min", type=int, default=2, help="Minimum group size to report (default 2).")
    args = ap.parse_args(argv)

    langs = load_lang_values(TRANSLATIONS)
    en = langs.get("en", {})
    ar = langs.get("ar", {})
    prefixes = detect_dynamic_prefixes()

    def is_dynamic(key):
        return any(key.startswith(p) for p in prefixes)

    # Group EN keys by their (whitespace-normalized) English value.
    groups = defaultdict(list)
    for key, val in en.items():
        groups[val.strip()].append(key)

    tier1, tier2 = [], []
    for val, keys in groups.items():
        if len(keys) < args.min:
            continue
        keys = sorted(keys)
        ar_vals = {ar.get(k, "").strip() for k in keys if k in ar}
        same_ar = len(ar_vals) <= 1
        (tier1 if same_ar else tier2).append((val, keys))

    tier1.sort(key=lambda g: (-len(g[1]), g[0]))
    tier2.sort(key=lambda g: (-len(g[1]), g[0]))

    def fmt_keys(keys):
        keep = canonical(keys)
        retire = [k for k in keys if k != keep]
        tag = lambda k: f"{k} [dynamic]" if is_dynamic(k) else k
        return keep + (" [dynamic]" if is_dynamic(keep) else ""), [tag(k) for k in retire]

    redundant = sum(len(k) - 1 for _, k in tier1) + (0 if args.tier1 else sum(len(k) - 1 for _, k in tier2))

    if args.md:
        print(f"# Duplicate translation values (auto-generated)\n")
        print(f"EN keys: {len(en)} · AR keys: {len(ar)}. "
              f"Tier 1 groups (identical EN+AR): {len(tier1)}; "
              f"Tier 2 (EN same, AR differs): {len(tier2)}. "
              f"~{redundant} redundant key(s).\n")
        print("Keys marked **[dynamic]** are looked up by computed name — unify via an "
              "alias map in `get_strings()`, never by deleting.\n")
        print("## Tier 1 — safe merges (identical EN + AR)\n")
        print("| Keep | Retire | English |\n|------|--------|---------|")
        for val, keys in tier1:
            keep, retire = fmt_keys(keys)
            print(f"| `{keep}` | {', '.join('`'+r+'`' for r in retire)} | {val} |")
        if not args.tier1:
            print("\n## Tier 2 — same English, different Arabic (pick one wording first)\n")
            print("| Keep (suggested) | Retire | English |\n|------|--------|---------|")
            for val, keys in tier2:
                keep, retire = fmt_keys(keys)
                print(f"| `{keep}` | {', '.join('`'+r+'`' for r in retire)} | {val} |")
        return 0

    print(f"EN keys: {len(en)} · AR keys: {len(ar)}")
    print(f"Detected {len(prefixes)} dynamic prefixes (keys flagged [dynamic] need an alias map).")
    print(f"Tier 1 (identical EN+AR): {len(tier1)} groups · "
          f"Tier 2 (EN same, AR differs): {len(tier2)} groups · ~{redundant} redundant keys.\n")

    def dump(title, groups_):
        print(f"== {title} ({len(groups_)} groups) ==")
        for val, keys in groups_:
            keep, retire = fmt_keys(keys)
            print(f'  "{val}"')
            print(f"      keep:   {keep}")
            print(f"      retire: {', '.join(retire)}")
        print()

    dump("Tier 1 — safe merges (identical EN + AR)", tier1)
    if not args.tier1:
        dump("Tier 2 — same EN, different AR (choose one Arabic form)", tier2)

    # Bonus: keys present in AR but missing from EN (templates fall back to literals).
    missing_en = sorted(set(ar) - set(en))
    if missing_en and not args.tier1:
        print(f"== Keys in AR but missing from EN ({len(missing_en)}) ==")
        for k in missing_en:
            print(f"  - {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
