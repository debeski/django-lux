# django-lux-sso-client

Lightweight Django OIDC client SDK for projects that authenticate against a
Dlux SSO provider. This package does not depend on `django-lux`.

This SDK is optional and Django-specific. Non-Django projects should connect to
the Dlux SSO provider with their platform's normal OIDC client library and
read the portable `dlux_sso_role` claim.

```python
from dlux_sso_client.settings import configure_dlux_sso

configure_dlux_sso(
    globals(),
    issuer_url="https://sso.example.com",
    client_id="client-id",
    client_secret="client-secret",
    role_mapping={
        "staff_roles": ["admin", "staff"],
        "groups": {"admin": ["Project Admins"], "staff": ["Project Staff"]},
    },
)
```

Mount the OIDC client routes:

```python
from django.urls import include, path

urlpatterns = [
    path("accounts/sso/", include("dlux_sso_client.urls")),
]
```
