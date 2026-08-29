from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path


urlpatterns = [path('', include('dlux.urls'))]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
