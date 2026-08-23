# Extension architecture direction

v0.9 established the first extension-shaped feature: validated, importable theme packages. v0.10 added reusable integration descriptors/capabilities, and v0.13 adds the first built-in widget runtime plus an Extension Manager inventory. Built-in adapters and widgets still ship with core for now, but their contracts are being shaped so later community packages can plug into the same UI safely.

The long-term extension system is intended to support several capability classes without requiring users to edit Homelab Dashboard source code:

- **Themes** — visual tokens only.
- **Service/catalog packs** — service metadata, icons, aliases, and setup hints.
- **Widgets** — dashboard components with explicitly declared capabilities.
- **Integration adapters** — backend connectors for supported services.
- **Authentication adapters** — OIDC/SSO and reverse-proxy-aware integrations.

Extensions should declare a manifest version, Homelab Dashboard compatibility range, extension type, and requested capabilities. Extensions must not automatically inherit access to Docker, saved service credentials, the filesystem, or unrelated integrations.

The theme format is intentionally the first importable implementation because it lets the project exercise validation, persistence, compatibility, selection, inventory, and removal flows without allowing executable community code. v0.13 widgets remain built into core; arbitrary widget/integration code is intentionally deferred until the permission model and SDK are ready.

## Future 3D Printer Center

A future optional Printer Center is planned around provider adapters rather than printer-specific UI code. Initial targets are:

- **Moonraker** for Klipper printers used through Mainsail or Fluidd.
- **OctoPrint** for a broad range of non-Klipper printers.
- **Bambuddy** for Bambu Lab printers through Bambuddy's external API rather than duplicating its printer-protocol implementation.

Printer monitoring should be read-only by default. Control capabilities such as pause/resume, cancel, heater control, movement, macros, file upload, and raw G-code should be separately permissioned according to what each provider supports.
