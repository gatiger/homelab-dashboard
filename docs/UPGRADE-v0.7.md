# Upgrade to v0.7.0

v0.7 changes the recommended distribution model from source-built frontend/backend containers to a published all-in-one image. The application database schema is compatible with v0.6.0.

## Important: preserve your existing data volume

Do not delete the v0.6 `dashboard-data` volume.

If your existing volume has a Compose-generated name such as `dashboard_dashboard-data`, set the v0.7 volume name before starting the new Compose stack:

```env
DASHBOARD_DATA_VOLUME=dashboard_dashboard-data
```

Find the current volume with:

```bash
docker volume ls | grep dashboard
```

Then deploy `compose.yaml`. Once the dashboard opens with your existing account/cards, the source-built frontend/backend containers can be retired.

The optional Docker socket proxy is now separated into `compose.docker.yaml`. The normal dashboard works without it.
