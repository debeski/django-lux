# Admin Guide

This is the operator entry point for DjangoLux after installation. It intentionally links to focused procedures instead of duplicating every configuration and operational detail.

## Configure the system

Start with [System Configuration](system-configuration.md) for the configuration layers, the seventeen-step first-launch wizard, Email, security, navigation, themes, and the Options view.

The short version:

- Use `/sys/setup/` for first launch and `/sys/options/` for ongoing changes.
- Put deployable defaults in `DLUX_CONFIG`; use System Settings for live policy; let `Profile.preferences` remain personal.
- Treat `homepage_config` and `search_config` as the canonical configuration for new work. Legacy flat/titlebar/public-root keys are v1.x mirrors.
- Configure proxy/IP policy before relying on rate limits, lockout, or activity-log attribution.

## Run the application

[Operations](operations.md) covers user/staff tiers, permissions, profile security, activity logs, reports, backups, restore boundaries, assets, and ScanLink.

Useful companion references:

- [Managed Assets](managed-assets.md) — storage, upload policy, and deletion protection.
- [Data & Privacy](data-privacy.md) — data inventory, retention, and consent controls.
- [Public Registration](registration.md) — the disabled-by-default local signup flow.
- [Verified Inline Updates](inline-updater.md) — Composer handoff, update safety, and rollback limits.
- [Deployment Doctor](doctor.md) — deployment diagnosis and safe remediation.

## Admin safety rules

Interface visibility never replaces backend authorization. System-changing actions are POST-only; security-sensitive actions also require the current password. Take a full backup before destructive data reset or restore work, and use `composer check` before changing a generated Compose stack.
