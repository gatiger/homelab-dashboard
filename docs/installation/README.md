# Installation guides

Homelab Dashboard is distributed as a standard OCI/Docker image. Dockge is optional.

| Platform | Guide | Status |
|---|---|---|
| Docker Compose | [Docker Compose](docker-compose.md) | Primary/reference install |
| Dockge | [Dockge](dockge.md) | Tested |
| TrueNAS SCALE | [TrueNAS SCALE](truenas-scale.md) | Documented; direct Custom App testing welcome |
| Portainer | [Portainer](portainer.md) | Documented |
| Unraid | [Unraid](unraid.md) | Documented; template planned |
| Synology DSM / Container Manager | [Synology](synology.md) | Documented |
| QNAP / Container Station | [QNAP](qnap.md) | Documented |

A normal installation needs only the dashboard image, a published web port, and persistent storage at `/app/data`. Local Docker host statistics are optional and are documented separately.

After installation, see [Networking and remote access](../configuration/networking.md) if service URLs use reverse proxies, split DNS, Tailscale, or other private-overlay addressing.
