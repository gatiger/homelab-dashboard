# Dashboard widgets

Widgets are persistent dashboard items that do not require a service URL. v0.14 makes widgets first-class layout items: unpinned service cards and widgets can be reordered together inside the same category.

## Built-in widgets

### Clock & Date

Displays time and optionally the date and seconds. Use `local` to follow the viewing device time zone, or enter an IANA time-zone name such as `America/New_York`.

### Note

Stores up to 4,000 characters of plain text for reminders, instructions, or homelab notes.

### Bookmarks

Stores up to 12 quick links. The editor accepts one entry per line:

```text
Sonarr | http://192.168.1.10:8989
Documentation | https://example.com
```

The backend accepts only `http://` and `https://` bookmark URLs.

### Dashboard Summary

Displays dashboard-level counts such as online/offline services, pending managed-service updates, and configured management connections. Each group can be shown or hidden.

### Service Status

Displays a live list of configured service states. The widget can show 3–12 entries and optionally includes response latency for online services.

### Update Overview

Displays managed services with pending updates and their known version transition. It can optionally include services that are already current.

## Placement and ordering

Every widget has:

- A dashboard page.
- A category.
- Compact, Standard, or Wide card size.
- An enabled/hidden state.

Widget categories participate in normal category ordering and collapse state. Pages containing widgets cannot be deleted until the widgets are moved or removed.

In Manage mode, widgets and unpinned service cards now share one persistent mixed order. Favorite service cards remain a pinned group at the front of the category.

## Extension direction

The current widgets are built into core. They establish a common persistent widget model before community widget packages are allowed to execute. A later extension milestone will define manifests, capabilities, permissions, compatibility rules, and a plugin SDK.
