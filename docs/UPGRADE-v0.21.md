# Upgrade to v0.21.0

v0.21 adds opt-in scheduled service maintenance, per-service update policies, post-update health verification, capability-aware rollback handling, Docker provider suggestions, and post-host-reboot service recovery checks.

## Required changes

No manual Compose, environment-variable, credential, or database changes are required for the application upgrade.

Continue to preserve the Dashboard `/app/data` volume. Existing installations receive the new SQLite columns/settings automatically at startup.

## Existing update configuration

Existing management-provider links remain unchanged. Manual **Check for updates**, individual **Update**, **Update all**, TrueNAS App upgrades, and explicitly confirmed TrueNAS System updates continue to use the providers already configured on each card.

Scheduled installation starts **disabled**, so upgrading to v0.21 does not begin unattended updates.

## Optional: enable scheduled maintenance

1. Sign in as an Owner or Admin.
2. Open **Settings → Updates**.
3. Enable **scheduled service updates**.
4. Select one or more maintenance days.
5. Set the maintenance start/end time. The Dashboard server/container local clock is used.
6. Choose the default release delay.
7. Leave **automatic rollback** enabled only if you understand the provider-specific rollback scope.
8. Leave **stop on failure** enabled for the safest unattended behavior.
9. Save Settings.

Host-scoped updates such as TrueNAS System remain manual even after this scheduler is enabled.

## Optional: configure per-service policies

Edit a managed service card and choose the desired policy:

- **Use global policy** — follows the global scheduler state/defaults.
- **Manual** — never scheduled; manual updates remain available.
- **Scheduled** — eligible during maintenance windows when the global scheduler is enabled.
- **Monitor only** — detect/report only; Dashboard cannot install the card's update.

A card may also override the global release delay and rollback policy.

## Docker provider auto-detection

When a card has no management provider configured and the optional Docker update agent is available, v0.21 may show **Update management detected** when the card exactly matches a discovered Compose service. Click **Use detected service**, review the selected project/service, and save the card to enable management. No update control is granted automatically.

## Docker rollback warning

The Docker provider can restore the image that was running before an update. It cannot generically reverse changes a new application version makes inside persistent volumes or databases.

For software with potentially incompatible migrations:

1. set the service's rollback policy to **Manual**;
2. keep an application/platform-supported backup or snapshot; and
3. follow the application's documented downgrade/restore procedure if needed.

## Post-host-reboot checks

Before a TrueNAS System update, Dashboard now records other enabled status-monitored services that are healthy. After the host returns, it checks those services again. If any do not recover, the host update remains recorded as successful when the target TrueNAS version is confirmed, but Update History identifies the services that need attention.
