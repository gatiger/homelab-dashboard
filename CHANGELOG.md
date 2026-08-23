# Changelog

All notable changes to Homelab Dashboard are documented here.

The project is in active pre-1.0 development. Minor releases may introduce migrations or configuration changes; upgrade notes will be provided when needed.

## [0.13.1] - 2026-08-23

### Fixed
- Build the architecture-independent frontend stage on BuildKit's native build platform instead of under ARM64 QEMU emulation.
- Prevent multi-architecture release publishing from stalling for hours during the ARM64 `npm install` step.

## [0.13.0] - 2026-08-23

### Added
- Central Settings hub with General, Appearance, Connections, Monitoring, Extensions, and About sections.
- Persistent dashboard title and optional greeting preference.
- Configurable telemetry refresh, cached update-state refresh, active-job refresh, and server-side update-discovery interval.
- Built-in Clock & Date, Note, Bookmarks, and Dashboard Summary widgets.
- Persistent widget configuration with page/category assignment, visibility, and Compact/Standard/Wide sizing.
- Extension Manager inventory showing built-in modules and imported theme packages.
- Widget and Settings configuration documentation.

### Changed
- Appearance and Connections now live under the Settings hub instead of occupying permanent top-level header buttons.
- Category discovery/counts and page-deletion safeguards now include widgets as well as service cards.
- Automatic update discovery reads its interval from persisted Settings and can be changed without recreating the container.
- Roadmap milestones were split so shipped Settings/widgets work is not conflated with still-pending advanced builder and executable extension-platform work.

### Security
- Widgets are data-only built-ins; Bookmark URLs are validated to HTTP/HTTPS by the backend.
- v0.13 does not load arbitrary extension JavaScript, Python, CSS, shell commands, or other executable community code.
- Existing CSRF, encrypted-secret, Docker-agent, and management-provider boundaries are unchanged.

## [0.12.0] - 2026-08-22

### Added
- Reusable management Connections, starting with TrueNAS, so controller credentials no longer require a visible dashboard card.
- Automatic migration of v0.11 TrueNAS controller-card references into reusable TrueNAS Connections.
- Consistent managed-card update status row with glowing semantic states for current, available, checking, and failed checks.
- Card-level update version information and one-click Update action in a fixed management position.
- Automatic browser refresh for service telemetry and cached update state, with faster polling while an update job is active and immediate refresh when the tab becomes visible again.
- TrueNAS connection test workflow and safe connection deletion guard when services still reference it.

### Changed
- Standard/Wide service cards reserve consistent detail and management regions so common status information stays aligned across services.
- TrueNAS App management now selects a reusable TrueNAS Connection instead of selecting a TrueNAS service card.
- Normal browser polling is 15 seconds; active update jobs refresh about every 2.5 seconds. Server-side update discovery remains 12 hours by default and configurable with `UPDATE_CHECK_INTERVAL_HOURS`.

### Security
- TrueNAS connection API keys and usernames remain encrypted at rest and are never returned to the browser.
- Existing Docker update-agent isolation and CSRF protections are unchanged.

## [0.11.0] - 2026-08-22

### Added
- Update Manager with per-service update availability, one-click updates, sequential Update All, progress, and persistent update history.
- Management-provider model that separates application integrations from the platform responsible for updating them.
- Optional restricted Docker Compose/Dockge update-agent sidecar with stack-directory allow-listing and no host-published API port.
- Docker Compose update discovery, container recreation, health verification, and automatic image rollback when the replacement container fails health checks.
- TrueNAS App discovery and upgrades through the JSON-RPC WebSocket API, without opening the TrueNAS UI.
- Automatic update checks every 12 hours by default, plus manual Check for updates.
- Service editor fields for linking cards to a Docker Compose service or TrueNAS App.

### Changed
- TrueNAS rich integration now attempts the 25.04+ JSON-RPC WebSocket API first and keeps the legacy REST path only as a compatibility fallback for older installations.
- TrueNAS API-key owner username can be saved encrypted for current/future `auth.login_ex` compatibility.

### Security
- The main dashboard container still receives no raw Docker socket. Docker write access lives in the optional update-agent sidecar, which only operates on discovered Compose services whose project files are inside an explicitly configured stacks root.
- Update actions remain CSRF-protected and require an authenticated dashboard administrator.


## [0.10.0] - 2026-08-22

### Added
- Reusable integration descriptors with declared authentication and capability metadata.
- Shared activity/progress records for downloads, queues, storage scans, and future long-running jobs.
- Sonarr and Radarr queue/progress, health, and upcoming activity integrations.
- Prowlarr health/indexer integration.
- qBittorrent WebUI integration with encrypted username/password storage, download progress, speed, and ETA.
- SABnzbd queue integration with progress, speed, and ETA.
- Immich server/statistics integration.
- TrueNAS pool health/capacity plus scrub, resilver, and expansion progress through the REST compatibility API.
- Progress-bar UI for rich service cards.

### Changed
- API-key configuration is now shared across supported integrations rather than being Jellyfin-specific.
- Service insight responses now include capabilities and normalized activities.

### Security
- New service integrations are read-only. Saved API keys and qBittorrent credentials remain encrypted at rest and backend-only.

## [0.9.0] - 2026-08-22

### Added
- System, Dark, Light, Slate, Ocean, Forest, Violet, and Amber appearance themes.
- Persistent server-side appearance selection.
- Validated importable JSON theme packages and downloadable authoring template.
- Theme-extension and future extension-architecture documentation.

### Changed
- Dashboard styling now uses reusable design tokens so themes can restyle shared components consistently.
- Stable GHCR publishing is release-tag driven rather than automatically publishing a multi-architecture image on every `main` push.

### Fixed
- Removed a duplicated service-icon element from the v0.8 card renderer.

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
