# Update Manager

Homelab Dashboard separates **application integrations** from **management providers**. A service such as Sonarr can use the Sonarr API for health/queue information while Docker Compose, Dockge, TrueNAS, or a future platform provider independently controls how that instance is updated.

## User experience

1. Edit a service card and choose **Managed by**.
2. Link it to a resource exposed by the selected management provider. The provider declares which operations it supports.
3. Open **Updates** and choose **Check for updates**. Server-side automatic checks run every 12 hours by default.
4. For an ordinary service-scoped provider that supports installation, click **Update** on the card or in Updates.
5. For a host-scoped provider, use its explicit host action (currently **Update & reboot** for TrueNAS System). Host operations use stronger confirmation and are not bulk operations.
6. **Update all** applies only provider-declared bulk-eligible service updates, sequentially, and stops if one fails.

A provider may be detection-only. In that case, update availability is still displayed but no install action is exposed.

## Provider capability model

Management providers declare their metadata/capabilities at runtime. The frontend consumes these descriptors instead of maintaining a fixed platform list. Relevant capabilities/flags include:

- check for an update;
- install an update;
- report progress;
- rollback;
- release notes;
- service-scoped vs host-scoped operation;
- reboot requirement;
- explicit-confirmation requirement; and
- Update All eligibility.

This keeps the framework platform-neutral. Future Proxmox, Unraid, Portainer, Synology, Kubernetes/Helm, Linux-host, and other adapters can implement only the operations their upstream platform safely exposes.

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
- waits for Docker health/running state; and
- retags/recreates the previous image automatically when the new container fails health verification.

Docker socket access is still powerful. Treat the update-agent as a privileged host-management component and do not expose its port/network to untrusted containers.

### Update discovery and mutable tags

The Docker provider uses `docker pull` during an update check. Pulling an image does **not** restart the running container. Homelab Dashboard compares the running container image ID with the newly pulled local image ID; when they differ, the card is marked **Update available**. This does not depend on a particular registry API. Dedicated private-registry credential support remains a future provider enhancement.

## TrueNAS Apps provider

Open **Connections** and create a TrueNAS Connection containing the TrueNAS HTTPS URL and API key. An API-key owner username is also supported/recommended for current TrueNAS releases. The connection is reusable and does not create or require a visible dashboard card.

When a service is set to **Managed by → TrueNAS App**, select the TrueNAS Connection and choose one of the apps returned by TrueNAS.

Homelab Dashboard uses the versioned JSON-RPC WebSocket API to:

- list apps and their upgrade/latest-version state;
- ask TrueNAS to perform the app upgrade; and
- monitor the resulting app/job state and progress where available.

TrueNAS remains authoritative for its app configuration/lifecycle. Homelab Dashboard does not directly recreate TrueNAS app containers.

## TrueNAS System provider

A TrueNAS service card can be set to **Managed by → TrueNAS System** and linked to a reusable TrueNAS Connection. The provider uses the native TrueNAS update/status APIs to report the installed release and whether a newer system release is available.

### Monitoring only

A read-capable TrueNAS API credential can be used simply to monitor system-update availability. If the upstream credential does not have update-write permission, Dashboard cannot install the update even though it may be able to detect it.

### Update & reboot

In v0.20, Owner/Admin users can start an available TrueNAS system release through **Update & reboot** when the configured API key is authorized for the TrueNAS update operation. The key needs the TrueNAS system-update write permission (including `SYSTEM_UPDATE_WRITE`) plus the system/update read access used for status and verification.

The host workflow is deliberately different from a normal service update:

1. Dashboard rechecks that an update is available.
2. The user must explicitly confirm the host-level operation.
3. Dashboard saves a persistent host-update job, including the expected target version.
4. Dashboard invokes the native TrueNAS updater with reboot requested.
5. The job moves to **Reconnecting** as the host restarts.
6. Dashboard repeatedly checks TrueNAS readiness and installed version.
7. The job succeeds only after the expected version is online and ready, or fails when verification times out.

**TrueNAS System is never included in Update All.**

### Dashboard running on the TrueNAS being updated

This deployment is supported. During the TrueNAS reboot, Dashboard, Dockge/Docker, and any reverse proxy on that host may also be unavailable. The host-update record is stored in `/app/data` before the reboot. When Dashboard starts again, it recovers active host-update records and resumes verification.

Recovery intentionally **does not re-run the host update**. It only checks whether the managed system returned on the expected version, preventing an interrupted Dashboard from accidentally submitting the disruptive operation twice.

An already-open browser page can resume polling when the backend returns. A browser reload while the host is offline cannot load Dashboard until the host is back.

If the TrueNAS host fails to boot, a Dashboard running on that same host cannot report the boot failure. A separate management host provides the strongest resilience, but it is optional.

## Automatic checks

Default:

```env
UPDATE_CHECK_INTERVAL_HOURS=12
```

Set it to `0` to disable automatic discovery. The manual **Check for updates** action continues to work.

Docker checks may download changed image layers even if you do not immediately recreate the service. If bandwidth/storage churn matters, increase the interval or disable automatic checks.

## Current provider coverage

The current release ships:

- Docker Compose / Dockge — detect + install + progress + rollback foundation; bulk eligible
- TrueNAS Apps — detect + install + progress; bulk eligible
- TrueNAS System — detect + explicit host install + reboot/reconnect verification; **not** bulk eligible

The capability-based provider API is designed for future Portainer, Unraid, Proxmox, Synology, Kubernetes/Helm, Linux-host, and other adapters without changing application integrations.
