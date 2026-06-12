# dlux/management/commands/dlux_check.py
"""
Management command to validate dlux configuration.
Checks INSTALLED_APPS, MIDDLEWARE, context processors, and URLs.
Prints exact code snippets for any missing configuration.
"""
import importlib
from pathlib import Path

from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Validate dlux configuration and show missing settings'

    def _get_settings_file(self):
        module_name = getattr(settings, "SETTINGS_MODULE", None)
        if not module_name:
            return None
        try:
            module = importlib.import_module(module_name)
        except Exception:
            return None
        module_file = getattr(module, "__file__", None)
        return Path(module_file).resolve() if module_file else None

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('\n🔍 DjangoLux Configuration Check\n'))
        self.stdout.write('=' * 50 + '\n')

        issues = []
        warnings = []

        # ─────────────────────────────────────────────────
        # Check INSTALLED_APPS
        # ─────────────────────────────────────────────────
        self.stdout.write('\n📋 INSTALLED_APPS: ', ending='')
        required_apps = ['dlux', 'crispy_forms', 'crispy_bootstrap5', 'django_filters', 'django_tables2']
        if 'dlux' in settings.INSTALLED_APPS:
            self.stdout.write(self.style.SUCCESS('✓ OK'))
        else:
            self.stdout.write(self.style.ERROR('✗ MISSING'))
            issues.append({
                'setting': 'INSTALLED_APPS',
                'snippet': """from dlux.utils import dlux_settings
dlux_settings(globals())"""
            })

        missing_deps = [d for d in required_apps if d not in settings.INSTALLED_APPS]
        if missing_deps:
            warnings.append({
                'setting': 'INSTALLED_APPS (dependencies)',
                'message': f"Missing recommended dependencies: {', '.join(missing_deps)}",
                'snippet': """# Recommended:
from dlux.utils import dlux_settings
dlux_settings(globals())"""
            })
        else:
            dlux_index = settings.INSTALLED_APPS.index('dlux')
            crispy_index = settings.INSTALLED_APPS.index('crispy_bootstrap5')
            if dlux_index > crispy_index:
                warnings.append({
                    'setting': 'INSTALLED_APPS order',
                    'message': "'dlux' appears after 'crispy_bootstrap5'; framework template overrides may lose precedence",
                    'snippet': """# Preferred ordering:
from dlux.utils import dlux_settings
dlux_settings(globals())"""
                })

        # ─────────────────────────────────────────────────
        # Check MIDDLEWARE
        # ─────────────────────────────────────────────────
        new_path = 'dlux.middleware.DluxMiddleware'
        old_path = 'dlux.middleware.ActivityLogMiddleware'
        self.stdout.write('\n📋 MIDDLEWARE: ', ending='')
        if new_path in settings.MIDDLEWARE or old_path in settings.MIDDLEWARE:
            self.stdout.write(self.style.SUCCESS('✓ OK'))
        else:
            self.stdout.write(self.style.ERROR('✗ MISSING'))
            issues.append({
                'setting': 'MIDDLEWARE',
                'snippet': """from dlux.utils import dlux_settings
dlux_settings(globals())"""
            })

        # ─────────────────────────────────────────────────
        # Check Context Processors
        # ─────────────────────────────────────────────────
        context_proc = 'dlux.context_processors.dlux_context'
        self.stdout.write('\n📋 CONTEXT_PROCESSORS: ', ending='')
        
        context_ok = False
        try:
            for template in settings.TEMPLATES:
                processors = template.get('OPTIONS', {}).get('context_processors', [])
                if context_proc in processors:
                    context_ok = True
                    break
        except (AttributeError, TypeError):
            pass

        if context_ok:
            self.stdout.write(self.style.SUCCESS('✓ OK'))
        else:
            self.stdout.write(self.style.ERROR('✗ MISSING'))
            issues.append({
                'setting': 'TEMPLATES context_processors',
                'snippet': """from dlux.utils import dlux_settings
dlux_settings(globals())"""
            })

        # ─────────────────────────────────────────────────
        # Check URL Configuration (informational)
        # ─────────────────────────────────────────────────
        self.stdout.write('\n📋 URLS: ', ending='')
        try:
            from django.urls import reverse
            reverse('login')
            self.stdout.write(self.style.SUCCESS('✓ OK'))
        except Exception:
            self.stdout.write(self.style.WARNING('⚠ Not detected'))
            warnings.append({
                'setting': 'urls.py',
                'message': "dlux URLs may not be included",
                'snippet': """# In your project's urls.py:
from django.urls import path, include

urlpatterns = [
    # ...
    path('', include('dlux.urls')),
]"""
            })

        # ─────────────────────────────────────────────────
        # Check Crispy Forms Bootstrap 5
        # ─────────────────────────────────────────────────
        self.stdout.write('\n📋 CRISPY_FORMS: ', ending='')
        crispy_pack = getattr(settings, 'CRISPY_TEMPLATE_PACK', None)
        if crispy_pack == 'bootstrap5':
            self.stdout.write(self.style.SUCCESS('✓ OK'))
        elif crispy_pack:
            self.stdout.write(self.style.WARNING(f'⚠ Using {crispy_pack}'))
        else:
            self.stdout.write(self.style.WARNING('⚠ Not configured'))
            warnings.append({
                'setting': 'CRISPY_TEMPLATE_PACK',
                'message': "Crispy forms template pack not set",
                'snippet': """# Recommended:
from dlux.utils import dlux_settings
dlux_settings(globals())"""
            })

        # ─────────────────────────────────────────────────
        # Check settings helper wiring (recommended)
        # ─────────────────────────────────────────────────
        self.stdout.write('\n📋 SETTINGS HELPER: ', ending='')
        settings_file = self._get_settings_file()
        helper_import = 'from dlux.utils import dlux_settings'
        helper_call = 'dlux_settings(globals())'
        if settings_file and settings_file.exists():
            contents = settings_file.read_text(encoding='utf-8')
            if helper_import in contents and helper_call in contents:
                self.stdout.write(self.style.SUCCESS('✓ Detected'))
            else:
                self.stdout.write(self.style.WARNING('⚠ Not detected'))
                warnings.append({
                    'setting': 'settings.py helper',
                    'message': 'Dlux is configured, but the recommended reusable settings helper is not wired into the project settings file',
                    'snippet': f"""# At the end of {settings_file.name}:
from dlux.utils import dlux_settings
dlux_settings(globals())"""
                })
        else:
            self.stdout.write(self.style.WARNING('⚠ Unable to inspect'))

        # ─────────────────────────────────────────────────
        # Print Issues
        # ─────────────────────────────────────────────────
        if issues:
            self.stdout.write('\n\n' + '=' * 50)
            self.stdout.write(self.style.ERROR('\n❌ REQUIRED CONFIGURATION MISSING:\n'))
            for issue in issues:
                self.stdout.write(self.style.WARNING(f"\n▶ {issue['setting']}:"))
                self.stdout.write(f"\n{issue['snippet']}\n")

        # ─────────────────────────────────────────────────
        # Print Warnings
        # ─────────────────────────────────────────────────
        if warnings:
            self.stdout.write('\n' + '=' * 50)
            self.stdout.write(self.style.WARNING('\n⚠️  WARNINGS:\n'))
            for warning in warnings:
                self.stdout.write(self.style.WARNING(f"\n▶ {warning['setting']}:"))
                if 'message' in warning:
                    self.stdout.write(f"  {warning['message']}")
                self.stdout.write(f"\n{warning['snippet']}\n")

        # ─────────────────────────────────────────────────
        # Summary
        # ─────────────────────────────────────────────────
        self.stdout.write('\n' + '=' * 50)
        if not issues and not warnings:
            self.stdout.write(self.style.SUCCESS('\n✅ All configurations are correct!\n'))
        elif not issues:
            self.stdout.write(self.style.SUCCESS('\n✅ Core configuration OK (warnings above)\n'))
        else:
            self.stdout.write(self.style.ERROR(f'\n❌ {len(issues)} issue(s) require attention\n'))
