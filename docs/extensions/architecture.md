# Extension architecture direction

v0.9 established validated importable theme packages, v0.10 added reusable integration descriptors/capabilities, v0.13 added the first built-in widget runtime and Extension Manager inventory, and v0.14 expanded the dashboard builder. v0.16 introduces the first general **versioned extension manifest** plus install/enable/disable/remove lifecycle for safe data-only page-template and service-catalog packs. Built-in executable adapters/widgets still ship with core; arbitrary third-party code remains disabled until a sandboxed SDK and broader permission system are ready.

The long-term extension system is intended to support several capability classes without requiring users to edit Homelab Dashboard source code:

- **Themes** — visual tokens only.
- **Service/catalog packs** — service metadata, icons, aliases, and setup hints.
- **Widgets** — dashboard components with explicitly declared capabilities.
- **Integration adapters** — backend connectors for supported services.
- **Authentication adapters** — OIDC/SSO and reverse-proxy-aware integrations.

Extensions should declare a manifest version, Homelab Dashboard compatibility range, extension type, and requested capabilities. Extensions must not automatically inherit access to Docker, saved service credentials, the filesystem, or unrelated integrations.

Themes remain a separate visual-token package format. General v0.16 extension manifests declare capabilities and permissions explicitly, but the accepted permission allow-list is intentionally narrow: packages may register page templates and service-catalog metadata only. The runtime rejects unknown/dangerous permissions and does not expose Docker, saved secrets, arbitrary networking, the filesystem, or executable code. Built-in widgets/integrations remain in core; community executable widget/integration code is deferred until a sandboxed SDK is ready. See [Data-only extension packages](packages.md).

## Future 3D Printer Center

A future optional Printer Center is planned around provider adapters rather than printer-specific UI code. Initial targets are:

- **Moonraker** for Klipper printers used through Mainsail or Fluidd.
- **OctoPrint** for a broad range of non-Klipper printers.
- **Bambuddy** for Bambu Lab printers through Bambuddy's external API rather than duplicating its printer-protocol implementation.

Printer monitoring should be read-only by default. Control capabilities such as pause/resume, cancel, heater control, movement, macros, file upload, and raw G-code should be separately permissioned according to what each provider supports.
