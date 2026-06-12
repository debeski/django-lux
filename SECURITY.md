# Security Policy

## Supported Versions

Security fixes are prioritized for the latest released `django-lux` package and the current `main` branch. Older releases may receive fixes when a backport is practical, but users should generally upgrade to the latest stable version after a security advisory is published.

Optional packages such as `django-lux-sso` and `django-lux-sso-client` are maintained separately. Report vulnerabilities for them through their own repositories when available, or include the affected package name in your report.

## Required Security Standard

All Dlux security-sensitive work must follow the active [DSRP-1 Security Standard](docs/security-dsrp-1.md). DSRP-1 is the required baseline for authorization boundaries, security-flow design, backend enforcement, CSP/runtime asset expectations, and related review decisions.

Contributions, fixes, refactors, configuration changes, and documentation updates must not weaken or bypass DSRP-1. If a proposed change conflicts with DSRP-1, update the design so it complies before merging or releasing it.

## Reporting a Vulnerability

Do not open a public GitHub issue for a suspected vulnerability.

Preferred reporting path:

1. Use GitHub's private vulnerability reporting flow for this repository.
2. If private reporting is unavailable, email `debeski1@gmail.com` with the subject `Security report: django-lux`.

Include as much detail as you can safely share:

- Affected package, version, branch, or commit.
- A clear description of the vulnerability and expected impact.
- Reproduction steps or a minimal proof of concept.
- Relevant settings, middleware, deployment mode, or optional package usage.
- Whether the issue is already public or being coordinated elsewhere.

## What to Expect

The maintainer will try to acknowledge valid reports within 7 days. Confirmed vulnerabilities are handled privately until a fix, mitigation, or advisory is ready. Public disclosure timing should be coordinated with the maintainer so users have a reasonable chance to upgrade.

Reports may be declined when they require unrealistic privileges, depend only on insecure host-project configuration outside Dlux control, or do not cross a security boundary.

## Scope

Security-sensitive areas include authentication, authorization, staff-tier permission checks, setup guards, 2FA and trusted-device flows, session handling, file download/export helpers, audit logging, SSO integration points, and any behavior that could expose secrets or private user data.

Out of scope examples include:

- Vulnerabilities in unsupported Django or Python versions.
- Denial-of-service claims without a practical attack path.
- Social engineering, spam, or physical access scenarios.
- Findings that only affect a project after disabling documented security controls.

## Safe Harbor

Good-faith security research is welcome when it avoids privacy violations, data destruction, service disruption, and public disclosure before a fix is available. Use only accounts, systems, and data you own or have explicit permission to test.
