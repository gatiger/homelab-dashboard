import React, { FormEvent, useEffect, useState } from "react";
import { Cable, Gauge, Info, Monitor, Palette, Puzzle, Save, Settings, X } from "lucide-react";

export type DashboardSettings = {
  dashboard_title: string;
  show_greeting: boolean;
  telemetry_refresh_seconds: number;
  update_status_refresh_seconds: number;
  active_refresh_seconds: number;
  update_check_interval_hours: number;
};

export type ExtensionDescriptor = {
  id: string;
  name: string;
  type: "core" | "theme" | "widget_pack";
  version: string;
  author: string;
  description: string;
  source: "built_in" | "imported";
  active: boolean;
  removable: boolean;
};

type ConnectionSummary = { id: number; name: string; type: string; used_by: number };
type Tab = "general" | "appearance" | "connections" | "monitoring" | "extensions" | "about";

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "general", label: "General", icon: <Settings size={16} /> },
  { id: "appearance", label: "Appearance", icon: <Palette size={16} /> },
  { id: "connections", label: "Connections", icon: <Cable size={16} /> },
  { id: "monitoring", label: "Monitoring", icon: <Gauge size={16} /> },
  { id: "extensions", label: "Extensions", icon: <Puzzle size={16} /> },
  { id: "about", label: "About", icon: <Info size={16} /> },
];

export function SettingsModal({
  settings,
  extensions,
  currentTheme,
  importedThemeCount,
  connections,
  widgetCount,
  appVersion,
  onClose,
  onSave,
  onOpenAppearance,
  onOpenConnections,
  onAddWidget,
  onRemoveTheme,
}: {
  settings: DashboardSettings;
  extensions: ExtensionDescriptor[];
  currentTheme: string;
  importedThemeCount: number;
  connections: ConnectionSummary[];
  widgetCount: number;
  appVersion: string;
  onClose: () => void;
  onSave: (settings: DashboardSettings) => Promise<void>;
  onOpenAppearance: () => void;
  onOpenConnections: () => void;
  onAddWidget: () => void;
  onRemoveTheme: (themeId: string) => Promise<void>;
}) {
  const [tab, setTab] = useState<Tab>("general");
  const [form, setForm] = useState(settings);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  useEffect(() => setForm(settings), [settings]);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError(""); setSaved("");
    try { await onSave(form); setSaved("Settings saved."); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to save settings."); }
    finally { setBusy(false); }
  }

  const openSub = (callback: () => void) => { onClose(); callback(); };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.currentTarget === event.target && onClose()}>
      <section className="modal settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <header className="modal-header"><div><p className="eyebrow">SETTINGS</p><h2 id="settings-title">Homelab Dashboard</h2><p className="modal-subhead">Dashboard behavior, appearance, connections, monitoring, and extensions.</p></div><button className="icon-button" type="button" onClick={onClose} aria-label="Close"><X size={20} /></button></header>
        <div className="settings-layout">
          <nav className="settings-nav" aria-label="Settings sections">{TABS.map((item) => <button key={item.id} className={tab === item.id ? "active" : ""} type="button" onClick={() => { setTab(item.id); setError(""); setSaved(""); }}>{item.icon}<span>{item.label}</span></button>)}</nav>
          <div className="settings-content">
            {(tab === "general" || tab === "monitoring") && <form className="settings-form" onSubmit={save}>
              {tab === "general" ? <>
                <div className="settings-heading"><Monitor size={19} /><div><h3>General</h3><p>Basic dashboard identity and header behavior.</p></div></div>
                <label><span>Dashboard title</span><input value={form.dashboard_title} maxLength={80} onChange={(event) => setForm((current) => ({ ...current, dashboard_title: event.target.value }))} /></label>
                <label className="check-row"><input type="checkbox" checked={form.show_greeting} onChange={(event) => setForm((current) => ({ ...current, show_greeting: event.target.checked }))} /><span>Show personalized time-of-day greeting</span></label>
                <div className="settings-callout"><strong>Widgets</strong><span>{widgetCount} configured dashboard widget{widgetCount === 1 ? "" : "s"}.</span><button className="secondary" type="button" onClick={() => openSub(onAddWidget)}>Add widget</button></div>
              </> : <>
                <div className="settings-heading"><Gauge size={19} /><div><h3>Monitoring</h3><p>Control live browser refresh and background update discovery.</p></div></div>
                <label><span>Service telemetry refresh</span><select value={form.telemetry_refresh_seconds} onChange={(event) => setForm((current) => ({ ...current, telemetry_refresh_seconds: Number(event.target.value) }))}>{[5,10,15,30,60,120].map((value) => <option key={value} value={value}>{value} seconds</option>)}</select></label>
                <label><span>Update-state refresh</span><select value={form.update_status_refresh_seconds} onChange={(event) => setForm((current) => ({ ...current, update_status_refresh_seconds: Number(event.target.value) }))}>{[5,10,15,30,60,120].map((value) => <option key={value} value={value}>{value} seconds</option>)}</select></label>
                <label><span>Active-job refresh</span><select value={form.active_refresh_seconds} onChange={(event) => setForm((current) => ({ ...current, active_refresh_seconds: Number(event.target.value) }))}>{[1,2,3,5,10].map((value) => <option key={value} value={value}>{value} second{value === 1 ? "" : "s"}</option>)}</select></label>
                <label><span>Automatic update discovery</span><select value={form.update_check_interval_hours} onChange={(event) => setForm((current) => ({ ...current, update_check_interval_hours: Number(event.target.value) }))}><option value={0}>Disabled</option>{[1,3,6,12,24,48,72].map((value) => <option key={value} value={value}>Every {value} hour{value === 1 ? "" : "s"}</option>)}</select><small>This is the heavier registry/TrueNAS check. Cards continue reading cached state at the faster interval above.</small></label>
              </>}
              {error && <div className="notice compact">{error}</div>}{saved && <div className="connection-success">{saved}</div>}
              <div className="settings-save"><button className="primary" type="submit" disabled={busy}><Save size={16} /> {busy ? "Saving…" : "Save settings"}</button></div>
            </form>}

            {tab === "appearance" && <div className="settings-panel"><div className="settings-heading"><Palette size={19} /><div><h3>Appearance</h3><p>Theme selection and community theme packages.</p></div></div><div className="settings-summary-row"><span>Current theme</span><strong>{currentTheme}</strong></div><div className="settings-summary-row"><span>Imported themes</span><strong>{importedThemeCount}</strong></div><button className="primary" type="button" onClick={() => openSub(onOpenAppearance)}>Manage appearance</button></div>}

            {tab === "connections" && <div className="settings-panel"><div className="settings-heading"><Cable size={19} /><div><h3>Connections</h3><p>Reusable controller credentials for TrueNAS and future management providers.</p></div></div>{connections.length ? <div className="settings-list">{connections.map((item) => <div key={item.id}><span><strong>{item.name}</strong><small>{item.type} · used by {item.used_by}</small></span></div>)}</div> : <div className="settings-empty">No management connections configured.</div>}<button className="primary" type="button" onClick={() => openSub(onOpenConnections)}>Manage connections</button></div>}

            {tab === "extensions" && <div className="settings-panel"><div className="settings-heading"><Puzzle size={19} /><div><h3>Extension Manager</h3><p>Installed built-in modules and safe data-only extensions. Arbitrary executable plugins are not enabled yet.</p></div></div><div className="extension-list">{extensions.map((extension) => <div className="extension-row" key={extension.id}><div className="extension-mark"><Puzzle size={17} /></div><span><strong>{extension.name}</strong><small>{extension.description}</small><em>{extension.author} · v{extension.version} · {extension.source === "built_in" ? "Built in" : "Imported"}{extension.active && extension.type === "theme" ? " · Active" : ""}</em></span>{extension.removable && <button className="danger-button compact-button" type="button" onClick={() => void onRemoveTheme(extension.id.replace(/^theme\./, ""))}>Remove</button>}</div>)}</div></div>}

            {tab === "about" && <div className="settings-panel"><div className="settings-heading"><Info size={19} /><div><h3>About</h3><p>Version and architecture summary.</p></div></div><div className="about-card"><strong>Homelab Dashboard v{appVersion}</strong><span>Self-hosted dashboard, service monitor, update manager, and extensible homelab control center.</span><small>v0.13 adds the Settings hub and first built-in widget runtime. The open executable plugin SDK remains a later milestone.</small></div></div>}
          </div>
        </div>
      </section>
    </div>
  );
}
