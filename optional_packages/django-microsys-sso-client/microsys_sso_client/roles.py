from django.conf import settings


VALID_ROLES = {"admin", "staff", "user"}


def get_client_config():
    config = getattr(settings, "MICROSYS_SSO_CLIENT", {})
    return config if isinstance(config, dict) else {}


def extract_role(claims):
    if claims.get("microsys_sso_role"):
        return str(claims["microsys_sso_role"]).strip().lower()
    microsys_claim = claims.get("microsys_sso") or {}
    if isinstance(microsys_claim, dict) and microsys_claim.get("role"):
        return str(microsys_claim["role"]).strip().lower()
    return str(claims.get("microsys:role") or claims.get("role") or "").strip().lower()


def is_role_allowed(role, config=None):
    config = config or get_client_config()
    allowed = set(config.get("required_roles") or VALID_ROLES)
    return role in allowed and role in VALID_ROLES


def apply_role_mapping(user, role, config=None):
    """
    Apply local role mapping without ever elevating to Django superuser.

    Staff status is synchronized only when the host project explicitly provides
    staff_roles. Group mapping is additive and local to the client project.
    """
    config = config or get_client_config()
    if config.get("sync_is_staff"):
        user.is_staff = role in set(config.get("staff_roles") or [])

    if config.get("sync_user_fields", True):
        user.is_superuser = bool(getattr(user, "is_superuser", False))

    groups = config.get("groups") or {}
    target_groups = groups.get(role) or []
    if target_groups:
        from django.contrib.auth.models import Group

        for group_name in target_groups:
            group, _created = Group.objects.get_or_create(name=group_name)
            user.groups.add(group)
    return user
