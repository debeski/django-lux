import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dlux import __version__
from dlux.cli import main
from dlux.scaffold import _register_app


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
            self.assertTrue((target / "req.txt").exists())
            self.assertTrue((target / ".nginx" / "nginx.conf").exists())
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
            nginx_contents = (target / ".nginx" / "nginx.conf").read_text(encoding="utf-8")
            req_contents = (target / "req.txt").read_text(encoding="utf-8")
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
            self.assertIn("DEFAULT_FROM_EMAIL=", env_contents)
            self.assertIn("SMTP_RELAY_HOST=", env_contents)
            self.assertIn("SMTP_RELAY_PORT=", env_contents)
            self.assertIn("SMTP_RELAY_USE_TLS=", env_contents)
            self.assertIn("SMTP_RELAY_USER=", env_contents)
            self.assertIn("SMTP_RELAY_PASSWORD=", env_contents)
            self.assertEqual(len([line for line in env_contents.splitlines() if line.strip()]), 12)
            self.assertIn("autorun.ini", gitignore_contents)
            self.assertIn("compose.yml", dockerignore_contents)
            self.assertIn("compose.dev.yml", dockerignore_contents)
            self.assertIn("FROM python:3.14-slim", dockerfile_contents)
            self.assertIn("name: demo_project", compose_contents)
            self.assertIn("image: nginx:latest", compose_contents)
            self.assertIn("./.nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro", compose_contents)
            self.assertIn("image: ${WEB_IMAGE:-demo_project:latest}", compose_contents)
            self.assertIn('POSTGRES_DB: "demo_project_db"', compose_contents)
            self.assertIn('POSTGRES_USER: ${POSTGRES_USER:-admin}', compose_contents)
            self.assertIn('DJANGO_SETTINGS_MODULE: "config.settings"', compose_contents)
            self.assertIn('command: ["python", "/app/tools/smtp_relay.py"]', compose_contents)
            self.assertIn("celery:", compose_contents)
            self.assertIn('command: ["python", "-m", "celery", "-A", "config", "worker", "-B", "--loglevel=info"]', compose_contents)
            self.assertIn('image: !reset null', compose_dev_contents)
            self.assertIn("celery:", compose_dev_contents)
            self.assertIn('published: "81"', compose_dev_contents)
            self.assertIn('BASE_URL: "http://localhost:81"', compose_dev_contents)
            self.assertIn("server_name _;", nginx_contents)
            self.assertIn("proxy_pass http://web:8000;", nginx_contents)
            self.assertIn("proxy_pass http://web:8000/health/;", nginx_contents)
            self.assertIn("celery", req_contents)
            self.assertIn("django-cors-headers", req_contents)
            self.assertIn("django-csp", req_contents)
            self.assertIn("django-health-check==3.20.0", req_contents)
            self.assertIn(".secrets/.env", readme_contents)
            self.assertIn("DJANGO_SECRET_KEY", readme_contents)
            self.assertNotIn("env_file", readme_contents)
            self.assertTrue(entrypoint_mode & 0o111)
            self.assertIn("debeski/decrypter:compose", start_sh_contents)
            self.assertIn("$projectRoot = (Resolve-Path $projectRoot).Path", start_ps1_contents)
            self.assertIn('$containerRoot = "/host_mnt/$drive/$tail"', start_ps1_contents)
            self.assertIn('-w "${containerRoot}"', start_ps1_contents)
            self.assertNotIn(b"\r\n", entrypoint_bytes)
            self.assertNotIn(b"\r\n", start_sh_bytes)
            self.assertTrue(start_sh_mode & 0o111)

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
