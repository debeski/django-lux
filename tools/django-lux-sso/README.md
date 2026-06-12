# django-lux-sso

Optional OIDC provider plugin for `django-lux`.

This package is intentionally separate from core `django-lux`. Install it only
in the Dlux deployment that should act as the identity provider.

Connected projects can be written in any stack that supports OpenID Connect
Authorization Code flow. The Django client package is only a convenience SDK for
Django projects; PHP, .NET, JavaScript, Java, Go, mobile, and desktop clients
should use their standard OIDC libraries.

```python
from dlux_sso.settings import dlux_sso_settings

dlux_sso_settings(globals())
```

Then mount the provider URLs explicitly:

```python
from django.urls import include, path

urlpatterns = [
    path("", include("dlux.urls")),
    path("", include("dlux_sso.urls")),
]
```

Generic OIDC clients should prefer provider discovery:

```text
https://sso.example.com/o/.well-known/openid-configuration/
```

The portable role claim is `dlux_sso_role`, with one of `admin`, `staff`, or
`user`.
