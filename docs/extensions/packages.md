# Data-only extension packages

Homelab Dashboard v0.16 introduced the first general extension-package format. The initial runtime is deliberately **data only**: packages can register reusable page templates and/or service-catalog metadata, but they cannot execute third-party JavaScript, Python, shell commands, CSS, or other code.

## Package format

An extension is a JSON file with this top-level structure:

```json
{
  "format": "homelab-dashboard-extension",
  "schema_version": 1,
  "id": "community.example-pack",
  "name": "Example Pack",
  "version": "1.0.0",
  "author": "Example Author",
  "description": "Reusable dashboard content.",
  "type": "bundle",
  "min_dashboard_version": "0.16.0",
  "capabilities": ["page_templates", "service_catalog"],
  "permissions": ["dashboard:register-templates", "catalog:register-entries"],
  "page_templates": [],
  "catalog_entries": []
}
```

Supported data-only package types are:

- `page_template_pack` — contains page templates only.
- `catalog_pack` — contains service-catalog entries only.
- `bundle` — may contain both supported data capabilities.

## Capabilities and permissions

The manifest distinguishes what an extension **provides** from what it is allowed to **register**.

| Capability | Required permission | Purpose |
|---|---|---|
| `page_templates` | `dashboard:register-templates` | Add reusable page templates to the Add Page workflow |
| `service_catalog` | `catalog:register-entries` | Add metadata-only entries to the Add Service catalog |

Unknown permissions are rejected. In particular, the current runtime has no permission that grants Docker control, credential access, filesystem access, arbitrary network access, or code execution.

## Installing a package

Open **Settings → Extensions → Import file**, select the JSON file, and review the capabilities/permissions shown in the confirmation dialog. v0.17 can also install the same package format from the Extension Registry after verifying the registry checksum. Imported data packs can then be enabled, disabled, or removed.

Disabling/removing a package removes its templates/catalog entries from future selection. It does **not** delete pages or service cards that were already created from that package.

## Page templates

A page template can contain categories, normal service-card definitions, and supported built-in widgets. Service-card exports contain the public card definition only. API keys, usernames/passwords, management targets, management connections, and other secrets are not exported.

To create a shareable package from an existing page:

1. Turn on **Manage** mode.
2. Edit the page.
3. Choose **Export template**.
4. Share or edit the generated JSON package.

When adding a new page, the **Start from** selector lists built-in templates plus templates from enabled imported packages.

## Service-catalog packs

Catalog packs add metadata used by the Add Service picker: name, service type, category, description, aliases, optional default port/scheme, and an optional icon slug that must already exist in the dashboard's bundled icon set.

Catalog entries do not add a backend API integration by themselves. A community catalog entry behaves as a normal monitored/link service until a compatible integration runtime is added in a later milestone.

## Future executable extensions

The manifest and permission language are foundations for a future sandboxed plugin SDK. Executable widgets, integration adapters, authentication adapters, broader executable permissions are intentionally deferred until isolation, signing/trust, compatibility, and secret-access boundaries are designed and tested.
