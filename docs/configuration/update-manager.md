# Update Manager

Homelab Dashboard separates **application integrations** from **management providers**. A service such as Sonarr can use the Sonarr API for health/queue information while Docker Compose, Dockge, or TrueNAS independently controls how that instance is updated.

## User experience

1. Edit a service card and choose **Managed by**.
2. Link it to a resource exposed by the selected management provider. The provider declares whether it supports detection only or can also install updates.
3. Open **Updates** and choose **Check for updates** (server-side automatic checks run every 12 hours by default). Open dashboard tabs refresh cached card state automatically without a page reload.
4. When that provider advertises install capability, click **Update** on a card or in the Updates screen. The work runs in the background and progress is shown in Homelab Dashboard.
5. **Update all** applies only actionable updates sequentially and stops if one fails. Detection-only updates remain visible but are never placed in the update queue.

No native service UI needs to be opened for providers that support installation.

## Docker Compose / Dockge provider

Docker write access is optional and is not given to the main dashboard container. Enable `compose.management.yaml`, which runs a dedicated update-agent sidecar.

Add to `.env`:

```env
UPDATE_AGENT_TOKEN=replace-with-a-long-random-value
UPDATE_AGENT_STACKS_ROOT=/absolute/host/path/to/your/compose/stacks
```

Generate a token with a password manager or, on Linux:

```bash
openssl rand -hex 32
```

Then start with:

```bash
docker compose -f compose.yaml -f compose.management.yaml up -d
```

For Dockge, `UPDATE_AGENT_STACKS_ROOT` is the host directory containing Dockge stack folders. Dockge may record its own internal `/opt/stacks/<name>` path in Docker Compose labels; the agent safely maps that label back to `<UPDATE_AGENT_STACKS_ROOT>/<name>` when needed.

The update agent:

- has no host-published HTTP port;
- accepts the shared token when configured;
- discovers only Compose-managed containers;
- rejects projects outside `UPDATE_AGENT_STACKS_ROOT`;
- mounts stack definitions read-only;
- exposes no arbitrary command endpoint;
- pulls the selected image and recreates only that Compose service;
- waits for Docker health/running state;
- retags/recreates the previous image automatically when the new container fails health verification.

Docker socket access is still powerful. Treat the update-agent as a privileged host-management component and do not expose its port/network to untrusted containers.

### Update discovery and mutable tags

The first Docker provider uses `docker pull` during an update check. Pulling an image does **not** restart the running container. Homelab Dashboard compares the running container image ID with the newly pulled local image ID; when they differ, the card is marked **Update available**. This does not depend on a particular registry API. v0.14 targets public container registries; dedicated private-registry credential support is planned for a later provider enhancement.

## TrueNAS Apps provider

Open **Connections** and create a TrueNAS Connection containing the TrueNAS HTTPS URL and API key. An API-key owner username is also supported/recommended for current TrueNAS releases. The connection is reusable and does not create or require a visible dashboard card.

When a service is set to **Managed by → TrueNAS App**, select the TrueNAS Connection and choose one of the apps returned by `app.query`. Existing v0.11 controller-card links are migrated automatically by v0.12+ installations.

Homelab Dashboard uses the TrueNAS versioned JSON-RPC WebSocket API to:

- list apps and their `upgrade_available`/latest-version state;
- ask TrueNAS to perform `app.upgrade`;
- monitor the resulting app/job state and progress where available.

Homelab Dashboard does not directly recreate TrueNAS app containers, so TrueNAS remains authoritative for its app configuration and lifecycle.

API keys are password-equivalent credentials. Use a dedicated user-linked key with only the roles required for the operations you want to allow. TrueNAS requires secure HTTPS/WSS transport for user-linked API key authentication.

## TrueNAS System provider

A TrueNAS service card can be set to **Managed by → TrueNAS System** and linked to a reusable TrueNAS Connection. v0.19 uses the native JSON-RPC update-status API to report the installed release and whether a newer system release is available.

TrueNAS System is deliberately **detection-only in v0.19**. The provider advertises check/release-note capability but not update-install capability, so neither the card nor Update All can start a NAS operating-system update. Host updates can reboot the machine that is running Homelab Dashboard itself; installation will be enabled only after the dashboard has reboot-aware reconnect/recovery behavior.

## Provider capability model

Management providers declare their display metadata and capabilities at runtime. The frontend consumes those descriptors instead of maintaining its own fixed list. A provider can declare capabilities such as update checking, installation, progress, rollback, and release notes, along with an optional reusable connection type and the label/shape of its managed target.

This keeps the framework platform-neutral: future Proxmox, Unraid, Portainer, Synology, Kubernetes/Helm, and other adapters can implement only the operations their upstream platform safely exposes. A provider that can detect releases but cannot safely install them can remain detection-only without special-case UI code.

## Automatic checks

Default:

```env
UPDATE_CHECK_INTERVAL_HOURS=12
```

Set it to `0` to disable automatic discovery. The manual **Check for updates** action continues to work.

Docker checks may download changed image layers even if you do not immediately recreate the service. If bandwidth/storage churn matters, increase the interval or disable automatic checks.

## Current provider coverage

The current release ships:

- Docker Compose / Dockge — detect + install + progress + rollback foundation
- TrueNAS Apps — detect + install + progress
- TrueNAS System — detect only in v0.19

The capability-based provider API is designed for future Portainer, Unraid, Proxmox, Synology, Kubernetes/Helm, and other platform adapters without changing application integrations.
