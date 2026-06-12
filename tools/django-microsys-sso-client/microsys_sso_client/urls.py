from django.urls import include, path

urlpatterns = []

try:
    import mozilla_django_oidc.urls  # noqa: F401
except ImportError:  # pragma: no cover - dependency is installed with the client package.
    pass
else:
    urlpatterns.append(path("oidc/", include("mozilla_django_oidc.urls")))

