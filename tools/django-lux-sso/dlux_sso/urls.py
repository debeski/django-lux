from django.urls import include, path

from . import views

app_name = "dlux_sso"

dashboard_view = views.SSOProviderDashboardView.as_view()
dashboard_view.sidebar_permissions = ["is_superuser"]

urlpatterns = [
    path("sys/sso/", dashboard_view, name="dashboard"),
    path("sys/sso/clients/<int:policy_id>/members/", views.SSOClientMembershipView.as_view(), name="client_members"),
    path("sys/sso/clients/<int:policy_id>/sessions/", views.SSOClientSessionView.as_view(), name="client_sessions"),
    path("sys/sso/sessions/<int:pk>/revoke/", views.revoke_sso_session, name="revoke_session"),
]

try:
    import oauth2_provider.urls  # noqa: F401
except ImportError:  # pragma: no cover - optional dependency is required when installed as a provider.
    pass
else:
    urlpatterns = [
        path("o/authorize/", views.DluxAuthorizationView.as_view(), name="authorize"),
        path("o/", include("oauth2_provider.urls", namespace="oauth2_provider")),
    ] + urlpatterns
