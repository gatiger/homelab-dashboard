# Upgrade to v0.12

v0.12 performs an in-place SQLite migration and preserves existing users, pages, categories, cards, layouts, themes, integration credentials, update history, and Docker management links.

## TrueNAS management migration

If a v0.11 service is managed as a TrueNAS App through a TrueNAS controller card, the first v0.12 startup creates a reusable **TrueNAS Connection** by copying that controller card's URL and encrypted API credentials. The managed service is linked to the new connection automatically.

The original TrueNAS card is not deleted or modified. Keep it if you want TrueNAS telemetry on the dashboard, or remove it later after confirming nothing else needs the card itself.

New TrueNAS App management should be configured through **Connections**, not through a visible TrueNAS card.

## Card refresh behavior

Open dashboard tabs refresh service telemetry and cached update states about every 15 seconds. While an update job is queued/running, the UI refreshes about every 2.5 seconds. Returning to a previously hidden browser tab triggers an immediate refresh.

This browser refresh is separate from server-side update discovery. Registry/TrueNAS update checks remain controlled by:

```env
UPDATE_CHECK_INTERVAL_HOURS=12
```

Set it to `0` to disable scheduled update discovery while keeping manual **Check for updates** available.
