# Account and password recovery

Homelab Dashboard currently uses one local administrator account. v0.15 adds password changes and recovery without requiring email or an external identity provider.

## Change the password while signed in

Open **Settings → Account** and enter the current password plus the new password twice.

A successful password change:

- updates the password hash in the local SQLite database;
- keeps the browser that performed the change signed in;
- invalidates every other active dashboard session; and
- records a security event without storing the password.

Passwords must be at least 10 characters.

## Recovery codes

A recovery code is a high-entropy one-time secret used only for account recovery. New installations receive one after first-run administrator setup. Existing installations upgraded to v0.15 can create one from **Settings → Account**.

Recovery codes are shown only when they are generated. Homelab Dashboard stores only a SHA-256 digest of the normalized high-entropy code, not the readable code itself.

Generating a new recovery code invalidates the previous code immediately. The current password is required to generate or replace a code while signed in.

Store the recovery code somewhere outside the Homelab Dashboard data volume, such as a password manager or another protected recovery record.

## Forgot password

On the login screen choose **Forgot password?** and provide:

1. the administrator username;
2. the saved recovery code;
3. a new password; and
4. confirmation of the new password.

A successful recovery:

- replaces the password;
- invalidates all existing sessions;
- signs the recovering browser in with a new session;
- invalidates the recovery code that was just used; and
- displays a replacement recovery code that must be saved before leaving the screen.

The recovery endpoint returns the same authentication failure for an unknown username and an invalid recovery code so it does not intentionally disclose whether an account name exists.

## Emergency host-side reset

If the password and recovery code are both lost, a person who already has legitimate shell access to the Docker host can reset the administrator account from inside the running dashboard container:

```bash
docker exec -it dashboard-dashboard-1 python -m app.admin reset-password
```

Use the actual dashboard container name if it differs.

The command prompts for the new password interactively. It deliberately does not accept the password as a command-line argument, avoiding exposure through shell history or process listings.

A successful emergency reset:

- changes the local administrator password;
- invalidates every dashboard session;
- invalidates the previous recovery code;
- prints a new recovery code once; and
- records an emergency-reset security event.

Someone with Docker/container-host access is already in a higher trust position than the dashboard application. Protect host shell access accordingly.

## Security activity

**Settings → Account** shows recent account-security events such as password changes, recovery-code generation, recovery resets, and host-side emergency resets. Passwords and readable recovery codes are never written to the audit log.

## Future authentication providers

The current recovery flow applies to the native local administrator account. Future OIDC/SSO or reverse-proxy authentication providers can delegate password recovery to their identity provider instead of using the local recovery-code mechanism.
