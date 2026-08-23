# Users and roles

Homelab Dashboard v0.18 supports multiple local accounts. The first account created during setup becomes the first **Owner**. Existing pre-v0.18 single-administrator installs are migrated automatically to an Owner account.

## Roles

| Role | Intended use | Key permissions |
|---|---|---|
| Owner | Primary homelab administrator | Everything, including user management |
| Admin | Trusted operational administrator | Dashboard/services, saved credentials, Connections, Extensions, Settings, and updates |
| Editor | Dashboard/content maintainer | Pages, categories, widgets, and normal service-card metadata; no saved credentials or update-management configuration |
| Viewer | Read-only household/team access | View dashboard, health, activity, and cached update status |

Role checks are enforced by the backend. The frontend also hides controls that a role cannot use, but the browser UI is not the security boundary.

## Manage users

Owners can open **Settings → Users** to:

- create a local account with an initial password and role;
- change another user's role;
- enable or disable accounts;
- reset another user's password;
- delete accounts that are no longer needed.

Disabling an account immediately invalidates its active sessions. Owner-initiated password resets also invalidate that user's active sessions.

Homelab Dashboard prevents disabling, demoting, or deleting the last enabled Owner. A signed-in Owner also cannot disable, delete, or change their own role from the Users screen; another Owner must make that role change.

## Credentials and Editors

Editors can create and edit ordinary service cards, pages, categories, and widgets. They cannot add/change/remove service API keys, saved usernames/passwords, management-provider links, or management Connections. Those fields require Admin or Owner permissions.

## Recovery

Every local user manages their own recovery code from **Settings → Account**. Owners do not see another user's recovery code. See [Account recovery](account-recovery.md).
