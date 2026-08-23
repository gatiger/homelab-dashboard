# Architecture

## Principles

1. The browser never receives stored API keys.
2. Integrations are isolated behind backend adapters.
3. Personal configuration is separate from source code.
4. A generic/custom card always remains available.
5. Installation should not require hand-editing YAML after startup.
6. The built-in catalog represents common self-hosted use cases, not one maintainer's personal stack.
7. New service identifiers should not require a database schema change.
8. Visual extensions must not execute code or inherit infrastructure/credential access.

## Current layers

- **Production application container:** Nginx serves the React/TypeScript frontend and proxies `/api` to the local FastAPI process inside the same image. The source tree still keeps frontend and backend concerns separate for development.
- **Service catalog:** `frontend/src/serviceCatalog.ts` contains built-in template metadata (identifier, name, category, icon, common port, description, aliases, and capability hints).
- **Backend:** FastAPI authentication, configuration, health checks, secret storage, and integration adapters.
- **Database:** SQLite in a persistent Docker volume. Services, pages, widgets, Settings, appearance selection, imported theme manifests, connections, and update history are stored alongside dashboard configuration.
- **Theme layer:** Frontend components consume validated design tokens. Built-in and imported themes share the same data shape; imported theme packages are non-executable JSON.
- **Integration adapters:** Service-specific backend functions for supported rich cards; unsupported catalog entries still work as generic monitored links.
- **Docker access (optional):** The base deployment has no Docker socket access. Read-only insight uses a restricted socket proxy. One-click Docker Compose updates use a separate update-agent sidecar on a private internal network; only that agent receives the raw socket.
- **Reverse proxy:** Caddy, Traefik, Nginx, or another user-selected proxy.

## Service model

Each configured service currently has an ID, display name, open-ended service type identifier, URL, dashboard page assignment, category, optional custom icon, enabled state, monitoring state, favorite/pinned state, card size, persistent sort order, optional encrypted API key and/or encrypted username/password credentials, and timestamps.

The catalog is intentionally separate from configured services. A catalog entry is a template; selecting it creates a normal service record that the user can rename, re-categorize, or point at any URL/port.

## Extension path

v0.9 established the first versioned extension-shaped package: non-executable theme manifests. v0.10 adds explicit backend integration descriptors and a shared activity/progress data model. The same package-management principles will later expand to catalog packs, widgets, installable integration adapters, and authentication adapters with explicit capability declarations.

The catalog metadata will become the basis for future versioned integration manifests. Rich integrations can declare capabilities (status, metrics, activity, controls, authentication methods) without requiring every catalog entry to ship custom backend code. See `docs/extensions/architecture.md`.

## Integration/activity model

Rich backend adapters normalize service-specific APIs into `ServiceInsight` records. Each insight can declare capabilities and zero or more `ServiceActivity` records. Activities use a common shape for operation, title, progress percentage, transferred/total bytes, transfer speed, ETA, status, and detail text. The frontend therefore renders one progress component for downloads, storage scans, updates, and future job types rather than embedding service-specific progress UI.

Credentials remain backend-only. API-key integrations use the existing encrypted key field; username/password integrations such as qBittorrent use separate encrypted credential fields. Empty credential fields during edit preserve existing secrets unless the user explicitly chooses to remove them.

## Management/update model

Application integrations and management providers are intentionally separate. A Sonarr adapter can provide health, queue, and activity while a Docker Compose or TrueNAS provider controls how that Sonarr instance is updated. This avoids service/platform combinations such as separate Sonarr-Docker and Sonarr-TrueNAS adapters.

Each service may optionally store a `management_provider`, provider target, and reusable management-connection reference. The current release ships two providers:

- **Docker Compose / Dockge:** the dashboard talks to an optional internal update-agent. The agent discovers Compose project/service labels from Docker, rejects projects outside an allow-listed stacks root, pulls the image, recreates only the selected Compose service, waits for Docker health/running state, and restores the previous image when health verification fails. Stack files are mounted read-only and the agent has no arbitrary shell-command API.
- **TrueNAS Apps:** the backend talks through a reusable encrypted TrueNAS Connection over the versioned JSON-RPC WebSocket API and invokes the TrueNAS app-management methods. TrueNAS remains the system of record for its apps; Homelab Dashboard does not manipulate the underlying app containers directly. Visible TrueNAS cards are optional telemetry views, not credential controllers.

Update state and history are stored in SQLite. Update work runs in background threads so browser/API requests return immediately and the frontend polls job progress. Update All is sequential and stops on failure.

The update-agent is a privileged component because Docker socket access is effectively host-level control. It is optional, isolated from the public network, token-protected, and intentionally narrower than exposing Docker write APIs directly to the main dashboard.

## Settings and widget model

Dashboard-wide preferences are persisted in the existing `app_settings` store and exposed through authenticated Settings endpoints. v0.14 uses these preferences for the dashboard title/greeting, browser telemetry refresh cadence, cached update-state refresh cadence, active-job refresh cadence, and the server-side update-discovery interval. Browser refresh timing and update discovery remain intentionally separate so the UI can feel live without repeatedly querying registries or platform APIs.

Built-in dashboard widgets are stored in `dashboard_widgets`. A widget has a type, title, page/category placement, card size, sort order, enabled state, and validated JSON configuration. v0.14 ships clock, note, bookmarks, system-summary, service-status, and update-overview widgets. Widget configuration is data-only; the current Extension Manager does not execute third-party JavaScript, Python, CSS, or other arbitrary plugin code.

## Layout model

Dashboard structure is persisted server-side rather than only in browser local storage. `dashboard_pages` stores page/tab names and order. Every service and widget has a `page_id`, while `category_layouts` stores category order, collapsed state, and optional header icon separately for each page. Services and widgets share the same numeric sort space inside a category through the mixed dashboard-item reorder endpoint. `favorite` keeps service cards in a pinned group ahead of the normal mixed service/widget group, and `card_size` is one of `compact`, `standard`, or `wide`.

The browser only keeps the most recently selected page ID as a convenience; the actual page/category/card structure remains portable across browsers and devices because it lives in SQLite. v0.14 also exposes a credential-free layout export/import format for sharing structure between installations; full backups still use `/app/data`.


## Distribution model

Stable releases publish a multi-architecture OCI image for `linux/amd64` and `linux/arm64` through GitHub Container Registry. `compose.yaml` is the reference production deployment. `compose.build.yaml` is a source-build override for contributors, `compose.docker.yaml` adds the optional local-Docker insight layer, and `compose.management.yaml` adds the optional restricted Docker Compose update agent. Platform-specific UIs such as Dockge, Portainer, TrueNAS Apps, Unraid, Synology Container Manager, and QNAP Container Station are deployment front ends rather than application dependencies.
