# Public Registration Playground

Public registration is a core Microsys playground feature. It is disabled by
default and separate from optional SSO.

## What It Does

When enabled, anonymous users can request a local Microsys account at:

```text
/accounts/register/
```

The form asks for email, password, and optional first/last name. Microsys
generates the username internally. The account is created inactive, a
verification token is stored hashed only, and the user must verify email before
the account can become usable.

Public registration supports two activation modes:

| Mode | Behavior |
| --- | --- |
| `auto_login_after_verify` | Email verification activates the local user and signs them in. |
| `verified_pending_approval` | Email verification keeps the user inactive until a superuser approves them. |

Pending approvals are managed at:

```text
/sys/registrations/
```

Approve and reject actions are POST-only and superuser-only.

Users created through this path are marked as public-registration-originated in Microsys runtime surfaces so operators can distinguish them from manually created local accounts.

## Required Email Setup

Public registration requires Microsys email delivery. Setup/System Settings
step 3 includes an **Email delivery** subsection with two independent choices:

| Choice | Behavior |
| --- | --- |
| Delivery path: `direct` | The web process connects to the SMTP provider itself. Use this when the web service has egress to the SMTP host. |
| Delivery path: `relay` | The web process sends to the generated internal `smtp-relay:1025` service. Use this when the web service is isolated and only the relay has internet egress. |
| Secret storage: `encrypted_db` | Microsys stores the SMTP password encrypted in `SystemSettings.email_config`. This works with both direct delivery and relay delivery. Exports include only a redacted “password configured” marker, so imported setups must re-enter the secret. |
| Secret storage: `env` | Environment/secrets-owned mode. The UI may store/export non-sensitive hints such as host, port, username, and from address, but the SMTP password stays in environment variables or secrets. |

Generated projects can still read standard Django email settings when secret
storage is environment/secrets-owned:

```text
EMAIL_BACKEND
EMAIL_HOST
EMAIL_PORT
EMAIL_USE_TLS
EMAIL_USE_SSL
EMAIL_HOST_USER
EMAIL_HOST_PASSWORD
DEFAULT_FROM_EMAIL
```

In production, use a real email backend with `EMAIL_HOST`,
`EMAIL_PORT`, and `DEFAULT_FROM_EMAIL`. In local `DEBUG=True` testing,
console, locmem, and file-based backends are accepted.

Generated Docker projects default to an internal SMTP relay so the `web` and
`celery` containers can remain on the internal Docker network. The app talks to
`smtp-relay:1025`; only the `smtp-relay` service joins the public network for
outbound SMTP egress, and the scaffold does not publish an inbound relay port.
The relay can fall back to these upstream env settings before UI-managed relay
delivery is configured:

```text
DEFAULT_FROM_EMAIL
SMTP_RELAY_HOST
SMTP_RELAY_PORT
SMTP_RELAY_USE_TLS
SMTP_RELAY_USER
SMTP_RELAY_PASSWORD
```

With this layout, choose delivery path `Internal SMTP relay`, choose secret
storage `Encrypted database secret`, and enter the upstream provider settings,
for example Gmail host `smtp.gmail.com`, port `587`, TLS enabled, SMTP
username, app password, and default-from address. The web container still sends
only to the internal `smtp-relay:1025` listener; the relay loads the upstream
settings from `SystemSettings.email_config` on delivery. If the web process can
reach the SMTP server directly, choose delivery path `Direct SMTP from web
service`; encrypted DB secrets still work in that mode.

The setup/System Settings security step refuses to enable public registration
or email 2FA when the selected Microsys email delivery path and secret storage
are not ready. Microsys-owned transactional mail uses this package-owned
configuration through helpers; it does not force the host project’s unrelated
Django email behavior to change.

## Security Defaults

- Email verification is mandatory.
- Verification tokens are generated with `secrets` and stored as SHA-256 hashes.
- Duplicate email signup returns the same generic sent page and does not reveal
  whether an account exists.
- Registration uses cache throttles by IP and email when
  `registration_throttle_enabled` is enabled.
- The form includes a honeypot field; filled honeypots silently get the generic
  sent response.
- Publicly registered users are not automatically assigned a generated scope by
  Microsys scope auto-creation.
- Login accepts username or email only when public registration is enabled.
- Email verification, readiness checks, and public registration all use the same Microsys email delivery contract as email 2FA.

## Relation To SSO

Public registration creates local users in the deployed Microsys project. It
does not create SSO client-originated registration APIs and does not change the
optional SSO provider/client packages.

SSO remains admin-provisioned for now: connected projects receive identities
through OIDC after a provider-side user and per-client role exist. Public
registration is the first local account-signup path that can later support a
broader identity-provider workflow.
