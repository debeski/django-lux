"""Shared scaffolding primitives: paths, prompts, template rendering.

``PACKAGE_ROOT`` is the *dlux* package, not this sub-package — the scaffold
templates live beside it, and this module is one level deeper than the module it
was split out of.
"""
import keyword
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

def _plain_identifier(raw_name, label):
    """An ASCII identifier that starts with a letter and is not a Python keyword."""
    normalized = _normalize_identifier(raw_name, label)
    if not normalized.isascii():
        raise ScaffoldError(f"{label} {raw_name!r} must use only ASCII letters, digits, '-' and '_'")
    if not normalized[0].isalpha():
        raise ScaffoldError(f"{label} {raw_name!r} must start with a letter")
    if keyword.iskeyword(normalized):
        raise ScaffoldError(f"{label} {raw_name!r} is a Python keyword")
    return normalized

# `<name>_db` must fit PostgreSQL's 63-character identifiers, with room to spare.
PROJECT_NAME_MAX = 50
# Words YAML reads as a boolean or null, so `name: <slug>` in compose.yml would not be a string.
_YAML_SCALAR_WORDS = {"true", "false", "null"}
# Windows refuses these as file or folder names, whatever the extension.
_WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{n}" for n in range(1, 10)), *(f"lpt{n}" for n in range(1, 10))}

def _normalize_project_name(raw_name):
    """The project slug, refused when Compose, PostgreSQL or Windows cannot use it."""
    name = _plain_identifier(raw_name, "project_name")
    lowered = name.lower()
    if lowered in _YAML_SCALAR_WORDS:
        raise ScaffoldError(f"project_name {raw_name!r} reads as a YAML {lowered} value, so compose.yml could not name the project")
    if lowered in _WINDOWS_RESERVED:
        raise ScaffoldError(f"project_name {raw_name!r} is a reserved device name on Windows")
    if len(name) > PROJECT_NAME_MAX:
        raise ScaffoldError(
            f"project_name must be at most {PROJECT_NAME_MAX} characters, so the database name "
            f"<name>_db fits PostgreSQL's 63-character limit (got {len(name)})"
        )
    return name

# Docker's reference grammar (distribution/reference): path components are
# lowercase; the first component is a registry host when it has a '.' or ':',
# or is 'localhost', or has an uppercase letter.
_PATH_COMPONENT = re.compile(r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*")
_DOMAIN = re.compile(
    r"(?:[a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9])"
    r"(?:\.(?:[a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]))*"
    r"(?::[0-9]+)?"
)
_TAG = re.compile(r"[\w][\w.-]{0,127}", re.ASCII)
IMAGE_NAME_MAX = 255

def _validate_image_name(name, reference):
    invalid = ScaffoldError(f"Invalid Docker image reference: {reference!r} (expected name[:tag], "
                            "lowercase path, for example registry.example.com/team/app:1.0)")
    if len(name) > IMAGE_NAME_MAX:
        raise invalid
    components = name.split("/")
    first = components[0]
    if len(components) > 1 and ("." in first or ":" in first or first == "localhost" or first != first.lower()):
        if not _DOMAIN.fullmatch(first):
            raise invalid
        components = components[1:]
    if not all(_PATH_COMPONENT.fullmatch(component) for component in components):
        raise invalid

def split_image_reference(reference, default_tag="latest"):
    """Split ``name[:tag]`` into ``(name, tag)``.

    Registry hosts may carry a port (``registry:5000/team/app``), so only a colon
    after the final slash is a tag separator.
    """
    value = str(reference or "").strip().rstrip("/")
    if not value:
        raise ScaffoldError("Docker image name must not be empty")
    if "@" in value:
        raise ScaffoldError(f"Docker image reference {reference!r} names a digest; give name[:tag] instead")
    head, _, tail = value.rpartition("/")
    if ":" in tail:
        name_tail, _, tag = tail.rpartition(":")
        name = f"{head}/{name_tail}" if head else name_tail
        if not name_tail or not _TAG.fullmatch(tag):
            raise ScaffoldError(f"Invalid Docker image reference: {reference!r} (a tag is up to 128 "
                                "letters, digits, '_', '.' and '-', not starting with '.' or '-')")
    else:
        name = value
        tag = default_tag
    _validate_image_name(name, reference)
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

def _write_rendered(template_name, destination, context, *, mode=None):
    """Render ``template_name`` to a new file; ``mode`` is set before any content is written."""
    content = _render_template(template_name, context)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ScaffoldError(f"Refusing to overwrite existing file: {destination}")
        if mode is not None:
            destination.touch(mode=mode, exist_ok=False)
            destination.chmod(mode)
        destination.write_text(content, encoding="utf-8", newline="\n")
        if destination.name in {"start.sh", "entrypoint.sh"}:
            current_mode = destination.stat().st_mode
            destination.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError as exc:
        raise ScaffoldError(f"Cannot write {destination}: {exc.strerror or exc}") from exc

def _prepare_root(target_root):
    try:
        if target_root.exists():
            if target_root.is_file():
                raise ScaffoldError(f"Target path is a file: {target_root}")
            if any(target_root.iterdir()):
                raise ScaffoldError(f"Target directory is not empty: {target_root}")
        else:
            target_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ScaffoldError(f"Cannot create {target_root}: {exc.strerror or exc}") from exc

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
