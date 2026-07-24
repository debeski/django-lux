import json
import os
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
from dlux.scaffold import _register_app, create_project, enable_agent


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
            self.assertIn("from dlux.utils import get_secret, dlux_settings", settings_contents)
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
            self.assertIn("PGADMIN_DEFAULT_EMAIL=", env_contents)
            self.assertIn("PGADMIN_DEFAULT_PASSWORD=", env_contents)
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
                "POSTGRES_USER",
                "POSTGRES_PASSWORD",
                "PGADMIN_DEFAULT_EMAIL",
                "PGADMIN_DEFAULT_PASSWORD",
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
            self.assertIn("dlux_update_egress:", compose_contents)
            self.assertIn("composer-agent:", compose_contents)
            self.assertIn("docker-socket-proxy:", compose_contents)
            self.assertIn("image: tecnativa/docker-socket-proxy:latest", compose_contents)
            self.assertIn("EVENTS: 1", compose_contents)
            self.assertIn("/var/run/docker.sock:/var/run/docker.sock:ro", compose_contents)
            self.assertIn("_docker_proxy:", compose_contents)
            self.assertIn("image: debeski/composer:latest", compose_contents)
            self.assertIn('COMPOSER_AGENT_STATE_DIR: "/var/lib/composer-agent"', compose_contents)
            self.assertIn('COMPOSER_EXCLUDE_SERVICES: "composer-agent,docker-socket-proxy,db,redis,db-backup,pgadmin"', compose_contents)
            self.assertIn('COMPOSER_AGENT_RESTART_SERVICES: "web,celery,smtp-relay,caddy"', compose_contents)
            self.assertIn('- "${PWD}:${PWD}:ro"', compose_contents)
            self.assertIn("composer_agent_state:/var/lib/composer-agent:rw", compose_contents)
            self.assertIn('COMPOSER_VERSION_LABEL: "org.demo_project.dlux_baked_version"', compose_contents)
            self.assertIn('COMPOSER_RELEASE_MANIFEST_LABEL: "org.dlux.project.release-manifest"', compose_contents)
            self.assertIn("post_start:", compose_contents)
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
            # Caddy mirror of the same routing.
            self.assertIn("reverse_proxy web:8000", caddy_contents)
            self.assertIn("handle /_update/status.json", caddy_contents)
            self.assertIn("/_edge-alive", caddy_contents)
            self.assertIn("handle_errors", caddy_contents)
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


if __name__ == "__main__":
    unittest.main()
