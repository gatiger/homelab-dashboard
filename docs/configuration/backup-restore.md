# Backup and restore

Everything unique to a Homelab Dashboard installation lives in `/app/data`, including the SQLite database and the local encryption key used for saved integration secrets.

**Back up the entire data directory/volume together.** Restoring only `dashboard.db` without the matching secret key can make encrypted integration credentials unreadable.

## Named-volume install

The default volume name is `homelab-dashboard-data`.

Backup example:

```bash
mkdir -p backups
docker run --rm \
  -v homelab-dashboard-data:/data:ro \
  -v "$PWD/backups:/backup" \
  alpine:3.22 \
  sh -c 'cd /data && tar czf /backup/homelab-dashboard-data.tgz .'
```

Restore into an empty/stopped dashboard volume:

```bash
docker run --rm \
  -v homelab-dashboard-data:/data \
  -v "$PWD/backups:/backup:ro" \
  alpine:3.22 \
  sh -c 'cd /data && tar xzf /backup/homelab-dashboard-data.tgz'
```

Stop the dashboard before taking or restoring a filesystem-level SQLite backup for the most consistent snapshot.

## Bind-mount install

Stop the dashboard and back up the host directory mapped to `/app/data` with your normal NAS/filesystem backup tooling.
