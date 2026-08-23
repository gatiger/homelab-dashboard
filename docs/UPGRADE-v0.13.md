# Upgrade to v0.13

v0.13 performs an in-place SQLite migration. Existing users, services, pages, categories, themes, credentials, management Connections, update state/history, and Docker update-agent configuration are preserved.

The migration adds:

- Persistent dashboard Settings values.
- The `dashboard_widgets` table.
- Widget-aware category/page safeguards.

No Compose change is required when upgrading from v0.12. Existing `dashboard` and `update-agent` containers continue to use the same environment variables and persistent dashboard volume.

After upgrade, open **Settings** to review the default monitoring intervals or add the first widget. Existing v0.12 refresh behavior maps to the v0.13 defaults (15-second telemetry/state refresh and 12-hour update discovery unless the deployment previously supplied another update-check interval).
