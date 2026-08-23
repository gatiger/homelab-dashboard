# Upgrade to v0.9.0

v0.9.0 adds appearance settings and importable theme packages. The migration is automatic and does not alter existing service, page, category, API-key, or account records.

The dashboard creates two new SQLite tables on startup:

- `app_settings`
- `custom_themes`

Existing installations default to **System** appearance after upgrading. Users can choose another theme from **Appearance**.

## Image-based installations

Update using your normal image workflow:

```bash
docker compose pull
docker compose up -d
```

For version-pinned installs, set `DASHBOARD_VERSION=0.9.0` before pulling.

Do not use `docker compose down -v`; the persistent data volume contains the dashboard database, encryption key, and imported themes.
