# Optional Docker host integration

Homelab Dashboard does not require Docker socket access. The base image can run on a Docker host, NAS, VM, Kubernetes-adjacent environment, or anywhere else that can run the container and reach service URLs.

When enabled, the Docker integration currently reads container state from the **local Docker Engine** to provide running/total counts and stopped-container information. It does not start, stop, delete, or modify containers.

## Security model

The dashboard container is **not** given `/var/run/docker.sock` directly. `compose.docker.yaml` starts a restricted socket proxy on an internal Docker network with:

- only the Containers API section enabled;
- POST requests disabled;
- no host-published proxy port.

Enable it with:

```bash
docker compose -f compose.yaml -f compose.docker.yaml up -d
```

Disable it by returning to the base file:

```bash
docker compose -f compose.yaml up -d --remove-orphans
```

Existing Dockge cards continue to show local Docker insight for backward compatibility. v0.7 also adds a dedicated **Docker Host** service template so container statistics are no longer conceptually tied to Dockge.

## Write/update access is separate

v0.12 does not turn the read-only socket proxy into a write proxy. One-click Compose updates use the separate `compose.management.yaml` update-agent architecture documented in [Update Manager](update-manager.md). This keeps normal Docker insight (`POST=0`) independent from lifecycle/update privileges.
