import React, { FormEvent, useEffect, useRef, useState } from "react";
import { Cable, Copy, Download, Gauge, Info, KeyRound, LayoutGrid, Monitor, Palette, Puzzle, RefreshCw, Save, Settings, ShieldCheck, Upload, UserPlus, Users, X } from "lucide-react";

export type DashboardSettings = {
  dashboard_title: string;
  show_greeting: boolean;
  telemetry_refresh_seconds: number;
  update_status_refresh_seconds: number;
  active_refresh_seconds: number;
  update_check_interval_hours: number;
  scheduled_updates_enabled: boolean;
  update_maintenance_days: number[];
  update_maintenance_start: string;
  update_maintenance_end: string;
  update_release_delay_days: number;
  update_stop_on_failure: boolean;
  update_automatic_rollback: boolean;
};

export type ExtensionDescriptor = {
  id: string;
  name: string;
  type: "core" | "theme" | "widget_pack" | "page_template_pack" | "catalog_pack" | "bundle";
  version: string;
  author: string;
  description: string;
  source: "built_in" | "imported";
  active: boolean;
  enabled: boolean;
  removable: boolean;
  capabilities: string[];
  permissions: string[];
};


export type ExtensionRegistryItem = {
  id: string;
  name: string;
  version: string;
  author: string;
  description: string;
  type: "page_template_pack" | "catalog_pack" | "bundle";
  min_dashboard_version: string;
  capabilities: string[];
  permissions: string[];
  trust: "official" | "verified_community" | "community";
  package: string;
  sha256: string;
  homepage_url?: string | null;
  repository_url?: string | null;
  installed_version?: string | null;
  installed_enabled?: boolean | null;
  update_available: boolean;
  compatible: boolean;
  compatibility_message?: string | null;
};

export type ExtensionRegistryResponse = {
  registry_id: string;
  registry_name: string;
  description: string;
  source_url: string;
  checked_at: string;
  entries: ExtensionRegistryItem[];
};

export type AccountAuditEvent = {
  id: number;
  event: string;
  detail?: string | null;
  created_at: string;
};

export type AccountSummary = {
  username: string;
  role: "owner" | "admin" | "editor" | "viewer";
  recovery_configured: boolean;
  recovery_generated_at?: string | null;
  password_changed_at?: string | null;
  recent_events: AccountAuditEvent[];
};

export type RecoveryCodeResult = {
  recovery_code: string;
  generated_at: string;
};


export type UserSummary = {
  id: number;
  username: string;
  role: "owner" | "admin" | "editor" | "viewer";
  enabled: boolean;
  recovery_configured: boolean;
  password_changed_at?: string | null;
  last_login_at?: string | null;
  created_at: string;
};

type ConnectionSummary = { id: number; name: string; type: string; used_by: number };
type Tab = "general" | "account" | "users" | "dashboard" | "appearance" | "connections" | "monitoring" | "updates" | "extensions" | "about";

const ALL_TABS: { id: Tab; label: string; icon: React.ReactNode; permission?: string }[] = [
  { id: "general", label: "General", icon: <Settings size={16} />, permission: "settings:manage" },
  { id: "account", label: "Account", icon: <ShieldCheck size={16} /> },
  { id: "users", label: "Users", icon: <Users size={16} />, permission: "users:manage" },
  { id: "dashboard", label: "Dashboard", icon: <LayoutGrid size={16} />, permission: "dashboard:edit" },
  { id: "appearance", label: "Appearance", icon: <Palette size={16} />, permission: "settings:manage" },
  { id: "connections", label: "Connections", icon: <Cable size={16} />, permission: "connections:manage" },
  { id: "monitoring", label: "Monitoring", icon: <Gauge size={16} />, permission: "settings:manage" },
  { id: "updates", label: "Updates", icon: <RefreshCw size={16} />, permission: "settings:manage" },
  { id: "extensions", label: "Extensions", icon: <Puzzle size={16} />, permission: "extensions:manage" },
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

function UserAdminRow({
  user,
  currentUsername,
  onUpdate,
  onResetPassword,
  onDelete,
  onError,
  onSaved,
}: {
  user: UserSummary;
  currentUsername: string;
  onUpdate: (user: UserSummary, role: UserSummary["role"], enabled: boolean) => Promise<void>;
  onResetPassword: (user: UserSummary, password: string) => Promise<void>;
  onDelete: (user: UserSummary) => Promise<void>;
  onError: (message: string) => void;
  onSaved: (message: string) => void;
}) {
  const [role, setRole] = useState<UserSummary["role"]>(user.role);
  const [enabled, setEnabled] = useState(user.enabled);
  const [resetOpen, setResetOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setRole(user.role); setEnabled(user.enabled); }, [user.role, user.enabled]);

  async function saveUser() {
    setBusy(true); onError(""); onSaved("");
    try { await onUpdate(user, role, enabled); onSaved(`${user.username} updated.`); }
    catch (err) { onError(err instanceof Error ? err.message : "Unable to update user."); }
    finally { setBusy(false); }
  }

  async function resetPassword() {
    if (password.length < 10) { onError("Reset password must be at least 10 characters."); return; }
    setBusy(true); onError(""); onSaved("");
    try {
      await onResetPassword(user, password);
      setPassword(""); setResetOpen(false);
      onSaved(`${user.username}'s password was reset and their active sessions were signed out.`);
    } catch (err) { onError(err instanceof Error ? err.message : "Unable to reset password."); }
    finally { setBusy(false); }
  }

  async function removeUser() {
    if (!window.confirm(`Delete local user "${user.username}"?`)) return;
    setBusy(true); onError(""); onSaved("");
    try { await onDelete(user); onSaved(`${user.username} deleted.`); }
    catch (err) { onError(err instanceof Error ? err.message : "Unable to delete user."); }
    finally { setBusy(false); }
  }

  const isSelf = user.username.toLowerCase() === currentUsername.toLowerCase();
  return <div className={`user-admin-row ${!user.enabled ? "user-disabled" : ""}`}>
    <div className="user-admin-heading"><span><strong>{user.username}</strong><small>{user.enabled ? "Enabled" : "Disabled"} · last login {formatWhen(user.last_login_at)}</small></span><em>{user.recovery_configured ? "Recovery configured" : "No recovery code"}</em></div>
    <div className="user-admin-controls">
      <label><span>Role</span><select value={role} disabled={isSelf} title={isSelf ? "Another owner must change your role" : undefined} onChange={(event) => setRole(event.target.value as UserSummary["role"])}><option value="viewer">Viewer</option><option value="editor">Editor</option><option value="admin">Admin</option><option value="owner">Owner</option></select></label>
      <label className="check-row"><input type="checkbox" checked={enabled} disabled={isSelf} onChange={(event) => setEnabled(event.target.checked)} /><span>Enabled</span></label>
      <button className="secondary compact-button" type="button" disabled={busy} onClick={() => void saveUser()}>Save</button>
      <button className="secondary compact-button" type="button" disabled={busy || isSelf} title={isSelf ? "Use the Account tab to change your own password" : "Reset this user's password"} onClick={() => setResetOpen((value) => !value)}>Reset password</button>
      <button className="danger-button compact-button" type="button" disabled={busy || isSelf} onClick={() => void removeUser()}>Delete</button>
    </div>
    {resetOpen && <div className="user-reset-row"><input type="password" value={password} minLength={10} placeholder="New password" onChange={(event) => setPassword(event.target.value)} /><button className="primary compact-button" type="button" disabled={busy} onClick={() => void resetPassword()}>Set new password</button></div>}
  </div>;
}

export function SettingsModal({
  settings,
  account,
  permissions,
  users,
  extensions,
  registry,
  registryLoading,
  registryError,
  currentTheme,
  importedThemeCount,
  connections,
  widgetCount,
  appVersion,
  onClose,
  onSave,
  onChangePassword,
  onRegenerateRecoveryCode,
  onCreateUser,
  onUpdateUser,
  onResetUserPassword,
  onDeleteUser,
  onOpenAppearance,
  onOpenConnections,
  onAddWidget,
  onExportDashboard,
  onImportDashboard,
  onRemoveTheme,
  onImportExtension,
  onToggleExtension,
  onRemoveExtension,
  onRefreshRegistry,
  onInstallRegistryExtension,
}: {
  settings: DashboardSettings;
  account: AccountSummary | null;
  permissions: string[];
  users: UserSummary[];
  extensions: ExtensionDescriptor[];
  registry: ExtensionRegistryResponse | null;
  registryLoading: boolean;
  registryError: string;
  currentTheme: string;
  importedThemeCount: number;
  connections: ConnectionSummary[];
  widgetCount: number;
  appVersion: string;
  onClose: () => void;
  onSave: (settings: DashboardSettings) => Promise<void>;
  onChangePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  onRegenerateRecoveryCode: (currentPassword: string) => Promise<RecoveryCodeResult>;
  onCreateUser: (username: string, password: string, role: UserSummary["role"]) => Promise<void>;
  onUpdateUser: (user: UserSummary, role: UserSummary["role"], enabled: boolean) => Promise<void>;
  onResetUserPassword: (user: UserSummary, password: string) => Promise<void>;
  onDeleteUser: (user: UserSummary) => Promise<void>;
  onOpenAppearance: () => void;
  onOpenConnections: () => void;
  onAddWidget: () => void;
  onExportDashboard: () => void;
  onImportDashboard: () => void;
  onRemoveTheme: (themeId: string) => Promise<void>;
  onImportExtension: (file: File) => Promise<void>;
  onToggleExtension: (extension: ExtensionDescriptor) => Promise<void>;
  onRemoveExtension: (extension: ExtensionDescriptor) => Promise<void>;
  onRefreshRegistry: () => Promise<void>;
  onInstallRegistryExtension: (entry: ExtensionRegistryItem) => Promise<void>;
}) {
  const [tab, setTab] = useState<Tab>(() => permissions.includes("settings:manage") ? "general" : "account");
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
  const [newUsername, setNewUsername] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newUserRole, setNewUserRole] = useState<UserSummary["role"]>("viewer");
  const extensionInputRef = useRef<HTMLInputElement | null>(null);
  const tabs = ALL_TABS.filter((item) => !item.permission || permissions.includes(item.permission));
  useEffect(() => setForm(settings), [settings]);
  useEffect(() => {
    if (!tabs.some((item) => item.id === tab)) setTab("account");
  }, [permissions, tab]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (form.update_maintenance_days.length === 0) { setError("Choose at least one maintenance day."); return; }
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

  async function createLocalUser(event: FormEvent) {
    event.preventDefault(); setError(""); setSaved("");
    if (newUserPassword.length < 10) { setError("Password must be at least 10 characters."); return; }
    setBusy(true);
    try {
      await onCreateUser(newUsername, newUserPassword, newUserRole);
      setNewUsername(""); setNewUserPassword(""); setNewUserRole("viewer");
      setSaved("User created.");
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to create user."); }
    finally { setBusy(false); }
  }

  const openSub = (callback: () => void) => { onClose(); callback(); };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.currentTarget === event.target && onClose()}>
      <section className="modal settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <header className="modal-header"><div><p className="eyebrow">SETTINGS</p><h2 id="settings-title">Homelab Dashboard</h2><p className="modal-subhead">Account security, dashboard behavior, appearance, connections, monitoring, and extensions.</p></div><button className="icon-button" type="button" onClick={onClose} aria-label="Close"><X size={20} /></button></header>
        <div className="settings-layout">
          <nav className="settings-nav" aria-label="Settings sections">{tabs.map((item) => <button key={item.id} className={tab === item.id ? "active" : ""} type="button" onClick={() => { setTab(item.id); setError(""); setSaved(""); }}>{item.icon}<span>{item.label}</span></button>)}</nav>
          <div className="settings-content">
            {(tab === "general" || tab === "monitoring" || tab === "updates") && <form className="settings-form" onSubmit={save}>
              {tab === "general" ? <>
                <div className="settings-heading"><Monitor size={19} /><div><h3>General</h3><p>Basic dashboard identity and header behavior.</p></div></div>
                <label><span>Dashboard title</span><input value={form.dashboard_title} maxLength={80} onChange={(event) => setForm((current) => ({ ...current, dashboard_title: event.target.value }))} /></label>
                <label className="check-row"><input type="checkbox" checked={form.show_greeting} onChange={(event) => setForm((current) => ({ ...current, show_greeting: event.target.checked }))} /><span>Show personalized time-of-day greeting</span></label>
                <div className="settings-callout"><strong>Widgets</strong><span>{widgetCount} configured dashboard widget{widgetCount === 1 ? "" : "s"}.</span><button className="secondary" type="button" onClick={() => openSub(onAddWidget)}>Add widget</button></div>
              </> : tab === "monitoring" ? <>
                <div className="settings-heading"><Gauge size={19} /><div><h3>Monitoring</h3><p>Control live browser refresh and background update discovery.</p></div></div>
                <label><span>Service telemetry refresh</span><select value={form.telemetry_refresh_seconds} onChange={(event) => setForm((current) => ({ ...current, telemetry_refresh_seconds: Number(event.target.value) }))}>{[5,10,15,30,60,120].map((value) => <option key={value} value={value}>{value} seconds</option>)}</select></label>
                <label><span>Update-state refresh</span><select value={form.update_status_refresh_seconds} onChange={(event) => setForm((current) => ({ ...current, update_status_refresh_seconds: Number(event.target.value) }))}>{[5,10,15,30,60,120].map((value) => <option key={value} value={value}>{value} seconds</option>)}</select></label>
                <label><span>Active-job refresh</span><select value={form.active_refresh_seconds} onChange={(event) => setForm((current) => ({ ...current, active_refresh_seconds: Number(event.target.value) }))}>{[1,2,3,5,10].map((value) => <option key={value} value={value}>{value} second{value === 1 ? "" : "s"}</option>)}</select></label>
                <label><span>Automatic update discovery</span><select value={form.update_check_interval_hours} onChange={(event) => setForm((current) => ({ ...current, update_check_interval_hours: Number(event.target.value) }))}><option value={0}>Disabled</option>{[1,3,6,12,24,48,72].map((value) => <option key={value} value={value}>Every {value} hour{value === 1 ? "" : "s"}</option>)}</select><small>This is the heavier container-registry/TrueNAS update check. Cards continue reading cached state at the faster interval above.</small></label>
              </> : <>
                <div className="settings-heading"><RefreshCw size={19} /><div><h3>Update automation</h3><p>Optional maintenance windows with staged health verification and rollback where the provider safely supports it.</p></div></div>
                <label className="check-row"><input type="checkbox" checked={form.scheduled_updates_enabled} onChange={(event) => setForm((current) => ({ ...current, scheduled_updates_enabled: event.target.checked }))} /><span>Enable scheduled service updates</span></label>
                <div className="settings-callout"><strong>Host safeguards</strong><span>Host/platform updates such as TrueNAS remain excluded from unattended scheduling and still require explicit approval.</span></div>
                <div className="span-2">
                  <span className="field-label">Maintenance days</span>
                  <div className="maintenance-days">{["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].map((label, day) => <label className="check-row compact-check" key={label}><input type="checkbox" checked={form.update_maintenance_days.includes(day)} onChange={(event) => setForm((current) => ({ ...current, update_maintenance_days: event.target.checked ? [...current.update_maintenance_days, day].sort() : current.update_maintenance_days.filter((item) => item !== day) }))} /><span>{label}</span></label>)}</div>
                  <small>At least one day must remain selected. Times use the Dashboard container/server local clock.</small>
                </div>
                <label><span>Window starts</span><input type="time" value={form.update_maintenance_start} onChange={(event) => setForm((current) => ({ ...current, update_maintenance_start: event.target.value }))} /></label>
                <label><span>Window ends</span><input type="time" value={form.update_maintenance_end} onChange={(event) => setForm((current) => ({ ...current, update_maintenance_end: event.target.value }))} /><small>Overnight windows are supported.</small></label>
                <label><span>Default release delay</span><select value={form.update_release_delay_days} onChange={(event) => setForm((current) => ({ ...current, update_release_delay_days: Number(event.target.value) }))}>{[0,1,3,7,14,30].map((value) => <option key={value} value={value}>{value === 0 ? "No delay" : `${value} day${value === 1 ? "" : "s"}`}</option>)}</select><small>Dashboard waits this long after first detecting a specific version before scheduled installation. Cards may override it.</small></label>
                <label className="check-row"><input type="checkbox" checked={form.update_automatic_rollback} onChange={(event) => setForm((current) => ({ ...current, update_automatic_rollback: event.target.checked }))} /><span>Automatically roll back failed updates when supported</span></label>
                <label className="check-row"><input type="checkbox" checked={form.update_stop_on_failure} onChange={(event) => setForm((current) => ({ ...current, update_stop_on_failure: event.target.checked }))} /><span>Stop the maintenance queue after the first failed/rolled-back update</span></label>
                <div className="settings-callout"><strong>Sequential by design</strong><span>Scheduled services update one at a time. Dashboard verifies the service after each update before moving to the next item.</span></div>
              </>}
              {error && <div className="notice compact">{error}</div>}{saved && <div className="connection-success">{saved}</div>}
              <div className="settings-save"><button className="primary" type="submit" disabled={busy}><Save size={16} /> {busy ? "Saving…" : "Save settings"}</button></div>
            </form>}

            {tab === "account" && <div className="settings-panel">
              <div className="settings-heading"><ShieldCheck size={19} /><div><h3>Account & recovery</h3><p>Protect your local account and keep a recovery path that does not depend on email.</p></div></div>
              <div className="settings-summary-row"><span>Signed in as</span><strong>{account?.username ?? "Loading…"} · {account?.role ?? ""}</strong></div>
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

            {tab === "users" && <div className="settings-panel">
              <div className="settings-heading"><Users size={19} /><div><h3>Users & roles</h3><p>Create local accounts and control what each person can change.</p></div></div>
              <div className="role-guide">
                <div><strong>Owner</strong><span>Everything, including user management.</span></div>
                <div><strong>Admin</strong><span>Dashboard, credentials, connections, extensions and updates; no user management.</span></div>
                <div><strong>Editor</strong><span>Pages, widgets and basic service cards; cannot manage secrets or updates.</span></div>
                <div><strong>Viewer</strong><span>Read-only dashboard access.</span></div>
              </div>
              <form className="security-section" onSubmit={createLocalUser}>
                <div className="settings-heading"><UserPlus size={18} /><div><h3>Add local user</h3><p>The new user can create their own recovery code from Account settings after signing in.</p></div></div>
                <label><span>Username</span><input value={newUsername} minLength={3} maxLength={64} onChange={(event) => setNewUsername(event.target.value)} required /></label>
                <label><span>Initial password</span><input type="password" value={newUserPassword} minLength={10} onChange={(event) => setNewUserPassword(event.target.value)} required /></label>
                <label><span>Role</span><select value={newUserRole} onChange={(event) => setNewUserRole(event.target.value as UserSummary["role"])}><option value="viewer">Viewer</option><option value="editor">Editor</option><option value="admin">Admin</option><option value="owner">Owner</option></select></label>
                <div><button className="primary" type="submit" disabled={busy}><UserPlus size={16} /> Add user</button></div>
              </form>
              <div className="user-admin-list">
                {users.map((user) => <UserAdminRow key={user.id} user={user} currentUsername={account?.username ?? ""} onUpdate={onUpdateUser} onResetPassword={onResetUserPassword} onDelete={onDeleteUser} onError={setError} onSaved={setSaved} />)}
              </div>
              {error && <div className="notice compact">{error}</div>}{saved && <div className="connection-success">{saved}</div>}
            </div>}

            {tab === "dashboard" && <div className="settings-panel"><div className="settings-heading"><LayoutGrid size={19} /><div><h3>Dashboard builder</h3><p>Move your layout between installations or keep a reusable structure file. Exported layout files intentionally exclude passwords, API keys, and controller credentials.</p></div></div><div className="builder-action-grid"><button className="secondary" type="button" onClick={onExportDashboard}><Download size={16} /> Export layout</button><button className="secondary" type="button" onClick={onImportDashboard}><Upload size={16} /> Import layout</button></div><div className="settings-callout"><strong>Safe layout export</strong><span>Pages, categories, service card definitions, and widgets are included. Secrets and management links are not.</span></div></div>}

            {tab === "appearance" && <div className="settings-panel"><div className="settings-heading"><Palette size={19} /><div><h3>Appearance</h3><p>Theme selection, visual theme editing, and community theme packages.</p></div></div><div className="settings-summary-row"><span>Current theme</span><strong>{currentTheme}</strong></div><div className="settings-summary-row"><span>Imported themes</span><strong>{importedThemeCount}</strong></div><button className="primary" type="button" onClick={() => openSub(onOpenAppearance)}>Manage appearance</button></div>}

            {tab === "connections" && <div className="settings-panel"><div className="settings-heading"><Cable size={19} /><div><h3>Connections</h3><p>Reusable controller credentials for TrueNAS and future management providers.</p></div></div>{connections.length ? <div className="settings-list">{connections.map((item) => <div key={item.id}><span><strong>{item.name}</strong><small>{item.type} · used by {item.used_by}</small></span></div>)}</div> : <div className="settings-empty">No management connections configured.</div>}<button className="primary" type="button" onClick={() => openSub(onOpenConnections)}>Manage connections</button></div>}

            {tab === "extensions" && <div className="settings-panel">
              <div className="settings-heading"><Puzzle size={19} /><div><h3>Extension Manager</h3><p>Browse the registry, install checksum-verified data extensions, and manage installed page-template and service-catalog packs.</p></div></div>
              <div className="builder-action-grid">
                <button className="primary" type="button" onClick={() => extensionInputRef.current?.click()}><Upload size={16} /> Import file</button>
                <button className="secondary" type="button" disabled={registryLoading} onClick={() => void onRefreshRegistry().catch(() => undefined)}><RefreshCw size={16} className={registryLoading ? "spin" : ""} /> {registryLoading ? "Checking…" : "Check registry"}</button>
                <input ref={extensionInputRef} className="visually-hidden" type="file" accept="application/json,.json" onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (!file) return; setError(""); void onImportExtension(file).catch((err) => setError(err instanceof Error ? err.message : "Unable to import extension.")); }} />
              </div>
              <div className="settings-callout"><strong>Safe extension boundary</strong><span>Registry packages are still data-only. Registry installs are checksum-verified and permission declarations must match exactly; packages still cannot execute code, access Docker, read credentials, make arbitrary network requests, or access the host filesystem.</span></div>
              {error && <div className="notice compact">{error}</div>}
              {registryError && <div className="notice compact">Registry unavailable: {registryError}. Manual JSON import remains available.</div>}
              {registry && <div className="registry-section">
                <div className="registry-heading"><span><strong>{registry.registry_name}</strong><small>{registry.description}</small></span><em>Checked {formatWhen(registry.checked_at)}</em></div>
                <div className="registry-grid">{registry.entries.map((entry) => {
                  const trustLabel = entry.trust === "official" ? "Official" : entry.trust === "verified_community" ? "Verified Community" : "Community";
                  const action = entry.update_available ? "Update" : entry.installed_version ? "Installed" : "Install";
                  return <div className={`registry-card ${!entry.compatible ? "registry-incompatible" : ""}`} key={entry.id}>
                    <div className="registry-card-top"><span><strong>{entry.name}</strong><small>{entry.description}</small></span><span className={`trust-badge trust-${entry.trust}`}>{trustLabel}</span></div>
                    <div className="registry-meta">{entry.author} · v{entry.version}{entry.installed_version ? ` · installed v${entry.installed_version}` : ""}</div>
                    <small>Capabilities: {entry.capabilities.join(", ") || "none"}</small>
                    <small>Permissions: {entry.permissions.join(", ") || "none"}</small>
                    {!entry.compatible && <small className="registry-warning">{entry.compatibility_message}</small>}
                    {entry.update_available && <small className="registry-update">Update available: {entry.installed_version} → {entry.version}</small>}
                    <button className={entry.update_available ? "primary compact-button" : "secondary compact-button"} type="button" disabled={!entry.compatible || (!!entry.installed_version && !entry.update_available)} onClick={() => void onInstallRegistryExtension(entry).catch((err) => setError(err instanceof Error ? err.message : "Unable to install extension."))}>{action}</button>
                  </div>;
                })}</div>
              </div>}
              <div className="extension-subheading"><strong>Installed extensions</strong><small>Built-in modules, themes, and installed data packs.</small></div>
              <div className="extension-list">{extensions.map((extension) => {
                const registryEntry = registry?.entries.find((entry) => entry.id === extension.id);
                return <div className={`extension-row ${!extension.enabled ? "extension-disabled" : ""}`} key={extension.id}>
                  <div className="extension-mark"><Puzzle size={17} /></div>
                  <span><strong>{extension.name}</strong><small>{extension.description}</small><em>{extension.author} · v{extension.version} · {extension.source === "built_in" ? "Built in" : "Imported"}{extension.active && extension.type === "theme" ? " · Active" : ""}{extension.source === "imported" && extension.type !== "theme" ? extension.enabled ? " · Enabled" : " · Disabled" : ""}</em>
                    {registryEntry?.update_available && <small className="registry-update">Registry update available: v{registryEntry.version}</small>}
                    {extension.capabilities?.length > 0 && <small>Capabilities: {extension.capabilities.join(", ")}</small>}
                    {extension.permissions?.length > 0 && <small>Permissions: {extension.permissions.join(", ")}</small>}
                  </span>
                  {registryEntry?.update_available && <button className="primary compact-button" type="button" onClick={() => void onInstallRegistryExtension(registryEntry).catch((err) => setError(err instanceof Error ? err.message : "Unable to update extension."))}>Update</button>}
                  {extension.source === "imported" && extension.type !== "theme" && <button className="secondary compact-button" type="button" onClick={() => void onToggleExtension(extension).catch((err) => setError(err instanceof Error ? err.message : "Unable to change extension state."))}>{extension.enabled ? "Disable" : "Enable"}</button>}
                  {extension.removable && (extension.type === "theme"
                    ? <button className="danger-button compact-button" type="button" onClick={() => void onRemoveTheme(extension.id.replace(/^theme\./, ""))}>Remove</button>
                    : <button className="danger-button compact-button" type="button" onClick={() => void onRemoveExtension(extension).catch((err) => setError(err instanceof Error ? err.message : "Unable to remove extension."))}>Remove</button>)}
                </div>;
              })}</div>
            </div>}

            {tab === "about" && <div className="settings-panel"><div className="settings-heading"><Info size={19} /><div><h3>About</h3><p>Version and architecture summary.</p></div></div><div className="about-card"><strong>Homelab Dashboard v{appVersion}</strong><span>Self-hosted dashboard, service monitor, update manager, and extensible homelab control center.</span><small>v0.21 adds opt-in scheduled maintenance, post-update verification, capability-aware rollback, and post-reboot service recovery while preserving the platform-neutral update framework and RBAC security model.</small></div></div>}
          </div>
        </div>
      </section>
    </div>
  );
}
