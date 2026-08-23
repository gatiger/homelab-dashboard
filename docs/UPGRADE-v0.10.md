# Upgrade to v0.10.0

v0.10.0 adds richer service integrations, encrypted username/password credential fields for integrations that need them, and the shared activity/progress model.

## Data migration

The database migration is automatic. Existing v0.9 services, API keys, pages, categories, card layout, themes, administrator account, and appearance settings remain in place. Two nullable encrypted credential columns are added to `services` for username/password integrations such as qBittorrent.

Keep the persistent dashboard data volume during the update. Do **not** run `docker compose down -v`.

## Normal image update

```bash
docker compose pull
docker compose up -d
```

For version-pinned installs, set `DASHBOARD_VERSION=0.10.0` before pulling.

## After upgrading

Existing cards continue to work without credentials. To enable the new rich integrations, edit the corresponding card and add its API key or qBittorrent WebUI credentials. Standard and Wide cards show activity/progress; Compact cards intentionally omit rich detail.

See `docs/configuration/service-integrations.md` for the supported authentication methods and TrueNAS compatibility note.
