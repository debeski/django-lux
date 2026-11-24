import os

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path


if os.environ.get('DLUX_E2E_OCR_MODELS'):
    # Six models with a file field, so Extra Features lists six models under
    # "Models included in automatic OCR". Layout only: nothing is read or saved.
    from dlux.files.registry import register_document_file
    from dlux.models import ManagedAsset, SystemSettings
    from dlux.models.files import FileVersion
    from dlux.models.users import Profile
    from dlux.tests.document_files_app.models import LegacyFileVersion, Paper

    for model, field in (
        (Paper, 'pdf_file'), (LegacyFileVersion, 'archived_file'), (FileVersion, 'archived_file'),
        (ManagedAsset, 'file'), (SystemSettings, 'logo'), (Profile, 'profile_picture'),
    ):
        register_document_file(model, field)

if os.environ.get('DLUX_E2E_PROJECT_SETTINGS'):
    # One sample project tile, for the setup wizard's Project settings step.
    from dlux.options import register_app_settings

    register_app_settings(
        namespace='e2e.project',
        title='E2E Project',
        fields=[
            {'name': 'enabled', 'type': 'boolean', 'label': 'Enable project feature', 'default': True},
            {'name': 'limit', 'type': 'integer', 'label': 'Limit', 'default': 5, 'min_value': 1, 'max_value': 20},
        ],
    )

    # And one grouped tile: two namespaces, one Options tile, one save.
    from dlux.options import register_app_settings_group

    register_app_settings_group(id='e2e.group', title='E2E Group')
    for order, name in ((1, 'alpha'), (2, 'beta')):
        register_app_settings(
            namespace=f'e2e.{name}',
            title=f'Section {name.title()}',
            group='e2e.group',
            order=order,
            fields=[{'name': 'limit', 'type': 'integer', 'label': 'Limit', 'default': order,
                     'min_value': 1, 'max_value': 50}],
        )



def project_scripts(request):
    """A project page whose {% block scripts %} file runs without defer."""
    from django.shortcuts import render
    return render(request, 'e2e/project_scripts.html')


urlpatterns = [path('e2e-project-scripts/', project_scripts), path('', include('dlux.urls'))]
if os.environ.get('DLUX_E2E_WEATHER'):
    from django.contrib.auth.decorators import login_required
    from django.shortcuts import render

    @login_required
    def weather_dashboard(request):
        return render(request, 'dlux/weather/e2e_dashboard.html')

    urlpatterns.insert(0, path('weather-dashboard/', weather_dashboard))
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
