# Upgrade to v0.20

v0.20 adds the generic safe host-update execution/recovery layer and enables explicitly confirmed TrueNAS operating-system updates.

## Upgrade impact

No Docker Compose, Dockge Compose, environment-variable, or manual database changes are required. Preserve `/app/data` and update the dashboard image normally.

Existing Docker Compose / Dockge, TrueNAS App, and TrueNAS System monitoring configurations continue to work without being recreated.

## TrueNAS System after upgrading

If a TrueNAS card is already configured with **Managed by → TrueNAS System**, continue to use **Updates → Check for updates** normally.

When TrueNAS reports a system update:

1. Owner/Admin users will see **Update & reboot** instead of a normal service-update button.
2. The operation requires a separate confirmation explaining that the managed host and its services will be interrupted.
3. The TrueNAS System provider is not counted by **Update All** and cannot be started through that bulk action.
4. Dashboard persists the operation before calling the TrueNAS updater.
5. While the host reboots, the job enters **Reconnecting**.
6. When TrueNAS returns, Dashboard checks readiness and verifies the expected installed version before marking the job successful.

### If Dashboard itself runs on that TrueNAS host

Dashboard and its reverse proxy may become unavailable during the reboot. This is expected. Once TrueNAS, Docker, and the Dashboard container start again, Dashboard finds the persisted host-update job and resumes **verification only**. It does not issue the update command a second time.

If you reload the browser while Dashboard is offline, the page cannot load until the host returns. If the already-loaded page remains open, it will resume API polling when the backend becomes available again.

### API-key permission requirement

The API key that was sufficient for v0.19 monitoring may not have permission to install updates. To use **Update & reboot**, the reusable TrueNAS Connection needs the upstream system-update write permission (including `SYSTEM_UPDATE_WRITE`) plus the read permissions needed for update/system status. Monitoring continues to work with read-only credentials even when installation is not authorized by TrueNAS.

## CI workflow maintenance

The repository workflow action majors were updated to Node.js 24-compatible versions. No user-side configuration is required.
