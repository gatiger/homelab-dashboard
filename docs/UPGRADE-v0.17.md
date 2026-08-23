# Upgrade to v0.17

v0.17 adds the Extension Registry and in-place updates for safe data-only extension packages.

No database migration that changes existing dashboard content is required. Existing v0.16 packages remain installed and enabled exactly as before. If an installed extension id also exists in the configured registry, the Extension Manager can now show whether a newer version is available.

No Dockge/Compose changes are required for the default registry. The bundled backend defaults to the official HTTPS registry URL. Advanced deployments may set `EXTENSION_REGISTRY_URL`, `EXTENSION_REGISTRY_TIMEOUT`, and `EXTENSION_REGISTRY_CACHE_SECONDS` as container environment variables.

Executable third-party plugin code remains disabled in v0.17.
