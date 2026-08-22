# Homelab Dashboard

> **Pre-1.0 / active development.** Homelab Dashboard is usable today, but configuration and APIs may evolve before v1.0.

A visual, self-hosted control center for homelab services. Add common self-hosted applications from a searchable catalog, organize them into categories, monitor reachability, and show richer service-aware details when an integration is available.

## What works now

- First-run administrator setup and password-protected dashboard
- Persistent login sessions with HttpOnly cookies
- CSRF protection on service changes
- SQLite persistence in a Docker volume
- Add, edit, disable, and remove services in the browser
- Searchable dashboard cards and categories
- Persistent dashboard layout preferences: card order, pinned favorites, and card size
- Native drag-and-drop reordering within categories while in Manage mode
- Compact, Standard, and Wide card layouts, with Wide cards giving rich integrations more room
- Searchable built-in service catalog with 60 starter templates
- Catalog categories for Media, Downloads, Photos & Files, Home & Automation, Monitoring, Networking & Security, Infrastructure, Development, Productivity, Gaming, and Custom services
- Default category, URL scheme, common web-port hints, aliases, descriptions, and recognizable logos for catalog entries
- Generic Web Service and Custom Service fallbacks for anything not included in the catalog
- Open-ended backend service type identifiers so future templates/plugins do not require a schema release
- Live service monitoring with Online / Degraded / Offline status and response latency
- Automatic status refresh every 30 seconds plus a manual Refresh button
- Per-service monitoring toggle for links that should not be probed
- Private-IP/self-signed HTTPS support for homelab services
- Optional Jellyfin API integration for server version and active playback details
- Read-only local Docker host overview on Dockge cards through an isolated Docker socket proxy
- Docker Compose / Dockge deployment

## Service catalog

The first catalog release covers common services across the self-hosting ecosystem, including examples such as:

- **Media:** Jellyfin, Plex, Emby, Sonarr, Radarr, Lidarr, Readarr, Bazarr, Prowlarr, Overseerr, Jellyseerr, Seerr, Tautulli, Tdarr, Navidrome, Audiobookshelf, Calibre-Web
- **Downloads:** qBittorrent, Transmission, Deluge, SABnzbd, NZBGet
- **Photos & Files:** Immich, Nextcloud, Syncthing, Paperless-ngx, File Browser, Homebox
- **Home & Automation:** Home Assistant, Node-RED, Frigate
- **Monitoring:** Uptime Kuma, Grafana, Prometheus, Netdata, Glances
- **Networking & Security:** Pi-hole, AdGuard Home, Nginx Proxy Manager, Traefik, Authentik, Authelia, Pocket ID
- **Infrastructure:** Dockge, Portainer, TrueNAS, Unraid, Proxmox VE, OpenMediaVault
- **Development:** Gitea, Forgejo, GitLab, Jenkins, code-server
- **Productivity:** Vaultwarden, Mealie, FreshRSS
- **Gaming:** Pterodactyl
- **Custom:** Generic Web Service and Custom Service

Catalog port values are convenience hints only. Self-hosted applications are frequently remapped to different host ports, reverse-proxied, or served at custom paths.

### Logos

Service logos are sourced from the Homarr Labs Dashboard Icons collection. The Docker frontend build downloads the catalog's required icon subset and bundles it into the final Nginx image. SVG is preferred; the build and runtime automatically fall back to PNG where necessary. Existing checked-in icons are reused.

If the icon source is temporarily unavailable during a build, the dashboard still builds and the affected service falls back to a generic link icon.

## Upgrade from v0.5.0

The existing `dashboard-data` volume is fully compatible. v0.6.0 performs an automatic in-place migration that adds layout fields to existing service records. It does not reset accounts, sessions, cards, categories, API keys, or monitoring preferences.

Do **not** delete the `dashboard-data` volume and do not run `docker compose down -v` during an upgrade.

The existing v0.5 Compose configuration remains valid for v0.6.0. Replace/rebuild the backend and frontend application files and start the stack with `--build` (or use Dockge's rebuild/start flow).

See `docs/UPGRADE-v0.6.md` for the short upgrade procedure.

## Start with Docker or Dockge

1. Copy the project folder to a persistent location on the Docker host.
2. Optionally copy `.env.example` to `.env` and change `DASHBOARD_PORT`.
3. From the project folder run:

```bash
docker compose up -d --build
```

4. Open `http://SERVER-IP:8080` (or your configured port).
5. On first launch, create the administrator account.
6. Use **Add service** to browse the service catalog.

### Dockge

Create/import a stack whose compose file is this repository's `docker-compose.yml`. The stack must retain the project directory because both images are built from the local `backend` and `frontend` folders.

The named volume `dashboard-data` contains the SQLite database and survives normal container recreation/upgrades.

## Live status checks

For cards with **Monitor this service and show live status** enabled, the backend requests the saved service URL. The dashboard shows:

- **Online** for a reachable service returning an HTTP status below 500
- **Degraded** for a reachable service returning HTTP 500 or higher
- **Offline** when the service cannot be reached within the timeout
- **Not monitored** when status monitoring is disabled for that card

Status is refreshed every 30 seconds while the dashboard is open. The default request timeout is four seconds. Configure it with:

```env
STATUS_TIMEOUT=4
STATUS_WORKERS=8
```

Private/local IP addresses using a self-signed HTTPS certificate are retried without certificate verification. Public Internet hostnames continue to require valid TLS certificates.

## HTTPS / reverse proxy

When the dashboard is served through HTTPS, set:

```env
COOKIE_SECURE=true
```

A reverse proxy such as Caddy can point to the dashboard's published port.

## Current rich integrations

### Jellyfin

Edit a Jellyfin card and paste a Jellyfin API key. Once saved, the card can show:

- Jellyfin server version
- Active stream count
- Up to two currently playing titles/users
- Paused/transcoding counts

Leaving the API key blank keeps the card as a normal monitored link.

### Dockge / local Docker host

A Dockge card can show a read-only summary of the Docker host that runs this dashboard:

- Compose stack count inferred from container labels
- Running/total container count
- Number of stopped containers and up to two stopped container names

This does not use an unofficial Dockge management API. It reads the local Docker Engine through the restricted internal socket proxy.

## Security notes

- Passwords are stored using Python's scrypt password derivation, never as plain text.
- Session tokens are stored hashed in SQLite and sent to the browser only as HttpOnly cookies.
- Write operations require a per-session CSRF token.
- Status checks are performed by the backend only for URLs saved by an authenticated administrator.
- Jellyfin API keys are encrypted at rest with a local Fernet key stored in the persistent dashboard data volume. Saved keys are never returned by the API after storage.
- Docker information is read through a socket proxy with POST requests disabled and only the container API section enabled. The proxy is on an internal Docker network and publishes no host port.
- Additional service credentials (Sonarr/Radarr/etc.) are not implemented yet.

## Local development

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

## Dashboard layout customization

Open **Manage** to rearrange cards. Drag-and-drop is intentionally limited to cards in the same category so reordering never silently changes a service's category. Pinned/favorite cards sort to the top of their category and can be toggled with the star control in Manage mode.

Edit a service to choose one of three card sizes:

- **Compact** — smaller launcher card; rich insight blocks are hidden to save space.
- **Standard** — the normal balanced card.
- **Wide** — spans two columns on larger screens and gives integration details more room.

Layout settings are stored in SQLite and follow the dashboard across browsers/devices.

## Project status

The project is now tracked as versioned open-source software. Releases before v1.0 should be treated as beta-quality: upgrades are tested to preserve existing dashboard data, but breaking changes are still possible when necessary.

See `CHANGELOG.md` for release history and `CONTRIBUTING.md` for contribution guidance.

## Next development target

The next layer is the reusable integration framework: common credential/API configuration patterns and richer adapters for Sonarr/Radarr, download clients, infrastructure platforms, and monitoring tools. Multi-page dashboards, themes, import/export, and a plugin manifest can then build on the persisted layout model.
