# Upgrade to v0.11

v0.11 performs an in-place SQLite migration and preserves existing users, pages, categories, cards, layouts, themes, and integration credentials.

## Standard upgrade

Update the dashboard image as usual. Existing installations continue to work with update management disabled.

## Enable Docker/Dockge one-click updates (optional)

The updater feature requires one additional privileged sidecar because the main dashboard deliberately retains no Docker write access.

Add the v0.11 `compose.management.yaml` overlay (or equivalent Dockge service definition), set:

```env
UPDATE_AGENT_TOKEN=<long-random-token>
UPDATE_AGENT_STACKS_ROOT=<absolute host path containing your compose stacks>
```

and recreate the stack. Do not publish the update-agent port.

TrueNAS App updates do not require this sidecar; they use the selected TrueNAS controller card/API key.

After upgrade, edit cards you want Homelab Dashboard to manage and choose their provider/target. Nothing is automatically given update privileges during migration.
