ROLE_ADMIN = "admin"
ROLE_STAFF = "staff"
ROLE_USER = "user"

ROLE_CHOICES = (
    (ROLE_ADMIN, "Project admin"),
    (ROLE_STAFF, "Project staff"),
    (ROLE_USER, "Project user"),
)

ROLE_VALUES = {ROLE_ADMIN, ROLE_STAFF, ROLE_USER}

AUDIT_AUTHORIZE_ALLOWED = "authorize_allowed"
AUDIT_AUTHORIZE_DENIED = "authorize_denied"
AUDIT_SESSION_REVOKED = "session_revoked"

