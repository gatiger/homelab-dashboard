# Upgrade to v0.16

v0.16 adds the first general data-only extension package runtime and reusable page templates.

## Container installs

Pull/recreate the dashboard normally or use your existing Homelab Dashboard updater. No Compose changes are required from v0.15.x.

The database migration creates `installed_extensions` automatically. Existing dashboard data and secrets are unchanged.

## After upgrading

- Open **Settings → Extensions** to import validated page-template or service-catalog JSON packages.
- Use **Add → Page** to choose a built-in or enabled imported page template.
- In Manage mode, edit an existing page and choose **Export template** to create a shareable, secret-free page-template package.

Executable third-party plugins are not enabled in v0.16.
