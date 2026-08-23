# Upgrade to v0.20.2

v0.20.2 fixes TrueNAS System **Update & reboot** requests rejected with:

```text
[EFAULT] `train` and `version` must either both be `null` or both be non-`null`
```

No Docker Compose, Dockge Compose, environment-variable, connection, or manual database changes are required. Preserve `/app/data` and update the Dashboard image normally.

After upgrading, run **Check for updates** again and confirm the TrueNAS card still shows the expected current and available versions before retrying **Update & reboot**.
