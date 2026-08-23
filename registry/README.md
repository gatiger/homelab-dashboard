# Homelab Dashboard Extension Registry

`index.json` is the default extension registry consumed by Homelab Dashboard v0.17 and newer. Packages in `packages/` remain data-only under the current extension permission model.

Registry entries include the extension identity/version, compatibility requirement, declared capabilities/permissions, a trust label, a relative package path, and the SHA-256 checksum of the exact package bytes. Package paths are resolved on the same HTTPS origin as the registry index.

## Trust labels

- `official` — published and maintained by the Homelab Dashboard project.
- `verified_community` — community-published and reviewed under the registry's verification process.
- `community` — community package listed by the registry; users should review its metadata and permissions before installation.

A trust label is not a security sandbox. v0.17 still validates every package against the data-only extension schema and rejects executable/privileged permissions.

## Updating a package

Replace the package JSON, increment its semantic version, recalculate the SHA-256 checksum, and update the matching `index.json` entry in the same pull request. Never reuse a version number for different package bytes.
