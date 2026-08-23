import React, { FormEvent, useEffect, useState } from "react";
import { Cable, Copy, Download, Gauge, Info, KeyRound, LayoutGrid, Monitor, Palette, Puzzle, Save, Settings, ShieldCheck, Upload, X } from "lucide-react";

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

export type AccountAuditEvent = {
  id: number;
  event: string;
  detail?: string | null;
  created_at: string;
};

export type AccountSummary = {
  username: string;
  recovery_configured: boolean;
  recovery_generated_at?: string | null;
  password_changed_at?: string | null;
  recent_events: AccountAuditEvent[];
};

export type RecoveryCodeResult = {
  recovery_code: string;
  generated_at: string;
};

type ConnectionSummary = { id: number; name: string; type: string; used_by: number };
type Tab = "general" | "account" | "dashboard" | "appearance" | "connections" | "monitoring" | "extensions" | "about";

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "general", label: "General", icon: <Settings size={16} /> },
  { id: "account", label: "Account", icon: <ShieldCheck size={16} /> },
  { id: "dashboard", label: "Dashboard", icon: <LayoutGrid size={16} /> },
  { id: "appearance", label: "Appearance", icon: <Palette size={16} /> },
  { id: "connections", label: "Connections", icon: <Cable size={16} /> },
  { id: "monitoring", label: "Monitoring", icon: <Gauge size={16} /> },
  { id: "extensions", label: "Extensions", icon: <Puzzle size={16} /> },
  { id: "about", label: "About", icon: <Info size={16} /> },
];

function formatWhen(value?: string | null): string {
  if (!value) return "Not yet";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function eventLabel(event: string): string {
  return event.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export function SettingsModal({
  settings,
  account,
  extensions,
  currentTheme,
  importedThemeCount,
  connections,
  widgetCount,
  appVersion,
  onClose,
  onSave,
  onChangePassword,
  onRegenerateRecoveryCode,
  onOpenAppearance,
  onOpenConnections,
  onAddWidget,
  onExportDashboard,
  onImportDashboard,
  onRemoveTheme,
}: {
  settings: DashboardSettings;
  account: AccountSummary | null;
  extensions: ExtensionDescriptor[];
  currentTheme: string;
  importedThemeCount: number;
  connections: ConnectionSummary[];
  widgetCount: number;
  appVersion: string;
  onClose: () => void;
  onSave: (settings: DashboardSettings) => Promise<void>;
  onChangePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  onRegenerateRecoveryCode: (currentPassword: string) => Promise<RecoveryCodeResult>;
  onOpenAppearance: () => void;
  onOpenConnections: () => void;
  onAddWidget: () => void;
  onExportDashboard: () => void;
  onImportDashboard: () => void;
  onRemoveTheme: (themeId: string) => Promise<void>;
}) {
  const [tab, setTab] = useState<Tab>("general");
  const [form, setForm] = useState(settings);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [recoveryPassword, setRecoveryPassword] = useState("");
  const [newRecoveryCode, setNewRecoveryCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => setForm(settings), [settings]);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError(""); setSaved("");
    try { await onSave(form); setSaved("Settings saved."); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to save settings."); }
    finally { setBusy(false); }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault(); setError(""); setSaved(""); setNewRecoveryCode(null);
    if (newPassword !== confirmPassword) { setError("New passwords do not match."); return; }
    if (newPassword.length < 10) { setError("New password must be at least 10 characters."); return; }
    setBusy(true);
    try {
      await onChangePassword(currentPassword, newPassword);
      setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
      setSaved("Password changed. Other signed-in sessions were invalidated.");
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to change password."); }
    finally { setBusy(false); }
  }

  async function regenerateRecovery() {
    setError(""); setSaved(""); setCopied(false);
    if (!recoveryPassword) { setError("Enter your current password first."); return; }
    setBusy(true);
    try {
      const result = await onRegenerateRecoveryCode(recoveryPassword);
      setRecoveryPassword(""); setNewRecoveryCode(result.recovery_code);
      setSaved("Recovery code generated. The previous code no longer works.");
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to generate a recovery code."); }
    finally { setBusy(false); }
  }

  async function copyRecoveryCode() {
    if (!newRecoveryCode) return;
    try { await navigator.clipboard.writeText(newRecoveryCode); setCopied(true); }
    catch { setError("Could not copy automatically. Select and copy the recovery code manually."); }
  }

  const openSub = (callback: () => void) => { onClose(); callback(); };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.currentTarget === event.target && onClose()}>
      <section className="modal settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <header className="modal-header"><div><p className="eyebrow">SETTINGS</p><h2 id="settings-title">Homelab Dashboard</h2><p className="modal-subhead">Account security, dashboard behavior, appearance, connections, monitoring, and extensions.</p></div><button className="icon-button" type="button" onClick={onClose} aria-label="Close"><X size={20} /></button></header>
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

            {tab === "account" && <div className="settings-panel">
              <div className="settings-heading"><ShieldCheck size={19} /><div><h3>Account & recovery</h3><p>Protect the local administrator account and keep a recovery path that does not depend on email.</p></div></div>
              <div className="settings-summary-row"><span>Administrator</span><strong>{account?.username ?? "Loading…"}</strong></div>
              <div className="settings-summary-row"><span>Password last changed</span><strong>{formatWhen(account?.password_changed_at)}</strong></div>
              <div className="settings-summary-row"><span>Recovery code</span><strong className={account?.recovery_configured ? "security-good" : "security-attention"}>{account?.recovery_configured ? "Configured" : "Not configured"}</strong></div>

              <form className="security-section" onSubmit={changePassword}>
                <div className="settings-heading"><KeyRound size={18} /><div><h3>Change password</h3><p>Changing your password signs out every other dashboard session while keeping this browser signed in.</p></div></div>
                <label><span>Current password</span><input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} autoComplete="current-password" required /></label>
                <label><span>New password</span><input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength={10} autoComplete="new-password" required /></label>
                <label><span>Confirm new password</span><input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} minLength={10} autoComplete="new-password" required /></label>
                <div><button className="primary" type="submit" disabled={busy}>Change password</button></div>
              </form>

              <div className="security-section">
                <div className="settings-heading"><ShieldCheck size={18} /><div><h3>Recovery code</h3><p>Use this one-time secret from the login screen if you forget your password. Generating a new code immediately invalidates the previous one.</p></div></div>
                <label><span>Current password</span><input type="password" value={recoveryPassword} onChange={(event) => setRecoveryPassword(event.target.value)} autoComplete="current-password" placeholder="Required to generate a recovery code" /></label>
                <div><button className="secondary" type="button" disabled={busy} onClick={() => void regenerateRecovery()}>{account?.recovery_configured ? "Generate new recovery code" : "Create recovery code"}</button></div>
                {newRecoveryCode && <div className="recovery-code-box"><span>Save this code now. It will not be shown again.</span><code>{newRecoveryCode}</code><button className="secondary compact-button" type="button" onClick={() => void copyRecoveryCode()}><Copy size={15} /> {copied ? "Copied" : "Copy code"}</button></div>}
              </div>

              {error && <div className="notice compact">{error}</div>}{saved && <div className="connection-success">{saved}</div>}

              <div className="security-section">
                <div className="settings-heading"><Info size={18} /><div><h3>Recent security activity</h3><p>Passwords and recovery codes are never written to this log.</p></div></div>
                {account?.recent_events?.length ? <div className="security-event-list">{account.recent_events.map((event) => <div key={event.id}><span><strong>{eventLabel(event.event)}</strong><small>{event.detail || "Account security event"}</small></span><time>{formatWhen(event.created_at)}</time></div>)}</div> : <div className="settings-empty">No account security events recorded yet.</div>}
              </div>
              <div className="settings-callout"><strong>Emergency host recovery</strong><span>If both the password and recovery code are lost, a person with shell access to the dashboard host can run the documented emergency reset command.</span></div>
            </div>}

            {tab === "dashboard" && <div className="settings-panel"><div className="settings-heading"><LayoutGrid size={19} /><div><h3>Dashboard builder</h3><p>Move your layout between installations or keep a reusable structure file. Exported layout files intentionally exclude passwords, API keys, and controller credentials.</p></div></div><div className="builder-action-grid"><button className="secondary" type="button" onClick={onExportDashboard}><Download size={16} /> Export layout</button><button className="secondary" type="button" onClick={onImportDashboard}><Upload size={16} /> Import layout</button></div><div className="settings-callout"><strong>Safe layout export</strong><span>Pages, categories, service card definitions, and widgets are included. Secrets and management links are not.</span></div></div>}

            {tab === "appearance" && <div className="settings-panel"><div className="settings-heading"><Palette size={19} /><div><h3>Appearance</h3><p>Theme selection, visual theme editing, and community theme packages.</p></div></div><div className="settings-summary-row"><span>Current theme</span><strong>{currentTheme}</strong></div><div className="settings-summary-row"><span>Imported themes</span><strong>{importedThemeCount}</strong></div><button className="primary" type="button" onClick={() => openSub(onOpenAppearance)}>Manage appearance</button></div>}

            {tab === "connections" && <div className="settings-panel"><div className="settings-heading"><Cable size={19} /><div><h3>Connections</h3><p>Reusable controller credentials for TrueNAS and future management providers.</p></div></div>{connections.length ? <div className="settings-list">{connections.map((item) => <div key={item.id}><span><strong>{item.name}</strong><small>{item.type} · used by {item.used_by}</small></span></div>)}</div> : <div className="settings-empty">No management connections configured.</div>}<button className="primary" type="button" onClick={() => openSub(onOpenConnections)}>Manage connections</button></div>}

            {tab === "extensions" && <div className="settings-panel"><div className="settings-heading"><Puzzle size={19} /><div><h3>Extension Manager</h3><p>Installed built-in modules and safe data-only extensions. Arbitrary executable plugins are not enabled yet.</p></div></div><div className="extension-list">{extensions.map((extension) => <div className="extension-row" key={extension.id}><div className="extension-mark"><Puzzle size={17} /></div><span><strong>{extension.name}</strong><small>{extension.description}</small><em>{extension.author} · v{extension.version} · {extension.source === "built_in" ? "Built in" : "Imported"}{extension.active && extension.type === "theme" ? " · Active" : ""}</em></span>{extension.removable && <button className="danger-button compact-button" type="button" onClick={() => void onRemoveTheme(extension.id.replace(/^theme\./, ""))}>Remove</button>}</div>)}</div></div>}

            {tab === "about" && <div className="settings-panel"><div className="settings-heading"><Info size={19} /><div><h3>About</h3><p>Version and architecture summary.</p></div></div><div className="about-card"><strong>Homelab Dashboard v{appVersion}</strong><span>Self-hosted dashboard, service monitor, update manager, and extensible homelab control center.</span><small>v0.15 adds local account password changes, one-time recovery codes, forgotten-password recovery, session invalidation, security audit history, and emergency host-side recovery.</small></div></div>}
          </div>
        </div>
      </section>
    </div>
  );
}
