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
- **Database:** SQLite in a persistent Docker volume. Appearance selection and imported theme manifests are stored alongside dashboard configuration.
- **Theme layer:** Frontend components consume validated design tokens. Built-in and imported themes share the same data shape; imported theme packages are non-executable JSON.
- **Integration adapters:** Service-specific backend functions for supported rich cards; unsupported catalog entries still work as generic monitored links.
- **Docker access (optional):** The base deployment has no Docker socket access. Users who enable local Docker insight add a restricted socket proxy on an internal network; the dashboard itself never receives the raw Docker socket.
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

## Layout model

Dashboard structure is persisted server-side rather than only in browser local storage. `dashboard_pages` stores page/tab names and order. Every service has a `page_id`, while `category_layouts` stores category order and collapsed state separately for each page. Service `sort_order` controls card order within a page/category, `favorite` pins a card ahead of unpinned cards in that category, and `card_size` is one of `compact`, `standard`, or `wide`.

The browser only keeps the most recently selected page ID as a convenience; the actual page/category/card structure remains portable across browsers and devices because it lives in SQLite.


## Distribution model

Stable releases publish a multi-architecture OCI image for `linux/amd64` and `linux/arm64` through GitHub Container Registry. `compose.yaml` is the reference production deployment. `compose.build.yaml` is a source-build override for contributors, and `compose.docker.yaml` adds the optional local-Docker insight layer. Platform-specific UIs such as Dockge, Portainer, TrueNAS Apps, Unraid, Synology Container Manager, and QNAP Container Station are deployment front ends rather than application dependencies.
