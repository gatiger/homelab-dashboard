export type ThemeMode = "dark" | "light";

export type ThemeColors = {
  background: string;
  backgroundAccent: string;
  surface: string;
  surfaceAlt: string;
  surfaceHover: string;
  surfaceInset: string;
  border: string;
  borderSoft: string;
  borderStrong: string;
  text: string;
  textSecondary: string;
  muted: string;
  subtle: string;
  accent: string;
  accentHover: string;
  accentStrong: string;
  accentSoft: string;
  accentLight: string;
  accentText: string;
};

export type ThemePackage = {
  format: "homelab-dashboard-theme";
  schema_version: 1;
  id: string;
  name: string;
  version: string;
  author: string;
  description?: string | null;
  mode: ThemeMode;
  colors: ThemeColors;
};

export type BuiltinTheme = ThemePackage & { builtin: true };

export const BUILTIN_THEMES: BuiltinTheme[] = [
  {
    format: "homelab-dashboard-theme", schema_version: 1, id: "dark", name: "Dark", version: "1.0.0", author: "Homelab Dashboard", builtin: true,
    description: "The original deep-blue Homelab Dashboard look.", mode: "dark",
    colors: {
      background: "#070b14", backgroundAccent: "#172554", surface: "#0b1220", surfaceAlt: "#0f172a", surfaceHover: "#111827", surfaceInset: "#020617",
      border: "#334155", borderSoft: "#263449", borderStrong: "#475569", text: "#f8fafc", textSecondary: "#cbd5e1", muted: "#94a3b8", subtle: "#64748b",
      accent: "#3b82f6", accentHover: "#2563eb", accentStrong: "#1d4ed8", accentSoft: "#172554", accentLight: "#60a5fa", accentText: "#dbeafe",
    },
  },
  {
    format: "homelab-dashboard-theme", schema_version: 1, id: "light", name: "Light", version: "1.0.0", author: "Homelab Dashboard", builtin: true,
    description: "Bright surfaces with a clean blue accent.", mode: "light",
    colors: {
      background: "#eef2f7", backgroundAccent: "#dbeafe", surface: "#ffffff", surfaceAlt: "#f8fafc", surfaceHover: "#eef2ff", surfaceInset: "#e2e8f0",
      border: "#cbd5e1", borderSoft: "#dbe3ed", borderStrong: "#94a3b8", text: "#0f172a", textSecondary: "#334155", muted: "#64748b", subtle: "#64748b",
      accent: "#2563eb", accentHover: "#1d4ed8", accentStrong: "#1e40af", accentSoft: "#dbeafe", accentLight: "#3b82f6", accentText: "#1e3a8a",
    },
  },
  {
    format: "homelab-dashboard-theme", schema_version: 1, id: "slate", name: "Slate", version: "1.0.0", author: "Homelab Dashboard", builtin: true,
    description: "Neutral charcoal surfaces with a cool cyan accent.", mode: "dark",
    colors: {
      background: "#0b0f14", backgroundAccent: "#12323a", surface: "#111820", surfaceAlt: "#17212b", surfaceHover: "#1c2833", surfaceInset: "#070a0e",
      border: "#33424f", borderSoft: "#263540", borderStrong: "#4b5c68", text: "#f3f7f9", textSecondary: "#c5d0d6", muted: "#8fa1aa", subtle: "#657780",
      accent: "#06b6d4", accentHover: "#0891b2", accentStrong: "#0e7490", accentSoft: "#12323a", accentLight: "#67e8f9", accentText: "#cffafe",
    },
  },
  {
    format: "homelab-dashboard-theme", schema_version: 1, id: "ocean", name: "Ocean", version: "1.0.0", author: "Homelab Dashboard", builtin: true,
    description: "Navy surfaces with vivid aqua highlights.", mode: "dark",
    colors: {
      background: "#04111d", backgroundAccent: "#083344", surface: "#071b2a", surfaceAlt: "#0b2536", surfaceHover: "#0f3044", surfaceInset: "#020b12",
      border: "#164e63", borderSoft: "#123c4d", borderStrong: "#277188", text: "#f0fdfa", textSecondary: "#c7e7e4", muted: "#83aaa9", subtle: "#5d8585",
      accent: "#14b8a6", accentHover: "#0d9488", accentStrong: "#0f766e", accentSoft: "#0b3c45", accentLight: "#5eead4", accentText: "#ccfbf1",
    },
  },
  {
    format: "homelab-dashboard-theme", schema_version: 1, id: "forest", name: "Forest", version: "1.0.0", author: "Homelab Dashboard", builtin: true,
    description: "Dark evergreen surfaces with fresh green accents.", mode: "dark",
    colors: {
      background: "#07110b", backgroundAccent: "#12351f", surface: "#0b1b12", surfaceAlt: "#10251a", surfaceHover: "#163021", surfaceInset: "#030904",
      border: "#28543a", borderSoft: "#203f2d", borderStrong: "#3a6a4b", text: "#f0fdf4", textSecondary: "#cae7d3", muted: "#8eaa96", subtle: "#688370",
      accent: "#22c55e", accentHover: "#16a34a", accentStrong: "#15803d", accentSoft: "#12351f", accentLight: "#4ade80", accentText: "#dcfce7",
    },
  },
  {
    format: "homelab-dashboard-theme", schema_version: 1, id: "violet", name: "Violet", version: "1.0.0", author: "Homelab Dashboard", builtin: true,
    description: "Deep purple surfaces with a bright violet accent.", mode: "dark",
    colors: {
      background: "#0d0815", backgroundAccent: "#2e1065", surface: "#171021", surfaceAlt: "#21152e", surfaceHover: "#2a1939", surfaceInset: "#08040d",
      border: "#4c3565", borderSoft: "#39294d", borderStrong: "#654b7e", text: "#faf5ff", textSecondary: "#e6d9ee", muted: "#ac98ba", subtle: "#806c8f",
      accent: "#8b5cf6", accentHover: "#7c3aed", accentStrong: "#6d28d9", accentSoft: "#2e1065", accentLight: "#a78bfa", accentText: "#ede9fe",
    },
  },
  {
    format: "homelab-dashboard-theme", schema_version: 1, id: "amber", name: "Amber", version: "1.0.0", author: "Homelab Dashboard", builtin: true,
    description: "Warm graphite surfaces with amber highlights.", mode: "dark",
    colors: {
      background: "#120d06", backgroundAccent: "#452b08", surface: "#1c150c", surfaceAlt: "#261c10", surfaceHover: "#302313", surfaceInset: "#0a0703",
      border: "#5c4728", borderSoft: "#44351f", borderStrong: "#745b35", text: "#fffbeb", textSecondary: "#eadfc5", muted: "#b1a182", subtle: "#887859",
      accent: "#f59e0b", accentHover: "#d97706", accentStrong: "#b45309", accentSoft: "#452b08", accentLight: "#fbbf24", accentText: "#fef3c7",
    },
  },
];

export const BUILTIN_THEME_BY_ID = Object.fromEntries(BUILTIN_THEMES.map((theme) => [theme.id, theme])) as Record<string, BuiltinTheme>;

export const THEME_TEMPLATE: ThemePackage = {
  format: "homelab-dashboard-theme",
  schema_version: 1,
  id: "my-theme",
  name: "My Theme",
  version: "1.0.0",
  author: "Your Name",
  description: "A custom Homelab Dashboard theme.",
  mode: "dark",
  colors: { ...BUILTIN_THEME_BY_ID.dark.colors },
};

const CSS_VARIABLES: Record<keyof ThemeColors, string> = {
  background: "--theme-background",
  backgroundAccent: "--theme-background-accent",
  surface: "--theme-surface",
  surfaceAlt: "--theme-surface-alt",
  surfaceHover: "--theme-surface-hover",
  surfaceInset: "--theme-surface-inset",
  border: "--theme-border",
  borderSoft: "--theme-border-soft",
  borderStrong: "--theme-border-strong",
  text: "--theme-text",
  textSecondary: "--theme-text-secondary",
  muted: "--theme-muted",
  subtle: "--theme-subtle",
  accent: "--theme-accent",
  accentHover: "--theme-accent-hover",
  accentStrong: "--theme-accent-strong",
  accentSoft: "--theme-accent-soft",
  accentLight: "--theme-accent-light",
  accentText: "--theme-accent-text",
};

export function applyTheme(theme: ThemePackage, selectedId: string): void {
  const root = document.documentElement;
  Object.entries(theme.colors).forEach(([key, value]) => {
    root.style.setProperty(CSS_VARIABLES[key as keyof ThemeColors], value);
  });
  root.dataset.theme = selectedId;
  root.dataset.themeMode = theme.mode;
  root.style.colorScheme = theme.mode;
}

export function resolveTheme(selectedId: string, customThemes: ThemePackage[]): ThemePackage {
  if (selectedId === "system") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? BUILTIN_THEME_BY_ID.dark : BUILTIN_THEME_BY_ID.light;
  }
  return BUILTIN_THEME_BY_ID[selectedId] ?? customThemes.find((theme) => theme.id === selectedId) ?? BUILTIN_THEME_BY_ID.dark;
}
