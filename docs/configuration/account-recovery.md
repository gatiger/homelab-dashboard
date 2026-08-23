# Account and password recovery

Homelab Dashboard v0.18 supports recovery for each local user account without requiring email or an external identity provider.

## Change your password while signed in

Open **Settings → Account** and enter the current password plus the new password twice.

A successful password change:

- updates the password hash in the local SQLite database;
- keeps the browser that performed the change signed in;
- invalidates every other active session for that user; and
- records a security event without storing the password.

Passwords must be at least 10 characters.

## Recovery codes

A recovery code is a high-entropy one-time secret belonging to one local user. New first-run Owner accounts receive one after setup. Other users can create their own code from **Settings → Account** after signing in.

Recovery codes are shown only when generated. Homelab Dashboard stores only a SHA-256 digest of the normalized high-entropy code, not the readable code itself.

Generating a new recovery code invalidates the previous code immediately. The current password is required to generate or replace a code while signed in.

Store each recovery code somewhere outside the Homelab Dashboard data volume, such as a password manager or another protected recovery record.

## Forgot password

On the login screen choose **Forgot password?** and provide the username, saved recovery code, a new password, and confirmation.

A successful recovery replaces the password, invalidates that user's existing sessions, signs the recovering browser in with a new session, invalidates the recovery code that was just used, and displays a replacement recovery code that must be saved.

The recovery endpoint returns the same authentication failure for an unknown username and an invalid recovery code so it does not intentionally disclose whether an account name exists.

## Owner reset for another local user

An Owner can open **Settings → Users**, choose another account, and set a new password. This invalidates all active sessions for that account. The Owner never receives or changes that user's recovery code through the web UI.

For their own password, Owners should use **Settings → Account** so the current browser can remain signed in.

## Emergency host-side reset

If the password and recovery code are both lost, a person who already has legitimate shell access to the container host can list local users:

```bash
docker exec -it dashboard-dashboard-1 python -m app.admin list-users
```

Then reset a specific account:

```bash
docker exec -it dashboard-dashboard-1 python -m app.admin reset-password USERNAME
```

If the username is omitted, the command targets the first Owner account. It prompts for the password interactively, enables the account, invalidates that user's sessions, rotates the recovery code, and prints the new recovery code once.

Someone with Docker/container-host access is already in a higher trust position than the dashboard application. Protect host shell access accordingly.

## Future authentication providers

The local recovery flow applies to native accounts. Future OIDC/SSO or reverse-proxy authentication providers can delegate password recovery to their identity provider instead.
