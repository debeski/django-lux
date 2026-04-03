from django.http import HttpResponse
from django.urls import include, path


def index(request):
    return HttpResponse('project index')


urlpatterns = [
    path('', include('microsys.urls')),
    path('', index, name='index'),
]
