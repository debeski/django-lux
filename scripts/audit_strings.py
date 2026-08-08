"""Report translation keys referenced in templates/python that do not resolve.

Alias-aware (dlux/translation_aliases.py). The same check runs in the suite as
dlux/tests/test_translation_coverage.py; this script is for ad-hoc inspection.
Run from the repository root.
"""
import ast, re, pathlib, collections, json, sys
root = pathlib.Path(__file__).resolve().parents[1]

src = (root / 'dlux/translations.py').read_text(encoding='utf-8')
cat = {}
for node in ast.walk(ast.parse(src)):
    if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'DLUX_STRINGS':
        for k, v in zip(node.value.keys, node.value.values):
            if isinstance(k, ast.Constant) and isinstance(v, ast.Dict):
                cat[k.value] = {kk.value for kk in v.keys if isinstance(kk, ast.Constant)}
ar, en = cat['ar'], cat['en']

al_src = (root/'dlux/translation_aliases.py').read_text(encoding='utf-8')
ALIASES = {}
for node in ast.walk(ast.parse(al_src)):
    if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'STRING_ALIASES':
        ALIASES = {k.value: v.value for k, v in zip(node.value.keys, node.value.values)}

def resolves(key, langset):
    seen = set()
    while key and key not in seen:
        if key in langset: return True
        seen.add(key); key = ALIASES.get(key)
    return False

used, defaults = collections.defaultdict(set), collections.defaultdict(set)
tpl = re.compile(r"DLUX_STRINGS\.([a-z0-9_]+)(?:\|default:(?:'([^']*)'|\"([^\"]*)\"))?")
pyp = re.compile(r"\b(?:s|strings|dlux_strings)\.get\(\s*'([a-z0-9_]+)'\s*(?:,\s*(?:'([^']*)'|\"([^\"]*)\"))?")
for p in (root/'dlux/templates').rglob('*.html'):
    for m in tpl.finditer(p.read_text(encoding='utf-8')):
        used[m.group(1)].add(str(p.relative_to(root)))
        d = m.group(2) if m.group(2) is not None else m.group(3)
        if d: defaults[m.group(1)].add(d)
for p in (root/'dlux').rglob('*.py'):
    if 'translations.py' in str(p) or '/tests/' in str(p) or 'translation_aliases' in str(p): continue
    for m in pyp.finditer(p.read_text(encoding='utf-8')):
        used[m.group(1)].add(str(p.relative_to(root)))
        d = m.group(2) if m.group(2) is not None else m.group(3)
        if d: defaults[m.group(1)].add(d)

# Deliberately undefined: templates test for presence and fall through.
OPTIONAL = {'footer_text'}
broken = sorted(k for k in used
                if k not in OPTIONAL and (not resolves(k, ar) or not resolves(k, en)))
aliased_ok = sorted(k for k in used if k in ALIASES and resolves(k, ar) and resolves(k, en))
print(f"referenced: {len(used)} | resolve via alias: {len(aliased_ok)} | GENUINELY MISSING: {len(broken)}\n")
for k in broken:
    ds = sorted(defaults.get(k, []), key=len, reverse=True)
    tgt = ALIASES.get(k)
    note = f"  [alias->{tgt}: ar={resolves(tgt,ar)} en={resolves(tgt,en)}]" if tgt else ""
    print(f"{k:44} = {ds[0] if ds else '<no default>'}{note}")
