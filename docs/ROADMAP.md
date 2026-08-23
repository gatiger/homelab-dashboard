# Roadmap

## Milestone 1 — Runnable foundation ✅

- FastAPI backend
- React + TypeScript frontend
- Docker Compose deployment
- Responsive dashboard shell

## Milestone 2 — Visual configuration ✅

- First-run administrator setup
- Login and sessions
- Add/edit/remove service workflow
- SQLite persistence
- Categories and icons
- Generic link cards

## Milestone 3 — Live service status ✅

- Backend reachability checks for configured service URLs
- Online / degraded / offline states
- Response latency on cards
- Automatic 30-second refresh
- Manual status refresh
- Per-service monitoring toggle
- Self-signed HTTPS support for private/local homelab addresses
- In-place database migration from Milestone 2

## Milestone 4 — First service-aware integrations ✅

- Backend-only encrypted secret storage ✅
- Recognizable service logos ✅
- Jellyfin sessions and server information ✅
- Dockge / local Docker stack and container state ✅
- Sonarr / Radarr queues, progress, health, and upcoming activity ✅
- Prowlarr health/indexer summary ✅
- qBittorrent / SABnzbd activity, progress, speed, and ETA ✅
- Immich server information/statistics ✅
- TrueNAS health, capacity, and storage-operation progress ✅

## Milestone 5 — Universal service catalog ✅

- Searchable service/app picker
- Broad built-in catalog beyond the maintainer's own homelab
- Categories, descriptions, aliases, common default ports, and URL hints
- SVG/PNG brand logo fallback
- Generic/custom service templates
- Open-ended backend service type identifiers for future extensions
- Catalog stored as a separate data module so new services are low-friction additions

## Milestone 6 — Dashboard personalization ✅

- Persistent card order
- Native drag-and-drop reordering within categories
- Favorite/pinned cards
- Compact / Standard / Wide card sizes
- Automatic in-place migration from v0.5
- Manage-mode safeguards so clicking a card while arranging it does not launch the service

## Milestone 7 — Distribution and installation ✅

- All-in-one production image
- Automated multi-architecture GHCR publishing
- Docker Compose reference installation
- Docker host insight optional rather than required
- Dedicated Docker Host service template
- Dockge / TrueNAS / Portainer / Unraid / Synology / QNAP installation documentation
- Backup/restore and update documentation
- Community-tested installation matrix foundation

## Milestone 8 — Dashboard organization ✅

- Multiple dashboard pages/tabs
- Persistent page assignment for every service
- Create, rename, reorder, and safely delete pages
- Persistent category ordering per page
- Collapsible categories with saved state
- Automatic in-place migration from v0.7 to a default Home page

## Milestone 9 — Appearance and extension foundation ✅

- System / Dark / Light appearance modes
- Built-in Slate / Ocean / Forest / Violet / Amber color themes
- Persistent appearance selection
- Importable validated JSON theme packages
- Theme authoring template and example
- Shared design-token layer
- First extension package validation/persistence/removal flow

## Milestone 10 — Reusable integration framework ✅ / 🚧

- Shared API-key and encrypted username/password credential configuration model ✅
- Service capability declarations ✅
- Integration status/error reporting ✅
- Normalized activity/progress model for long-running jobs ✅
- Sonarr/Radarr and qBittorrent/SABnzbd adapters ✅
- Prowlarr, Immich, and TrueNAS read-only adapters ✅
- Authentication capability metadata for built-in integrations ✅
- Native/OIDC/SSO/reverse-proxy authentication adapter metadata 🚧
- Installable/community integration adapter runtime 🚧

## Milestone 11 — Update Manager ✅

- Separate application-integration and management-provider concepts ✅
- Per-service update configuration and discovery ✅
- One-click background updates from Homelab Dashboard ✅
- Persistent update status/history and progress UI ✅
- Sequential Update All with stop-on-failure behavior ✅
- Docker Compose / Dockge provider through a restricted sidecar ✅
- Docker image health verification and automatic rollback foundation ✅
- TrueNAS App provider through the JSON-RPC WebSocket API ✅
- Automatic/manual update checks ✅
- Additional providers such as Portainer, Unraid, Synology, and Kubernetes 🚧

## Milestone 12 — Advanced dashboard builder

- Proper Settings area
- Custom theme editor
- Desktop and mobile layout refinements
- Import/export of dashboard structure
- Category naming/icon customization
- Dashboard cloning/templates
- Optional widgets

## Milestone 13 — Open extension platform

- Versioned extension manifest
- Permission/capability model
- Plugin SDK and examples
- Community extension registry
- Role-based permissions
- OIDC / Authentik / Authelia support

## Future optional modules

### 3D Printer Center

- Provider-adapter architecture with a shared printer status/control model
- Moonraker adapter for Klipper / Mainsail / Fluidd
- OctoPrint adapter for non-Klipper printers
- Bambuddy adapter for Bambu Lab printers via Bambuddy's external API
- Multi-printer/farm overview, progress, temperatures, camera, and job state
- Monitoring-only permissions by default; pause/resume/cancel, heater/motion, file upload, macros, and raw G-code opt-in separately where supported

## Distribution follow-ups

- [ ] Community-tested installation badges/matrix
- [ ] Unraid Community Applications template
- [ ] Additional NAS/platform templates as contributors validate them
