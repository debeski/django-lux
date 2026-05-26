import re
import secrets
from datetime import date
from pathlib import Path
import stat

from . import __version__


PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATES_ROOT = PACKAGE_ROOT / "scaffold_templates"


class ScaffoldError(RuntimeError):
    pass


def _normalize_identifier(raw_name, label):
    normalized = raw_name.replace("-", "_").strip()
    if not normalized or not normalized.isidentifier():
        raise ScaffoldError(f"{label} must be a valid Python identifier")
    return normalized


def _render_template(template_name, context):
    template_path = TEMPLATES_ROOT / template_name
    if not template_path.exists():
        raise ScaffoldError(f"Missing scaffold template: {template_name}")

    content = template_path.read_text(encoding="utf-8")
    for key, value in context.items():
        content = content.replace(f"{{{{ {key} }}}}", str(value))
    return content


def _write_rendered(template_name, destination, context):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ScaffoldError(f"Refusing to overwrite existing file: {destination}")
    destination.write_text(
        _render_template(template_name, context),
        encoding="utf-8",
        newline="\n",
    )
    if destination.name in {"start.sh", "entrypoint.sh"}:
        current_mode = destination.stat().st_mode
        destination.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _prepare_root(target_root):
    if target_root.exists():
        if target_root.is_file():
            raise ScaffoldError(f"Target path is a file: {target_root}")
        if any(target_root.iterdir()):
            raise ScaffoldError(f"Target directory is not empty: {target_root}")
    else:
        target_root.mkdir(parents=True, exist_ok=True)


def _camel_case(name):
    return "".join(part.capitalize() for part in name.split("_"))


def create_project(project_name, destination=None):
    normalized_project_name = _normalize_identifier(project_name, "project_name")
    config_package = "config"
    target_root = Path(destination) if destination else Path(normalized_project_name)
    target_root = target_root.resolve()

    _prepare_root(target_root)

    context = {
        "project_name": project_name,
        "project_package": normalized_project_name,
        "config_package": config_package,
        "project_title": normalized_project_name.replace("_", " ").title(),
        "project_slug": normalized_project_name,
        "project_image": normalized_project_name.lower(),
        "microsys_version": __version__,
        "generated_date": date.today().isoformat(),
        "secret_key": secrets.token_urlsafe(38),
    }

    writes = {
        "project/manage.py.tmpl": target_root / "manage.py",
        "project/dockerignore.tmpl": target_root / ".dockerignore",
        "project/gitattributes.tmpl": target_root / ".gitattributes",
        "project/gitignore.tmpl": target_root / ".gitignore",
        "project/.secrets/.env.tmpl": target_root / ".secrets" / ".env",
        "project/Dockerfile.tmpl": target_root / "Dockerfile",
        "project/compose.yml.tmpl": target_root / "compose.yml",
        "project/compose.dev.yml.tmpl": target_root / "compose.dev.yml",
        "project/entrypoint.sh.tmpl": target_root / "entrypoint.sh",
        "project/tools/smtp_relay.py.tmpl": target_root / "tools" / "smtp_relay.py",
        "project/gunicorn.py.tmpl": target_root / "gunicorn.py",
        "project/requirements.txt.tmpl": target_root / "requirements.txt",
        "project/.nginx/nginx.conf.tmpl": target_root / ".nginx" / "nginx.conf",
        "project/start.sh.tmpl": target_root / "start.sh",
        "project/start.ps1.tmpl": target_root / "start.ps1",
        "project/README.md.tmpl": target_root / "README.md",
        "project/docs/README.md.tmpl": target_root / "docs" / "README.md",
        "project/tests/__init__.py.tmpl": target_root / "tests" / "__init__.py",
        "project/tests/test_scaffold.py.tmpl": target_root / "tests" / "test_scaffold.py",
        "project/package/__init__.py.tmpl": target_root / config_package / "__init__.py",
        "project/package/asgi.py.tmpl": target_root / config_package / "asgi.py",
        "project/package/celery.py.tmpl": target_root / config_package / "celery.py",
        "project/package/settings.py.tmpl": target_root / config_package / "settings.py",
        "project/package/urls.py.tmpl": target_root / config_package / "urls.py",
        "project/package/wsgi.py.tmpl": target_root / config_package / "wsgi.py",
    }

    for template_name, destination_path in writes.items():
        _write_rendered(template_name, destination_path, context)

    return target_root


def _resolve_project_files(project_root):
    manage_py = project_root / "manage.py"
    if not manage_py.exists():
        raise ScaffoldError("Current directory does not contain manage.py")

    manage_contents = manage_py.read_text(encoding="utf-8")
    match = re.search(
        r"DJANGO_SETTINGS_MODULE[\"']\s*,\s*[\"']([^\"']+)[\"']",
        manage_contents,
    )
    if not match:
        raise ScaffoldError("Could not determine DJANGO_SETTINGS_MODULE from manage.py")

    settings_module = match.group(1)
    settings_path = project_root.joinpath(*settings_module.split(".")).with_suffix(".py")
    urls_path = settings_path.with_name("urls.py")

    if not settings_path.exists():
        raise ScaffoldError(f"Resolved settings.py does not exist: {settings_path}")
    if not urls_path.exists():
        raise ScaffoldError(f"Resolved urls.py does not exist: {urls_path}")

    return settings_path, urls_path


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
        "# MicroSys generated apps start",
        "# MicroSys generated apps end",
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
        "# MicroSys generated routes start",
        "# MicroSys generated routes end",
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
