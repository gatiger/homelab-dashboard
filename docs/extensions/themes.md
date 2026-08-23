# Theme extensions

Homelab Dashboard v0.9 introduces a deliberately limited theme extension format. Theme packages are JSON data only: they cannot contain JavaScript, arbitrary CSS, network requests, filesystem access, Docker access, or credential access.

## Importing a theme

1. Sign in to Homelab Dashboard.
2. Choose **Appearance**.
3. Select **Import theme**.
4. Choose a `.json` theme package.
5. Select the imported theme from the Appearance screen.

Imported themes are stored in the dashboard's persistent SQLite data and therefore survive container updates.

## Package format

```json
{
  "format": "homelab-dashboard-theme",
  "schema_version": 1,
  "id": "midnight-blue",
  "name": "Midnight Blue",
  "version": "1.0.0",
  "author": "Example Author",
  "description": "A dark blue community theme.",
  "mode": "dark",
  "colors": {
    "background": "#050914",
    "backgroundAccent": "#102a56",
    "surface": "#0a1220",
    "surfaceAlt": "#101b2e",
    "surfaceHover": "#172640",
    "surfaceInset": "#02050b",
    "border": "#30415f",
    "borderSoft": "#24334c",
    "borderStrong": "#465c82",
    "text": "#f5f9ff",
    "textSecondary": "#ced9ea",
    "muted": "#91a4bf",
    "subtle": "#667b99",
    "accent": "#3b82f6",
    "accentHover": "#2563eb",
    "accentStrong": "#1d4ed8",
    "accentSoft": "#102a56",
    "accentLight": "#60a5fa",
    "accentText": "#dbeafe"
  }
}
```

All color values must be six-digit hexadecimal colors. Theme IDs must contain only lowercase letters, numbers, and hyphens. IDs used by built-in themes are reserved.

The Appearance screen can download a current starter template, and `examples/themes/` contains an example package in the repository.

## Why themes cannot contain CSS or JavaScript

Homelab Dashboard can hold API credentials and can optionally connect to infrastructure-management services. Allowing an appearance package to execute code would give a visual add-on an unnecessarily large security surface. The v1 theme format therefore exposes approved design tokens only.

Future theme schema versions may add more visual tokens while retaining the same no-code rule.
