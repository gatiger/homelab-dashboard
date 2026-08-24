# Changelog

All notable changes to Homelab Dashboard are documented here.

The project is in active pre-1.0 development. Minor releases may introduce migrations or configuration changes; upgrade notes will be provided when needed.

## [0.21.0] - 2026-08-23

### Added
- Opt-in scheduled service-update maintenance windows with configurable days, start/end times, release delays, and one unattended pass per maintenance window.
- Per-service update policies: inherit global behavior, manual, scheduled, or monitor-only, plus per-service release-delay and rollback-policy overrides.
- Automatic Docker Compose / Dockge management-provider suggestions when an unconfigured card exactly matches a discovered Compose service; user approval is still required.
- Pre-update HTTP/integration health baselines and application-level post-update verification.
- Capability-aware provider rollback metadata and provider-specific manual recovery guidance.
- Docker update-agent commit/rollback flow that preserves the previously running image until Dashboard-level verification succeeds.
- Persistent pre-host-update service recovery snapshots and post-reboot checks for services that were healthy before the host update.
- Scheduled/manual trigger information, update first-seen timestamps, rollback mode, and recovery guidance in the Update Manager.
- Backend/update-agent regression coverage for maintenance windows, release delays, monitor-only behavior, provider rollback modes, Docker rollback, and rollback snapshot commit.

### Changed
- Scheduled maintenance performs a fresh update discovery before selecting work and updates eligible services sequentially.
- Scheduled queues stop after the first failure by default; this behavior is configurable.
- TrueNAS System updates continue to require explicit Owner/Admin confirmation and remain excluded from Update All and scheduled maintenance.
- Docker updates are not considered complete until both provider/container health and any meaningful pre-update Dashboard HTTP/integration health signals recover.
- Host-update completion now reports monitored services that fail to recover after the expected host version returns.

### Safety
- Scheduled installation remains disabled by default.
- Rollback is provider-declared rather than assumed. Docker's automatic path restores the previous image only; persistent application data/database migrations are not automatically reversed.
- Providers without a safe automatic rollback path stop/preserve failure details and expose manual recovery guidance instead of pretending rollback succeeded.

## [0.20.3] - 2026-08-23

### Added
- Optional per-service **Internal / monitoring URL** that is used only by backend health checks and rich service integrations while the normal Browser URL remains the card's launch target.
- Monitoring-path regression tests covering persistence, health-check routing, rich-integration routing, and fallback to the Browser URL.
- Networking guidance for split DNS, Docker `extra_hosts`, Tailscale/private-overlay remote access, and direct LAN/container-DNS monitoring paths.

### Changed
- Service configuration now labels the normal address as **Browser URL** and explains when an internal monitoring route is useful.
- Full dashboard layout export/import and page cloning preserve configured internal monitoring URLs. Shareable page-template packs remain environment-neutral and do not export backend-only internal addresses.

### Fixed
- Services no longer need to appear Offline merely because their user-facing hostname resolves through a remote-access or reverse-proxy path that is unreachable from the Dashboard container.

## [0.20.2] - 2026-08-23

### Fixed
- TrueNAS System host updates now resolve the update train for the detected target version through `update.available_versions` before calling `update.run`.
- Dashboard now supplies `train` and `version` together, matching the TrueNAS 25.10 validation requirement and preventing `[EFAULT] train and version must either both be null or both be non-null`.
- The host-update regression test now verifies the exact train/version pair passed to TrueNAS.

### Changed
- Added regression coverage for mapping a detected TrueNAS system version to its advertised update train.

## [0.20.1] - 2026-08-23

### Fixed
- TrueNAS System host updates now attach to the TrueNAS `core.get_jobs` event stream and capture the middleware job ID instead of waiting for the long-running `update.run` method result to return through the ordinary short RPC timeout.
- Host-update progress can now be polled reliably from the real TrueNAS job after it starts, allowing the expected update/reboot/reconnect flow to proceed.
- Update History now displays backend failure details for failed jobs so asynchronous host-update errors are visible instead of appearing to stop silently.

### Changed
- Added regression coverage for the TrueNAS JSON-RPC job-start event flow documented for job methods.

## [0.20.0] - 2026-08-23

### Added
- Reboot-safe host-update execution framework with persistent SQLite operation state and post-restart recovery.
- Explicit host-update confirmation endpoint protected by a dedicated `updates:host` permission.
- TrueNAS System **Update & reboot** support through the native `update.run` JSON-RPC job API.
- Reconnecting job state and automatic post-reboot TrueNAS readiness/version verification.
- Provider metadata for host/service update scope, reboot requirements, bulk eligibility, and confirmation requirements.
- Frontend host-update warning/reconnect banner and role-aware host-update controls.

### Changed
- Host-scoped providers are excluded from **Update All** by provider capability metadata rather than platform-specific checks.
- Owner and Admin roles may explicitly start supported host updates; Editor and Viewer remain unable to run updates.
- Active-job polling continues at the fast interval while a host update is reconnecting.
- GitHub Actions workflows now use Node.js 24-compatible major versions of the official checkout, setup, Docker build, login, and metadata actions.
- FastAPI startup initialization now uses the supported lifespan hook instead of the deprecated startup-event decorator.

### Security
- Host updates require a separate explicit confirmation request and cannot be triggered through the ordinary service-update endpoint.
- A recovering Dashboard never reissues an interrupted host-update command after restart; it only verifies whether the managed host returned on the expected version.
- TrueNAS System updates are never included in Update All. A TrueNAS API credential must have the upstream permissions required to install system updates before Dashboard can execute one.

## [0.19.0] - 2026-08-23

### Added
- Platform-neutral management-provider descriptor registry exposed to the frontend at runtime.
- Capability declarations for update checking, installation, progress, rollback, release notes, connection requirements, and managed-target shape.
- Generic provider resource-discovery API so the service editor no longer hard-codes Docker and TrueNAS App discovery routes.
- TrueNAS System provider for native operating-system update detection through the TrueNAS JSON-RPC update API.
- Backend tests for provider discovery, provider validation, TrueNAS system version parsing, and detection-only capability enforcement.

### Changed
- Existing Docker Compose / Dockge and TrueNAS App update paths now dispatch through the common provider registry.
- Service management-provider IDs are open-ended validated identifiers rather than a frontend/backend enum tied to two platforms.
- The service editor renders provider names, connection requirements, target labels, descriptions, and warnings from provider metadata.
- Update All includes only available updates whose provider explicitly supports installation; detection-only updates remain visible without becoming actionable.
- Update buttons are shown only when the provider advertises update-install capability.

### Security
- Provider capability checks are enforced server-side before single-service or batch updates.
- TrueNAS System updates are detection-only in v0.19.0. Dashboard can report an available NAS OS update but cannot initiate the host update/reboot until reboot-safe reconnect and recovery handling is implemented.

## [0.18.0] - 2026-08-23

### Added
- Local multi-user accounts with Owner, Admin, Editor, and Viewer roles.
- Permission-aware API enforcement for dashboard editing, service management, credentials, updates, connections, extensions, global settings, and user management.
- Settings → Users for creating, enabling/disabling, role-changing, password-resetting, and deleting local accounts.
- Per-user password recovery codes and account-security history.
- Host-side `list-users` and username-targeted emergency password reset commands.
- Backend RBAC tests covering owner migration, role boundaries, disabled-session invalidation, and sensitive service configuration.

### Changed
- Existing single-administrator installations migrate automatically to an Owner account and preserve valid sessions.
- Editors can manage dashboard structure and ordinary service-card metadata but cannot configure saved credentials or update-management providers.
- Viewers receive a read-only dashboard; update status/history remains visible while update actions are hidden.
- Admins can manage dashboard configuration, secrets, updates, connections, extensions, and global settings but cannot manage user accounts.

### Security
- Role checks are enforced server-side; hiding controls in the browser is only a usability layer.
- Disabling a user or resetting their password immediately invalidates all of that user's active sessions.
- The final enabled Owner account cannot be disabled, demoted, or deleted.

## [0.17.0] - 2026-08-23

### Added
- In-app Extension Registry browser under Settings → Extensions.
- Registry trust labels: Official, Verified Community, and Community.
- Minimum-dashboard compatibility status for registry entries.
- SHA-256 package verification and same-HTTPS-origin package enforcement.
- One-click registry installation for data-only page-template and service-catalog packs.
- Registry-backed update detection and in-place package updates while preserving enabled/disabled state.
- Registry maintainer validator (`scripts/validate-registry.py`) and CI coverage.
- Default repository-hosted registry index plus example community data packs.

### Changed
- Extension Manager now separates registry discovery from the installed-extension inventory.
- Manual extension import remains available as an offline/fallback installation path.
- Extension update confirmation displays publisher trust, author, capabilities, and permissions before the backend downloads the package.

### Security
- Registry package paths must remain relative to—and download from—the same HTTPS origin as the registry index.
- Package bytes must match the registry SHA-256 digest before manifest parsing/installation.
- Registry and downloaded package identity, version, capabilities, and permissions must match exactly.
- Registry trust labels do not bypass validation; executable third-party code remains disabled.

## [0.16.0] - 2026-08-23

### Added
- Versioned `homelab-dashboard-extension` manifest format for general community data packages.
- Explicit extension capability and permission declarations with a strict v0.16 allow-list.
- Import/enable/disable/remove lifecycle for data-only extension packages in Settings → Extensions.
- Reusable page-template packs available directly from the Add Page workflow.
- Built-in Operations and Personal Start page templates.
- Export any dashboard page as a shareable page-template extension package.
- Community service-catalog packs that add metadata-only entries to the Add Service picker without editing source code.
- Extension package authoring documentation and example page-template/catalog packs.
- Automated backend tests for extension validation, enable/disable behavior, page instantiation, and secret-free page-template export.

### Changed
- Milestone 14 is now complete because reusable distributable page-template packs have shipped.
- Extension Manager now shows capabilities, requested permissions, and enabled/disabled state for imported data packs.
- Service editor and catalog picker merge enabled community catalog entries with the built-in catalog.

### Security
- v0.16 extension packages remain data-only. Unknown permissions such as Docker write access are rejected during validation.
- Page-template exports exclude API keys, usernames/passwords, management providers/targets, controller links, and stored encrypted secrets.
- Removing/disabling an extension affects future template/catalog availability only; it cannot silently delete existing dashboard content.

## [0.15.0] - 2026-08-23

### Added
- Settings → Account section for local administrator security.
- Authenticated password-change workflow requiring the current password.
- High-entropy recovery codes displayed only when generated and stored only as digests.
- Forgot-password recovery from the login screen without requiring SMTP.
- Automatic recovery-code rotation after successful use.
- Recent account-security activity that never logs passwords or readable recovery codes.
- Host-side `python -m app.admin reset-password` emergency recovery command.
- Automatic in-place account-schema migration from v0.14.x.

### Changed
- Password changes invalidate all other dashboard sessions while keeping the initiating browser signed in.
- Password recovery invalidates every prior session before creating a fresh authenticated session.
- New installations receive a recovery code immediately after first-run setup; upgraded installations can create one from Settings.

### Security
- Passwords remain scrypt-hashed with random salts.
- Recovery codes use high entropy and are stored only as normalized SHA-256 digests.
- Emergency recovery accepts the replacement password only through an interactive prompt rather than command-line arguments.

## [0.14.0] - 2026-08-23

### Added
- Compact responsive command bar with persistent Updates/Manage controls plus consolidated Add and account/settings menus.
- Unified mixed ordering for unpinned service cards and widgets within each category.
- Category rename and icon customization in Manage mode.
- Page cloning.
- Safe dashboard layout export/import from Settings → Dashboard.
- Visual custom-theme editor that creates the same validated data-only packages used by imported themes.
- Service Status and Update Overview built-in widgets.

### Changed
- Dashboard cards use deterministic 12-column desktop/tablet/mobile spans for more predictable layouts.
- Favorite services remain pinned, while the normal unpinned layout group can freely mix services and widgets.
- Service creation/moves and widget moves now choose sort positions across both service and widget records to avoid mixed-layout collisions.
- Settings now includes a Dashboard section for portable layout tools.

### Security
- Layout exports intentionally exclude API keys, passwords, encrypted secrets, management-controller credentials, and active management links.
- Imported layouts restore service management as unconfigured rather than silently reconnecting privileged controllers.
- Visual theme editing remains data-only and cannot inject CSS, JavaScript, Python, or shell commands.

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
