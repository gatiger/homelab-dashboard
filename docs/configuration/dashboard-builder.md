# Advanced dashboard builder

v0.14 expands Manage mode into a more consistent page builder while keeping dashboard data server-side in SQLite.

## Compact command bar

The large row of permanent header actions has been replaced by a compact command bar:

- **Updates** stays visible and shows an amber attention badge only when cached update checks report available updates.
- **Manage / Done** toggles layout editing.
- **Add** opens one menu for services, widgets, and pages.
- **Menu** contains Settings, Connections, Appearance, and Sign out.

On small screens the text labels collapse so the controls occupy much less horizontal space.

## Unified service and widget ordering

Services and widgets now share one order within a category. In Manage mode, an unpinned service can be dragged before or after a widget and the mixed order is persisted together.

Favorite service cards remain pinned ahead of normal cards. Pinned cards can be reordered with other pinned cards; unpinned services and widgets form the normal mixed layout group.

## Responsive card widths

The desktop grid uses a deterministic 12-column layout rather than relying only on browser auto-fit behavior:

- Compact and Standard cards use one third of a wide desktop row.
- Wide cards use two thirds of a wide desktop row.
- Tablet layouts reduce to two normal cards per row.
- Narrow/mobile layouts use one card per row.

The card's internal information order remains consistent across breakpoints.

## Category customization

In Manage mode, use the pencil on a category header to:

- Rename that category across all services and widgets on the current page.
- Select a category header icon.

Category order and collapsed state continue to persist independently for each page.

## Page cloning

Edit a page in Manage mode and choose **Clone page** to duplicate the page's categories, services, widgets, layout, and saved service configuration into a new page. The clone receives a new page identity and does not copy update-history records.

This is intended for quickly creating a variation of an existing dashboard. Reusable distributable page-template packs remain a later enhancement.

## Layout export and import

Open **Settings → Dashboard** to export or import dashboard structure.

Exports include:

- pages;
- category names, order, collapse state, and icons;
- public service-card configuration;
- widgets and widget configuration;
- card sizes and ordering.

Exports deliberately do **not** include passwords, API keys, encrypted secrets, management-controller credentials, or active management links. An import adds new pages alongside the existing dashboard and resolves duplicate page names automatically.

This feature is for portable layout/templates, not a substitute for a full `/app/data` backup.

## Visual custom-theme editor

Appearance now includes **Create custom theme**. The editor starts from the currently active theme and exposes the validated design-token colors. Saved themes use the same data-only theme package format as imported themes and still cannot run CSS or JavaScript.
