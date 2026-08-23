# Extension Registry

Homelab Dashboard v0.17 adds an in-app registry for discovering and updating the same validated data-only extension packages introduced in v0.16.

Open **Settings → Extensions** to browse the registry. Each entry shows its author, version, trust label, minimum dashboard version, capabilities, requested permissions, and whether the installed copy has an update available.

## Default registry

The default registry index is hosted with the Homelab Dashboard GitHub repository:

`https://raw.githubusercontent.com/gatiger/homelab-dashboard/main/registry/index.json`

The backend caches a valid index briefly so opening Settings does not repeatedly download it. **Check registry** forces a refresh. If the registry is unavailable, installed extensions continue working and manual JSON import remains available.

The registry source can be overridden with `EXTENSION_REGISTRY_URL`. v0.17 requires the registry index to use HTTPS.

## Package verification

Registry entries do not contain executable package contents. They contain metadata plus:

- a **relative** package path,
- the package SHA-256 checksum,
- the package's declared capabilities/permissions,
- compatibility metadata, and
- a registry-assigned trust label.

The backend resolves package paths against the registry index URL and rejects paths that leave that HTTPS origin. Before install/update it downloads the package, verifies the exact SHA-256 digest, validates the extension schema, and confirms the package id/version/capabilities/permissions match the registry entry.

The confirmation shown to the administrator includes the current trust label, author, capabilities, and permissions. If the registry entry changes between browsing and installation, the request is rejected and the administrator must refresh before continuing.

## Trust labels

- **Official** — maintained by the Homelab Dashboard project.
- **Verified Community** — community-published and reviewed under the registry's verification process.
- **Community** — listed community package; review the author, metadata, and permissions before installing.

A trust label is descriptive metadata, not a sandbox or cryptographic signature. The v0.17 registry is protected primarily by HTTPS, same-origin package fetching, checksum verification, strict schema validation, and the existing data-only permission boundary. Signed packages/transparency are future hardening work before executable extensions are supported.

## Extension updates

Registry entries are matched by extension id. If the registry version is newer than the installed semantic version, Settings shows **Update available**. Updating uses the same confirmation and checksum-validation path as a first install and preserves the extension's enabled/disabled state.

The backend refuses to install the same or an older version over an installed package.

## Maintainer workflow

Registry packages live under `registry/packages/` and are indexed by `registry/index.json`. When package bytes change:

1. increment the package version,
2. update the matching registry metadata,
3. recalculate its SHA-256 checksum,
4. run `python scripts/validate-registry.py`, and
5. submit the package and index change together.

CI runs the same registry validator and rejects missing packages, checksum mismatches, unsafe package paths, unsupported capabilities/permissions, and registry/package metadata mismatches.
