"""A realistic app URLconf for discovery-profile tests.

Covers the shapes that used to be silently dropped: a context-free add page, an
id-bound edit page, an id-bound detail page, plus the ajax/api endpoints that
must stay out of every navigation feature.
"""
from django.http import HttpResponse
from django.urls import include, path


def _view(request, *args, **kwargs):
    return HttpResponse('ok')


# The fixture lives inside the dlux package, so without this it would inherit the
# hidden `dlux` group; a downstream app declares its group the same way.
_view.sidebar_group = 'chapters'


urlpatterns = [
    path('', include('dlux.urls')),
    path('chapters/', _view, name='chapter_list'),
    path('chapters/add/', _view, name='chapter_add'),
    path('chapters/<int:pk>/', _view, name='chapter_detail'),
    path('chapters/<int:pk>/edit/', _view, name='chapter_edit'),
    path('chapters/ajax/search/', _view, name='chapter_ajax_search'),
    path('chapters/api/list/', _view, name='chapter_api_list'),
]
