"""Report import cycles inside dlux, separated by the only distinction that matters.

A **module-scope** cycle is a real defect: while module A is executing its
top-level statements, it imports B, which imports A back and receives a
half-built module object. That is how a project's urls-reachable
`from dlux.utils import X` can fail, or how a ROOT_URLCONF ends up with no
`urlpatterns`.

A **deferred** cycle — where at least one edge is an import inside a function
body — cannot do that. The import runs at call time, long after both modules
finished executing. Those edges still describe coupling worth watching, but they
are not bugs, and treating them as bugs hides the ones that are.

Usage:
    python scripts/import_cycles.py            # human report, exit 1 on real cycles
    python scripts/import_cycles.py --json     # machine-readable summary
"""
import ast
import json
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1] / 'dlux'
SKIP_PARTS = ('tests', 'migrations')


def module_name(path):
    rel = path.relative_to(ROOT).with_suffix('')
    parts = list(rel.parts)
    if parts and parts[-1] == '__init__':
        parts.pop()
    return '.'.join(['dlux'] + parts)


def _resolve(node, mod, is_pkg):
    """Absolute module names a single import node can point at.

    ``from pkg import thing`` is ambiguous in the AST: ``thing`` may be a
    submodule (a real edge to ``pkg.thing``) or an attribute of ``pkg`` (an edge
    to ``pkg`` only). Both candidates are returned; callers keep the ones that
    match a real module, so the ambiguity resolves itself without guessing.
    """
    parts = mod.split('.')
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if node.level:
        base = parts[:len(parts) - node.level + 1] if is_pkg else parts[:-node.level]
        target = '.'.join(base + ([node.module] if node.module else []))
    else:
        target = node.module or ''
    if not target:
        return []
    return [target] + [f'{target}.{alias.name}' for alias in node.names if alias.name != '*']


def _split_imports(tree):
    """Imports that run at import time vs. imports deferred into function bodies.

    Class bodies execute during import, so they count as module scope. Function
    and lambda bodies do not, so their imports are deferred.
    """
    eager, deferred = [], []

    def walk(node, in_function):
        for child in ast.iter_child_nodes(node):
            entering_function = isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                (deferred if in_function else eager).append(child)
            walk(child, in_function or entering_function)

    walk(tree, False)
    return eager, deferred


def build_graphs():
    files = {
        module_name(p): p
        for p in ROOT.rglob('*.py')
        if not any(f'/{part}/' in str(p) for part in SKIP_PARTS)
    }
    eager_graph, full_graph = defaultdict(set), defaultdict(set)
    deferred_count = 0
    for mod, path in files.items():
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'))
        except SyntaxError:
            continue
        is_pkg = path.name == '__init__.py'
        eager, deferred = _split_imports(tree)
        deferred_count += len(deferred)
        for node in eager:
            eager_graph[mod].update(_resolve(node, mod, is_pkg))
        for node in eager + deferred:
            full_graph[mod].update(_resolve(node, mod, is_pkg))
    return files, eager_graph, full_graph, deferred_count


def cyclic_groups(files, graph):
    """Strongly-connected components of size > 1 — the actual cyclic clusters.

    Enumerating every cyclic *path* explodes combinatorially; the SCCs are what
    matter, because every module in one can be reached half-initialised.
    """
    known = set(files)
    index, low, on_stack, stack, counter, groups = {}, {}, set(), [], [0], []

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in sorted(graph.get(v, ())):
            if w not in known:
                continue
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            component = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                component.append(w)
                if w == v:
                    break
            if len(component) > 1:
                groups.append(sorted(component))

    sys.setrecursionlimit(10000)
    for vertex in sorted(known):
        if vertex not in index:
            strong(vertex)
    return sorted(groups, key=len, reverse=True)


def analyse():
    files, eager_graph, full_graph, deferred_count = build_graphs()
    return {
        'modules': len(files),
        'deferred_imports': deferred_count,
        'module_scope_cycles': cyclic_groups(files, eager_graph),
        'deferred_cycles': cyclic_groups(files, full_graph),
    }


def main():
    result = analyse()
    if '--json' in sys.argv:
        print(json.dumps(result, indent=2))
        return 1 if result['module_scope_cycles'] else 0

    print(f"modules: {result['modules']}   deferred imports: {result['deferred_imports']}")
    print()
    if result['module_scope_cycles']:
        print("MODULE-SCOPE CYCLES (defects — a partner can observe a half-built module):")
        for group in result['module_scope_cycles']:
            print(f"  [{len(group)}] {', '.join(group)}")
    else:
        print("MODULE-SCOPE CYCLES: none.")
    print()
    print("DEFERRED CYCLES (coupling only — an edge runs at call time, not import time):")
    if not result['deferred_cycles']:
        print("  none.")
    for group in result['deferred_cycles']:
        print(f"  [{len(group)}] {', '.join(group)}")
    print()
    print("Promoting any deferred import in those clusters to module scope would")
    print("create a real cycle. dlux/tests/test_import_graph.py guards both facts.")
    return 1 if result['module_scope_cycles'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
