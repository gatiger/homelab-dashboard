# Updating Homelab Dashboard

## Image-based installations

If `DASHBOARD_VERSION=latest`:

```bash
docker compose pull
docker compose up -d
```

For a pinned release, change `DASHBOARD_VERSION` in `.env`, then pull/recreate.

## Git/source-build installations

```bash
git pull --ff-only
docker compose -f compose.yaml -f compose.build.yaml up -d --build
```

## Before an upgrade

- Read the release notes.
- Back up `/app/data` for important installations.
- Never run `docker compose down -v` as an update command.
