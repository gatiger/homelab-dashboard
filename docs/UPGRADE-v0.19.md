# Upgrade to v0.19

v0.19 introduces the universal management-provider foundation and adds detection-only TrueNAS operating-system update monitoring.

## Upgrade impact

No Docker Compose, environment-variable, or manual database changes are required. Preserve `/app/data` as usual and update the dashboard image normally.

Existing Docker Compose / Dockge and TrueNAS App management configurations continue to use the same stored provider IDs and targets. The frontend now discovers those providers from the backend registry.

## Enable TrueNAS system update monitoring

1. Open or create a TrueNAS service card.
2. Under **Update management**, choose **TrueNAS System**.
3. Choose a reusable TrueNAS Connection.
4. Select the discovered **TrueNAS System** target and save.
5. Run **Updates → Check for updates** or wait for the scheduled check.

v0.19 can report the current and available TrueNAS system versions, but it cannot install the system update. This is intentional: a TrueNAS update may reboot the host, including the machine running Homelab Dashboard. Host-update installation will be added only with reboot-aware reconnect/recovery handling.

## Provider compatibility

Update All now includes only providers that explicitly advertise update-install capability. Detection-only providers can still report available updates without being queued for installation.
