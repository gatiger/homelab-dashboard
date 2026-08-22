# Upgrade to v0.5.0

v0.5.0 adds the searchable universal service catalog. It does not change the SQLite schema.

## Preserve your data

Keep the existing `dashboard-data` Docker volume. Do not use `docker compose down -v`.

## Replace application files

Copy the v0.5.0 `backend/` and `frontend/` contents over the existing stack copies. The v0.4.x Compose configuration can remain in place.

Then rebuild/recreate:

```bash
docker compose build
docker compose up -d --force-recreate
```

Or use the equivalent rebuild/start workflow in Dockge.

## Verify

Hard-refresh the browser after the containers start. The footer should read:

```text
Homelab Dashboard v0.5.0
```

Click **Add service**. The searchable service catalog should open before the service configuration form.

Existing accounts, cards, categories, API keys, and monitoring settings remain unchanged.
