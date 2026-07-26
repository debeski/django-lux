import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dlux import __version__
from dlux.cli import main
from dlux.scaffold import (
    ScaffoldError,
    _register_app,
    create_project,
    enable_agent,
    split_image_reference,
)


MANAGE_TEMPLATE = """#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
"""

SETTINGS_TEMPLATE = """INSTALLED_APPS = [
    "django.contrib.admin",
]
"""

URLS_TEMPLATE = """from django.urls import path

urlpatterns = [
]
"""


class ScaffoldTests(unittest.TestCase):
    def test_startproject_creates_expected_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "demo_project"

            exit_code = main(["startproject", "demo_project", str(target)])

            self.assertEqual(exit_code, 0)
            self.assertTrue((target / "manage.py").exists())
            self.assertTrue((target / "config" / "celery.py").exists())
            self.assertTrue((target / "config" / "settings.py").exists())
            self.assertTrue((target / "docs" / "README.md").exists())
            self.assertTrue((target / ".gitattributes").exists())
            self.assertTrue((target / ".gitignore").exists())
            self.assertTrue((target / ".secrets" / ".env").exists())
            self.assertTrue((target / ".dockerignore").exists())
            self.assertTrue((target / "Dockerfile").exists())
            self.assertTrue((target / "compose.yml").exists())
            self.assertTrue((target / "compose.dev.yml").exists())
            self.assertTrue((target / "entrypoint.sh").exists())
            self.assertTrue((target / "gunicorn.py").exists())
            self.assertTrue((target / "requirements.txt").exists())
            self.assertTrue((target / ".proxy" / "Caddyfile").exists())
            self.assertTrue((target / ".proxy" / "default.conf.template").exists())
            self.assertTrue((target / ".proxy" / "maintenance.html").exists())
            self.assertTrue((target / "tools" / "dlux_runtime_supervisor.py").exists())
            self.assertTrue((target / "start.sh").exists())
            self.assertTrue((target / "start.ps1").exists())

            manage_contents = (target / "manage.py").read_text(encoding="utf-8")
            config_init_contents = (target / "config" / "__init__.py").read_text(encoding="utf-8")
            celery_contents = (target / "config" / "celery.py").read_text(encoding="utf-8")
            settings_contents = (target / "config" / "settings.py").read_text(encoding="utf-8")
            urls_contents = (target / "config" / "urls.py").read_text(encoding="utf-8")
            gitattributes_contents = (target / ".gitattributes").read_text(encoding="utf-8")
            gitignore_contents = (target / ".gitignore").read_text(encoding="utf-8")
            env_contents = (target / ".secrets" / ".env").read_text(encoding="utf-8")
            dockerignore_contents = (target / ".dockerignore").read_text(encoding="utf-8")
            dockerfile_contents = (target / "Dockerfile").read_text(encoding="utf-8")
            compose_contents = (target / "compose.yml").read_text(encoding="utf-8")
            compose_dev_contents = (target / "compose.dev.yml").read_text(encoding="utf-8")
            nginx_contents = (target / ".proxy" / "default.conf.template").read_text(encoding="utf-8")
            caddy_contents = (target / ".proxy" / "Caddyfile").read_text(encoding="utf-8")
            maintenance_contents = (target / ".proxy" / "maintenance.html").read_text(encoding="utf-8")
            requirements_contents = (target / "requirements.txt").read_text(encoding="utf-8")
            readme_contents = (target / "README.md").read_text(encoding="utf-8")
            entrypoint_mode = (target / "entrypoint.sh").stat().st_mode
            start_sh_contents = (target / "start.sh").read_text(encoding="utf-8")
            start_ps1_contents = (target / "start.ps1").read_text(encoding="utf-8")
            start_sh_mode = (target / "start.sh").stat().st_mode
            entrypoint_bytes = (target / "entrypoint.sh").read_bytes()
            start_sh_bytes = (target / "start.sh").read_bytes()

            self.assertIn('DJANGO_SETTINGS_MODULE", "config.settings"', manage_contents)
            self.assertIn(f"Generated with django-lux {__version__}.", manage_contents)
            self.assertIn("Project name: demo_project.", manage_contents)
            self.assertIn(f"Generated on: {date.today().isoformat()}.", manage_contents)
            self.assertIn("from .celery import app as celery_app", config_init_contents)
            self.assertIn('os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")', celery_contents)
            self.assertIn('app = Celery("demo_project")', celery_contents)
            settings_import = re.search(
                r"^from dlux\.utils import (.+)$", settings_contents, re.MULTILINE
            )
            self.assertIsNotNone(settings_import)
            imported = {name.strip() for name in settings_import.group(1).split(",")}
            self.assertLessEqual({"get_secret", "dlux_settings", "get_project_version"}, imported)
            self.assertIn('SECRET_KEY = get_secret("DJANGO_SECRET_KEY", "DJANGO_SECRET_KEY")', settings_contents)
            self.assertIn("dlux_settings(globals())", settings_contents)
            self.assertIn('"ENGINE": "django.db.backends.postgresql"', settings_contents)
            self.assertIn('"LOCATION": os.getenv("REDIS_URL_DB", "redis://redis:6379/1")', settings_contents)
            self.assertIn('"corsheaders"', settings_contents)
            self.assertIn('"csp"', settings_contents)
            self.assertIn('"health_check"', settings_contents)
            self.assertIn('"health_check.db"', settings_contents)
            self.assertIn('"corsheaders.middleware.CorsMiddleware"', settings_contents)
            self.assertIn('"csp.middleware.CSPMiddleware"', settings_contents)
            self.assertIn('CORS_ALLOW_ALL_ORIGINS = DEBUG', settings_contents)
            self.assertIn('CORS_ALLOWED_ORIGINS = TRUSTED_ORIGINS', settings_contents)
            self.assertIn('CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/2")', settings_contents)
            self.assertIn('CONTENT_SECURITY_POLICY = {', settings_contents)
            self.assertIn('"default-src": [SELF]', settings_contents)
            self.assertIn('path("", include("dlux.urls"))', urls_contents)
            self.assertIn('path("health/", include("health_check.urls"))', urls_contents)
            self.assertEqual(gitattributes_contents.strip(), "* text=auto  eol=lf")
            self.assertIn(".secrets/", gitignore_contents)
            self.assertIn("DJANGO_SECRET_KEY=", env_contents)
            self.assertIn("POSTGRES_USER=", env_contents)
            self.assertIn("POSTGRES_PASSWORD=", env_contents)
            self.assertNotIn("PGADMIN", env_contents)
            self.assertIn("ADMIN_PASS=", env_contents)
            self.assertIn("BASE_URL=", env_contents)
            self.assertIn("ALLOWED_URLS=", env_contents)
            self.assertIn("ALLOWED_HOSTS=", env_contents)
            self.assertIn("DEFAULT_FROM_EMAIL=", env_contents)
            self.assertIn("SMTP_RELAY_HOST=", env_contents)
            self.assertIn("SMTP_RELAY_PORT=", env_contents)
            self.assertIn("SMTP_RELAY_USE_TLS=", env_contents)
            self.assertIn("SMTP_RELAY_USER=", env_contents)
            self.assertIn("SMTP_RELAY_PASSWORD=", env_contents)
            self.assertIn("NGINX_PORT=", env_contents)
            self.assertIn("NGINX_SERVER_NAME=", env_contents)
            self.assertIn("NGINX_MAX_SIZE=", env_contents)
            self.assertIn("CADDY_PORT=", env_contents)
            self.assertIn("CADDY_SITE_ADDRESS=", env_contents)
            self.assertIn("CADDY_MAX_SIZE=", env_contents)
            env_keys = [
                line.partition("=")[0]
                for line in env_contents.splitlines()
                if line.strip()
            ]
            self.assertEqual(len(env_keys), len(set(env_keys)))
            expected_env_keys = {
                "DJANGO_SECRET_KEY",
                "WEB_IMAGE",
                "POSTGRES_USER",
                "POSTGRES_PASSWORD",
                "ADMIN_PASS",
                "BASE_URL",
                "ALLOWED_URLS",
                "ALLOWED_HOSTS",
                "NGINX_PORT",
                "NGINX_SERVER_NAME",
                "NGINX_MAX_SIZE",
                "CADDY_PORT",
                "CADDY_SITE_ADDRESS",
                "CADDY_MAX_SIZE",
                "DEFAULT_FROM_EMAIL",
                "SMTP_RELAY_HOST",
                "SMTP_RELAY_PORT",
                "SMTP_RELAY_USE_TLS",
                "SMTP_RELAY_USER",
                "SMTP_RELAY_PASSWORD",
            }
            self.assertEqual(set(env_keys), expected_env_keys)
            self.assertIn("autorun.ini", gitignore_contents)
            self.assertIn("compose.yml", dockerignore_contents)
            self.assertIn("compose.dev.yml", dockerignore_contents)
            self.assertIn("FROM python:3.14-slim", dockerfile_contents)
            self.assertIn('LABEL org.demo_project.dlux_baked_version=', dockerfile_contents)
            self.assertIn('ARG DLUX_PROJECT_RELEASE_MANIFEST=""', dockerfile_contents)
            self.assertIn('LABEL org.dlux.project.release-manifest=', dockerfile_contents)
            self.assertIn("name: demo_project", compose_contents)
            # Caddy is the active proxy; nginx is a commented-out drop-in fallback.
            self.assertIn("image: caddy:latest", compose_contents)
            self.assertIn("./.proxy/Caddyfile:/etc/caddy/Caddyfile:ro", compose_contents)
            self.assertIn('CADDY_SITE_ADDRESS: "${CADDY_SITE_ADDRESS:-:80}"', compose_contents)
            self.assertIn('CADDY_MAX_SIZE: "${CADDY_MAX_SIZE:-10MB}"', compose_contents)
            self.assertIn('published: "${CADDY_PORT:-${NGINX_PORT:-80}}"', compose_contents)
            self.assertIn("# nginx (fallback", compose_contents)
            self.assertIn("./.proxy/default.conf.template:/etc/nginx/templates/default.conf.template:ro", compose_contents)
            self.assertIn("image: ${WEB_IMAGE:-demo_project:latest}", compose_contents)
            self.assertIn('POSTGRES_DB: "${POSTGRES_DB:-demo_project_db}"', compose_contents)
            self.assertIn('POSTGRES_USER: ${POSTGRES_USER:-admin}', compose_contents)
            self.assertIn('DJANGO_SETTINGS_MODULE: "config.settings"', compose_contents)
            self.assertIn('command: ["python", "-m", "tools.smtp_relay"]', compose_contents)
            self.assertIn("celery:", compose_contents)
            self.assertIn('command: ["python", "-m", "tools.dlux_runtime_supervisor", "--", "python", "-m", "celery", "-A", "config", "worker", "-B", "--loglevel=info"]', compose_contents)
            self.assertIn("dlux-updater:", compose_contents)
            self.assertIn('DLUX_INLINE_UPDATES_ENABLED: "True"', compose_contents)
            self.assertIn("dlux_runtime:/opt/dlux-runtime:rw", compose_contents)
            self.assertIn("dlux_runtime:/opt/dlux-runtime:ro", compose_contents)
            self.assertIn("  egress:", compose_contents)
            self.assertIn("composer-agent:", compose_contents)
            self.assertIn("docker-socket-proxy:", compose_contents)
            self.assertIn("image: tecnativa/docker-socket-proxy:latest", compose_contents)
            self.assertIn("EVENTS: 1", compose_contents)
            self.assertIn("/var/run/docker.sock:/var/run/docker.sock:ro", compose_contents)
            self.assertIn("  docker_proxy:", compose_contents)
            self.assertIn("image: debeski/composer:latest", compose_contents)
            self.assertIn('COMPOSER_AGENT_STATE_DIR: "/var/lib/composer-agent"', compose_contents)
            self.assertIn('COMPOSER_EXCLUDE_SERVICES: "composer-agent,docker-socket-proxy,db,redis"', compose_contents)
            self.assertIn('COMPOSER_AGENT_RESTART_SERVICES: "web,celery,smtp-relay,caddy"', compose_contents)
            # db-backup (superseded by DjangoLux system backups) and pgadmin are
            # no longer part of the default stack.
            self.assertNotIn("db-backup:", compose_contents)
            self.assertNotIn("pgadmin", compose_contents)
            self.assertNotIn("BACKUP_INTERVAL", compose_contents)
            self.assertIn('- "${PWD}:${PWD}:ro"', compose_contents)
            self.assertIn("composer_agent_state:/var/lib/composer-agent:rw", compose_contents)
            self.assertIn('COMPOSER_VERSION_LABEL: "org.demo_project.dlux_baked_version"', compose_contents)
            self.assertIn('COMPOSER_RELEASE_MANIFEST_LABEL: "org.dlux.project.release-manifest"', compose_contents)
            self.assertIn("post_start:", compose_contents)
            # The post_start migrator must run under the runtime supervisor so its
            # collectstatic uses the same runtime-active DjangoLux release gunicorn
            # serves templates from; run raw it collects from the baked image and,
            # running last on recreate, leaves version-mismatched static.
            self.assertIn(
                "- command: python -m tools.dlux_runtime_supervisor --no-watch -- python manage.py migrator",
                compose_contents,
            )
            self.assertNotIn("- command: python manage.py migrator\n", compose_contents)
            self.assertIn('image: !reset null', compose_dev_contents)
            self.assertIn("celery:", compose_dev_contents)
            self.assertIn('published: "90"', compose_dev_contents)
            self.assertIn('BASE_URL: "http://localhost:90"', compose_dev_contents)
            self.assertIn("server_name ${NGINX_SERVER_NAME};", nginx_contents)
            self.assertIn("client_max_body_size ${NGINX_MAX_SIZE};", nginx_contents)
            self.assertIn("resolver 127.0.0.11", nginx_contents)
            self.assertIn("proxy_pass http://$web_upstream;", nginx_contents)
            self.assertIn("proxy_pass http://$web_upstream/health/;", nginx_contents)
            self.assertIn("location = /_update/status.json", nginx_contents)
            self.assertIn("location = /_edge-alive", nginx_contents)
            self.assertIn("dlux-maintenance.html", nginx_contents)
            self.assertIn("/opt/dlux-runtime/state/maintenance", nginx_contents)
            # Front-proxy header handling: nginx passes an incoming
            # X-Forwarded-Proto through and appends to X-Forwarded-For.
            self.assertIn("map $http_x_forwarded_proto $forwarded_proto", nginx_contents)
            self.assertIn("proxy_set_header X-Forwarded-Proto $forwarded_proto;", nginx_contents)
            self.assertIn("proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;", nginx_contents)
            # Caddy mirror of the same routing.
            self.assertIn("reverse_proxy web:8000", caddy_contents)
            self.assertIn("handle /_update/status.json", caddy_contents)
            self.assertIn("/_edge-alive", caddy_contents)
            self.assertIn("handle_errors", caddy_contents)
            # Caddy equivalent of the front-proxy header handling.
            self.assertIn("trusted_proxies static private_ranges", caddy_contents)
            self.assertIn("scheduleRecoveryProbe", maintenance_contents)
            self.assertIn('fetch("/", { cache: "no-store" })', maintenance_contents)
            self.assertIn('window.location.replace("/")', maintenance_contents)
            self.assertIn("celery", requirements_contents)
            self.assertIn(f"django-lux[updater]=={__version__}", requirements_contents)
            self.assertIn("django-cors-headers", requirements_contents)
            self.assertIn("django-csp", requirements_contents)
            self.assertIn("django-health-check==3.20.0", requirements_contents)
            self.assertIn(".secrets/.env", readme_contents)
            self.assertIn("DJANGO_SECRET_KEY", readme_contents)
            for env_key in expected_env_keys:
                self.assertIn(f"- `{env_key}`", readme_contents)
            self.assertNotIn("- `COMPOSER_CONTROL_URL`", readme_contents)
            self.assertNotIn("- `COMPOSER_ENROLLMENT_TOKEN`", readme_contents)
            self.assertNotIn("env_file", readme_contents)
            self.assertTrue(entrypoint_mode & 0o111)
            self.assertIn("debeski/composer:latest", start_sh_contents)
            self.assertIn('--env-file "${secret_path}"', start_sh_contents)
            self.assertIn("COMPOSER_INHERITED_SECRET_KEYS", start_sh_contents)
            self.assertIn("$args.Count -eq 1", start_ps1_contents)
            self.assertIn('"--env-file", $secretPath', start_ps1_contents)
            self.assertIn("COMPOSER_INHERITED_SECRET_KEYS", start_ps1_contents)
            self.assertIn("$projectRoot = (Resolve-Path $projectRoot).Path", start_ps1_contents)
            self.assertIn('$containerRoot = "/host_mnt/$drive/$tail"', start_ps1_contents)
            self.assertIn('"-w", $containerRoot', start_ps1_contents)
            self.assertNotIn(b"\r\n", entrypoint_bytes)
            self.assertNotIn(b"\r\n", start_sh_bytes)
            self.assertTrue(start_sh_mode & 0o111)

    def test_enable_agent_forwards_to_the_project_composer_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = create_project("demo_project", Path(tmp_dir) / "demo_project")
            result = {
                "applied": True,
                "files": ["compose.yml"],
                "command": "docker compose up -d --force-recreate docker-socket-proxy composer-agent",
                "backup_root": ".xpose/dlux-agent-bootstrap/example",
                "warnings": [],
            }
            runner = mock.Mock(
                return_value=SimpleNamespace(
                    returncode=0,
                    stdout=f"notice\n{json.dumps(result)}\n",
                    stderr="",
                )
            )

            forwarded = enable_agent(
                target,
                apply=True,
                compose_file="compose.yml",
                command_runner=runner,
            )

            self.assertEqual(forwarded, result)
            self.assertEqual(
                runner.call_args.args[0],
                [
                    str(target / "start.sh"),
                    "enable-agent",
                    "--apply",
                    "--file",
                    "compose.yml",
                    "--json",
                ],
            )

    def test_enable_agent_surfaces_composer_forwarding_failure(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = create_project("demo_project", Path(tmp_dir) / "demo_project")
            runner = mock.Mock(
                return_value=SimpleNamespace(
                    returncode=2,
                    stdout='{"error": "DjangoLux 1.5.0 is required"}\n',
                    stderr="",
                )
            )

            with self.assertRaisesRegex(Exception, "DjangoLux 1.5.0 is required"):
                enable_agent(target, apply=True, command_runner=runner)

    def test_startapp_creates_expected_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "manage.py").write_text(MANAGE_TEMPLATE, encoding="utf-8")
            project_package = root / "config"
            project_package.mkdir()
            (project_package / "__init__.py").write_text("", encoding="utf-8")
            (project_package / "settings.py").write_text(SETTINGS_TEMPLATE, encoding="utf-8")
            (project_package / "urls.py").write_text(URLS_TEMPLATE, encoding="utf-8")

            old_cwd = Path.cwd()
            os.chdir(root)
            try:
                exit_code = main(["startapp", "inventory"])
            finally:
                os.chdir(old_cwd)

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "inventory" / "models.py").exists())
            self.assertTrue((root / "inventory" / "translations.py").exists())
            self.assertTrue((root / "inventory" / "tests" / "test_inventory.py").exists())

            views_contents = (root / "inventory" / "views.py").read_text(encoding="utf-8")
            tables_contents = (root / "inventory" / "tables.py").read_text(encoding="utf-8")
            list_template_contents = (root / "inventory" / "templates" / "inventory" / "example_record_list.html").read_text(encoding="utf-8")
            readme_contents = (root / "inventory" / "README.md").read_text(encoding="utf-8")
            translations_contents = (root / "inventory" / "translations.py").read_text(encoding="utf-8")
            self.assertIn("LoginRequiredMixin", views_contents)
            self.assertIn("PermissionRequiredMixin", views_contents)
            self.assertIn('permission_required = "inventory.view_examplerecord"', views_contents)
            self.assertIn('permission_required = "inventory.add_examplerecord"', views_contents)
            self.assertIn('permission_required = "inventory.change_examplerecord"', views_contents)
            self.assertIn('permission_required = "inventory.delete_examplerecord"', views_contents)
            self.assertIn("_scope_filtered_queryset", views_contents)
            self.assertIn("log_user_action", views_contents)
            self.assertIn('reverse("modal_manager", args=[app_label, model_name, record.pk]) + "?action=view"', tables_contents)
            self.assertIn('"event": "dlux:dynamic_modal:open"', tables_contents)
            self.assertIn("{% url 'modal_manager' 'inventory' 'ExampleRecord' 'new' %}", list_template_contents)
            self.assertIn('data-dynamic-modal=', list_template_contents)
            self.assertIn("Dynamic Modal Example", readme_contents)
            self.assertIn("DLUX_STRINGS", translations_contents)

    def test_register_updates_settings_and_urls_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "manage.py").write_text(MANAGE_TEMPLATE, encoding="utf-8")
            project_package = root / "config"
            project_package.mkdir()
            (project_package / "__init__.py").write_text("", encoding="utf-8")
            settings_path = project_package / "settings.py"
            urls_path = project_package / "urls.py"
            settings_path.write_text(SETTINGS_TEMPLATE, encoding="utf-8")
            urls_path.write_text(URLS_TEMPLATE, encoding="utf-8")

            _register_app(root, "inventory")
            _register_app(root, "inventory")

            settings_contents = settings_path.read_text(encoding="utf-8")
            urls_contents = urls_path.read_text(encoding="utf-8")

            self.assertEqual(settings_contents.count('"inventory",'), 1)
            self.assertIn("# DjangoLux generated apps start", settings_contents)
            self.assertEqual(urls_contents.count('namespace="inventory"'), 1)
            self.assertIn("from django.urls import include, path", urls_contents)


class ComposeNetworkTopologyTests(unittest.TestCase):
    """The generated Compose file segregates traffic into four networks. Substring
    assertions cannot catch a service attached to the wrong one, so parse the
    service -> networks map and assert it against the stack contract — the same
    spec Composer's drift-diff checks a deployed compose.yml against."""

    def setUp(self):
        from dlux import stack_contract

        self.contract = stack_contract.load_contract()
        self.stack_contract = stack_contract
        self.EGRESS_SERVICES = set(self.contract["invariants"]["egress_services"])
        self.INTERNAL_ONLY_SERVICES = set(self.contract["invariants"]["internal_only_services"])
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        target = create_project(
            "demo_project", Path(self._tmp.name) / "demo_project", image="acme/demo"
        )
        self.compose = (target / "compose.yml").read_text(encoding="utf-8")
        self.attachments = self._parse_service_networks(self.compose)

    def test_scaffold_matches_the_stack_contract(self):
        """One assertion covering the whole service -> network map, so the
        scaffold and Composer's drift-diff are checked against the same source."""
        self.assertEqual(self.stack_contract.diff_attachments(self.contract, self.attachments), [])

    @staticmethod
    def _parse_service_networks(compose):
        """{service: {networks}} for the active (uncommented) services."""
        body = compose.partition("\nservices:\n")[2].partition("\nvolumes:\n")[0]
        attachments = {}
        service = None
        in_networks = False
        for line in body.splitlines():
            header = re.match(r"^  ([A-Za-z][\w-]*):\s*$", line)
            if header:
                service = header.group(1)
                attachments[service] = set()
                in_networks = False
            elif re.match(r"^    \S", line):
                in_networks = line.strip() == "networks:"
            elif in_networks and service:
                item = re.match(r"^      - (\S+)\s*$", line)
                if item:
                    attachments[service].add(item.group(1))
        return attachments

    @staticmethod
    def _parse_restart_labels(compose):
        """{service: 'safe'|'protected'} from each service's org.dlux.restart label."""
        body = compose.partition("\nservices:\n")[2].partition("\nvolumes:\n")[0]
        service = None
        labels = {}
        for line in body.splitlines():
            header = re.match(r"^  ([A-Za-z][\w-]*):\s*$", line)
            if header:
                service = header.group(1)
                continue
            match = re.match(r'^\s+org\.dlux\.restart:\s*"(safe|protected)"\s*$', line)
            if match and service:
                labels[service] = match.group(1)
        return labels

    def test_restart_labels_match_the_contract(self):
        expected = {name: spec["restart"] for name, spec in self.contract["services"].items()}
        self.assertEqual(self._parse_restart_labels(self.compose), expected)

    def test_safe_restart_label_matches_the_composer_restart_env(self):
        """The label is the new source of truth; it must agree with the existing
        COMPOSER_AGENT_RESTART_SERVICES env so the two never drift while Composer
        migrates from the hardcoded list to reading labels."""
        env_line = re.search(r'COMPOSER_AGENT_RESTART_SERVICES:\s*"([^"]*)"', self.compose)
        self.assertIsNotNone(env_line)
        env_restart = {s for s in env_line.group(1).split(",") if s}
        safe = {name for name, cls in self._parse_restart_labels(self.compose).items() if cls == "safe"}
        self.assertEqual(safe, env_restart)

    def test_declared_networks_are_exactly_the_four_standard_ones(self):
        declared = set(
            re.findall(
                r"^  ([a-z_]+):$", self.compose.partition("\nnetworks:\n")[2], re.MULTILINE
            )
        )
        self.assertEqual(declared, set(self.contract["networks"]))
        for name, spec in self.contract["networks"].items():
            if spec.get("internal"):
                self.assertIn(f"  {name}:\n    internal: true", self.compose)

    def test_every_service_is_attached_to_a_declared_network(self):
        declared = set(self.contract["networks"])
        for service, networks in self.attachments.items():
            self.assertTrue(networks, f"{service} joins no network")
            self.assertLessEqual(networks, declared, service)

    def test_only_the_proxy_is_on_frontend_and_publishes_ports(self):
        on_frontend = {s for s, n in self.attachments.items() if "frontend" in n}
        self.assertEqual(on_frontend, set(self.contract["invariants"]["ingress_services"]))
        body = self.compose.partition("\nservices:\n")[2].partition("\nvolumes:\n")[0]
        service = None
        publishing = set()
        for line in body.splitlines():
            header = re.match(r"^  ([A-Za-z][\w-]*):\s*$", line)
            if header:
                service = header.group(1)
            elif line.strip() == "ports:" and service:
                publishing.add(service)
        expected_publishers = {
            name for name, spec in self.contract["services"].items() if spec.get("publishes_ports")
        }
        self.assertEqual(publishing, expected_publishers)

    def test_frontend_and_egress_stay_disjoint(self):
        """The two bridges only buy isolation while no service bridges them."""
        self.assertTrue(self.contract["invariants"]["frontend_egress_disjoint"])
        for service, networks in self.attachments.items():
            self.assertFalse({"frontend", "egress"} <= networks, service)

    def test_egress_is_limited_to_services_that_need_the_internet(self):
        on_egress = {s for s, n in self.attachments.items() if "egress" in n}
        self.assertEqual(on_egress, self.EGRESS_SERVICES)

    def test_application_services_have_no_internet_route(self):
        for service in self.INTERNAL_ONLY_SERVICES:
            self.assertEqual(self.attachments[service], {"internal"}, service)

    def test_docker_proxy_path_is_isolated(self):
        self.assertEqual(self.attachments["docker-socket-proxy"], {"docker_proxy"})
        self.assertEqual(self.attachments["composer-agent"], {"egress", "docker_proxy"})
        socket = self.contract["invariants"]["docker_socket"]
        # The socket proxy is the agent's only Docker route; a raw socket mount
        # on any other service would hand it host root.
        mounts = re.findall(r"^\s+- /var/run/docker\.sock:.*$", self.compose, re.MULTILINE)
        self.assertEqual(len(mounts), len(socket["allowed_services"]))
        self.assertTrue(mounts[0].endswith(f":{socket['access']}"), mounts[0])

    def test_runtime_volume_read_write_split_matches_the_contract(self):
        """dlux_runtime is read/write only for the updater and agent; every other
        mount is read-only, so a compromised web/proxy cannot rewrite the active
        release pointer or staged wheels."""
        rule = self.contract["invariants"]["runtime_volume"]
        volume = rule["volume"]
        body = self.compose.partition("\nservices:\n")[2].partition("\nvolumes:\n")[0]
        service = None
        rw, ro = set(), set()
        for line in body.splitlines():
            header = re.match(r"^  ([A-Za-z][\w-]*):\s*$", line)
            if header:
                service = header.group(1)
                continue
            mount = re.match(rf"^\s+- {volume}:/opt/dlux-runtime:(rw|ro)\s*$", line)
            if mount and service:
                (rw if mount.group(1) == "rw" else ro).add(service)
        self.assertEqual(rw, set(rule["read_write_services"]))
        self.assertEqual(ro, set(rule["read_only_services"]))

    def test_contract_env_keys_and_volumes_match_the_scaffold(self):
        env = (Path(self._tmp.name) / "demo_project" / ".secrets" / ".env").read_text(encoding="utf-8")
        env_keys = {line.partition("=")[0] for line in env.splitlines() if "=" in line and not line.startswith("#")}
        self.assertEqual(set(self.contract["env_keys"]), env_keys)
        declared_volumes = set(re.findall(
            r"^  ([a-z_]+):$", self.compose.partition("\nvolumes:\n")[2].partition("\nnetworks:\n")[0], re.MULTILINE
        ))
        self.assertEqual(set(self.contract["volumes"]), declared_volumes)


class StackContractTests(unittest.TestCase):
    """The contract is the shared spec; its diff helper is what Composer mirrors,
    so its behaviour is pinned here."""

    def setUp(self):
        from dlux import stack_contract

        self.stack_contract = stack_contract
        self.contract = stack_contract.load_contract()

    def _expected_attachments(self):
        return {name: set(spec["networks"]) for name, spec in self.contract["services"].items()}

    def test_load_stamps_the_running_version(self):
        from dlux import __version__

        self.assertEqual(self.contract["dlux_version"], __version__)
        self.assertEqual(self.contract["schema_version"], 1)

    def test_contract_is_internally_consistent(self):
        declared = set(self.contract["networks"])
        for name, spec in self.contract["services"].items():
            self.assertLessEqual(set(spec["networks"]), declared, name)
        inv = self.contract["invariants"]
        # The role lists must agree with the per-service network map.
        egress = {n for n, s in self.contract["services"].items() if "egress" in s["networks"]}
        internal_only = {n for n, s in self.contract["services"].items() if s["networks"] == ["internal"]}
        self.assertEqual(set(inv["egress_services"]), egress)
        self.assertEqual(set(inv["internal_only_services"]), internal_only)
        # Every service declares a restart class, and the restart invariant lists
        # agree with the per-service classes.
        for name, spec in self.contract["services"].items():
            self.assertIn(spec.get("restart"), {"safe", "protected"}, name)
        safe = {n for n, s in self.contract["services"].items() if s["restart"] == "safe"}
        protected = {n for n, s in self.contract["services"].items() if s["restart"] == "protected"}
        self.assertEqual(set(inv["restart"]["safe"]), safe)
        self.assertEqual(set(inv["restart"]["protected"]), protected)
        self.assertEqual(inv["restart"]["label"], "org.dlux.restart")

    def test_diff_is_empty_when_the_map_matches(self):
        self.assertEqual(
            self.stack_contract.diff_attachments(self.contract, self._expected_attachments()), []
        )

    def test_diff_flags_a_misattached_service(self):
        bad = self._expected_attachments()
        bad["web"] = {"egress", "internal"}
        drift = self.stack_contract.diff_attachments(self.contract, bad)
        self.assertTrue(any("web" in line for line in drift))

    def test_diff_flags_a_missing_service(self):
        bad = self._expected_attachments()
        del bad["composer-agent"]
        drift = self.stack_contract.diff_attachments(self.contract, bad)
        self.assertTrue(any("composer-agent" in line and "missing" in line for line in drift))

    def test_diff_flags_an_undeclared_network(self):
        bad = self._expected_attachments()
        bad["web"] = {"internal", "rogue_net"}
        drift = self.stack_contract.diff_attachments(self.contract, bad)
        self.assertTrue(any("rogue_net" in line for line in drift))

    def test_diff_flags_a_sidecar_bridging_frontend_and_egress(self):
        """Even a project's own extra service must not collapse ingress/egress
        isolation by joining both public bridges."""
        bad = self._expected_attachments()
        bad["my-sidecar"] = {"frontend", "egress"}
        drift = self.stack_contract.diff_attachments(self.contract, bad)
        self.assertTrue(any("my-sidecar" in line and "disjoint" in line for line in drift))

    def test_diff_ignores_extra_services(self):
        """A project may run its own sidecars; only contract services are checked."""
        extended = self._expected_attachments()
        extended["my-worker"] = {"internal"}
        self.assertEqual(self.stack_contract.diff_attachments(self.contract, extended), [])

    def test_removed_services_are_listed(self):
        removed = self.contract["removed_services"]
        self.assertIn("db-backup", removed)
        self.assertIn("pgadmin", removed)
        # A removed service must not also be a live service.
        self.assertFalse(set(removed) & set(self.contract["services"]))

    def test_removed_services_present_flags_leftovers(self):
        advisories = self.stack_contract.removed_services_present(
            self.contract, ["web", "db", "pgadmin", "db-backup", "my-worker"]
        )
        self.assertEqual(len(advisories), 2)
        self.assertTrue(any("pgadmin" in a for a in advisories))
        self.assertTrue(any("db-backup" in a for a in advisories))
        # A project's own sidecar is not a removed service, so it isn't flagged.
        self.assertFalse(any("my-worker" in a for a in advisories))

    def test_removed_services_present_is_empty_for_a_current_stack(self):
        self.assertEqual(
            self.stack_contract.removed_services_present(self.contract, list(self.contract["services"])),
            [],
        )


class ProjectReleaseScaffoldTests(unittest.TestCase):
    """A generated project must be releasable without hand-rolling the pipeline,
    and must not default to an image reference that exists in no registry
    without saying so."""

    def _project(self, tmp_dir, **kwargs):
        return create_project("demo_project", Path(tmp_dir) / "demo_project", **kwargs)

    def test_release_pipeline_is_generated(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = self._project(tmp_dir, image="acme/demo", repo="acme/demo-app")
            self.assertTrue((target / "release-manifest.json").exists())
            self.assertTrue((target / ".github" / "workflows" / "release.yml").exists())
            self.assertTrue((target / "tools" / "validate_project_release_manifest.py").exists())

            workflow = (target / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
            self.assertIn("IMAGE: acme/demo", workflow)
            self.assertIn("python3 tools/validate_project_release_manifest.py", workflow)
            self.assertIn("DLUX_BAKED_VERSION=", workflow)
            self.assertIn("DLUX_PROJECT_RELEASE_MANIFEST=", workflow)
            # GitHub expression syntax must survive scaffold rendering.
            self.assertIn("${{ secrets.DOCKERHUB_TOKEN }}", workflow)

    def test_image_option_drives_every_reference(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = self._project(tmp_dir, image="acme/demo:stable", repo="acme/demo-app")

            env = (target / ".secrets" / ".env").read_text(encoding="utf-8")
            self.assertIn("WEB_IMAGE=acme/demo:stable", env)

            compose = (target / "compose.yml").read_text(encoding="utf-8")
            self.assertNotIn("demo_project:latest", compose)
            self.assertEqual(compose.count("acme/demo:stable"), 7)

            workflow = (target / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
            self.assertIn("${{ env.IMAGE }}:stable", workflow)

    def test_repo_option_sets_the_release_url(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = self._project(
                tmp_dir, image="acme/demo", repo="https://github.com/acme/demo-app.git"
            )
            manifest = json.loads((target / "release-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["release_url"],
                "https://github.com/acme/demo-app/releases/tag/v0.1.0",
            )
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["version"], "0.1.0")

    def test_omitted_repo_leaves_an_obvious_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = self._project(tmp_dir, image="acme/demo")
            manifest = json.loads((target / "release-manifest.json").read_text(encoding="utf-8"))
            self.assertIn("OWNER/REPO", manifest["release_url"])
            self.assertNotIn("github.com//", manifest["release_url"])

    def test_settings_reports_the_version_from_the_manifest(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = self._project(tmp_dir, image="acme/demo")
            settings = (target / "config" / "settings.py").read_text(encoding="utf-8")
            self.assertIn("get_project_version", settings)
            self.assertIn("DLUX_APP_VERSION = get_project_version(BASE_DIR)", settings)

    def test_generated_validator_accepts_its_own_manifest(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = self._project(tmp_dir, image="acme/demo", repo="acme/demo-app")
            output = target / "gh-output.txt"
            completed = subprocess.run(
                [sys.executable, "tools/validate_project_release_manifest.py"],
                cwd=target,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "GITHUB_REF_NAME": "v0.1.0",
                    "GITHUB_REPOSITORY": "acme/demo-app",
                    "GITHUB_OUTPUT": str(output),
                },
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            emitted = output.read_text(encoding="utf-8")
            self.assertIn("label=base64:", emitted)
            self.assertIn(f"dlux_version={__version__}", emitted)

    def test_generated_validator_rejects_a_mismatched_tag(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = self._project(tmp_dir, image="acme/demo", repo="acme/demo-app")
            completed = subprocess.run(
                [sys.executable, "tools/validate_project_release_manifest.py"],
                cwd=target,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "GITHUB_REF_NAME": "v9.9.9",
                    "GITHUB_REPOSITORY": "acme/demo-app",
                },
            )
            self.assertEqual(completed.returncode, 1)
            self.assertIn("version mismatch", completed.stdout)

    def test_image_reference_parsing(self):
        self.assertEqual(split_image_reference("app"), ("app", "latest"))
        self.assertEqual(split_image_reference("acme/app:stable"), ("acme/app", "stable"))
        # A colon before the final slash is a registry port, not a tag.
        self.assertEqual(
            split_image_reference("registry:5000/acme/app"),
            ("registry:5000/acme/app", "latest"),
        )
        self.assertEqual(
            split_image_reference("registry:5000/acme/app:v2"),
            ("registry:5000/acme/app", "v2"),
        )
        with self.assertRaises(ScaffoldError):
            split_image_reference("")

    def test_repo_slug_validation(self):
        with self.assertRaises(ScaffoldError):
            create_project("demo_project", "/tmp/never-created", repo="not-a-slug")


if __name__ == "__main__":
    unittest.main()
