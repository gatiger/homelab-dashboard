# Update Manager

Homelab Dashboard separates **application integrations** from **management providers**. A service such as Sonarr can use the Sonarr API for health/queue information while Docker Compose, Dockge, TrueNAS, or a future platform provider independently controls how that instance is updated.

v0.21 adds an optional maintenance scheduler, per-service update policies, release delays, post-update verification, capability-aware rollback, automatic Docker-provider suggestions, and post-host-reboot service recovery checks. Scheduled installation is **disabled by default**.

## Basic workflow

1. Edit a service card and choose **Managed by**.
2. Link it to a resource exposed by the selected management provider. The provider declares which operations it supports.
3. Open **Updates** and choose **Check for updates**. Server-side automatic discovery also runs on the configured discovery interval (12 hours by default).
4. For an ordinary service-scoped provider that supports installation, click **Update** on the card or in Updates.
5. For a host-scoped provider, use its explicit host action (currently **Update & reboot** for TrueNAS System). Host operations use stronger confirmation and are not bulk operations.
6. **Update all** applies only provider-declared bulk-eligible service updates, sequentially, and stops if one fails.

A provider may be detection-only. In that case, update availability is still displayed but no install action is exposed.

## Automatic provider matching

When the service editor can see the optional Docker Compose/Dockge update agent, v0.21 looks for an obvious Compose-service match when update management has not been configured yet. Matching is conservative: Dashboard normalizes the visible card name/service type and compares it to discovered Compose service names.

When there is an exact match, the editor shows **Update management detected** and a **Use detected service** button. Dashboard does **not** silently grant itself update control. An Owner/Admin must approve the detected resource and save the card.

This is useful for cards such as Lidarr, Tdarr, Seerr, Bazarr, Caddy, Tailscale, or any other Compose-managed application even when that application does not have a rich Dashboard integration. Application telemetry and update management are independent features.

## Provider capability model

Management providers declare their metadata/capabilities at runtime. The frontend consumes these descriptors instead of maintaining a fixed platform list. Relevant capabilities/flags include:

- check for an update;
- install an update;
- report progress;
- rollback mode (`automatic`, `manual`, or `none`);
- release notes;
- service-scoped vs host-scoped operation;
- reboot requirement;
- explicit-confirmation requirement;
- Update All eligibility; and
- provider-specific recovery guidance.

This keeps the framework platform-neutral. Future Proxmox, Unraid, Portainer, Synology, Kubernetes/Helm, Linux-host, and other adapters can implement only the operations their upstream platform safely exposes.

## Per-service update policy

An Owner/Admin can configure each managed service card with an update policy:

- **Use global policy** — follows the global scheduled-update setting. When scheduling is disabled globally, the service remains manual.
- **Manual** — update availability is visible and an authorized user can update manually, but the scheduler will skip the service.
- **Scheduled** — eligible for a maintenance-window run when global scheduled updates are enabled.
- **Monitor only** — Dashboard may detect/report updates but cannot start that card's update manually or through the scheduler.

A service can also override the global **release delay** and **rollback policy**. Leaving either override unset uses the global setting.

> Global scheduled updates are the master switch. Setting one card to Scheduled does not turn on unattended installation by itself.

## Scheduled maintenance

Open **Settings → Updates** to configure scheduled service updates. The scheduler is fully opt-in and is disabled on a new installation.

Available controls are:

- enable/disable scheduled service updates;
- one or more maintenance days;
- maintenance-window start and end time;
- default release delay;
- automatic rollback when the provider safely supports it; and
- whether to stop the remaining maintenance queue after the first failed update.

The default values after enabling the feature are Sunday, 03:00–06:00, a 3-day release delay, automatic rollback enabled where supported, and stop-on-failure enabled.

### How a maintenance window runs

At the first scheduler pass inside an eligible maintenance window, Dashboard:

1. confirms that no update/check/host-recovery job is already active;
2. performs a fresh update check for configured management providers;
3. selects only service-scoped, bulk-eligible updates whose service policy permits scheduling;
4. applies each service's release-delay rule using the first time that specific update was detected;
5. records the maintenance window before starting work so a Dashboard restart cannot accidentally repeat the unattended run; and
6. updates eligible services **sequentially**, never as a simultaneous batch.

A maintenance window is consumed once per configured occurrence. If no update is old enough/eligible at that pass, Dashboard waits for the next configured maintenance window rather than repeatedly retrying during the same window.

The schedule uses the Dashboard server/container's local clock. If the window crosses midnight (for example 23:00–02:00), the early-morning portion belongs to the previous selected maintenance day.

**Host-scoped updates are never scheduled in v0.21.** TrueNAS System remains explicit/manual even when scheduled service updates are enabled.

## Release delay

Release delay prevents a newly detected update from being installed immediately by scheduled maintenance. Dashboard stores an `available_since` timestamp when it first sees a specific available update and preserves that timestamp across normal rechecks.

For example, with a 3-day delay:

- an update first detected Sunday morning is not eligible for Sunday's maintenance run;
- it becomes eligible once it has been continuously known to Dashboard for at least three days; and
- it will be picked up in the next configured maintenance window, assuming it is still available.

Manual updates are not blocked by the scheduler's release-delay rule.

## Post-update verification

For an ordinary service update, Dashboard records the health signals that were meaningful **before** the update. After the management provider finishes, Dashboard verifies those same signals again.

Examples:

- if the card's HTTP status was Online/Degraded before the update, the HTTP status must recover;
- if the service had a working rich integration before the update, that integration must return to `ok`;
- if the service had no usable pre-update health signal, Dashboard does not invent one and incorrectly fail the update.

This adds application-level verification on top of a provider's own container/job checks.

## Rollback and manual recovery

Rollback is capability-aware. Dashboard never assumes that every provider or application can safely return to an earlier version.

### Docker Compose / Dockge

The Docker provider supports **image rollback**. Before recreation it records the image that is currently running and preserves an addressable reference to that image until Dashboard-level verification finishes.

If Docker recreation/container health fails, the update agent immediately attempts to restore the previous image. If the container comes up but Dashboard's HTTP/integration verification subsequently fails, Dashboard can also request the preserved image rollback when the service/global rollback policy permits it.

After a successful application-level verification, Dashboard commits the update and releases the temporary rollback reference.

**Important data-migration limitation:** Docker image rollback does not rewind a service's application database, configuration files, or other persistent volumes. Some applications perform irreversible or backward-incompatible data migrations on first start. For those applications, configure the card's rollback policy as **Manual**, maintain provider/platform backups or snapshots, and follow the upstream application's downgrade/recovery instructions. A future provider-specific snapshot capability can extend this framework without treating an image rollback as a universal data rollback.

### TrueNAS Apps

The current TrueNAS App provider can detect/install upgrades but does not advertise an automatic rollback operation in v0.21. On failure, Dashboard stops the automated queue when configured to do so, preserves the failure details, and shows provider recovery guidance. Use TrueNAS's native app/backup/snapshot workflow as appropriate for that application.

### TrueNAS System

TrueNAS System is marked as a **manual recovery** provider. Dashboard preserves the host-update history and recovery guidance, but does not automatically activate an older boot environment. If a system update requires rollback, use the TrueNAS boot-environment recovery workflow from the native UI/console as appropriate.

### Queue behavior after failure

Scheduled maintenance defaults to **Stop remaining updates after a failure**. This prevents an unattended maintenance window from continuing through several unrelated services after one update has already failed or rolled back. The setting can be disabled, but stop-on-failure is the recommended policy for most homelabs.

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
- preserves the previous image until Dashboard-level verification succeeds; and
- exposes narrow commit/rollback operations only for an update job that is awaiting verification.

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

Owner/Admin users can start an available TrueNAS system release through **Update & reboot** when the configured API key is authorized for the TrueNAS update operation. The host workflow is deliberately different from a normal service update:

1. Dashboard rechecks that an update is available.
2. The user must explicitly confirm the host-level operation.
3. Dashboard records which other enabled HTTP-monitored services were healthy before the update.
4. Dashboard saves a persistent host-update job, including the expected target version and service-recovery snapshot.
5. Dashboard invokes the native TrueNAS updater with reboot requested.
6. The job moves to **Reconnecting** as the host restarts.
7. Dashboard repeatedly checks TrueNAS readiness and installed version.
8. After the expected host version returns, Dashboard waits for the previously healthy monitored services to recover.
9. The host update is recorded as successful once the expected TrueNAS version is online; the result additionally reports any monitored services that still need attention.

**TrueNAS System is never included in Update All and is never included in scheduled service maintenance.**

### Dashboard running on the TrueNAS being updated

This deployment is supported. During the TrueNAS reboot, Dashboard, Dockge/Docker, and any reverse proxy on that host may also be unavailable. The host-update record is stored in `/app/data` before the reboot. When Dashboard starts again, it recovers active host-update records and resumes verification.

Recovery intentionally **does not re-run the host update**. It only checks whether the managed system returned on the expected version, preventing an interrupted Dashboard from accidentally submitting the disruptive operation twice.

The post-reboot service snapshot is also persistent, so Dashboard can continue checking the services that were healthy before the reboot even if Dashboard itself went offline with the host.

If the TrueNAS host fails to boot, a Dashboard running on that same host cannot report the boot failure. A separate management host provides the strongest resilience, but it is optional.

## Automatic update discovery

Scheduled **discovery** and scheduled **installation** are separate features.

Default discovery interval:

```env
UPDATE_CHECK_INTERVAL_HOURS=12
```

The setting is also configurable under **Settings → Monitoring**. Set it to `0`/Disabled to stop automatic discovery. Manual **Check for updates** continues to work.

Disabling automatic discovery does not automatically disable an already configured maintenance scheduler: when a maintenance window starts, v0.21 performs its own fresh update check before selecting eligible work.

Docker discovery may download changed image layers even if you do not immediately recreate the service. If bandwidth/storage churn matters, increase the discovery interval or disable automatic discovery.

## Current provider coverage

v0.21 ships:

- **Docker Compose / Dockge** — detect + install + progress + preserved-image rollback + Dashboard-level post-update verification; bulk/scheduler eligible.
- **TrueNAS Apps** — detect + install + progress; bulk/scheduler eligible; automatic rollback not currently advertised.
- **TrueNAS System** — detect + explicit host install + reboot/reconnect + post-reboot service recovery checks; manual recovery guidance; **not** bulk/scheduler eligible.

The capability-based provider API is designed for future Portainer, Unraid, Proxmox, Synology, Kubernetes/Helm, Linux-host, and other adapters without changing application integrations.
