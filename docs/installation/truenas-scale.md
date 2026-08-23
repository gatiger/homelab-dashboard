# Install on TrueNAS SCALE

Current TrueNAS SCALE releases use Docker for Apps and support third-party applications through either the Custom App wizard or **Install via YAML**.

## Simplest: Custom App wizard

1. Configure an Apps pool in **Apps > Settings** if one is not already configured.
2. Open **Apps > Discover Apps > Custom App**.
3. Use image repository `ghcr.io/gatiger/homelab-dashboard` and tag `latest` (or a specific version such as `0.13.1`).
4. Publish container port `80` to an unused host port such as `8080`.
5. Configure persistent storage so a TrueNAS dataset/path is mounted at `/app/data`.
6. Add environment variables only if needed (`APP_NAME`, `SESSION_HOURS`, `COOKIE_SECURE`, `STATUS_TIMEOUT`, `STATUS_WORKERS`).
7. Save/install and open the host IP plus chosen port.

Using a host-path dataset for `/app/data` makes backup/restore straightforward on TrueNAS.

## Alternative: Install via YAML

TrueNAS also provides an advanced YAML editor for Docker Compose. Paste `compose.yaml` and adjust the data volume to a host path if desired.

Example storage replacement:

```yaml
services:
  dashboard:
    volumes:
      - /mnt/POOL/apps/homelab-dashboard:/app/data
```

Remove the unused top-level `volumes:` declaration when using only a host path.

## Docker host statistics

Treat Docker socket access as an optional advanced feature. Use `compose.docker.yaml` only when you explicitly want local Docker container statistics. The normal dashboard, service catalog, health checks, and API integrations work without Docker socket access.

Official TrueNAS references:
- https://apps.truenas.com/managing-apps/installing-custom-apps/
- https://www.truenas.com/docs/scale/apps/installcustomappscreens/
