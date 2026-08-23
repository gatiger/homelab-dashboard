# Settings

v0.13 introduces a central **Settings** hub so configuration does not keep expanding across the dashboard header.

## General

General settings currently include:

- Dashboard title.
- Whether the time-of-day greeting is shown.
- A shortcut to add dashboard widgets.

Settings are stored in the same persistent SQLite database as services and pages.

## Appearance

The Appearance section links to the existing theme manager. Built-in and imported themes continue to use the validated design-token model introduced in v0.9.

## Connections

The Connections section links to reusable management connections such as TrueNAS. Connections remain independent from visible service cards.

## Monitoring

The following intervals can be changed without rebuilding or recreating the dashboard container:

- **Service telemetry refresh** — how often an open browser refreshes live HTTP/integration data.
- **Update-state refresh** — how often an open browser reads the already-cached update state.
- **Active-job refresh** — faster polling while a service update is actually running.
- **Automatic update discovery** — the heavier server-side Docker/TrueNAS update check schedule. Set this to Disabled to stop scheduled discovery; manual **Check for updates** still works.

The browser refresh intervals do not themselves pull Docker images or repeatedly query registries. They read current backend state.

## Extensions

The v0.13 Extension Manager is deliberately conservative. It inventories:

- Built-in core modules.
- The built-in widget pack.
- Imported data-only themes.

Imported themes can be removed from the manager. v0.13 does **not** execute arbitrary community plugin code. The permission-aware executable extension runtime remains a later milestone.
