from django.urls import include, path


urlpatterns = [
    path('dlux/', include('dlux.urls')),
]
