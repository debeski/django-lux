import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
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


def split_image_reference(reference, default_tag="latest"):
    """Split ``name[:tag]`` into ``(name, tag)``.

    Registry hosts may carry a port (``registry:5000/team/app``), so only a colon
    after the final slash is a tag separator.
    """
    value = str(reference or "").strip().rstrip("/")
    if not value:
        raise ScaffoldError("Docker image name must not be empty")
    head, _, tail = value.rpartition("/")
    if ":" in tail:
        name_tail, _, tag = tail.rpartition(":")
        if not name_tail:
            raise ScaffoldError(f"Invalid Docker image reference: {reference!r}")
        name = f"{head}/{name_tail}" if head else name_tail
        tag = tag.strip() or default_tag
    else:
        name = value
        tag = default_tag
    if any(char.isspace() for char in name) or any(char.isspace() for char in tag):
        raise ScaffoldError(f"Invalid Docker image reference: {reference!r}")
    return name, tag


def _normalize_repo_slug(repo):
    """``owner/name`` for the release URL, or '' when the project has no remote yet."""
    value = str(repo or "").strip().strip("/")
    if not value:
        return ""
    value = re.sub(r"^(?:https?://)?(?:www\.)?github\.com/", "", value)
    value = re.sub(r"\.git$", "", value)
    if value.count("/") != 1 or not all(part.strip() for part in value.split("/")):
        raise ScaffoldError(f"GitHub repository must be 'owner/name', got {repo!r}")
    return value


def _prompt(label, default, *, enabled):
    if not enabled:
        return default
    try:
        answer = input(f"{label} [{default or 'skip'}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        return default
    return answer or default


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


def create_project(project_name, destination=None, image=None, repo=None, interactive=None):
    """Scaffold a project.

    ``image`` is the Docker reference the deployment pulls and the release
    workflow pushes (``name`` or ``name:tag``); ``repo`` is the ``owner/name``
    GitHub slug used for the release URL. Both are prompted for on a TTY when
    omitted, because leaving the image as the bare project name produces a
    reference that exists in no registry — update discovery then silently never
    fires.
    """
    normalized_project_name = _normalize_identifier(project_name, "project_name")
    config_package = "config"
    target_root = Path(destination) if destination else Path(normalized_project_name)
    target_root = target_root.resolve()

    if interactive is None:
        interactive = sys.stdin.isatty() and (image is None or repo is None)
    if interactive:
        print(f"Configuring release settings for {project_name} (press Enter to accept).")
    image = _prompt(
        "Docker image (name[:tag])",
        image or normalized_project_name.lower(),
        enabled=interactive and image is None,
    )
    repo = _prompt(
        "GitHub repository (owner/name, blank to skip)",
        repo or "",
        enabled=interactive and repo is None,
    )

    project_image, project_image_tag = split_image_reference(image)
    github_repo = _normalize_repo_slug(repo)

    _prepare_root(target_root)

    context = {
        "project_name": project_name,
        "project_package": normalized_project_name,
        "config_package": config_package,
        "project_title": normalized_project_name.replace("_", " ").title(),
        "project_slug": normalized_project_name,
        "project_image": project_image,
        "project_image_tag": project_image_tag,
        # A visible placeholder rather than an empty segment: the release
        # workflow's validator then fails loudly with the URL it expects.
        "github_repo": github_repo or "OWNER/REPO",
        "dlux_version": __version__,
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
        "project/tools/dlux_runtime_supervisor.py.tmpl": target_root / "tools" / "dlux_runtime_supervisor.py",
        "project/gunicorn.py.tmpl": target_root / "gunicorn.py",
        "project/requirements.txt.tmpl": target_root / "requirements.txt",
        "project/release-manifest.json.tmpl": target_root / "release-manifest.json",
        "project/.github/workflows/release.yml.tmpl": target_root / ".github" / "workflows" / "release.yml",
        "project/tools/validate_project_release_manifest.py.tmpl": (
            target_root / "tools" / "validate_project_release_manifest.py"
        ),
        # Reverse proxy configs live in .proxy/ (proxy-agnostic) alongside the
        # shared maintenance.html. Caddy is the active proxy; nginx is a
        # commented-out fallback in compose.yml. The nginx `default.conf.template`
        # relies on the official nginx image's envsubst startup rendering
        # (${NGINX_*} → /etc/nginx/conf.d/), so it carries both suffixes —
        # `.template` (nginx) inside `.tmpl` (scaffold).
        "project/.proxy/Caddyfile.tmpl": target_root / ".proxy" / "Caddyfile",
        "project/.proxy/default.conf.template.tmpl": target_root / ".proxy" / "default.conf.template",
        "project/.proxy/maintenance.html.tmpl": target_root / ".proxy" / "maintenance.html",
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


UPDATER_COMPOSE_START = "# DjangoLux updater start"
UPDATER_COMPOSE_END = "# DjangoLux updater end"


def _replace_once(contents, old, new, label):
    if contents.count(old) != 1:
        raise ScaffoldError(f"Refusing ambiguous/custom {label}; expected one generated anchor")
    return contents.replace(old, new, 1)


def _compose_service(contents, service_name):
    pattern = re.compile(
        rf"(?ms)^  {re.escape(service_name)}:\n.*?(?=^  [A-Za-z0-9_-]+:\n|^volumes:\n|\Z)",
    )
    match = pattern.search(contents)
    if not match:
        raise ScaffoldError(f"Refusing custom Compose layout; service {service_name!r} was not recognized")
    return match


def _replace_compose_service(contents, service_name, transform):
    match = _compose_service(contents, service_name)
    updated = transform(match.group(0))
    return contents[:match.start()] + updated + contents[match.end():]


def _updater_service_block(project_slug):
    return f'''  {UPDATER_COMPOSE_START}
  dlux-updater:
    image: ${{WEB_IMAGE:-{project_slug.lower()}:latest}}
    restart: always
    labels:
      org.dlux.restart: "protected"
    command: ["python", "-m", "tools.dlux_runtime_supervisor", "--no-watch", "--", "bash", "-c", "python manage.py migrator && exec python manage.py dlux_update_worker"]
    entrypoint: ["/app/entrypoint.sh"]
    volumes:
      - dlux_runtime:/opt/dlux-runtime:rw
      - static:/app/staticfiles:rw
      - ./media/:/app/media:rw
      - ./logs/:/app/logs:rw
    environment:
      <<: *de
      POSTGRES_USER: ${{POSTGRES_USER:-admin}}
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD:-admin_pass}}
      DJANGO_SECRET_KEY: ${{DJANGO_SECRET_KEY:-local_secret}}
      ADMIN_PASS: ${{ADMIN_PASS:-admin}}
    healthcheck:
      test: ["CMD", "python", "-m", "dlux.updater.health"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 60s
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - {project_slug}_internal
      - dlux_update_egress
  {UPDATER_COMPOSE_END}

'''


def _enable_updater_compose(contents, project_slug, config_package):
    if UPDATER_COMPOSE_START in contents:
        if UPDATER_COMPOSE_END not in contents or "  dlux-updater:\n" not in contents:
            raise ScaffoldError("The existing DjangoLux updater Compose block is incomplete")
        return contents
    required_services = ("db", "redis", "smtp-relay", "nginx", "web", "celery")
    for service in required_services:
        _compose_service(contents, service)
    contents = _replace_once(
        contents,
        '  DEBUG_STATUS: "${DEBUG_STATUS:-False}"\n',
        '  DEBUG_STATUS: "${DEBUG_STATUS:-False}"\n'
        '  # DjangoLux verified inline updater (generated Compose deployments only)\n'
        '  DLUX_INLINE_UPDATES_ENABLED: "True"\n'
        '  DLUX_UPDATE_CHECK_INTERVAL: "${DLUX_UPDATE_CHECK_INTERVAL:-86400}"\n'
        '  DLUX_UPDATE_RUNTIME_ROOT: "/opt/dlux-runtime"\n',
        "Compose environment",
    )
    contents = _replace_once(
        contents,
        "  nginx:\n",
        _updater_service_block(project_slug) + "  nginx:\n",
        "nginx service anchor",
    )

    def nginx(section):
        section = _replace_once(
            section,
            "      - ./media/:/app/media:ro\n",
            "      - ./media/:/app/media:ro\n"
            "      - dlux_runtime:/opt/dlux-runtime:ro\n"
            "      - ./.nginx/maintenance.html:/usr/share/nginx/html/dlux-maintenance.html:ro\n",
            "nginx volumes",
        )
        return section

    def web(section):
        section = _replace_once(
            section,
            "      bash -c ' if [ \"$$DEBUG_STATUS\" = \"True\" ]; then\n",
            "      python -m tools.dlux_runtime_supervisor -- bash -c ' if [ \"$$DEBUG_STATUS\" = \"True\" ]; then\n",
            "web command",
        )
        section = section.replace(
            "    post_start:\n      - command: python manage.py migrator\n",
            "",
            1,
        )
        section = _replace_once(
            section,
            "      - ./imports/:/app/imports:ro\n",
            "      - ./imports/:/app/imports:ro\n      - dlux_runtime:/opt/dlux-runtime:ro\n",
            "web volumes",
        )
        section = _replace_once(
            section,
            "      smtp-relay:\n        condition: service_healthy\n",
            "      smtp-relay:\n        condition: service_healthy\n"
            "      dlux-updater:\n        condition: service_healthy\n",
            "web dependencies",
        )
        section = _replace_once(
            section,
            '      test: [ "CMD", "python", "manage.py", "check" ]\n',
            '      test: ["CMD", "python", "-c", "import urllib.request; '
            "urllib.request.urlopen('http://127.0.0.1:8000/health/', timeout=5).read()\"]\n",
            "web health check",
        )
        return section

    def celery(section):
        old_command = (
            f'    command: ["python", "-m", "celery", "-A", "{config_package}", '
            '"worker", "-B", "--loglevel=info"]\n'
        )
        new_command = (
            f'    command: ["python", "-m", "tools.dlux_runtime_supervisor", "--", '
            f'"python", "-m", "celery", "-A", "{config_package}", "worker", "-B", "--loglevel=info"]\n'
        )
        section = _replace_once(section, old_command, new_command, "Celery command")
        section = _replace_once(
            section,
            "      - ./logs/:/app/logs:rw\n",
            "      - ./logs/:/app/logs:rw\n      - dlux_runtime:/opt/dlux-runtime:ro\n",
            "Celery volumes",
        )
        section = _replace_once(
            section,
            "      redis:\n        condition: service_healthy\n",
            "      redis:\n        condition: service_healthy\n"
            "      dlux-updater:\n        condition: service_healthy\n",
            "Celery dependencies",
        )
        return section

    contents = _replace_compose_service(contents, "nginx", nginx)
    contents = _replace_compose_service(contents, "web", web)
    contents = _replace_compose_service(contents, "celery", celery)
    contents = _replace_once(contents, "  static:\n\nnetworks:\n", "  static:\n  dlux_runtime:\n\nnetworks:\n", "Compose volumes")
    contents = _replace_once(
        contents,
        f"  {project_slug}_internal:\n    internal: true",
        f"  {project_slug}_internal:\n    internal: true\n  dlux_update_egress:\n    driver: bridge",
        "Compose networks",
    )
    return contents


def _enable_updater_dev_compose(contents):
    if "  dlux-updater:\n" in contents:
        return contents
    _compose_service(contents, "smtp-relay")
    _compose_service(contents, "web")
    _compose_service(contents, "celery")
    contents = _replace_once(
        contents,
        "  nginx:\n",
        "  dlux-updater:\n"
        "    build: .\n"
        "    image: !reset null\n"
        "    volumes: !override\n"
        "      - ./:/app:rw\n"
        "      - dlux_runtime:/opt/dlux-runtime:rw\n"
        "      - static:/app/staticfiles:rw\n"
        "      - ./media/:/app/media/:rw\n"
        "      - ./logs/:/app/logs:rw\n\n"
        "  nginx:\n",
        "development Compose nginx anchor",
    )

    def add_runtime(section):
        anchor = "      - ./logs/:/app/logs:rw"
        if section.count(anchor) != 1:
            raise ScaffoldError(
                "Refusing ambiguous/custom development runtime volume; expected one generated anchor"
            )
        suffix = "\n" if section.endswith("\n") else ""
        return section.replace(
            anchor + suffix,
            anchor + "\n      - dlux_runtime:/opt/dlux-runtime:ro" + suffix,
            1,
        )

    contents = _replace_compose_service(contents, "web", add_runtime)
    contents = _replace_compose_service(contents, "celery", add_runtime)
    return contents


def _enable_updater_nginx(contents):
    if "dlux-maintenance.html" in contents and "/_update/status.json" in contents:
        return contents
    if "dlux-maintenance.html" not in contents:
        contents = _replace_once(
            contents,
            "    client_max_body_size 5M;\n",
            "    client_max_body_size 5M;\n"
            "    error_page 502 503 504 =503 /dlux-maintenance.html;\n\n"
            "    location = /dlux-maintenance.html {\n"
            "        root /usr/share/nginx/html;\n"
            "        internal;\n"
            "    }\n",
            "nginx server",
        )
    contents = _replace_once(
        contents,
        "    location / {\n",
        "    location = /_update/status.json {\n"
        "        alias /opt/dlux-runtime/state/deploy-status.json;\n"
        "        default_type application/json;\n"
        "        add_header Cache-Control \"no-store\";\n"
        "        add_header X-Robots-Tag \"noindex\";\n"
        "    }\n\n"
        "    location = /_update/log.txt {\n"
        "        alias /opt/dlux-runtime/state/deploy-log.txt;\n"
        "        default_type text/plain;\n"
        "        add_header Cache-Control \"no-store\";\n"
        "        add_header X-Robots-Tag \"noindex\";\n"
        "    }\n\n"
        "    location / {\n",
        "nginx update status endpoints",
    )
    if "location / {\n        if (-f /opt/dlux-runtime/state/maintenance)" not in contents:
        contents = _replace_once(
            contents,
            "    location / {\n        proxy_pass http://web:8000;\n",
            "    location / {\n"
            "        if (-f /opt/dlux-runtime/state/maintenance) { return 503; }\n"
            "        proxy_pass http://web:8000;\n",
            "nginx web proxy",
        )
    if "location /health {\n        if (-f /opt/dlux-runtime/state/maintenance)" not in contents:
        contents = _replace_once(
            contents,
            "    location /health {\n        proxy_pass http://web:8000/health/;\n",
            "    location /health {\n"
            "        if (-f /opt/dlux-runtime/state/maintenance) { return 503; }\n"
            "        proxy_pass http://web:8000/health/;\n",
            "nginx health proxy",
        )
    return contents


def _bootstrap_backup_root(project_root):
    base = project_root / ".xpose" / "dlux-updater-bootstrap"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = base / stamp
    suffix = 1
    while destination.exists():
        suffix += 1
        destination = base / f"{stamp}-{suffix}"
    return destination


def enable_agent(
    project_root=None,
    *,
    apply=False,
    compose_file="",
    allow_unverified_dlux=False,
    command_runner=subprocess.run,
):
    project_root = Path(project_root or Path.cwd()).resolve()
    _resolve_project_files(project_root)
    command = []
    shell_wrapper = project_root / "start.sh"
    powershell_wrapper = project_root / "start.ps1"
    if os.name != "nt" and shell_wrapper.is_file():
        command = [str(shell_wrapper), "enable-agent"]
    elif os.name == "nt" and powershell_wrapper.is_file():
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell:
            command = [powershell, "-NoProfile", "-File", str(powershell_wrapper), "enable-agent"]
    if not command:
        composer = shutil.which("composer")
        if composer:
            command = [composer, "enable-agent", "--project-dir", str(project_root)]
    if not command:
        raise ScaffoldError(
            "Composer v1.2.0+ is required; pull it through start.sh or install the composer command"
        )
    if apply:
        command.append("--apply")
    if compose_file:
        command.extend(["--file", compose_file])
    if allow_unverified_dlux:
        command.append("--allow-unverified-dlux")
    command.append("--json")
    completed = command_runner(
        command,
        cwd=str(project_root),
        check=False,
        capture_output=True,
        text=True,
    )
    payload = None
    for line in reversed(str(completed.stdout or "").splitlines()):
        try:
            candidate = json.loads(line)
        except ValueError:
            continue
        if isinstance(candidate, dict):
            payload = candidate
            break
    if completed.returncode != 0 or payload is None or payload.get("error"):
        detail = (payload or {}).get("error") or str(completed.stderr or "").strip()
        raise ScaffoldError(detail or "Composer enable-agent forwarding failed")
    return payload


def enable_updater(project_root=None, *, apply=False, command_runner=subprocess.run):
    project_root = Path(project_root or Path.cwd()).resolve()
    settings_path, _urls_path = _resolve_project_files(project_root)
    manage_contents = (project_root / "manage.py").read_text(encoding="utf-8")
    if "Generated with django-lux" not in manage_contents:
        raise ScaffoldError("enable-updater supports only recognized DjangoLux-generated projects")
    config_package = settings_path.parent.name
    paths = {
        "compose.yml": project_root / "compose.yml",
        "compose.dev.yml": project_root / "compose.dev.yml",
        ".nginx/nginx.conf": project_root / ".nginx" / "nginx.conf",
        "requirements.txt": project_root / "requirements.txt",
    }
    for relative, path in paths.items():
        if not path.is_file():
            raise ScaffoldError(f"Generated project file is missing: {relative}")
    compose = paths["compose.yml"].read_text(encoding="utf-8")
    name_match = re.search(r"(?m)^name:\s*([A-Za-z0-9_-]+)\s*$", compose)
    if not name_match:
        raise ScaffoldError("Could not determine the generated Compose project name")
    project_slug = name_match.group(1)
    updated = {
        "compose.yml": _enable_updater_compose(compose, project_slug, config_package),
        "compose.dev.yml": _enable_updater_dev_compose(paths["compose.dev.yml"].read_text(encoding="utf-8")),
        ".nginx/nginx.conf": _enable_updater_nginx(paths[".nginx/nginx.conf"].read_text(encoding="utf-8")),
    }
    requirements = paths["requirements.txt"].read_text(encoding="utf-8")
    matches = re.findall(r"(?m)^django-lux(?:\[updater\])?==[^\s]+$", requirements)
    if len(matches) != 1:
        raise ScaffoldError("requirements.txt must contain one exact generated django-lux pin")
    updated["requirements.txt"] = requirements.replace(
        matches[0], f"django-lux[updater]=={__version__}", 1,
    )
    additions = {
        "tools/dlux_runtime_supervisor.py": _render_template(
            "project/tools/dlux_runtime_supervisor.py.tmpl", {},
        ),
        ".nginx/maintenance.html": _render_template(
            "project/.proxy/maintenance.html.tmpl", {},
        ),
    }
    for relative, content in additions.items():
        destination = project_root / relative
        if destination.exists() and destination.read_text(encoding="utf-8") != content:
            raise ScaffoldError(f"Refusing to overwrite custom updater file: {relative}")

    changed = [relative for relative, content in updated.items() if paths[relative].read_text(encoding="utf-8") != content]
    changed.extend(relative for relative in additions if not (project_root / relative).exists())
    rebuild_command = (
        f"docker build -t ${{WEB_IMAGE:-{project_slug.lower()}:latest}} . && "
        "docker compose up -d --force-recreate dlux-updater web celery smtp-relay nginx"
    )
    if not apply:
        return {"applied": False, "files": changed, "command": rebuild_command, "backup_root": ""}

    if not shutil.which("docker"):
        raise ScaffoldError("Docker is required to validate the generated Compose configuration")
    probe = command_runner(
        ["docker", "compose", "version"],
        cwd=str(project_root),
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        raise ScaffoldError("Docker Compose v2 is required to apply the updater bootstrap")
    backup_root = _bootstrap_backup_root(project_root)
    if changed:
        for relative in updated:
            source = paths[relative]
            if source.read_text(encoding="utf-8") == updated[relative]:
                continue
            backup = backup_root / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, backup)
            source.write_text(updated[relative], encoding="utf-8", newline="\n")
        for relative, content in additions.items():
            destination = project_root / relative
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8", newline="\n")
    validation = command_runner(
        ["docker", "compose", "config"],
        cwd=str(project_root),
        check=False,
        capture_output=True,
        text=True,
    )
    if validation.returncode != 0:
        raise ScaffoldError(
            f"docker compose config failed; timestamped originals remain at {backup_root}"
        )
    return {
        "applied": True,
        "files": changed,
        "command": rebuild_command,
        "backup_root": str(backup_root) if changed else "",
    }
