from pathlib import Path


def _coerce_list(scope, key):
    value = scope.setdefault(key, [])
    if isinstance(value, tuple):
        value = list(value)
        scope[key] = value
    if not isinstance(value, list):
        raise TypeError(f"{key} must be a list or tuple before microsys_sso_settings() runs")
    return value


def _insert_once(items, value, *, before=None, after=None):
    if value in items:
        items.remove(value)
    if before and before in items:
        items.insert(items.index(before), value)
    elif after and after in items:
        items.insert(items.index(after) + 1, value)
    else:
        items.append(value)


def microsys_sso_settings(scope):
    """
    Apply optional Microsys SSO provider settings to a Django settings module.

    The core Microsys package intentionally does not call this helper. Projects
    that want to act as an SSO provider opt in from settings.py.
    """
    if not isinstance(scope, dict):
        raise TypeError("microsys_sso_settings() expects the result of globals() from settings.py")

    installed_apps = _coerce_list(scope, "INSTALLED_APPS")
    middleware = _coerce_list(scope, "MIDDLEWARE")

    for app_label in reversed(["microsys_sso", "oauth2_provider"]):
        if app_label in installed_apps:
            installed_apps.remove(app_label)
        installed_apps.insert(0, app_label)

    _insert_once(
        middleware,
        "oauth2_provider.middleware.OAuth2TokenMiddleware",
        after="django.contrib.auth.middleware.AuthenticationMiddleware",
    )

    if not scope.get("OIDC_RSA_PRIVATE_KEY"):
        env_key = scope.get("MICROSYS_SSO_PRIVATE_KEY")
        key_path = scope.get("MICROSYS_SSO_PRIVATE_KEY_PATH")
        if env_key:
            scope["OIDC_RSA_PRIVATE_KEY"] = env_key
        elif key_path:
            scope["OIDC_RSA_PRIVATE_KEY"] = Path(key_path).read_text(encoding="utf-8")

    provider_config = dict(scope.get("MICROSYS_SSO_PROVIDER", {}))
    provider_config.setdefault("issuer", scope.get("MICROSYS_SSO_ISSUER", ""))
    provider_config.setdefault("require_https_redirects", True)
    provider_config.setdefault("allow_localhost_redirects", bool(scope.get("DEBUG", False)))
    provider_config.setdefault("allowed_roles", ["admin", "staff", "user"])
    scope["MICROSYS_SSO_PROVIDER"] = provider_config

    oauth2_settings = dict(scope.get("OAUTH2_PROVIDER", {}))
    oauth2_settings.setdefault("OIDC_ENABLED", True)
    oauth2_settings.setdefault("OIDC_RSA_PRIVATE_KEY", scope.get("OIDC_RSA_PRIVATE_KEY", ""))
    oauth2_settings.setdefault("SCOPES", {
        "openid": "OpenID Connect",
        "email": "Email address",
        "profile": "Basic profile",
    })
    oauth2_settings.setdefault(
        "OAUTH2_VALIDATOR_CLASS",
        "microsys_sso.validators.MicrosysOIDCValidator",
    )
    oauth2_settings.setdefault("PKCE_REQUIRED", True)
    scope["OAUTH2_PROVIDER"] = oauth2_settings
    return scope
