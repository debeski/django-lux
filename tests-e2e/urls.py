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

urlpatterns = [path('', include('dlux.urls'))]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
