# Upgrade to v0.18

v0.18 adds local multi-user accounts and role-based permissions.

## Automatic migration

Existing installations require no manual database work. On first start, the existing single administrator is copied into the new local-user store as an **Owner**. Valid existing sessions are migrated as well, so the upgrade should not force an immediate sign-in again.

The legacy authentication tables remain in the database for migration compatibility but the v0.18 runtime uses the new multi-user tables.

## After upgrading

Open **Settings → Users** to create additional local accounts if desired. The available roles are Owner, Admin, Editor, and Viewer.

No Docker Compose, update-agent, persistent-volume, or environment-variable changes are required.

## Recovery

Each local user owns their own recovery code. Existing Owner recovery configuration is migrated. Newly created users can generate a recovery code from **Settings → Account** after their first login.

Emergency host recovery can target a username:

```bash
docker exec -it dashboard-dashboard-1 python -m app.admin reset-password USERNAME
```
