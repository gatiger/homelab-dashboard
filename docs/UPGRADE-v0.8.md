# Upgrade to v0.8.0

v0.8 adds persistent dashboard pages and category layout metadata. The backend performs the database migration automatically on startup.

## What happens to existing v0.7 data

- A default **Home** page is created automatically.
- Every existing service is assigned to Home.
- Existing service names, URLs, categories, favorites, card sizes, ordering, API credentials, and monitoring settings are preserved.
- Existing categories are registered in their current display order and start expanded.

No manual database conversion is required.

## Image-based installation

Set the desired version and recreate the application container without deleting the data volume:

```bash
DASHBOARD_VERSION=0.8.0 docker compose pull
docker compose up -d
```

If you manage the version in `.env`, change `DASHBOARD_VERSION` there first and then run:

```bash
docker compose pull
docker compose up -d
```

## Important

Do **not** run `docker compose down -v` during a normal upgrade. The `-v` flag removes persistent volumes and can delete the dashboard database and local encryption key.

Back up `/app/data` or the dashboard data volume before upgrading. See `docs/configuration/backup-restore.md`.
