# microsys/management/commands/microsys_check.py
"""
Management command to validate microsys configuration.
Checks INSTALLED_APPS, MIDDLEWARE, context processors, and URLs.
Prints exact code snippets for any missing configuration.
"""
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Validate microsys configuration and show missing settings'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('\n🔍 MicroSys Configuration Check\n'))
        self.stdout.write('=' * 50 + '\n')

        issues = []
        warnings = []

        # ─────────────────────────────────────────────────
        # Check INSTALLED_APPS
        # ─────────────────────────────────────────────────
        self.stdout.write('\n📋 INSTALLED_APPS: ', ending='')
        if 'microsys' in settings.INSTALLED_APPS:
            self.stdout.write(self.style.SUCCESS('✓ OK'))
        else:
            self.stdout.write(self.style.ERROR('✗ MISSING'))
            issues.append({
                'setting': 'INSTALLED_APPS',
                'snippet': """INSTALLED_APPS = [
    'microsys',  # Add at the top
    # ... other apps
]"""
            })

        # Check dependencies
        deps = ['crispy_forms', 'crispy_bootstrap5', 'django_filters', 'django_tables2']
        missing_deps = [d for d in deps if d not in settings.INSTALLED_APPS]
        if missing_deps:
            warnings.append({
                'setting': 'INSTALLED_APPS (dependencies)',
                'message': f"Missing recommended dependencies: {', '.join(missing_deps)}",
                'snippet': f"""# Add these dependencies to INSTALLED_APPS:
{chr(10).join(f"    '{d}'," for d in missing_deps)}"""
            })

        # ─────────────────────────────────────────────────
        # Check MIDDLEWARE
        # ─────────────────────────────────────────────────
        middleware_path = 'microsys.middleware.ActivityLogMiddleware'
        self.stdout.write('\n📋 MIDDLEWARE: ', ending='')
        if middleware_path in settings.MIDDLEWARE:
            self.stdout.write(self.style.SUCCESS('✓ OK'))
        else:
            self.stdout.write(self.style.ERROR('✗ MISSING'))
            issues.append({
                'setting': 'MIDDLEWARE',
                'snippet': f"""MIDDLEWARE = [
    # ... after AuthenticationMiddleware
    '{middleware_path}',
]"""
            })

        # ─────────────────────────────────────────────────
        # Check Context Processors
        # ─────────────────────────────────────────────────
        context_proc = 'microsys.context_processors.microsys_context'
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
                'snippet': f"""TEMPLATES = [
    {{
        # ...
        'OPTIONS': {{
            'context_processors': [
                # ... other processors
                '{context_proc}',
            ],
        }},
    }},
]"""
            })

        # ─────────────────────────────────────────────────
        # Check URL Configuration (informational)
        # ─────────────────────────────────────────────────
        self.stdout.write('\n📋 URLS: ', ending='')
        try:
            from django.urls import reverse
            reverse('microsys:login')
            self.stdout.write(self.style.SUCCESS('✓ OK'))
        except Exception:
            self.stdout.write(self.style.WARNING('⚠ Not detected'))
            warnings.append({
                'setting': 'urls.py',
                'message': "microsys URLs may not be included",
                'snippet': """# In your project's urls.py:
from django.urls import path, include

urlpatterns = [
    # ...
    path('sys/', include('microsys.urls')),
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
                'snippet': """# Add to settings.py:
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5" """
            })

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
