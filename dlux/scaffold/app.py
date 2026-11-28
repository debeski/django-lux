"""``dlux startapp`` — render an app and register it in the project.

Registration is planned before anything is written: settings.py and urls.py are
parsed with ``ast``, both edits are computed, and the app's files are written
only when both edits are known to apply. The two files keep their line endings
and are written together or not at all.
"""
import ast
import os
import sys
from importlib.util import find_spec
from pathlib import Path

from ._shared import (
    ScaffoldError,
    _plain_identifier,
    _resolve_project_files,
    _write_rendered,
)

APPS_START = "# DjangoLux generated apps start"
APPS_END = "# DjangoLux generated apps end"
ROUTES_START = "# DjangoLux generated routes start"
ROUTES_END = "# DjangoLux generated routes end"

# Labels Django's contrib apps and the scaffold's own apps use; a second app with
# one of them stops Django at start-up ("Application labels aren't unique").
RESERVED_APP_LABELS = frozenset({
    "admin", "admindocs", "auth", "contenttypes", "flatpages", "gis", "humanize", "messages",
    "postgres", "redirects", "sessions", "sitemaps", "sites", "staticfiles", "syndication",
    "dlux", "corsheaders", "csp", "health_check", "db", "django_filters", "django_tables2",
    "crispy_forms", "crispy_bootstrap5", "config",
})

def _camel_case(name):
    return "".join(part.capitalize() for part in name.split("_"))

def _top_level_assignment(tree, name):
    """The last top-level ``name = ...`` statement (the one Django sees)."""
    found = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            found = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            found = node
    return found

def _parse(contents, label):
    try:
        return ast.parse(contents)
    except SyntaxError as exc:
        raise ScaffoldError(f"{label} is not valid Python (line {exc.lineno}); fix it first") from exc

def _installed_app_labels(settings_path):
    """The default labels of the dotted entries in the project's INSTALLED_APPS."""
    try:
        tree = ast.parse(settings_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return set()
    node = _top_level_assignment(tree, "INSTALLED_APPS")
    if node is None or not isinstance(node.value, (ast.List, ast.Tuple)):
        return set()
    labels = set()
    for element in node.value.elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            parts = element.value.split(".")
            labels.add(parts[-3] if len(parts) >= 3 and parts[-2] == "apps" else parts[-1])
    return labels

def _check_app_name(name, project_root, settings_path=None):
    """Refuse a name that is already an app label or an importable module."""
    if name in RESERVED_APP_LABELS or (settings_path and name in _installed_app_labels(settings_path)):
        raise ScaffoldError(f"app_name {name!r} is already the label of a Django or DjangoLux app")
    shadowed = name in sys.stdlib_module_names
    if not shadowed:
        # The project root is on sys.path at runtime; only modules found elsewhere are shadowed.
        root = os.path.realpath(project_root)
        saved_path = sys.path[:]
        sys.path[:] = [entry for entry in sys.path if os.path.realpath(entry or ".") != root]
        try:
            shadowed = find_spec(name) is not None
        except (ImportError, ValueError):
            shadowed = True
        finally:
            sys.path[:] = saved_path
    if shadowed:
        raise ScaffoldError(
            f"app_name {name!r} is already an importable module (the standard library or an "
            "installed package); an app with that name would hide it. Choose another name."
        )

def _offset(lines, lineno, col_offset):
    """The character offset of an ``ast`` position (``col_offset`` counts UTF-8 bytes)."""
    line = lines[lineno - 1]
    return sum(len(text) for text in lines[:lineno - 1]) + len(line.encode("utf-8")[:col_offset].decode("utf-8"))

def _ensure_url_imports(contents):
    """Make ``include`` and ``path`` importable from ``django.urls`` in a urls.py source."""
    tree = _parse(contents, "urls.py")
    imports = [
        node for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "django.urls" and node.level == 0
    ]
    bound = {alias.name for node in imports for alias in node.names if alias.asname is None}
    missing = [name for name in ("include", "path") if name not in bound]
    if not missing:
        return contents

    lines = contents.splitlines(keepends=True)
    single = next((node for node in imports if node.lineno == node.end_lineno
                   and all(alias.name != "*" for alias in node.names)), None)
    if single is not None:
        line = lines[single.lineno - 1]
        names = [alias.name if alias.asname is None else f"{alias.name} as {alias.asname}" for alias in single.names]
        ordered = [name for name in ("include", "path") if name in bound or name in missing]
        ordered += [name for name in names if name not in ordered]
        ending = line[len(line.rstrip("\r\n")):] or "\n"
        indent = line[:len(line) - len(line.lstrip())]
        lines[single.lineno - 1] = f"{indent}from django.urls import {', '.join(ordered)}{ending}"
        return "".join(lines)

    # A multi-line import stays as it is; the missing names get a line of their own after it.
    anchors = imports or [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    after = anchors[-1].end_lineno if anchors else 0
    if after == 0 and ast.get_docstring(tree, clean=False) is not None:
        after = tree.body[0].end_lineno
    if after and not lines[after - 1].endswith("\n"):
        lines[after - 1] += "\n"
    lines.insert(after, f"from django.urls import {', '.join(missing)}\n")
    return "".join(lines)

def _missing_comma(contents, elements, ends, position):
    """Where a comma is missing after the last element before ``position``, if one is."""
    before = [end for end in ends if end <= position]
    if not elements or not before:
        return None
    end = before[-1]
    code = "".join(line.split("#", 1)[0] for line in contents[end:position].splitlines(keepends=True))
    return None if "," in code else end

def _upsert_list_block(contents, list_name, entries, start_marker, end_marker):
    """Add ``entries`` between the markers inside the top-level ``list_name = [...]``."""
    tree = _parse(contents, f"The file defining {list_name}")
    node = _top_level_assignment(tree, list_name)
    if node is None:
        raise ScaffoldError(f"Could not safely update {list_name}: no top-level '{list_name} = [...]' found")
    if not isinstance(node.value, ast.List):
        kind = type(node.value).__name__.lower()
        raise ScaffoldError(
            f"Could not safely update {list_name}: it is a {kind}, not a list. Make it a list "
            f"('{list_name} = [...]') and run the command again."
        )
    lines = contents.splitlines(keepends=True)
    list_start = _offset(lines, node.value.lineno, node.value.col_offset)
    list_end = _offset(lines, node.value.end_lineno, node.value.end_col_offset)
    literal = contents[list_start:list_end]
    if "\n" not in literal:
        raise ScaffoldError(
            f"Could not safely update {list_name}: write it over several lines, with its closing ']' on a line of its own"
        )
    has_start, has_end = start_marker in literal, end_marker in literal
    if has_start != has_end:
        present, absent = (start_marker, end_marker) if has_start else (end_marker, start_marker)
        raise ScaffoldError(
            f"Could not safely update {list_name}: it has the line '{present}' but not '{absent}'. "
            "Restore the missing marker line and run the command again."
        )

    insert_at = list_start + literal.index(start_marker) if has_start else list_end - 1
    ends = [_offset(lines, element.end_lineno, element.end_col_offset) for element in node.value.elts]
    comma_at = _missing_comma(contents, node.value.elts, ends, insert_at)
    if comma_at is not None:
        return _upsert_list_block(contents[:comma_at] + "," + contents[comma_at:],
                                  list_name, entries, start_marker, end_marker)

    body = literal[1:-1]
    if has_start:
        pre, rest = body.split(start_marker, 1)
        existing_block, post = rest.split(end_marker, 1)
        current_entries = []
        for line in existing_block.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                current_entries.append(stripped)
        current_entries += [entry for entry in entries if entry not in current_entries]
        new_body = (
            pre.rstrip(" ")
            + f"    {start_marker}\n"
            + "".join(f"    {entry}\n" for entry in current_entries)
            + f"    {end_marker}"
            + post
        )
    else:
        head = body.rstrip(" ")
        if not head.endswith("\n"):
            head += "\n"
        new_body = (
            head
            + f"    {start_marker}\n"
            + "".join(f"    {entry}\n" for entry in entries)
            + f"    {end_marker}\n"
        )
    updated = contents[:list_start] + "[" + new_body + "]" + contents[list_end:]
    _parse(updated, f"The updated {list_name}")
    return updated

def _read_source(path):
    """``(text with \\n line endings, the file's own line ending)``."""
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline

def _plan_registration(project_root, app_name):
    """``[(path, new contents)]`` for settings.py and urls.py; raises before anything is written."""
    settings_path, urls_path = _resolve_project_files(project_root)
    try:
        settings_contents, settings_newline = _read_source(settings_path)
        urls_contents, urls_newline = _read_source(urls_path)
    except (OSError, UnicodeDecodeError) as exc:
        raise ScaffoldError(f"Cannot read the project's settings.py or urls.py: {exc}") from exc

    updated_settings = _upsert_list_block(
        settings_contents, "INSTALLED_APPS", [f'"{app_name}",'], APPS_START, APPS_END,
    )
    updated_urls = _upsert_list_block(
        _ensure_url_imports(urls_contents),
        "urlpatterns",
        [f'path("{app_name}/", include(("{app_name}.urls", "{app_name}"), namespace="{app_name}")),'],
        ROUTES_START,
        ROUTES_END,
    )
    planned = []
    for path, original, updated, newline in (
        (settings_path, settings_contents, updated_settings, settings_newline),
        (urls_path, urls_contents, updated_urls, urls_newline),
    ):
        if updated == original:
            continue
        if not os.access(path, os.W_OK):
            raise ScaffoldError(f"Cannot register the app: {path} is not writable")
        planned.append((path, updated.replace("\n", newline)))
    return planned

def _apply_registration(planned):
    """Write every planned file, or put back the ones already written and raise."""
    written = []
    try:
        for path, contents in planned:
            original = path.read_bytes()
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(contents)
            written.append((path, original))
    except OSError as exc:
        for path, original in reversed(written):
            path.write_bytes(original)
        raise ScaffoldError(f"Cannot register the app: {exc}; settings.py and urls.py are unchanged") from exc

def _register_app(project_root, app_name):
    _apply_registration(_plan_registration(project_root, app_name))

def create_app(app_name, register=False):
    normalized_app_name = _plain_identifier(app_name, "app_name")
    project_root = Path.cwd().resolve()
    if not (project_root / "manage.py").exists():
        raise ScaffoldError("Current directory does not contain manage.py")
    app_root = project_root / normalized_app_name

    if app_root.exists():
        raise ScaffoldError(f"App directory already exists: {app_root}")

    try:
        settings_path = _resolve_project_files(project_root)[0]
    except ScaffoldError:
        if register:
            raise
        settings_path = None
    _check_app_name(normalized_app_name, project_root, settings_path)
    planned = _plan_registration(project_root, normalized_app_name) if register else []

    # Model names carry the app's name, so two generated apps never clash on
    # Scope's reverse accessors (scope.<model>_set).
    model_prefix = _camel_case(normalized_app_name)
    record_model = f"{model_prefix}Record"
    context = {
        "app_name": normalized_app_name,
        "app_title": normalized_app_name.replace("_", " ").title(),
        "app_config_class": f"{model_prefix}Config",
        "model_prefix": model_prefix,
        "record_model": record_model,
        "record_model_lower": record_model.lower(),
    }

    templates_dir = app_root / "templates" / normalized_app_name
    writes = {
        "app/__init__.py.tmpl": app_root / "__init__.py",
        "app/apps.py.tmpl": app_root / "apps.py",
        "app/models.py.tmpl": app_root / "models.py",
        "app/forms.py.tmpl": app_root / "forms.py",
        "app/tables.py.tmpl": app_root / "tables.py",
        "app/filters.py.tmpl": app_root / "filters.py",
        "app/views.py.tmpl": app_root / "views.py",
        "app/urls.py.tmpl": app_root / "urls.py",
        "app/translations.py.tmpl": app_root / "translations.py",
        "app/README.md.tmpl": app_root / "README.md",
        "app/migrations/__init__.py.tmpl": app_root / "migrations" / "__init__.py",
        "app/tests/__init__.py.tmpl": app_root / "tests" / "__init__.py",
        "app/tests/test_app.py.tmpl": app_root / "tests" / f"test_{normalized_app_name}.py",
        "app/templates/example_record_list.html.tmpl": templates_dir / "example_record_list.html",
        "app/templates/example_record_form.html.tmpl": templates_dir / "example_record_form.html",
        "app/templates/example_record_detail.html.tmpl": templates_dir / "example_record_detail.html",
        "app/templates/example_record_confirm_delete.html.tmpl": templates_dir / "example_record_confirm_delete.html",
    }

    for template_name, destination_path in writes.items():
        _write_rendered(template_name, destination_path, context)

    _apply_registration(planned)

    return app_root
