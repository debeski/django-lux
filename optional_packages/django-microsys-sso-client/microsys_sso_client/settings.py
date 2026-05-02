def _coerce_list(scope, key):
    value = scope.setdefault(key, [])
    if isinstance(value, tuple):
        value = list(value)
        scope[key] = value
    if not isinstance(value, list):
        raise TypeError(f"{key} must be a list or tuple before configure_microsys_sso() runs")
    return value


def _insert_once(items, value, *, before=None, after=None, index=None):
    if value in items:
        items.remove(value)
    if index is not None:
        items.insert(index, value)
    elif before and before in items:
        items.insert(items.index(before), value)
    elif after and after in items:
        items.insert(items.index(after) + 1, value)
    else:
        items.append(value)


def configure_microsys_sso(
    scope,
    *,
    issuer_url,
    client_id,
    client_secret,
    role_mapping=None,
    required_roles=None,
    auto_create=True,
):
    """
    Configure a Django project as an OIDC client of a Microsys SSO provider.

    The helper intentionally does not import or require django-microsys.
    """
    if not isinstance(scope, dict):
        raise TypeError("configure_microsys_sso() expects the result of globals() from settings.py")

    issuer_url = issuer_url.rstrip("/")
    installed_apps = _coerce_list(scope, "INSTALLED_APPS")
    middleware = _coerce_list(scope, "MIDDLEWARE")
    auth_backends = _coerce_list(scope, "AUTHENTICATION_BACKENDS")

    for app_label in reversed(["microsys_sso_client", "mozilla_django_oidc"]):
        if app_label in installed_apps:
            installed_apps.remove(app_label)
        installed_apps.insert(0, app_label)

    backend_path = "microsys_sso_client.backends.MicrosysSSOAuthenticationBackend"
    _insert_once(auth_backends, backend_path, index=0)
    if "django.contrib.auth.backends.ModelBackend" not in auth_backends:
        auth_backends.append("django.contrib.auth.backends.ModelBackend")

    _insert_once(
        middleware,
        "mozilla_django_oidc.middleware.SessionRefresh",
        after="django.contrib.auth.middleware.AuthenticationMiddleware",
    )

    scope.setdefault("OIDC_OP_AUTHORIZATION_ENDPOINT", f"{issuer_url}/o/authorize/")
    scope.setdefault("OIDC_OP_TOKEN_ENDPOINT", f"{issuer_url}/o/token/")
    scope.setdefault("OIDC_OP_USER_ENDPOINT", f"{issuer_url}/o/userinfo/")
    scope.setdefault("OIDC_OP_JWKS_ENDPOINT", f"{issuer_url}/o/jwks/")
    scope.setdefault("OIDC_RP_SIGN_ALGO", "RS256")
    scope.setdefault("OIDC_RP_SCOPES", "openid email profile")
    scope.setdefault("OIDC_USE_NONCE", True)
    scope.setdefault("OIDC_CREATE_USER", bool(auto_create))

    scope["OIDC_RP_CLIENT_ID"] = client_id
    scope["OIDC_RP_CLIENT_SECRET"] = client_secret

    client_config = dict(scope.get("MICROSYS_SSO_CLIENT", {}))
    client_config["issuer"] = issuer_url
    client_config["client_id"] = client_id
    client_config["auto_create"] = bool(auto_create)
    client_config["required_roles"] = list(required_roles or ["admin", "staff", "user"])
    role_mapping = dict(role_mapping or {})
    client_config["staff_roles"] = list(role_mapping.get("staff_roles", []))
    client_config["groups"] = dict(role_mapping.get("groups", {}))
    client_config["sync_is_staff"] = bool(role_mapping.get("staff_roles"))
    client_config.setdefault("sync_user_fields", True)
    scope["MICROSYS_SSO_CLIENT"] = client_config

    scope.setdefault("LOGIN_URL", "oidc_authentication_init")
    scope.setdefault("LOGIN_REDIRECT_URL", "/")
    scope.setdefault("LOGOUT_REDIRECT_URL", "/")
    return scope

