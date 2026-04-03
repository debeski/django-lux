# Fundemental imports
import json
import os
import re
import sys
import platform
import urllib.request

import django
import psutil
from django.apps import apps
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.db.models import Count
from django.db.models.functions import TruncHour
from django.utils.module_loading import import_string

from microsys import __version__

try:
    import rest_framework
except ImportError:
    rest_framework = None


# Dashboard View removed as per UX enhancements
# @login_required
# def dashboard(request):
#     ...

# System Options — Displays accessibility settings, system info, and README specs
@login_required
def options_view(request):
    """
    View for system options, accessibility settings, and system info.
    Reads documented specs from README.md.
    """
    readme_path = os.path.join(settings.BASE_DIR, "README.md")
    readme_content = ""
    if os.path.exists(readme_path):
        try:
            with open(readme_path, "r", encoding="utf-8") as f:
                readme_content = f.read()
        except:
            pass

    # Helper to pull version strings from README using regex capture groups
    def extract_spec(pattern):
        match = re.search(pattern, readme_content)
        return match.group(1).strip() if match else "N/A"

    # API Health Check (Targeting project's own API via loopback)
    api_reachable = False
    api_error = ""
    try:
        # Hit the loopback address to verify the API is responding inside the container
        api_url = "http://127.0.0.1:8000/api/decrees/" 
        
        req = urllib.request.Request(api_url)
        req.add_header("X-API-KEY", getattr(settings, "X_API_KEY", ""))
        req.add_header("X-SECRET-KEY", getattr(settings, "X_SECRET_KEY", ""))
        
        with urllib.request.urlopen(req, timeout=3) as response:
            if response.status == 200:
                api_reachable = True
            else:
                api_error = f"Status: {response.status}"
    except Exception as e:
        api_reachable = False
        api_error = str(e)

    # System Stats
    try:
        # RAM
        mem = psutil.virtual_memory()
        ram_total_gb = mem.total / (1024 ** 3)
        ram_used_gb = mem.used / (1024 ** 3)
        ram_percent = mem.percent
        
        # Disk
        disk = psutil.disk_usage('/')
        disk_total_gb = disk.total / (1024 ** 3)
        disk_used_gb = disk.used / (1024 ** 3)
        disk_percent = disk.percent
    except Exception as e:
        ram_total_gb = ram_used_gb = ram_percent = 0
        disk_total_gb = disk_used_gb = disk_percent = 0

    context = {
        'current_time': timezone.now(),
        'os_info': f"{platform.system()} {platform.release()}",
        'python_version': sys.version.split()[0],
        'django_version': django.get_version(),
        'drf_version': getattr(rest_framework, 'VERSION', 'N/A'),
        'api_reachable': api_reachable,
        'api_error': api_error,
        'db_info': extract_spec(r'PostgreSQL ([\d.]+)'),
        'redis_info': extract_spec(r'Redis ([\d.]+)'),
        'celery_info': extract_spec(r'Celery ([\d.]+)'),
        'version': __version__,
        
        # System Stats
        'ram_total': f"{ram_total_gb:.1f}",
        'ram_used': f"{ram_used_gb:.1f}",
        'ram_percent': ram_percent,
        'disk_total': f"{disk_total_gb:.1f}",
        'disk_used': f"{disk_used_gb:.1f}",
        'disk_percent': disk_percent,
    }
    return render(request, 'microsys/includes/options.html', context)


@login_required
def system_setup_view(request):
    """Dedicated first-launch setup page for superusers."""
    if not request.user.is_superuser:
        raise PermissionDenied

    SystemSettings = apps.get_model('microsys', 'SystemSettings')
    instance = SystemSettings.load()
    if getattr(instance, 'is_configured', False):
        return redirect('options_view')

    SystemSettingsForm = import_string('microsys.forms.SystemSettingsForm')

    if request.method == 'POST':
        form = SystemSettingsForm(
            request.POST,
            request.FILES,
            instance=instance,
            request=request,
            user=request.user,
            mode='setup',
        )
        if form.is_valid():
            form.save()
            from microsys.utils import get_system_config
            return redirect(get_system_config().get('home_url', '/sys/'))
    else:
        form = SystemSettingsForm(
            instance=instance,
            request=request,
            user=request.user,
            mode='setup',
        )

    context = {
        'form': form,
        'page_title': 'System Setup',
    }
    return render(request, 'microsys/includes/system_setup.html', context)
