# Upgrade to v0.15

v0.15 adds local administrator password management and recovery.

## Database migration

The existing administrator account is preserved. The dashboard adds nullable recovery/password-change metadata columns plus an account-security audit table automatically on startup.

Existing installations do **not** receive a recovery code automatically during migration because a readable recovery code must only be shown to the administrator at generation time. After upgrading, open **Settings → Account** and choose **Create recovery code**.

## Compose changes

No Docker Compose or Dockge stack changes are required when upgrading from v0.14.x.

## Recommended post-upgrade step

1. Open **Settings → Account**.
2. Confirm the administrator username.
3. Create a recovery code using the current password.
4. Store the recovery code somewhere safe outside the dashboard installation.

For emergency host-side recovery, see [Account recovery](configuration/account-recovery.md).
