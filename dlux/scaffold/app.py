"""``dlux startapp`` — render an app and register it in the project."""
import re
from pathlib import Path

from ._shared import (
    ScaffoldError,
    _normalize_identifier,
    _resolve_project_files,
    _write_rendered,
)

def _camel_case(name):
    return "".join(part.capitalize() for part in name.split("_"))

def _ensure_url_imports(contents):
    match = re.search(r"^from django\.urls import ([^\n]+)$", contents, re.MULTILINE)
    if not match:
        raise ScaffoldError("Could not safely update urls.py import line")

    tokens = [token.strip() for token in match.group(1).split(",") if token.strip()]
    for required in ("include", "path"):
        if required not in tokens:
            tokens.append(required)

    ordered = []
    for preferred in ("include", "path"):
        if preferred in tokens:
            ordered.append(preferred)
    ordered.extend(token for token in tokens if token not in ordered)

    new_line = "from django.urls import " + ", ".join(ordered)
    return contents[:match.start()] + new_line + contents[match.end():]

def _upsert_list_block(contents, list_name, entries, start_marker, end_marker):
    pattern = re.compile(
        rf"(?ms)^({list_name}\s*=\s*\[\n)(.*?)(^\])",
    )
    match = pattern.search(contents)
    if not match:
        raise ScaffoldError(f"Could not safely update {list_name}")

    body = match.group(2)
    block = None

    if start_marker in body and end_marker in body:
        pre, rest = body.split(start_marker, 1)
        existing_block, post = rest.split(end_marker, 1)
        current_entries = []
        for line in existing_block.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            current_entries.append(stripped)
        for entry in entries:
            if entry not in current_entries:
                current_entries.append(entry)
        block = (
            f"    {start_marker}\n"
            + "".join(f"    {entry}\n" for entry in current_entries)
            + f"    {end_marker}\n"
        )
        new_body = pre.rstrip("\n")
        if new_body:
            new_body += "\n"
        new_body += block
        if post.strip():
            new_body += post if post.startswith("\n") else f"\n{post}"
    else:
        new_body = body
        if new_body and not new_body.endswith("\n"):
            new_body += "\n"
        new_body += (
            f"    {start_marker}\n"
            + "".join(f"    {entry}\n" for entry in entries)
            + f"    {end_marker}\n"
        )

    return (
        contents[:match.start()]
        + match.group(1)
        + new_body
        + match.group(3)
        + contents[match.end(3):]
    )

def _register_app(project_root, app_name):
    settings_path, urls_path = _resolve_project_files(project_root)

    settings_contents = settings_path.read_text(encoding="utf-8")
    updated_settings = _upsert_list_block(
        settings_contents,
        "INSTALLED_APPS",
        [f'"{app_name}",'],
        "# DjangoLux generated apps start",
        "# DjangoLux generated apps end",
    )

    urls_contents = urls_path.read_text(encoding="utf-8")
    updated_urls = _upsert_list_block(
        _ensure_url_imports(urls_contents),
        "urlpatterns",
        [
            (
                f'path("{app_name}/", include(("{app_name}.urls", "{app_name}"), '
                f'namespace="{app_name}")),'
            )
        ],
        "# DjangoLux generated routes start",
        "# DjangoLux generated routes end",
    )

    settings_path.write_text(updated_settings, encoding="utf-8", newline="\n")
    urls_path.write_text(updated_urls, encoding="utf-8", newline="\n")

def create_app(app_name, register=False):
    normalized_app_name = _normalize_identifier(app_name, "app_name")
    project_root = Path.cwd().resolve()
    if not (project_root / "manage.py").exists():
        raise ScaffoldError("Current directory does not contain manage.py")
    app_root = project_root / normalized_app_name

    if app_root.exists():
        raise ScaffoldError(f"App directory already exists: {app_root}")

    context = {
        "app_name": normalized_app_name,
        "app_title": normalized_app_name.replace("_", " ").title(),
        "app_config_class": f"{_camel_case(normalized_app_name)}Config",
    }

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
        "app/templates/example_record_list.html.tmpl": app_root / "templates" / normalized_app_name / "example_record_list.html",
        "app/templates/example_record_form.html.tmpl": app_root / "templates" / normalized_app_name / "example_record_form.html",
    }

    for template_name, destination_path in writes.items():
        _write_rendered(template_name, destination_path, context)

    if register:
        _register_app(project_root, normalized_app_name)

    return app_root
