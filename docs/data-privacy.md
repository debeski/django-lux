# Data & Privacy

> **Not legal advice.** This page documents what personal data the DjangoLux
> framework stores so that *you*, the operator, can meet your own obligations.
> Data-protection law is jurisdiction-specific (GDPR/UK GDPR, CCPA/CPRA, PIPEDA,
> LGPD, and local/public-sector rules). Confirm your obligations with your own
> counsel or Data Protection Officer.

## Who is responsible

DjangoLux is a **framework**. Under GDPR-style law the legal duties — publishing a
privacy notice, having a lawful basis, capturing consent where required, and
handling access/deletion requests — fall on the **data controller**: the
organization that deploys DjangoLux and decides why it processes user data. The
framework cannot write a legally-correct notice for your deployment because it
does not know your identity, purposes, retention, processors, or jurisdiction.
What it does provide are the hooks to disclose and (optionally) capture consent —
see [Operator controls](#operator-controls-what-djangolux-gives-you).

## Transparency vs. consent

Most of what DjangoLux collects is **security / operational** data. For that kind
of processing the usual lawful basis is **legitimate interest, legal obligation,
or contract — not consent**. You generally should *not* gate audit logging or
brute-force protection behind an opt-in checkbox. What you *do* owe is
**transparency**: a privacy notice telling users what is collected and why.
DjangoLux's cookies are all **essential** (session, CSRF, signed device-trust,
presence), which typically do not require a cookie-consent banner. Consent mainly
matters if you add optional/marketing/analytics processing on top — which
DjangoLux does not do.

## Personal data DjangoLux stores

| Area | Model / store | Data |
| --- | --- | --- |
| **Profile** | `Profile` | Phone number, profile picture, per-user preferences, 2FA flags, encrypted TOTP secret, hashed backup codes, email-verification timestamp |
| **Activity / audit log** | `ActivityLog` | Actor (user), action, category (user/system/audit), model + object identity, document number, **IP address**, timestamps. Sensitive field values are masked; audit rows are append-only |
| **Known devices** | `UserKnownDevice` | Per-user device history keyed by a **signed, hashed** first-party device cookie — device label, **IP address list**, **user-agent list**, first/last seen |
| **Trusted devices (2FA)** | `TrustedDevice` | Hashed device token, session key, device label, **IP address**, **user agent**, expiry (30-day 2FA trust) |
| **Presence / online status** | `UserPresenceSession` | Per-user last-seen, device label, **IP address list**, **user-agent list** |
| **Login lockout** | Django cache (not the DB) | Rolling per-**IP** and per-**username** failed-attempt counters; expire with the configured window/lock duration |
| **Public registration** | `PublicRegistration` | Email, hashed verification token, **IP address**, **user agent**, activation/approval metadata (only when public registration is enabled) |
| **Notifications** | `DluxNotification` | User-facing event content and target metadata, delivered only through per-recipient state after scope and view-permission checks |

Client-IP resolution (which header DjangoLux trusts for the IP addresses above) is
itself configurable — see the Admin Guide, Step 3 / Access & Security.

## Retention

- **Activity logs** have configurable retention/pruning per category
  (System Settings → logging); **audit** rows are kept by default (retention `0` =
  keep forever) and are never auto-pruned unless you set a retention window.
- **Trusted devices** expire after 30 days; users can revoke device trust and
  individual sessions from their Profile → Signed-in Devices card.
- **Login-lockout** counters live only in the cache and expire automatically.

## Data subject rights (what already helps)

- **Access/export**: the per-user **User Report** (`/sys/users/<pk>/report`) and
  the activity-log views expose a user's recorded activity; system settings export
  is available for operators.
- **Rectification**: users edit their own profile; staff can edit users.
- **Erasure**: deleting a user cascades their profile/devices/presence; audit rows
  are intentionally durable — decide your audit-retention policy accordingly.
- **Session/device control**: users can revoke trusted devices and active sessions
  themselves.

There is not yet a one-click "export all my data / delete my account" self-service
flow; if you need that for your jurisdiction, build it on top of the surfaces
above (or ask for it as a feature).

## Operator controls (what DjangoLux gives you)

Configure these in **System Settings → Access & Security → Privacy & Consent**
(or via `DLUX_CONFIG['registration_config']`):

| Setting | Key | Effect |
| --- | --- | --- |
| Privacy policy URL | `privacy_policy_url` | When set, a small privacy line/link appears on the **sign-in and sign-up** pages |
| Terms of service URL | `terms_url` | Optional link shown alongside the privacy policy (and in the consent line) |
| Privacy notice text | `privacy_notice_text` | Optional short sentence shown with the privacy link on the auth pages |
| Require agreement to sign up | `registration_require_consent` | Adds a **required** "I agree to the Terms & Privacy Policy" checkbox to the public registration form |

DjangoLux ships **no legal text** — you supply the policy at the URLs above. The
privacy line renders only when you set a policy URL or notice text; the consent
checkbox appears only when you enable it and only affects the public sign-up form.

## Recommended baseline

1. Publish your own privacy policy and set `privacy_policy_url` (and `terms_url`).
2. Decide your **activity-log/audit retention** and set it deliberately.
3. If your jurisdiction/users need it, enable `registration_require_consent`.
4. Have your legal/compliance function review the above for your jurisdiction.
