"""Guarded Compose migrations for projects generated before the current scaffold.

``enable_updater`` bootstraps the in-container updater and ``enable_agent``
forwards to Composer; both are deprecated and **removed in 1.9.0**, at which
point this whole module goes with them. Kept in one file for exactly that
reason — the deletion is one path, not a hunt through the scaffolder.

See ``docs/deprecation-countdown.md``.
"""
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .. import __version__
from ._shared import ScaffoldError, _render_template, _resolve_project_files

UPDATER_COMPOSE_START = "# DjangoLux updater start"

UPDATER_COMPOSE_END = "# DjangoLux updater end"

POST_START_LABEL = "org.dlux.post-start"

POST_START_MIGRATOR = (
    "python -m dlux.updater.supervisor --no-watch -- python manage.py migrator"
)

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
    command: ["python", "-m", "dlux.updater.supervisor", "--no-watch", "--", "bash", "-c", "python manage.py dlux_reconcile; python manage.py migrator && exec python manage.py dlux_update_worker"]
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

def _migrate_manage_py(contents):
    """Point an existing project's manage.py release resolver at the packaged
    supervisor (idempotent). New scaffolds already import from the package."""
    return contents.replace(
        "from dlux_runtime_supervisor import baked_version, resolve_release",
        "from dlux.updater.supervisor import baked_version, resolve_release",
    )

def _migrate_smtp_relay_compose(contents):
    """Point an existing project's smtp-relay service at the packaged relay.

    The relay moved out of ``tools/smtp_relay.py`` into ``dlux.smtp_relay`` for the
    same reason the supervisor did: fixes to it were stranded in whatever copy each
    project was scaffolded with. Unlike the updater this service has no marked
    block, but the module path is distinctive enough to rewrite directly, and doing
    so is idempotent. The project's own ``tools/smtp_relay.py`` is left on disk —
    unused, and harmless to keep.
    """
    return contents.replace("tools.smtp_relay", "dlux.smtp_relay")

def _enable_updater_compose(contents, project_slug, config_package):
    if UPDATER_COMPOSE_START in contents:
        if UPDATER_COMPOSE_END not in contents or "  dlux-updater:\n" not in contents:
            raise ScaffoldError("The existing DjangoLux updater Compose block is incomplete")
        # Self-heal an existing updater block to the current runtime wiring
        # (idempotent, surgical — the marked block only). Two migrations:
        #   1. Supervisor now ships in the dlux package, not a scaffold file.
        #   2. A pre-migration pointer reconcile guards against a stale pinned
        #      release wedging the boot chain behind a maintenance screen.
        contents = contents.replace("tools.dlux_runtime_supervisor", "dlux.updater.supervisor")
        if "dlux_reconcile" not in contents:
            contents = contents.replace(
                "python manage.py migrator && exec python manage.py dlux_update_worker",
                "python manage.py dlux_reconcile; python manage.py migrator "
                "&& exec python manage.py dlux_update_worker",
            )
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
            "      python -m dlux.updater.supervisor -- bash -c ' if [ \"$$DEBUG_STATUS\" = \"True\" ]; then\n",
            "web command",
        )
        # Composer owns the migrator now, so the native Compose post_start hook
        # (which Compose runs itself, unflagged, racing composer's flagged run)
        # becomes a label composer reads. Supervisor-wrapped, so collectstatic
        # uses the runtime-active release rather than the baked image.
        legacy_hook = "    post_start:\n      - command: python manage.py migrator\n"
        if legacy_hook in section:
            section = section.replace(legacy_hook, "", 1)
        if POST_START_LABEL not in section:
            label_line = f"      {POST_START_LABEL}: \"{POST_START_MIGRATOR}\"\n"
            if "    labels:\n" in section:
                section = section.replace("    labels:\n", "    labels:\n" + label_line, 1)
            else:
                section = _replace_once(
                    section,
                    "    entrypoint: [\"/app/entrypoint.sh\"]\n",
                    "    labels:\n" + label_line + "    entrypoint: [\"/app/entrypoint.sh\"]\n",
                    "web entrypoint anchor",
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
            f'    command: ["python", "-m", "dlux.updater.supervisor", "--", '
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
        return contents.replace("tools.dlux_runtime_supervisor", "dlux.updater.supervisor")
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
        "manage.py": project_root / "manage.py",
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
        "compose.yml": _migrate_smtp_relay_compose(
            _enable_updater_compose(compose, project_slug, config_package)
        ),
        "compose.dev.yml": _enable_updater_dev_compose(paths["compose.dev.yml"].read_text(encoding="utf-8")),
        ".nginx/nginx.conf": _enable_updater_nginx(paths[".nginx/nginx.conf"].read_text(encoding="utf-8")),
        "manage.py": _migrate_manage_py(manage_contents),
    }
    requirements = paths["requirements.txt"].read_text(encoding="utf-8")
    matches = re.findall(r"(?m)^django-lux(?:\[updater\])?==[^\s]+$", requirements)
    if len(matches) != 1:
        raise ScaffoldError("requirements.txt must contain one exact generated django-lux pin")
    updated["requirements.txt"] = requirements.replace(
        matches[0], f"django-lux[updater]=={__version__}", 1,
    )
    additions = {
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
