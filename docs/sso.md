# Optional SSO Packages

Microsys SSO is implemented as optional packages in this repository. Core
`django-microsys` does not import or mount SSO code at runtime.

Public registration is a separate core playground feature for local Microsys
accounts. It does not create client-originated SSO registration APIs and does
not change the provider/client package contract documented here.

The provider is an OpenID Connect provider. Connected projects do not need to
use Django, Python, or Microsys. Any PHP, .NET, JavaScript, Java, Go, desktop,
or mobile client that supports OIDC Authorization Code flow can connect to a
deployed Microsys SSO server.

## Provider Plugin

Install `django-microsys-sso` only in the Microsys deployment that should act as
the OIDC identity provider.

```python
from microsys.utils import microsys_settings
from microsys_sso.settings import microsys_sso_settings

microsys_settings(globals())
microsys_sso_settings(globals())
```

Mount provider URLs explicitly:

```python
from django.urls import include, path

urlpatterns = [
    path("", include("microsys.urls")),
    path("", include("microsys_sso.urls")),
]
```

The provider app adds:

- `SSOClientPolicy` for each registered connected project.
- `SSOClientMembership` for per-client `admin`, `staff`, or `user` roles.
- `SSOAdminInvitation` for first-admin bootstrap flows.
- `SSOAuditEvent` and `SSOSessionState` for audit and revocation state.
- OIDC validator hooks that emit standard identity claims plus portable
  `microsys_sso_role` / `microsys_sso_client_id` claims.

For v1, connected clients must use OIDC Authorization Code flow. Redirect URIs
must match exactly, HTTPS is required outside explicitly allowed localhost
development callbacks, and users are denied unless the client policy is active
and the user has an active per-client role.

## Generic OIDC Clients

For non-Django projects, register the project as an SSO client in the deployed
Microsys SSO server, then configure the project's normal OIDC library with the
issuer/discovery URL, client credentials, and exact redirect URI.

Use OIDC discovery when the client library supports it:

```text
Issuer / authority: https://sso.example.com
Discovery URL:      https://sso.example.com/o/.well-known/openid-configuration/
JWKS URL:           https://sso.example.com/o/.well-known/jwks.json
Authorization URL:  https://sso.example.com/o/authorize/
Token URL:          https://sso.example.com/o/token/
UserInfo URL:       https://sso.example.com/o/userinfo/
Scopes:             openid email profile
Flow:               Authorization Code
Token signing:      RS256
Redirect URI:       exact URI registered on the provider
```

Generic client behavior:

- Treat `sub` as the stable user identifier for this issuer; do not key users
  only by email.
- Read `microsys_sso_role` as the provider-issued role for that registered
  client. Valid values are `admin`, `staff`, and `user`.
- Optionally read `microsys_sso.client_id` / `microsys_sso.role` if the client
  supports nested JSON claims.
- Map roles to local permissions, groups, or policies inside the connected
  project. Do not expect Microsys-generated Django permissions.
- Never treat `admin` as automatic root/superuser authority. It means "admin for
  this registered client" and must be mapped locally.
- Reject login if the ID token cannot be validated against JWKS, the issuer does
  not match, the audience/client ID does not match, or the role is absent.

Typical platform configuration:

| Platform | Normal integration path |
| --- | --- |
| PHP/Laravel | Use an OIDC/OAuth client package with the discovery URL or the explicit endpoints above. |
| .NET / ASP.NET Core | Configure OpenID Connect with `Authority = "https://sso.example.com"` and the registered client ID/secret. |
| JavaScript / Node | Use an OIDC client library such as `openid-client` with issuer discovery. |
| Java / Spring | Configure Spring Security OAuth2 client with `issuer-uri` or explicit provider endpoints. |
| Go | Use an OIDC verifier/client library with issuer discovery and JWKS validation. |

## Django Client SDK

Install `django-microsys-sso-client` in connected Django projects. It does not
depend on `django-microsys`.

```python
from microsys_sso_client.settings import configure_microsys_sso

configure_microsys_sso(
    globals(),
    issuer_url="https://sso.example.com",
    client_id="client-id",
    client_secret="client-secret",
    role_mapping={
        "staff_roles": ["admin", "staff"],
        "groups": {
            "admin": ["Project Admins"],
            "staff": ["Project Staff"],
        },
    },
)
```

Mount the client callback/login routes:

```python
from django.urls import include, path

urlpatterns = [
    path("accounts/sso/", include("microsys_sso_client.urls")),
]
```

The client SDK stores a local `SSOIdentity` keyed by `(issuer, subject)`, so
account linking does not depend on email. Local user creation is controlled by
the provider-issued role. The provider `admin` role never becomes Django
`is_superuser`; host projects must map roles to local groups or staff status
explicitly.
