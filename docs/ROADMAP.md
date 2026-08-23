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

- Separate application-integration and management-provider concepts
- Per-service update configuration and discovery
- One-click background updates from Homelab Dashboard
- Persistent update status/history and progress UI
- Sequential Update All with stop-on-failure behavior
- Docker Compose / Dockge provider through a restricted sidecar
- Docker image health verification and automatic rollback foundation
- TrueNAS App provider through the JSON-RPC WebSocket API
- Automatic/manual update checks

Additional management providers are tracked separately below rather than making this completed milestone appear partially unfinished.

## Milestone 12 — Live cards and management connections ✅

- Reusable controller Connections independent of visible service cards
- Automatic migration of v0.11 TrueNAS controller-card references
- TrueNAS connection testing and encrypted credential reuse
- Standardized card regions for connectivity, application detail/activity, and management/update state
- Bright green/glowing **Up to date** state
- Bright amber/glowing **Update available** state with card-level Update action
- Red/glowing failed-update-check state and blue checking state
- Automatic 15-second browser refresh for telemetry/update state without page reloads
- Faster refresh while update jobs are active and refresh-on-tab-return
- Server-side scheduled update discovery remains configurable (12 hours by default)

## Milestone 13 — Settings hub and built-in widgets ✅

- Central Settings navigation for General, Appearance, Connections, Monitoring, Extensions, and About
- Persistent dashboard title and greeting preference
- Configurable browser telemetry/update-state polling intervals
- Configurable server-side automatic update-discovery interval
- Built-in Clock & Date widget
- Built-in Note widget
- Built-in Bookmarks widget with HTTP/HTTPS URL validation
- Built-in Dashboard Summary widget
- Widget page/category assignment, visibility, and Compact/Standard/Wide sizing
- Widget-aware category counts/order and page-deletion safeguards
- Extension Manager inventory for bundled modules and imported data-only themes

## Milestone 14 — Advanced dashboard builder ✅

- Custom visual theme editor ✅
- Unified drag/reorder behavior for unpinned service and widget cards ✅
- Desktop and mobile layout refinements ✅
- Import/export of dashboard structure with secrets excluded ✅
- Category naming/icon customization ✅
- Dashboard page cloning ✅
- Reusable distributable page-template packs ✅
- Additional built-in widget types ✅
- Compact responsive command bar / header cleanup ✅

## Milestone 15 — Account and recovery ✅

- Settings → Account security section
- Authenticated password changes requiring the current password
- Invalidate other active sessions after password changes
- High-entropy one-time recovery-code generation/regeneration
- Forgot-password flow without requiring email/SMTP
- Automatic recovery-code rotation after successful use
- Account-security audit history without secret logging
- Host-side emergency administrator reset command
- In-place migration for existing single-administrator installations

## Milestone 16 — Open extension platform ✅ / 🚧

- Versioned extension manifest ✅
- Explicit capability/permission declarations and allow-list validation ✅
- Safe data-only page-template pack runtime ✅
- Safe data-only service/catalog pack runtime ✅
- Extension import, enable/disable, inventory, and removal lifecycle ✅
- Export an existing dashboard page as a shareable secret-free template package ✅
- Package authoring documentation and examples ✅
- Executable plugin SDK/runtime with sandboxed permissions 🚧
- Community extension registry/discovery ✅
- Installable/community integration adapter runtime 🚧
- Community executable widget packs 🚧
- Role-based permissions ✅
- Native/OIDC/SSO/reverse-proxy authentication adapters 🚧
- OIDC / Authentik / Authelia support 🚧

## Milestone 17 — Extension registry and package updates ✅

- In-app registry discovery for data-only extensions
- Official / Verified Community / Community trust labels
- Minimum-dashboard compatibility checks
- SHA-256 verification of downloaded extension packages
- Same-HTTPS-origin package enforcement
- Registry install flow with explicit permission/capability confirmation
- Installed-version comparison and update availability
- In-place extension updates that preserve enabled/disabled state
- Manual JSON import fallback when the registry is offline
- Registry contribution format, maintainer validator, and CI checks
- Package signing/transparency remains a future prerequisite before executable third-party extensions


## Milestone 18 — Users and role-based permissions ✅

- Local multi-user account store with automatic migration of the legacy administrator
- Owner / Admin / Editor / Viewer roles
- Server-side permission enforcement for dashboard editing, secrets, updates, connections, extensions, settings, and users
- Settings → Users lifecycle management
- Per-user password recovery and security audit history
- Immediate session invalidation when an account is disabled or password-reset
- Last-enabled-Owner safeguards
- Role-aware dashboard controls and read-only Viewer experience
- Host-side user listing and targeted emergency password reset

## Milestone 19 — Universal update-provider foundation ✅

- Platform-neutral management-provider descriptor registry
- Provider capability declarations for check/install/progress/rollback/release notes
- Dynamic service-editor provider discovery and managed-resource selection
- Common dispatch layer for Docker Compose / Dockge and TrueNAS App update implementations
- TrueNAS operating-system update detection through the native update API
- Detection-only provider support without exposing unsafe update actions
- Server-side capability gates for single-service updates and Update All
- Reboot-safe host update orchestration/reconnect remains a follow-up before TrueNAS System installation is enabled

## Management-provider follow-ups 🚧

- Portainer provider
- Unraid provider
- Synology provider where supported
- Kubernetes/Helm provider
- Private-registry credential support and richer pinned-tag discovery

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
