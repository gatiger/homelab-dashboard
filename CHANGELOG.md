# Changelog

All notable changes to Homelab Dashboard are documented here.

The project is in active pre-1.0 development. Minor releases may introduce migrations or configuration changes; upgrade notes will be provided when needed.

## [0.8.0] - 2026-08-22

### Added
- Multiple dashboard pages/tabs with persistent page assignment.
- Create, rename, reorder, and safely delete empty non-default pages.
- Persistent category ordering within each page.
- Collapsible categories whose expanded/collapsed state survives reloads and devices.
- Service page selection in the Add/Edit Service workflow.
- Automatic v0.7 migration that creates a Home page and keeps every existing service/category in place.

### Changed
- Card ordering is now scoped by both dashboard page and category.
- Dashboard structure is stored server-side so page/category organization follows the account across browsers.

## [0.7.0] - 2026-08-22

### Added
- All-in-one production Docker image and automated GHCR publishing for amd64/arm64.
- Universal production Compose file plus optional Docker-insight and local-build overlays.
- Platform installation documentation for Docker Compose, Dockge, TrueNAS SCALE, Portainer, Unraid, Synology, and QNAP.
- Backup/restore and update documentation.
- Dedicated Docker Host service template.

### Changed
- Docker host insight is optional and no longer requires the base deployment to mount or proxy the Docker socket.
- Docker Compose is now the reference deployment model; Dockge is documented as one optional management UI.

## [0.6.0] - 2026-08-22

### Added
- Persistent drag-and-drop service ordering within categories.
- Favorite/pinned services.
- Compact, Standard, and Wide card sizes.
- Persisted layout fields and automatic in-place database migration.

## [0.5.0] - 2026-08-22

### Added
- Searchable catalog of common self-hosted services.
- Default categories, aliases, port hints, and service descriptions.
- Open-ended service type identifiers for future integrations/plugins.
- SVG/PNG service-logo fallback handling.

## [0.4.1] - 2026-08-22

### Fixed
- Known-service logos now take precedence over legacy saved icon values.
- Added more reliable service recognition by name and URL.

## [0.4.0] - 2026-08-22

### Added
- Bundled service logos.
- Jellyfin API integration for server/session information.
- Read-only Docker overview through an isolated socket proxy.

## [0.3.0] - 2026-08-22

### Added
- Live service health monitoring and latency display.
- Automatic and manual status refresh.
- Per-service monitoring toggle.

## [0.2.0] - 2026-08-22

### Added
- First-run administrator setup.
- Login/session authentication and CSRF protection.
- SQLite persistence.
- Add/edit/delete/disable service management.

## [0.1.0] - 2026-08-04

### Added
- Initial Docker/Dockge dashboard starter.
