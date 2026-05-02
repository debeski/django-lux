# django-microsys-sso-client

Lightweight Django OIDC client SDK for projects that authenticate against a
Microsys SSO provider. This package does not depend on `django-microsys`.

This SDK is optional and Django-specific. Non-Django projects should connect to
the Microsys SSO provider with their platform's normal OIDC client library and
read the portable `microsys_sso_role` claim.

```python
from microsys_sso_client.settings import configure_microsys_sso

configure_microsys_sso(
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
    path("accounts/sso/", include("microsys_sso_client.urls")),
]
```
