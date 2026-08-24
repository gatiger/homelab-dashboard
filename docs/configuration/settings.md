# Settings

The central **Settings** hub keeps configuration from expanding across the dashboard header. Settings are role-aware: Owners/Admins can manage global operational settings, while Owners alone manage local users.

## General

General settings currently include:

- Dashboard title.
- Whether the time-of-day greeting is shown.
- A shortcut to add dashboard widgets.

Settings are stored in the same persistent SQLite database as services and pages.

## Account

Account settings provide:

- Change-password workflow requiring the current password.
- Recovery-code creation/regeneration requiring the current password.
- Recovery-code status and password-change timestamps.
- Recent account-security activity.

Changing the password invalidates other active sessions. Recovery codes are shown only when generated and are stored only as digests. See [Account recovery](account-recovery.md).

## Users

Owners see **Settings → Users**. It provides local account creation, role changes, enable/disable controls, Owner-initiated password resets, and deletion. Admin, Editor, and Viewer accounts do not receive this tab. See [Users and roles](users-roles.md).

## Dashboard

Dashboard settings provide:

- **Export layout** — downloads a portable JSON structure containing pages, categories, public service-card configuration, and widgets.
- **Import layout** — adds pages from a compatible layout file alongside the current dashboard.

Layout files intentionally exclude API keys, passwords, encrypted secrets, controller credentials, and active management links. Use `/app/data` backup/restore for full disaster recovery.

## Appearance

Appearance links to the theme manager. In addition to built-in/imported themes, v0.14 adds a visual custom-theme editor that starts from the active theme and edits the same validated design tokens used by community theme packages.

## Connections

Owner/Admin accounts can manage reusable management connections such as TrueNAS. Connections remain independent from visible service cards.

## Monitoring

Owner/Admin accounts can change the following intervals without rebuilding or recreating the dashboard container:

- **Service telemetry refresh** — how often an open browser refreshes live HTTP/integration data.
- **Update-state refresh** — how often an open browser reads the already-cached update state.
- **Active-job refresh** — faster polling while a service update is actually running.
- **Automatic update discovery** — the heavier server-side Docker/TrueNAS update check schedule. Set this to Disabled to stop scheduled discovery; manual **Check for updates** still works.

The browser refresh intervals do not themselves pull Docker images or repeatedly query registries. They read current backend state.

## Updates

Owner/Admin accounts can configure the optional update-maintenance scheduler. Scheduled installation is disabled by default. Settings include:

- **Enable scheduled service updates** — master switch for unattended service-scoped updates.
- **Maintenance days** — one or more days of the week.
- **Maintenance window** — start/end times interpreted using the Dashboard server/container local clock; overnight windows are supported.
- **Default release delay** — minimum age of a detected update before the scheduler may install it.
- **Automatic rollback** — when enabled, requests rollback only from providers that explicitly advertise a safe automatic rollback path.
- **Stop on failure** — stops the remaining sequential maintenance queue after the first failed/rolled-back update.

Individual service cards can inherit these defaults or override scheduling, release delay, and rollback behavior. **Monitor only** prevents both manual and scheduled installation for that card. Host-scoped operations such as TrueNAS System updates remain manual and require their normal explicit confirmation.

See [Update Manager](update-manager.md) for scheduler timing, verification, rollback limitations, and recovery behavior.

## Extensions

Owner/Admin accounts can use Settings → Extensions to inventory built-in modules, themes, and imported extension packages. v0.17 also browses the configured extension registry, shows trust/compatibility metadata, checks for newer package versions, and installs or updates checksum-verified data-only page-template/service-catalog packs. Manual JSON import remains available if the registry is offline. Executable third-party plugins remain disabled.
