"""``dlux startproject`` — render a complete Compose project."""
import secrets
import sys
from datetime import date
from pathlib import Path

from .. import __version__
from ._shared import (
    ScaffoldError,
    _normalize_identifier,
    _normalize_repo_slug,
    _prepare_root,
    _prompt,
    _write_rendered,
    split_image_reference,
)

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
