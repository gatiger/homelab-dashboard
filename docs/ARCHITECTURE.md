# Architecture

## Principles

1. The browser never receives stored API keys.
2. Integrations are isolated behind backend adapters.
3. Personal configuration is separate from source code.
4. A generic/custom card always remains available.
5. Installation should not require hand-editing YAML after startup.
6. The built-in catalog represents common self-hosted use cases, not one maintainer's personal stack.
7. New service identifiers should not require a database schema change.

## Current layers

- **Production application container:** Nginx serves the React/TypeScript frontend and proxies `/api` to the local FastAPI process inside the same image. The source tree still keeps frontend and backend concerns separate for development.
- **Service catalog:** `frontend/src/serviceCatalog.ts` contains built-in template metadata (identifier, name, category, icon, common port, description, aliases, and capability hints).
- **Backend:** FastAPI authentication, configuration, health checks, secret storage, and integration adapters.
- **Database:** SQLite in a persistent Docker volume.
- **Integration adapters:** Service-specific backend functions for supported rich cards; unsupported catalog entries still work as generic monitored links.
- **Docker access (optional):** The base deployment has no Docker socket access. Users who enable local Docker insight add a restricted socket proxy on an internal network; the dashboard itself never receives the raw Docker socket.
- **Reverse proxy:** Caddy, Traefik, Nginx, or another user-selected proxy.

## Service model

Each configured service currently has an ID, display name, open-ended service type identifier, URL, category, optional custom icon, enabled state, monitoring state, favorite/pinned state, card size, persistent sort order, optional encrypted API credential, and timestamps.

The catalog is intentionally separate from configured services. A catalog entry is a template; selecting it creates a normal service record that the user can rename, re-categorize, or point at any URL/port.

## Extension path

The catalog metadata will become the basis for a future versioned integration manifest. Rich integrations can declare capabilities (status, metrics, activity, controls, authentication methods) without requiring every catalog entry to ship custom backend code.

## Layout model

Layout preferences are stored with each configured service rather than only in browser local storage. `sort_order` controls card order within a category, `favorite` pins a card ahead of unpinned cards in that category, and `card_size` is one of `compact`, `standard`, or `wide`. This keeps a dashboard consistent across browsers and makes later multi-page/import-export features possible without redesigning the persistence layer.


## Distribution model

Stable releases publish a multi-architecture OCI image for `linux/amd64` and `linux/arm64` through GitHub Container Registry. `compose.yaml` is the reference production deployment. `compose.build.yaml` is a source-build override for contributors, and `compose.docker.yaml` adds the optional local-Docker insight layer. Platform-specific UIs such as Dockge, Portainer, TrueNAS Apps, Unraid, Synology Container Manager, and QNAP Container Station are deployment front ends rather than application dependencies.
