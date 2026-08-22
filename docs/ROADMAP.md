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

## Milestone 4 — First service-aware integrations ✅ / 🚧

- Backend-only encrypted secret storage ✅
- Recognizable service logos ✅
- Jellyfin sessions and server information ✅
- Dockge / local Docker stack and container state ✅
- Sonarr / Radarr queues and upcoming activity
- Prowlarr health
- qBittorrent / SABnzbd activity
- Immich server information
- TrueNAS health and storage summary

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

## Milestone 9 — Reusable integration framework

- Shared API credential configuration model
- Service capability declarations
- Integration status/error reporting
- Sonarr/Radarr and download-client adapters
- Infrastructure and monitoring adapters
- Authentication capability metadata (native, API, OIDC/SSO, reverse-proxy)

## Milestone 10 — Advanced dashboard builder

- Theme editor and appearance presets
- Desktop and mobile layout refinements
- Import/export
- Category naming/icon customization
- Dashboard cloning/templates

## Milestone 11 — Open plugin platform

- Versioned integration manifest
- Plugin SDK and examples
- Community integration registry
- Role-based permissions
- OIDC / Authentik / Authelia support

## Distribution follow-ups

- [ ] Community-tested installation badges/matrix
- [ ] Unraid Community Applications template
- [ ] Additional NAS/platform templates as contributors validate them
