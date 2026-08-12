"""Shared scaffolding primitives: paths, prompts, template rendering.

``PACKAGE_ROOT`` is the *dlux* package, not this sub-package — the scaffold
templates live beside it, and this module is one level deeper than the module it
was split out of.
"""
import re
import stat
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = Path(__file__).resolve().parent / "templates"

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
