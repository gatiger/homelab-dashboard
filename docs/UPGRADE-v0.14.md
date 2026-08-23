# Upgrade to v0.14

v0.14 performs an in-place SQLite migration and preserves existing users, services, widgets, pages, themes, connections, update state/history, and update-agent configuration.

The migration adds an optional `icon` field to persisted category layouts. Existing categories default to the standard Server icon until customized.

No Compose changes are required when upgrading from v0.13.1. Continue using the same dashboard data volume and update-agent configuration.

After upgrade:

1. Existing service and widget sort values are retained.
2. The first unified mixed-card reorder in a category normalizes service/widget sort positions together.
3. Favorite service cards remain pinned ahead of unpinned services and widgets.
4. Dashboard layout exports intentionally omit credentials and are not full backups.

Use the normal image-update procedure described in `docs/configuration/updating.md`.
