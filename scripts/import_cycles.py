"""Report module-level import cycles inside dlux.

A cycle leaves a module half-initialised while its partner imports it, which is
how `from dlux.utils import X` at module scope in a project's urls-reachable
module can fail, or how a project's ROOT_URLCONF ends up without `urlpatterns`.
Run from the repository root.
"""
import ast
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1] / 'dlux'


def module_name(path):
    rel = path.relative_to(ROOT).with_suffix('')
    parts = list(rel.parts)
    if parts and parts[-1] == '__init__':
        parts.pop()
    return '.'.join(['dlux'] + parts)


def build_graph():
    files = {
        module_name(p): p
        for p in ROOT.rglob('*.py')
        if '/tests/' not in str(p) and '/migrations/' not in str(p)
    }
    graph = defaultdict(set)
    for mod, path in files.items():
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'))
        except SyntaxError:
            continue
        parts = mod.split('.')
        is_pkg = path.name == '__init__.py'
        for node in tree.body:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Import):
                    graph[mod].update(a.name for a in sub.names)
                elif isinstance(sub, ast.ImportFrom):
                    if sub.level:
                        base = parts[:len(parts) - sub.level + 1] if is_pkg else parts[:-sub.level]
                        target = '.'.join(base + ([sub.module] if sub.module else []))
                    else:
                        target = sub.module or ''
                    if target:
                        graph[mod].add(target)
    return files, graph


def cyclic_groups(files, graph):
    """Strongly-connected components of size > 1 — the actual cyclic clusters.

    Enumerating every cyclic *path* explodes combinatorially; the SCCs are what
    matter, because every module in one can be reached half-initialised.
    """
    known = set(files)
    index, low, on_stack, stack, counter, groups = {}, {}, set(), [], [0], []

    def strongconnect(node):
        index[node] = low[node] = counter[0]
        counter[0] += 1
        stack.append(node)
        on_stack.add(node)
        for nxt in sorted(t for t in graph.get(node, ()) if t in known):
            if nxt not in index:
                strongconnect(nxt)
                low[node] = min(low[node], low[nxt])
            elif nxt in on_stack:
                low[node] = min(low[node], index[nxt])
        if low[node] == index[node]:
            component = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                component.append(w)
                if w == node:
                    break
            if len(component) > 1:
                groups.append(sorted(component))

    sys.setrecursionlimit(10000)
    for mod in sorted(known):
        if mod not in index:
            strongconnect(mod)
    return groups


def main():
    files, graph = build_graph()
    groups = cyclic_groups(files, graph)
    total = sum(len(g) for g in groups)
    print(f'modules: {len(files)}   cyclic clusters: {len(groups)}   modules involved: {total}')
    for group in groups:
        print(f'  [{len(group)}] ' + ', '.join(group))
    return 1 if groups else 0


if __name__ == '__main__':
    sys.exit(main())
