import os

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path


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

urlpatterns = [path('', include('dlux.urls'))]
if os.environ.get('DLUX_E2E_WEATHER'):
    from django.contrib.auth.decorators import login_required
    from django.shortcuts import render

    @login_required
    def weather_dashboard(request):
        return render(request, 'dlux/weather/e2e_dashboard.html')

    urlpatterns.insert(0, path('weather-dashboard/', weather_dashboard))
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
