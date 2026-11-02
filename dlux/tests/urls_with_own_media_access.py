from django.http import HttpResponse
from django.urls import include, path


def own_media_access(request):
    return HttpResponse(status=403)


urlpatterns = [
    path('sys/files/media-access/', own_media_access),
    path('dlux/', include('dlux.urls')),
]
