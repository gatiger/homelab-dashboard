# Upgrade to v0.6.0

1. Stop the dashboard stack.
2. Replace the `backend` and `frontend` folders with the v0.6.0 versions.
3. Keep the existing `dashboard-data` Docker volume. Do **not** run `docker compose down -v`.
4. Rebuild and recreate the application containers:

```bash
docker compose build
docker compose up -d --force-recreate
```

5. Hard-refresh the browser and confirm the footer shows `Homelab Dashboard v0.6.0`.

No Compose changes are required from v0.5.0. On first startup, the backend automatically adds `favorite`, `card_size`, and `sort_order` columns to existing service records. Existing accounts, sessions, service cards, encrypted API keys, monitoring preferences, and URLs are preserved.
