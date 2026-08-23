# Homelab Dashboard

> **Pre-1.0 / active development.** Homelab Dashboard is usable today, but configuration and APIs may evolve before v1.0.

A configurable, self-hosted dashboard and control center for homelab services. It is designed to be useful across many self-hosting platforms rather than tied to one NAS, container manager, or service stack.

## Quick start

**Requirements:** a container runtime capable of running the published OCI image. Docker Compose is the reference installation. Dockge, Portainer, TrueNAS SCALE, Unraid, Synology, and QNAP are optional deployment environments.

```bash
docker compose pull
docker compose up -d
```

Open `http://SERVER-IP:8080`, create the first administrator account, and add services from the catalog.

See **[Installation guides](docs/installation/README.md)** for platform-specific steps.

## Supported/documented deployment paths

| Platform | Role |
|---|---|
| Docker Compose | Primary/reference installation |
| Dockge | Tested Compose management UI |
| TrueNAS SCALE | Custom App / YAML documentation |
| Portainer | Stack / Git deployment documentation |
| Unraid | Single-container Docker UI documentation |
| Synology DSM | Container Manager Project documentation |
| QNAP | Container Station Compose application documentation |

Platform guides that have not yet had hands-on community testing are labeled accordingly; issue reports and installation confirmations are welcome.

## Distribution

Stable releases publish a multi-architecture image for `linux/amd64` and `linux/arm64`:

```text
ghcr.io/gatiger/homelab-dashboard:latest
ghcr.io/gatiger/homelab-dashboard:0.13.1
```

The normal install is a **single application container** containing the React/Nginx frontend and FastAPI backend. Persistent state is stored at `/app/data`.

Developers can still build from source with:

```bash
docker compose -f compose.yaml -f compose.build.yaml up -d --build
```

## Docker access is optional

Homelab Dashboard does **not** require the Docker socket. Service launching, catalog cards, URL monitoring, service API integrations, and normal dashboard functions work without Docker host access.

To enable read-only local Docker statistics, add the restricted socket-proxy overlay:

```bash
docker compose -f compose.yaml -f compose.docker.yaml up -d
```

See [Docker integration](docs/configuration/docker-integration.md).

## Current features

- First-run administrator setup and password-protected dashboard
- SQLite persistence and encrypted saved integration secrets
- Searchable service catalog with common self-hosted applications
- Recognizable bundled service logos with generic/custom fallbacks
- Live Online / Degraded / Offline monitoring and response latency
- Favorites, Compact/Standard/Wide cards, and drag-and-drop card ordering
- Multiple dashboard pages/tabs with persistent page assignment and ordering
- Persisted category ordering and collapsible category sections
- Optional Jellyfin server/session integration
- Sonarr/Radarr queue, health, progress, and upcoming activity
- Prowlarr indexer/health insight
- qBittorrent and SABnzbd live queue/download progress with speed and ETA when available
- Immich server/storage statistics
- TrueNAS pool health/storage plus scrub/resilver progress, with current JSON-RPC WebSocket support and legacy REST fallback
- Optional read-only local Docker host overview
- System, light/dark, and multiple color themes with persistent appearance settings
- Safe importable JSON theme extensions with no executable code
- Open-ended service identifiers for future templates/plugins
- Shared integration capability/activity model for progress-aware service cards
- Update Manager with one-click Docker Compose/Dockge and TrueNAS App updates
- Reusable management Connections so platform credentials do not require visible controller cards
- Standardized managed-card update indicators with glowing current/available/error states
- Automatic in-browser telemetry/update-state refresh without manually reloading the page
- Central Settings hub for General, Appearance, Connections, Monitoring, Extensions, and About
- Configurable browser telemetry/update refresh intervals and scheduled update-discovery interval
- Built-in Clock/Date, Note, Bookmarks, and Dashboard Summary widgets
- Widgets can be assigned to any page/category and use Compact/Standard/Wide card sizes
- Extension Manager inventory for built-in modules and imported data-only theme packages
- Sequential Update All, health verification, update history, and Docker rollback on failed health checks


## Update Manager

The **Updates** screen can discover and apply updates without opening each service separately. Application integrations (for example Sonarr status/queue) are separate from management providers (for example Docker Compose or TrueNAS Apps), so the same service can be monitored one way and updated another.

TrueNAS App updates use a reusable TrueNAS Connection (URL + encrypted API credentials), so no visible TrueNAS dashboard card is required. Docker Compose/Dockge one-click updates require the optional restricted update-agent sidecar:

```bash
docker compose -f compose.yaml -f compose.management.yaml up -d
```

The update agent is not required for normal dashboard use. See [Update Manager](docs/configuration/update-manager.md).

## Settings, themes, widgets, and extensions

Open **Settings** for General, Appearance, Connections, Monitoring, Extensions, and About. Appearance still provides System, Dark, Light, Slate, Ocean, Forest, Violet, and Amber themes; System follows the viewing device's light/dark preference.

The first built-in widget pack includes Clock & Date, Note, Bookmarks, and Dashboard Summary widgets. Widgets are stored in SQLite and can be assigned to any dashboard page/category with Compact, Standard, or Wide sizing. See [Widgets](docs/configuration/widgets.md) and [Settings](docs/configuration/settings.md).

Community themes can be imported as validated JSON packages. Theme extensions contain approved color tokens only and cannot execute CSS/JavaScript or access network services, Docker, files, or stored credentials. The v0.13 Extension Manager shows installed built-in modules and imported theme packages; arbitrary executable community plugins remain a later milestone. See [Theme extensions](docs/extensions/themes.md) and the broader [extension architecture](docs/extensions/architecture.md).

## Service catalog

The built-in catalog covers media, download clients, files/photos, home automation, monitoring, networking/security, infrastructure, development, productivity, gaming, and generic custom services. Examples include Jellyfin, Plex, Emby, Sonarr, Radarr, Prowlarr, qBittorrent, SABnzbd, Immich, Nextcloud, Home Assistant, Grafana, Uptime Kuma, Pi-hole, Authentik, Dockge, Portainer, TrueNAS, Unraid, Proxmox VE, Gitea, Vaultwarden, and Pterodactyl.

Catalog port values are hints only; users can enter any URL, reverse proxy, port, or path. Rich integrations are opt-in by adding the credential requested by that service. See [Service integrations](docs/configuration/service-integrations.md).

## Persistent data

`/app/data` contains the SQLite database and local encryption key. The default Compose volume is named `homelab-dashboard-data`.

Back up the **whole** data directory/volume together. See [Backup and restore](docs/configuration/backup-restore.md).

Never use `docker compose down -v` for a normal update.

## HTTPS / reverse proxy

When the dashboard itself is served over HTTPS, set:

```env
COOKIE_SECURE=true
```

Any standard reverse proxy can forward to the dashboard's published HTTP port.

## Upgrading

Image installs normally update with:

```bash
docker compose pull
docker compose up -d
```

See [Updating](docs/configuration/updating.md) and the version-specific upgrade notes in `docs/`.

## Development

Backend:

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Security

- Passwords use scrypt and are never stored as plain text.
- Login sessions use HttpOnly cookies and hashed server-side tokens.
- State-changing requests require a CSRF token.
- Saved API keys and qBittorrent WebUI credentials are encrypted at rest and are never returned after storage.
- Docker access is absent by default. The optional integration uses a restricted internal socket proxy with POST operations disabled.
- Imported themes are validated data-only manifests; they cannot contain executable CSS or JavaScript.

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Project status / roadmap

v0.13 adds the central Settings hub, configurable refresh/update-discovery intervals, the first built-in widget runtime, and an Extension Manager inventory. Advanced dashboard import/export, page templates, deeper widget layout controls, SSO options, additional management providers, and the permission-aware executable plugin SDK remain explicitly tracked as future work.

See [CHANGELOG.md](CHANGELOG.md), [ROADMAP](docs/ROADMAP.md), and [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. Service logos are sourced from the Homarr Labs Dashboard Icons collection; see `THIRD_PARTY_NOTICES.md` and `third_party/`.
