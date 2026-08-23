# Settings

The central **Settings** hub keeps configuration from expanding across the dashboard header. v0.15 adds an Account section for password and recovery management.

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

## Dashboard

Dashboard settings provide:

- **Export layout** — downloads a portable JSON structure containing pages, categories, public service-card configuration, and widgets.
- **Import layout** — adds pages from a compatible layout file alongside the current dashboard.

Layout files intentionally exclude API keys, passwords, encrypted secrets, controller credentials, and active management links. Use `/app/data` backup/restore for full disaster recovery.

## Appearance

Appearance links to the theme manager. In addition to built-in/imported themes, v0.14 adds a visual custom-theme editor that starts from the active theme and edits the same validated design tokens used by community theme packages.

## Connections

Connections links to reusable management connections such as TrueNAS. Connections remain independent from visible service cards.

## Monitoring

The following intervals can be changed without rebuilding or recreating the dashboard container:

- **Service telemetry refresh** — how often an open browser refreshes live HTTP/integration data.
- **Update-state refresh** — how often an open browser reads the already-cached update state.
- **Active-job refresh** — faster polling while a service update is actually running.
- **Automatic update discovery** — the heavier server-side Docker/TrueNAS update check schedule. Set this to Disabled to stop scheduled discovery; manual **Check for updates** still works.

The browser refresh intervals do not themselves pull Docker images or repeatedly query registries. They read current backend state.

## Extensions

The Extension Manager remains deliberately conservative. It inventories:

- Built-in core modules.
- The built-in widget pack.
- Imported data-only themes.

Imported themes can be removed from the manager. v0.15 does **not** execute arbitrary community plugin code. The permission-aware executable extension runtime remains a later milestone.
