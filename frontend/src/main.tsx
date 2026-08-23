import React, { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ChevronDown,
  ChevronRight,
  Cable,
  Download,
  ArrowUpCircle,
  History,
  ExternalLink,
  GripVertical,
  LayoutGrid,
  Link as LinkIcon,
  LogOut,
  Palette,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Server,
  Settings,
  Star,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import "./styles.css";
import { CATALOG_BY_TYPE, CATALOG_CATEGORIES, SERVICE_CATALOG, catalogSearchText, urlPlaceholder, type CatalogEntry } from "./serviceCatalog";
import { BUILTIN_THEMES, BUILTIN_THEME_BY_ID, THEME_TEMPLATE, applyTheme, resolveTheme, type ThemePackage } from "./themes";
import { WidgetCard, WidgetModal, type DashboardWidget } from "./widgets";
import { SettingsModal, type DashboardSettings, type ExtensionDescriptor } from "./settings";

type AuthStatus = {
  setup_required: boolean;
  authenticated: boolean;
  username?: string | null;
  csrf_token?: string | null;
};

type Service = {
  id: number;
  name: string;
  type: string;
  url: string;
  category: string;
  page_id: number;
  icon?: string | null;
  enabled: boolean;
  status_check: boolean;
  favorite: boolean;
  card_size: "compact" | "standard" | "wide";
  sort_order: number;
  created_at: string;
  updated_at: string;
  has_api_key: boolean;
  has_auth_username: boolean;
  has_auth_credentials: boolean;
  management_provider: "none" | "docker_compose" | "truenas_app";
  management_target?: string | null;
  management_controller_service_id?: number | null;
  management_connection_id?: number | null;
};

type ServiceForm = {
  name: string;
  type: string;
  url: string;
  category: string;
  page_id: number;
  icon: string;
  enabled: boolean;
  status_check: boolean;
  favorite: boolean;
  card_size: "compact" | "standard" | "wide";
  sort_order: number;
  api_key: string;
  clear_api_key: boolean;
  auth_username: string;
  auth_password: string;
  clear_auth_credentials: boolean;
  management_provider: "none" | "docker_compose" | "truenas_app";
  management_target: string;
  management_controller_service_id: number | null;
  management_connection_id: number | null;
};

type DashboardPage = {
  id: number;
  name: string;
  sort_order: number;
  is_default: boolean;
  created_at: string;
  updated_at: string;
};

type CategoryLayout = {
  page_id: number;
  name: string;
  sort_order: number;
  collapsed: boolean;
  icon?: string | null;
};

type AppearanceSettings = {
  theme_id: string;
  custom_themes: ThemePackage[];
};

type ServiceActivity = {
  operation: string;
  title: string;
  progress?: number | null;
  transferred_bytes?: number | null;
  total_bytes?: number | null;
  speed_bps?: number | null;
  eta_seconds?: number | null;
  status?: string | null;
  detail?: string | null;
};

type ServiceInsight = {
  id: number;
  kind: string;
  state: "ok" | "setup" | "unavailable" | "none";
  summary?: string | null;
  secondary?: string | null;
  items: string[];
  activities: ServiceActivity[];
  capabilities: string[];
};

type ServiceUpdateState = {
  service_id: number;
  provider: "none" | "docker_compose" | "truenas_app";
  target?: string | null;
  state: "unknown" | "checking" | "current" | "available" | "unavailable" | "unconfigured";
  current_version?: string | null;
  latest_version?: string | null;
  checked_at?: string | null;
  message?: string | null;
  can_update: boolean;
};

type UpdateJob = {
  id: string;
  kind: "check" | "update" | "batch";
  service_id?: number | null;
  active_service_id?: number | null;
  provider?: string | null;
  target?: string | null;
  state: "queued" | "running" | "success" | "failed" | "rolled_back";
  progress: number;
  message: string;
  current_version?: string | null;
  latest_version?: string | null;
  detail?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
};

type ManagementConnection = {
  id: number;
  name: string;
  type: "truenas";
  url: string;
  has_api_key: boolean;
  has_auth_username: boolean;
  used_by: number;
  created_at: string;
  updated_at: string;
};

type ConnectionTestResult = {
  ok: boolean;
  message: string;
};

type ManagedResource = {
  id: string;
  name: string;
  provider: "docker_compose" | "truenas_app";
  current_version?: string | null;
  latest_version?: string | null;
  update_available?: boolean | null;
  state?: string | null;
  detail?: string | null;
};

type ServiceStatus = {
  id: number;
  state: "online" | "degraded" | "offline" | "disabled" | "unchecked";
  http_status?: number | null;
  latency_ms?: number | null;
  checked_at: string;
  detail?: string | null;
};

const APP_VERSION = "0.14.0";

const EMPTY_SERVICE: ServiceForm = {
  name: "",
  type: "link",
  url: "https://",
  category: "General",
  page_id: 1,
  icon: "",
  enabled: true,
  status_check: true,
  favorite: false,
  card_size: "standard",
  sort_order: 0,
  api_key: "",
  clear_api_key: false,
  auth_username: "",
  auth_password: "",
  clear_auth_credentials: false,
  management_provider: "none",
  management_target: "",
  management_controller_service_id: null,
  management_connection_id: null,
};

const API_KEY_INTEGRATIONS: Record<string, { label: string; hint: string }> = {
  jellyfin: { label: "Jellyfin API key", hint: "enables stream details" },
  sonarr: { label: "Sonarr API key", hint: "enables queue, progress, health, and upcoming activity" },
  radarr: { label: "Radarr API key", hint: "enables queue, progress, health, and upcoming activity" },
  prowlarr: { label: "Prowlarr API key", hint: "enables indexer and health details" },
  sabnzbd: { label: "SABnzbd API key", hint: "enables queue, speed, ETA, and progress" },
  immich: { label: "Immich API key", hint: "enables server and storage statistics" },
  truenas: { label: "TrueNAS API key", hint: "enables pool health, storage, and scrub/resilver progress" },
};

const TYPE_LABELS = Object.fromEntries(SERVICE_CATALOG.map((entry) => [entry.type, entry.name])) as Record<string, string>;

async function api<T>(path: string, options: RequestInit = {}, csrfToken?: string | null): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (csrfToken) headers.set("X-CSRF-Token", csrfToken);

  const response = await fetch(path, {
    ...options,
    headers,
    credentials: "same-origin",
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (data?.detail) message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      // Ignore a non-JSON error body.
    }
    throw new Error(message);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function greetingForHour(hour: number): string {
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function formatBytes(value?: number | null): string | null {
  if (value == null || !Number.isFinite(value)) return null;
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let size = Math.max(0, value);
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit += 1; }
  const digits = size >= 100 ? 0 : 1;
  return `${size.toFixed(digits)} ${units[unit]}`;
}

function formatEta(value?: number | null): string | null {
  if (value == null || !Number.isFinite(value)) return null;
  const seconds = Math.max(0, Math.round(value));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  if (hours < 24) return remainder ? `${hours}h ${remainder}m` : `${hours}h`;
  const days = Math.floor(hours / 24);
  const hourRemainder = hours % 24;
  return hourRemainder ? `${days}d ${hourRemainder}h` : `${days}d`;
}

function ActivityProgress({ activity, additional }: { activity: ServiceActivity; additional: number }) {
  const progress = activity.progress == null ? null : Math.max(0, Math.min(100, activity.progress));
  const transferred = formatBytes(activity.transferred_bytes);
  const total = formatBytes(activity.total_bytes);
  const speed = formatBytes(activity.speed_bps);
  const eta = formatEta(activity.eta_seconds);
  const operation = activity.operation.replace(/[-_]/g, " ");
  const details = [
    transferred && total ? `${transferred} / ${total}` : total ? total : null,
    speed ? `↓ ${speed}/s` : null,
    eta ? `${eta} left` : null,
  ].filter(Boolean) as string[];
  return (
    <div className="activity-block">
      <div className="activity-heading">
        <span className="activity-operation">{operation}</span>
        <strong title={activity.title}>{activity.title}</strong>
        {progress != null && <span className="activity-percent">{Math.round(progress)}%</span>}
      </div>
      <div className={`activity-track ${progress == null ? "indeterminate" : ""}`} aria-label={progress == null ? `${activity.title} in progress` : `${activity.title} ${Math.round(progress)} percent`}>
        <span className="activity-bar" style={progress == null ? undefined : { width: `${progress}%` }} />
      </div>
      <div className="activity-meta">
        {activity.status && <span>{activity.status}</span>}
        {details.map((detail) => <span key={detail}>{detail}</span>)}
        {additional > 0 && <span>+{additional} more</span>}
      </div>
    </div>
  );
}

function AuthScreen({ status, onAuthenticated }: { status: AuthStatus; onAuthenticated: (auth: AuthStatus) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const isSetup = status.setup_required;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (isSetup && password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const result = await api<AuthStatus>(isSetup ? "/api/auth/setup" : "/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      onAuthenticated(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to sign in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <div className="auth-mark"><Server size={25} /></div>
        <p className="eyebrow">SELF-HOSTED CONTROL CENTER</p>
        <h1>{isSetup ? "Create your admin account" : "Welcome back"}</h1>
        <p className="subhead">
          {isSetup
            ? "This account protects your dashboard and service configuration."
            : "Sign in to open your homelab dashboard."}
        </p>

        <form className="form-stack" onSubmit={submit}>
          <label>
            <span>Username</span>
            <input value={username} onChange={(event) => setUsername(event.target.value)} minLength={3} autoComplete="username" required autoFocus />
          </label>
          <label>
            <span>Password</span>
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={10} autoComplete={isSetup ? "new-password" : "current-password"} required />
          </label>
          {isSetup && (
            <label>
              <span>Confirm password</span>
              <input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} minLength={10} autoComplete="new-password" required />
            </label>
          )}
          {error && <div className="notice compact">{error}</div>}
          <button className="primary wide" disabled={busy} type="submit">
            {busy ? "Working…" : isSetup ? "Create dashboard" : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}

function CatalogLogo({ entry, fallback }: { entry?: CatalogEntry | null; fallback?: React.ReactNode }) {
  const [format, setFormat] = useState<"svg" | "png">("svg");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFormat("svg");
    setFailed(false);
  }, [entry?.icon]);

  if (!entry?.icon || failed) return <>{fallback ?? <LinkIcon size={27} />}</>;
  return (
    <img
      className="service-logo"
      src={`/icons/${entry.icon}.${format}`}
      alt=""
      onError={() => format === "svg" ? setFormat("png") : setFailed(true)}
    />
  );
}

function ServiceCatalogModal({ onClose, onSelect }: { onClose: () => void; onSelect: (entry: CatalogEntry) => void }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");

  const entries = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return SERVICE_CATALOG.filter((entry) => {
      if (category !== "All" && entry.category !== category) return false;
      return !needle || catalogSearchText(entry).includes(needle);
    });
  }, [query, category]);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.currentTarget === event.target && onClose()}>
      <section className="modal catalog-modal" role="dialog" aria-modal="true" aria-labelledby="catalog-title">
        <header className="modal-header">
          <div>
            <p className="eyebrow">SERVICE CATALOG</p>
            <h2 id="catalog-title">What do you want to add?</h2>
            <p className="modal-subhead">Choose a common self-hosted service or start with a custom card.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close"><X size={20} /></button>
        </header>

        <div className="catalog-search">
          <Search size={18} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search Plex, Proxmox, Home Assistant, monitoring…" autoFocus />
          <span>{entries.length}</span>
        </div>

        <div className="catalog-categories" aria-label="Service categories">
          {CATALOG_CATEGORIES.map((item) => (
            <button key={item} className={category === item ? "active" : ""} type="button" onClick={() => setCategory(item)}>{item}</button>
          ))}
        </div>

        <div className="catalog-grid">
          {entries.map((entry) => (
            <button className="catalog-card" type="button" key={entry.type} onClick={() => onSelect(entry)}>
              <div className="catalog-icon"><CatalogLogo entry={entry} /></div>
              <div className="catalog-copy">
                <strong>{entry.name}</strong>
                <span>{entry.description}</span>
                <div className="catalog-meta">
                  <small>{entry.category}</small>
                  {entry.defaultPort && <small>Default :{entry.defaultPort}</small>}
                  {entry.integration === "jellyfin" && <small className="integration-tag">Live API integration</small>}
                  {entry.integration === "api" && <small className="integration-tag">Live API integration</small>}
                  {entry.integration === "credentials" && <small className="integration-tag">Live credential integration</small>}
                  {entry.integration === "docker" && <small className="integration-tag">Docker insight</small>}
                </div>
              </div>
            </button>
          ))}
        </div>

        {entries.length === 0 && <div className="catalog-empty">No catalog matches. Try another term or choose the Custom category.</div>}
      </section>
    </div>
  );
}

function ServiceModal({
  service,
  template,
  onClose,
  onSaved,
  onDeleted,
  csrfToken,
  pages,
  defaultPageId,
  allServices,
  connections,
}: {
  service: Service | null;
  template?: CatalogEntry | null;
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
  csrfToken?: string | null;
  pages: DashboardPage[];
  defaultPageId: number;
  allServices: Service[];
  connections: ManagementConnection[];
}) {
  const initialTemplate = template ?? (service ? CATALOG_BY_TYPE[service.type] : null);
  const [form, setForm] = useState<ServiceForm>(service ? {
    name: service.name,
    type: service.type,
    url: service.url,
    category: service.category,
    page_id: service.page_id,
    icon: service.icon ?? "",
    enabled: service.enabled,
    status_check: service.status_check,
    favorite: service.favorite,
    card_size: service.card_size,
    sort_order: service.sort_order,
    api_key: "",
    clear_api_key: false,
    auth_username: "",
    auth_password: "",
    clear_auth_credentials: false,
    management_provider: service.management_provider ?? "none",
    management_target: service.management_target ?? "",
    management_controller_service_id: service.management_controller_service_id ?? null,
    management_connection_id: service.management_connection_id ?? null,
  } : initialTemplate ? {
    name: ["link", "other"].includes(initialTemplate.type) ? "" : initialTemplate.name,
    type: initialTemplate.type,
    url: `${initialTemplate.defaultScheme ?? "http"}://`,
    category: initialTemplate.category === "Custom" ? "General" : initialTemplate.category,
    page_id: defaultPageId,
    icon: "",
    enabled: true,
    status_check: true,
    favorite: false,
    card_size: "standard",
    sort_order: 0,
    api_key: "",
    clear_api_key: false,
    auth_username: "",
    auth_password: "",
    clear_auth_credentials: false,
    management_provider: "none",
    management_target: "",
    management_controller_service_id: null,
    management_connection_id: null,
  } : { ...EMPTY_SERVICE, page_id: defaultPageId });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [managedResources, setManagedResources] = useState<ManagedResource[]>([]);
  const [resourceLoading, setResourceLoading] = useState(false);
  const [resourceError, setResourceError] = useState("");
  const selectedCatalogEntry = CATALOG_BY_TYPE[form.type];
  // allServices is retained for compatibility with existing editor behavior; management controllers now use Connections.
  void allServices;

  useEffect(() => {
    let cancelled = false;
    async function loadManagedResources() {
      if (form.management_provider === "none") { setManagedResources([]); setResourceError(""); return; }
      if (form.management_provider === "truenas_app" && !form.management_connection_id) { setManagedResources([]); setResourceError(""); return; }
      setResourceLoading(true);
      setResourceError("");
      try {
        const path = form.management_provider === "docker_compose"
          ? "/api/management/docker/resources"
          : `/api/management/truenas/connections/${form.management_connection_id}/apps`;
        const resources = await api<ManagedResource[]>(path);
        if (!cancelled) setManagedResources(resources);
      } catch (err) {
        if (!cancelled) { setManagedResources([]); setResourceError(err instanceof Error ? err.message : "Unable to discover managed services."); }
      } finally {
        if (!cancelled) setResourceLoading(false);
      }
    }
    void loadManagedResources();
    return () => { cancelled = true; };
  }, [form.management_provider, form.management_connection_id]);

  function setField<K extends keyof ServiceForm>(key: K, value: ServiceForm[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function changeType(value: string) {
    const entry = CATALOG_BY_TYPE[value];
    setForm((current) => ({
      ...current,
      type: value,
      category: entry && (!service || current.category === (CATALOG_BY_TYPE[current.type]?.category ?? current.category))
        ? (entry.category === "Custom" ? "General" : entry.category)
        : current.category,
    }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = {
        ...form,
        icon: form.icon.trim() || null,
        api_key: form.api_key.trim() || null,
        auth_username: form.auth_username.trim() || null,
        auth_password: form.auth_password || null,
      };
      await api<Service>(service ? `/api/services/${service.id}` : "/api/services", {
        method: service ? "PUT" : "POST",
        body: JSON.stringify(payload),
      }, csrfToken);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save service.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!service || !window.confirm(`Remove ${service.name} from the dashboard?`)) return;
    setBusy(true);
    setError("");
    try {
      await api<void>(`/api/services/${service.id}`, { method: "DELETE" }, csrfToken);
      onDeleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to remove service.");
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.currentTarget === event.target && onClose()}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="service-modal-title">
        <header className="modal-header">
          <div>
            <p className="eyebrow">SERVICE CONFIGURATION</p>
            <h2 id="service-modal-title">{service ? `Edit ${service.name}` : `Add ${initialTemplate?.name ?? "a service"}`}</h2>
            {selectedCatalogEntry && <p className="modal-subhead">{selectedCatalogEntry.description}</p>}
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close"><X size={20} /></button>
        </header>

        <form className="form-grid" onSubmit={save}>
          <label>
            <span>Name</span>
            <input value={form.name} onChange={(event) => setField("name", event.target.value)} placeholder={selectedCatalogEntry?.name ?? "My service"} required autoFocus />
          </label>
          <label>
            <span>Service template</span>
            <select value={form.type} onChange={(event) => changeType(event.target.value)}>
              {SERVICE_CATALOG.map((entry) => <option key={entry.type} value={entry.type}>{entry.name}</option>)}
            </select>
          </label>
          <label className="span-2">
            <span>URL</span>
            <input value={form.url} onChange={(event) => setField("url", event.target.value)} type="url" placeholder={selectedCatalogEntry ? urlPlaceholder(selectedCatalogEntry) : "https://service.example.com"} required />
            {selectedCatalogEntry?.defaultPort && <small>Common default web port: {selectedCatalogEntry.defaultPort}. Your installation may use a different port.</small>}
          </label>
          <label>
            <span>Dashboard page</span>
            <select value={form.page_id} onChange={(event) => setField("page_id", Number(event.target.value))}>
              {pages.map((page) => <option key={page.id} value={page.id}>{page.name}</option>)}
            </select>
          </label>
          <label>
            <span>Category</span>
            <input value={form.category} onChange={(event) => setField("category", event.target.value)} placeholder={selectedCatalogEntry?.category ?? "General"} required />
          </label>
          {selectedCatalogEntry?.icon ? (
            <div className="brand-preview-field">
              <span>Service logo</span>
              <div className="brand-preview"><CatalogLogo entry={selectedCatalogEntry} /><span>Bundled {selectedCatalogEntry.name} logo</span></div>
            </div>
          ) : (
            <label>
              <span>Custom icon / emoji <small>optional</small></span>
              <input value={form.icon} onChange={(event) => setField("icon", event.target.value)} placeholder="🔗" />
            </label>
          )}
          {API_KEY_INTEGRATIONS[form.type] && (
            <>
              <label className="span-2">
                <span>{API_KEY_INTEGRATIONS[form.type].label} <small>optional, {API_KEY_INTEGRATIONS[form.type].hint}</small></span>
                <input
                  type="password"
                  value={form.api_key}
                  onChange={(event) => setField("api_key", event.target.value)}
                  placeholder={service?.has_api_key ? "API key saved — leave blank to keep it" : `Paste ${API_KEY_INTEGRATIONS[form.type].label}`}
                  autoComplete="off"
                />
                <small>The key is encrypted before it is stored and is only sent server-side to this configured service.</small>
              </label>
              {service?.has_api_key && (
                <label className="check-row span-2">
                  <input type="checkbox" checked={form.clear_api_key} onChange={(event) => setField("clear_api_key", event.target.checked)} />
                  <span>Remove the saved API key</span>
                </label>
              )}
            </>
          )}
          {form.type === "truenas" && (
            <>
              <label className="span-2">
                <span>TrueNAS API-key username <small>optional on current releases, recommended for future compatibility</small></span>
                <input
                  value={form.auth_username}
                  onChange={(event) => setField("auth_username", event.target.value)}
                  placeholder={service?.has_auth_username ? "Username saved — leave blank to keep it" : "API key owner username"}
                  autoComplete="off"
                />
                <small>TrueNAS 25.04+ management uses the encrypted JSON-RPC WebSocket API. Use an HTTPS TrueNAS URL.</small>
              </label>
              {service?.has_auth_username && (
                <label className="check-row span-2">
                  <input type="checkbox" checked={form.clear_auth_credentials} onChange={(event) => setField("clear_auth_credentials", event.target.checked)} />
                  <span>Remove the saved TrueNAS API username</span>
                </label>
              )}
            </>
          )}
          {form.type === "qbittorrent" && (
            <>
              <label>
                <span>qBittorrent WebUI username</span>
                <input
                  value={form.auth_username}
                  onChange={(event) => setField("auth_username", event.target.value)}
                  placeholder={service?.has_auth_credentials ? "Credentials saved — leave blank to keep" : "WebUI username"}
                  autoComplete="off"
                />
              </label>
              <label>
                <span>qBittorrent WebUI password</span>
                <input
                  type="password"
                  value={form.auth_password}
                  onChange={(event) => setField("auth_password", event.target.value)}
                  placeholder={service?.has_auth_credentials ? "Credentials saved — leave blank to keep" : "WebUI password"}
                  autoComplete="off"
                />
              </label>
              <small className="span-2 credential-note">Credentials are encrypted at rest and used only by the backend to read qBittorrent queue and transfer status.</small>
              {service?.has_auth_credentials && (
                <label className="check-row span-2">
                  <input type="checkbox" checked={form.clear_auth_credentials} onChange={(event) => setField("clear_auth_credentials", event.target.checked)} />
                  <span>Remove the saved qBittorrent credentials</span>
                </label>
              )}
            </>
          )}
          <div className="span-2 management-section">
            <div className="management-heading">
              <div><strong>Update management</strong><small> Optional · lets this card update the service without opening its native UI.</small></div>
            </div>
            <div className="form-grid management-grid">
              <label>
                <span>Managed by</span>
                <select value={form.management_provider} onChange={(event) => {
                  const provider = event.target.value as ServiceForm["management_provider"];
                  setForm((current) => ({
                    ...current,
                    management_provider: provider,
                    management_target: "",
                    management_controller_service_id: null,
                    management_connection_id: provider === "truenas_app" ? current.management_connection_id : null,
                  }));
                }}>
                  <option value="none">Not managed / detect only</option>
                  <option value="docker_compose">Docker Compose / Dockge</option>
                  <option value="truenas_app">TrueNAS App</option>
                </select>
              </label>
              {form.management_provider === "truenas_app" && (
                <label>
                  <span>TrueNAS connection</span>
                  <select value={form.management_connection_id ?? ""} onChange={(event) => setForm((current) => ({ ...current, management_connection_id: event.target.value ? Number(event.target.value) : null, management_controller_service_id: null, management_target: "" }))}>
                    <option value="">Choose a TrueNAS connection…</option>
                    {connections.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                  {connections.length === 0 && <small className="field-error">Add a TrueNAS connection from Connections first.</small>}
                </label>
              )}
              {form.management_provider !== "none" && (
                <label className={form.management_provider === "docker_compose" ? "span-2" : "span-2"}>
                  <span>{form.management_provider === "docker_compose" ? "Compose service" : "TrueNAS app"}</span>
                  <select value={form.management_target} onChange={(event) => setField("management_target", event.target.value)} disabled={resourceLoading || (form.management_provider === "truenas_app" && !form.management_connection_id)}>
                    <option value="">{resourceLoading ? "Discovering…" : "Choose managed service…"}</option>
                    {managedResources.map((resource) => <option key={resource.id} value={resource.id}>{resource.name}{resource.current_version ? ` · ${resource.current_version}` : ""}</option>)}
                  </select>
                  {resourceError && <small className="field-error">{resourceError}</small>}
                  {!resourceError && form.management_provider === "docker_compose" && <small>Requires the optional restricted update-agent sidecar. Only Compose services inside its allow-listed stacks directory are shown.</small>}
                  {!resourceError && form.management_provider === "truenas_app" && <small>Homelab Dashboard asks TrueNAS to perform the app upgrade through its own API.</small>}
                </label>
              )}
            </div>
          </div>

          <label>
            <span>Card size</span>
            <select value={form.card_size} onChange={(event) => setField("card_size", event.target.value as ServiceForm["card_size"])}>
              <option value="compact">Compact</option>
              <option value="standard">Standard</option>
              <option value="wide">Wide</option>
            </select>
            <small>Wide cards have extra room for rich integration details.</small>
          </label>
          <label className="check-row favorite-form-row">
            <input type="checkbox" checked={form.favorite} onChange={(event) => setField("favorite", event.target.checked)} />
            <span>Pin this service to the top of its category</span>
          </label>
          <label className="check-row span-2">
            <input type="checkbox" checked={form.enabled} onChange={(event) => setField("enabled", event.target.checked)} />
            <span>Show this service on the dashboard</span>
          </label>
          <label className="check-row span-2">
            <input type="checkbox" checked={form.status_check} onChange={(event) => setField("status_check", event.target.checked)} />
            <span>Monitor this service and show live status</span>
          </label>

          {error && <div className="notice compact span-2">{error}</div>}

          <div className="modal-actions span-2">
            {service && (
              <button className="danger-button" disabled={busy} type="button" onClick={remove}>
                <Trash2 size={17} /> Remove
              </button>
            )}
            <div className="action-spacer" />
            <button className="secondary" disabled={busy} type="button" onClick={onClose}>Cancel</button>
            <button className="primary" disabled={busy} type="submit">{busy ? "Saving…" : "Save service"}</button>
          </div>
        </form>
      </section>
    </div>
  );
}

function PageModal({
  page,
  itemCount,
  onClose,
  onSaved,
  onDeleted,
  csrfToken,
}: {
  page: DashboardPage | null;
  itemCount: number;
  onClose: () => void;
  onSaved: (page: DashboardPage) => void;
  onDeleted: () => void;
  csrfToken?: string | null;
}) {
  const [name, setName] = useState(page?.name ?? "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const saved = await api<DashboardPage>(page ? `/api/pages/${page.id}` : "/api/pages", {
        method: page ? "PUT" : "POST",
        body: JSON.stringify({ name }),
      }, csrfToken);
      onSaved(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save page.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!page || page.is_default) return;
    if (!window.confirm(`Delete the ${page.name} page?`)) return;
    setBusy(true);
    setError("");
    try {
      await api<void>(`/api/pages/${page.id}`, { method: "DELETE" }, csrfToken);
      onDeleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete page.");
      setBusy(false);
    }
  }

  async function clonePage() {
    if (!page) return;
    const cloneName = window.prompt("Name for the cloned page", `${page.name} Copy`)?.trim();
    if (!cloneName) return;
    setBusy(true);
    setError("");
    try {
      const cloned = await api<DashboardPage>(`/api/pages/${page.id}/clone`, { method: "POST", body: JSON.stringify({ name: cloneName }) }, csrfToken);
      onSaved(cloned);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to clone page.");
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.currentTarget === event.target && onClose()}>
      <section className="modal page-modal" role="dialog" aria-modal="true" aria-labelledby="page-modal-title">
        <header className="modal-header">
          <div>
            <p className="eyebrow">DASHBOARD PAGE</p>
            <h2 id="page-modal-title">{page ? `Edit ${page.name}` : "Add dashboard page"}</h2>
            <p className="modal-subhead">Pages let you separate media, infrastructure, monitoring, home automation, or any other group of services.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close"><X size={20} /></button>
        </header>
        <form className="page-form" onSubmit={save}>
          <label>
            <span>Page name</span>
            <input value={name} onChange={(event) => setName(event.target.value)} maxLength={60} placeholder="Infrastructure" required autoFocus />
          </label>
          {page?.is_default && <small>The default Home page can be renamed but cannot be deleted.</small>}
          {page && !page.is_default && itemCount > 0 && <small>Move or remove the {itemCount} item{itemCount === 1 ? "" : "s"} on this page before deleting it.</small>}
          {error && <div className="notice compact">{error}</div>}
          <div className="modal-actions">
            {page && <button className="secondary" disabled={busy} type="button" onClick={() => void clonePage()}><LayoutGrid size={16} /> Clone page</button>}
            {page && !page.is_default && (
              <button className="danger-button" disabled={busy || itemCount > 0} type="button" onClick={() => void remove()}>
                <Trash2 size={16} /> Delete page
              </button>
            )}
            <div className="action-spacer" />
            <button className="secondary" disabled={busy} type="button" onClick={onClose}>Cancel</button>
            <button className="primary" disabled={busy} type="submit">{busy ? "Saving…" : page ? "Save page" : "Add page"}</button>
          </div>
        </form>
      </section>
    </div>
  );
}

const CATEGORY_ICON_OPTIONS = [
  { id: "server", label: "Server" },
  { id: "grid", label: "Grid" },
  { id: "link", label: "Links" },
  { id: "star", label: "Favorites" },
  { id: "settings", label: "Settings" },
  { id: "cable", label: "Network" },
  { id: "updates", label: "Updates" },
  { id: "palette", label: "Custom" },
];

function CategoryIcon({ icon, size = 18 }: { icon?: string | null; size?: number }) {
  if (icon === "grid") return <LayoutGrid size={size} />;
  if (icon === "link") return <LinkIcon size={size} />;
  if (icon === "star") return <Star size={size} />;
  if (icon === "settings") return <Settings size={size} />;
  if (icon === "cable") return <Cable size={size} />;
  if (icon === "updates") return <ArrowUpCircle size={size} />;
  if (icon === "palette") return <Palette size={size} />;
  return <Server size={size} />;
}

function CategoryEditModal({ category, csrfToken, onClose, onSaved }: { category: CategoryLayout; csrfToken?: string | null; onClose: () => void; onSaved: () => Promise<void> | void }) {
  const [name, setName] = useState(category.name);
  const [icon, setIcon] = useState(category.icon ?? "server");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await api<CategoryLayout>("/api/categories/configure", { method: "PUT", body: JSON.stringify({ page_id: category.page_id, old_name: category.name, name, icon }) }, csrfToken);
      await onSaved(); onClose();
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to update category."); }
    finally { setBusy(false); }
  }
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.currentTarget === event.target && onClose()}>
    <section className="modal category-modal" role="dialog" aria-modal="true" aria-labelledby="category-modal-title">
      <header className="modal-header"><div><p className="eyebrow">CATEGORY</p><h2 id="category-modal-title">Customize {category.name}</h2><p className="modal-subhead">Rename the category across this page and choose a consistent header icon.</p></div><button className="icon-button" type="button" onClick={onClose} aria-label="Close"><X size={20} /></button></header>
      <form className="page-form" onSubmit={save}>
        <label><span>Category name</span><input value={name} maxLength={80} required onChange={(event) => setName(event.target.value)} /></label>
        <label><span>Header icon</span><select value={icon} onChange={(event) => setIcon(event.target.value)}>{CATEGORY_ICON_OPTIONS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        <div className="category-icon-preview"><CategoryIcon icon={icon} size={20} /><span>{name || category.name}</span></div>
        {error && <div className="notice compact">{error}</div>}
        <div className="modal-actions"><div className="action-spacer" /><button className="secondary" type="button" disabled={busy} onClick={onClose}>Cancel</button><button className="primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save category"}</button></div>
      </form>
    </section>
  </div>;
}

function AppearanceModal({
  appearance,
  busy,
  error,
  onClose,
  onSelect,
  onImport,
  onDelete,
}: {
  appearance: AppearanceSettings;
  busy: boolean;
  error: string;
  onClose: () => void;
  onSelect: (themeId: string) => Promise<void>;
  onImport: (theme: ThemePackage) => Promise<void>;
  onDelete: (themeId: string) => Promise<void>;
}) {
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [themeDraft, setThemeDraft] = useState<ThemePackage>(() => ({ ...THEME_TEMPLATE, colors: { ...THEME_TEMPLATE.colors } }));

  function beginThemeEditor() {
    const base = resolveTheme(appearance.theme_id, appearance.custom_themes);
    setThemeDraft({ ...THEME_TEMPLATE, id: `custom-${Date.now().toString(36)}`, name: "Custom Theme", author: "Dashboard Admin", mode: base.mode, colors: { ...base.colors } });
    setEditorOpen(true);
  }

  async function saveThemeDraft(event: FormEvent) {
    event.preventDefault();
    await onImport(themeDraft);
  }

  async function importFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text()) as ThemePackage;
      await onImport(parsed);
    } catch {
      window.alert("That file is not valid JSON. Download the theme template for the supported format.");
    }
  }

  function downloadTemplate() {
    const blob = new Blob([JSON.stringify(THEME_TEMPLATE, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "homelab-dashboard-theme-template.json";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  const systemDark = BUILTIN_THEME_BY_ID.dark;
  const systemLight = BUILTIN_THEME_BY_ID.light;
  const choices: { theme: ThemePackage; custom: boolean }[] = [
    ...BUILTIN_THEMES.map((theme) => ({ theme, custom: false })),
    ...appearance.custom_themes.map((theme) => ({ theme, custom: true })),
  ];

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.currentTarget === event.target && onClose()}>
      <section className="modal appearance-modal" role="dialog" aria-modal="true" aria-labelledby="appearance-title">
        <header className="modal-header">
          <div>
            <p className="eyebrow">APPEARANCE</p>
            <h2 id="appearance-title">Choose your dashboard theme</h2>
            <p className="modal-subhead">Built-in themes are always available. Imported themes are validated visual-only packages and cannot run code.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close"><X size={20} /></button>
        </header>

        <div className="appearance-tools">
          <button className="primary" type="button" disabled={busy} onClick={beginThemeEditor}><Palette size={16} /> Create custom theme</button>
          <button className="secondary" type="button" disabled={busy} onClick={() => fileInput.current?.click()}><Upload size={16} /> Import theme</button>
          <button className="secondary" type="button" onClick={downloadTemplate}><Download size={16} /> Theme template</button>
          <input ref={fileInput} className="hidden-file" type="file" accept="application/json,.json" onChange={(event) => void importFile(event)} />
          <span>Community theme format v1 · colors only · no CSS or JavaScript</span>
        </div>

        {error && <div className="notice appearance-error">{error}</div>}

        {editorOpen && <form className="theme-editor" onSubmit={(event) => void saveThemeDraft(event)}>
          <div className="theme-editor-heading"><div><strong>Visual theme editor</strong><span>Start from the active theme, then adjust any design token. The saved result is the same safe data-only format as an imported community theme.</span></div><button className="icon-button" type="button" onClick={() => setEditorOpen(false)} aria-label="Close theme editor"><X size={17} /></button></div>
          <div className="theme-editor-meta">
            <label><span>Name</span><input required maxLength={80} value={themeDraft.name} onChange={(event) => setThemeDraft((current) => ({ ...current, name: event.target.value }))} /></label>
            <label><span>Theme ID</span><input required maxLength={40} pattern="[a-z0-9][a-z0-9-]+" value={themeDraft.id} onChange={(event) => setThemeDraft((current) => ({ ...current, id: event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-") }))} /></label>
            <label><span>Mode</span><select value={themeDraft.mode} onChange={(event) => setThemeDraft((current) => ({ ...current, mode: event.target.value as "dark" | "light" }))}><option value="dark">Dark</option><option value="light">Light</option></select></label>
            <label><span>Author</span><input required maxLength={100} value={themeDraft.author} onChange={(event) => setThemeDraft((current) => ({ ...current, author: event.target.value }))} /></label>
          </div>
          <div className="theme-token-grid">{(Object.keys(themeDraft.colors) as (keyof ThemePackage["colors"])[]).map((key) => <label key={key}><span>{key.replace(/([A-Z])/g, " $1")}</span><div><input type="color" value={themeDraft.colors[key]} onChange={(event) => setThemeDraft((current) => ({ ...current, colors: { ...current.colors, [key]: event.target.value } }))} /><input value={themeDraft.colors[key]} pattern="#[0-9a-fA-F]{6}" onChange={(event) => setThemeDraft((current) => ({ ...current, colors: { ...current.colors, [key]: event.target.value } }))} /></div></label>)}</div>
          <div className="modal-actions"><div className="action-spacer" /><button className="secondary" type="button" onClick={() => setEditorOpen(false)}>Cancel</button><button className="primary" type="submit" disabled={busy}>Save custom theme</button></div>
        </form>}

        <div className="theme-grid">
          <article className={`theme-card ${appearance.theme_id === "system" ? "selected" : ""}`}>
            <button className="theme-select" type="button" disabled={busy} onClick={() => void onSelect("system")}>
              <div className="theme-preview system-preview" style={{ background: `linear-gradient(90deg, ${systemDark.colors.background} 0 50%, ${systemLight.colors.background} 50% 100%)` }}>
                <span style={{ background: systemDark.colors.accent }} />
                <span style={{ background: systemLight.colors.accent }} />
              </div>
              <div className="theme-copy"><strong>System</strong><span>Follows this device's light or dark preference.</span></div>
              {appearance.theme_id === "system" && <span className="selected-badge">Selected</span>}
            </button>
          </article>

          {choices.map(({ theme, custom }) => (
            <article className={`theme-card ${appearance.theme_id === theme.id ? "selected" : ""}`} key={theme.id}>
              <button className="theme-select" type="button" disabled={busy} onClick={() => void onSelect(theme.id)}>
                <div className="theme-preview" style={{ background: `linear-gradient(145deg, ${theme.colors.surfaceAlt}, ${theme.colors.background})`, borderColor: theme.colors.border }}>
                  <span style={{ background: theme.colors.accent }} />
                  <span style={{ background: theme.colors.text }} />
                  <span style={{ background: theme.colors.muted }} />
                </div>
                <div className="theme-copy">
                  <strong>{theme.name}</strong>
                  <span>{theme.description || `${theme.mode === "light" ? "Light" : "Dark"} theme by ${theme.author}`}</span>
                  {custom && <small>{theme.author} · v{theme.version}</small>}
                </div>
                {appearance.theme_id === theme.id && <span className="selected-badge">Selected</span>}
              </button>
              {custom && (
                <button className="theme-delete" type="button" disabled={busy} onClick={() => void onDelete(theme.id)} aria-label={`Delete ${theme.name}`} title={`Delete ${theme.name}`}>
                  <Trash2 size={14} />
                </button>
              )}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function inferredServiceType(service: Service): string | null {
  if (CATALOG_BY_TYPE[service.type]?.icon) return service.type;
  if (!["link", "other"].includes(service.type)) return service.type;

  const haystack = `${service.name} ${service.url}`.toLowerCase();
  for (const entry of SERVICE_CATALOG) {
    if (!entry.icon || ["link", "other"].includes(entry.type)) continue;
    const candidates = [entry.name.toLowerCase(), entry.type.toLowerCase(), ...(entry.aliases ?? []).map((alias) => alias.toLowerCase())]
      .filter((candidate) => candidate.length >= 4);
    if (candidates.some((candidate) => haystack.includes(candidate))) return entry.type;
  }
  return null;
}

function ConnectionsModal({ connections, csrfToken, onClose, onChanged }: { connections: ManagementConnection[]; csrfToken?: string | null; onClose: () => void; onChanged: () => Promise<void> | void }) {
  const blank = { name: "", url: "https://", api_key: "", auth_username: "", clear_api_key: false, clear_auth_username: false };
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  function startAdd() { setEditingId(null); setForm(blank); setError(""); setMessage(""); }
  function startEdit(connection: ManagementConnection) {
    setEditingId(connection.id);
    setForm({ name: connection.name, url: connection.url, api_key: "", auth_username: "", clear_api_key: false, clear_auth_username: false });
    setError(""); setMessage("");
  }

  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      await api<ManagementConnection>(editingId ? `/api/connections/${editingId}` : "/api/connections", {
        method: editingId ? "PUT" : "POST",
        body: JSON.stringify({ ...form, type: "truenas", api_key: form.api_key.trim() || null, auth_username: form.auth_username.trim() || null }),
      }, csrfToken);
      await onChanged();
      setMessage(editingId ? "Connection saved." : "Connection added.");
      if (!editingId) setForm(blank);
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to save connection."); }
    finally { setBusy(false); }
  }

  async function test(connection: ManagementConnection) {
    setBusy(true); setError(""); setMessage("");
    try { const result = await api<ConnectionTestResult>(`/api/connections/${connection.id}/test`, { method: "POST" }, csrfToken); setMessage(result.message); }
    catch (err) { setError(err instanceof Error ? err.message : "Connection test failed."); }
    finally { setBusy(false); }
  }

  async function remove(connection: ManagementConnection) {
    if (!window.confirm(`Delete the ${connection.name} connection?`)) return;
    setBusy(true); setError(""); setMessage("");
    try { await api<void>(`/api/connections/${connection.id}`, { method: "DELETE" }, csrfToken); await onChanged(); if (editingId === connection.id) startAdd(); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to delete connection."); }
    finally { setBusy(false); }
  }

  const editing = connections.find((item) => item.id === editingId);
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.currentTarget === event.target && onClose()}>
      <section className="modal connections-modal" role="dialog" aria-modal="true" aria-labelledby="connections-title">
        <header className="modal-header">
          <div><p className="eyebrow">CONNECTIONS</p><h2 id="connections-title">Management connections</h2><p className="modal-subhead">Store controller credentials once, then reuse them for managed services. Connections do not have to appear as dashboard cards.</p></div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close"><X size={20} /></button>
        </header>
        <div className="connections-layout">
          <div className="connections-list">
            <button className={`connection-list-item ${editingId === null ? "active" : ""}`} type="button" onClick={startAdd}><Plus size={16} /><span><strong>Add connection</strong><small>New TrueNAS controller</small></span></button>
            {connections.map((connection) => (
              <button className={`connection-list-item ${editingId === connection.id ? "active" : ""}`} type="button" key={connection.id} onClick={() => startEdit(connection)}>
                <Cable size={16} /><span><strong>{connection.name}</strong><small>{connection.used_by} managed service{connection.used_by === 1 ? "" : "s"}</small></span>
              </button>
            ))}
          </div>
          <form className="connection-form" onSubmit={save}>
            <h3>{editing ? `Edit ${editing.name}` : "Add TrueNAS connection"}</h3>
            <label><span>Name</span><input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} placeholder="Home TrueNAS" required /></label>
            <label><span>TrueNAS URL</span><input type="url" value={form.url} onChange={(event) => setForm((current) => ({ ...current, url: event.target.value }))} placeholder="https://192.168.1.10" required /><small>Use the HTTPS address reachable from the dashboard container.</small></label>
            <label><span>API key {editing?.has_api_key && <small>saved — leave blank to keep</small>}</span><input type="password" value={form.api_key} onChange={(event) => setForm((current) => ({ ...current, api_key: event.target.value }))} placeholder={editing?.has_api_key ? "API key saved" : "TrueNAS API key"} autoComplete="off" required={!editing} /></label>
            <label><span>API-key username <small>optional</small></span><input value={form.auth_username} onChange={(event) => setForm((current) => ({ ...current, auth_username: event.target.value }))} placeholder={editing?.has_auth_username ? "Username saved — leave blank to keep" : "API key owner username"} autoComplete="off" /></label>
            {editing?.has_api_key && <label className="check-row"><input type="checkbox" checked={form.clear_api_key} onChange={(event) => setForm((current) => ({ ...current, clear_api_key: event.target.checked }))} /><span>Remove saved API key</span></label>}
            {editing?.has_auth_username && <label className="check-row"><input type="checkbox" checked={form.clear_auth_username} onChange={(event) => setForm((current) => ({ ...current, clear_auth_username: event.target.checked }))} /><span>Remove saved username</span></label>}
            {error && <div className="notice compact">{error}</div>}
            {message && <div className="connection-success">{message}</div>}
            <div className="connection-actions">
              {editing && <button className="secondary" type="button" disabled={busy} onClick={() => void test(editing)}>Test connection</button>}
              {editing && <button className="danger-button" type="button" disabled={busy || editing.used_by > 0} title={editing.used_by > 0 ? "Remove this connection from managed services before deleting it" : undefined} onClick={() => void remove(editing)}>Delete</button>}
              <span className="action-spacer" />
              <button className="primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save connection"}</button>
            </div>
          </form>
        </div>
      </section>
    </div>
  );
}

function UpdateManagerModal({
  services,
  states,
  jobs,
  busy,
  onClose,
  onCheck,
  onUpdate,
  onUpdateAll,
}: {
  services: Service[];
  states: Record<number, ServiceUpdateState>;
  jobs: UpdateJob[];
  busy: boolean;
  onClose: () => void;
  onCheck: () => void;
  onUpdate: (service: Service) => void;
  onUpdateAll: () => void;
}) {
  const managed = services.filter((service) => service.management_provider !== "none");
  const available = managed.filter((service) => states[service.id]?.state === "available");
  const active = jobs.find((job) => job.state === "queued" || job.state === "running");
  const serviceName = (id?: number | null) => services.find((service) => service.id === id)?.name ?? "Service";
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.currentTarget === event.target && onClose()}>
      <section className="modal updates-modal" role="dialog" aria-modal="true" aria-labelledby="updates-title">
        <header className="modal-header">
          <div>
            <p className="eyebrow">UPDATE MANAGER</p>
            <h2 id="updates-title">Service updates</h2>
            <p className="modal-subhead">Check and apply updates through each service's configured management provider.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close"><X size={20} /></button>
        </header>
        <div className="update-toolbar">
          <button className="secondary" type="button" disabled={busy || !!active} onClick={onCheck}><RefreshCw className={active?.kind === "check" ? "spin" : ""} size={16} /> Check for updates</button>
          <button className="primary" type="button" disabled={busy || !!active || available.length === 0} onClick={onUpdateAll}><ArrowUpCircle size={17} /> Update all ({available.length})</button>
        </div>
        {active && (
          <div className="update-active">
            <div className="activity-heading"><strong>{active.message}</strong><span>{active.progress}%</span></div>
            <div className="activity-track"><span className="activity-bar" style={{ width: `${active.progress}%` }} /></div>
            {active.active_service_id && <small>{serviceName(active.active_service_id)}</small>}
            {active.detail && <small className="field-error">{active.detail}</small>}
          </div>
        )}
        <div className="update-list">
          {managed.length === 0 && <div className="catalog-empty">No services have update management configured yet. Edit a service card to link it to Docker Compose/Dockge or a TrueNAS App.</div>}
          {managed.map((service) => {
            const state = states[service.id];
            const isActive = active?.active_service_id === service.id || active?.service_id === service.id;
            return (
              <div className="update-row" key={service.id}>
                <div className="update-row-main">
                  <div className="update-row-title"><ServiceIcon service={service} /><div><strong>{service.name}</strong><small>{service.management_provider === "docker_compose" ? "Docker Compose / Dockge" : "TrueNAS App"}</small></div></div>
                  <div className={`update-state update-state-${state?.state ?? "unknown"}`}>
                    {state?.state === "available" ? "Update available" : state?.state === "current" ? "Up to date" : state?.state === "checking" ? "Checking…" : state?.state === "unavailable" ? "Check failed" : state?.state === "unknown" ? "Not checked" : "Not configured"}
                  </div>
                  {(state?.current_version || state?.latest_version) && <small className="version-line">{state.current_version ?? "?"}{state.latest_version && state.latest_version !== state.current_version ? ` → ${state.latest_version}` : ""}</small>}
                  {state?.message && <small>{state.message}</small>}
                </div>
                <button className="secondary update-row-button" type="button" disabled={busy || !!active || state?.state !== "available" || isActive} onClick={() => onUpdate(service)}>{isActive ? "Updating…" : "Update"}</button>
              </div>
            );
          })}
        </div>
        {jobs.length > 0 && (
          <div className="update-history">
            <div className="section-title"><History size={16} /><h3>Recent activity</h3></div>
            {jobs.slice(0, 8).map((job) => <div className="history-row" key={job.id}><span className={`history-dot history-${job.state}`} /> <strong>{job.kind === "update" ? serviceName(job.service_id) : job.kind === "batch" ? "Update all" : "Update check"}</strong><span>{job.message}</span><small>{job.state}</small></div>)}
          </div>
        )}
      </section>
    </div>
  );
}

function CardManagementStatus({ service, state, job, manageMode, onUpdate }: { service: Service; state?: ServiceUpdateState; job?: UpdateJob; manageMode: boolean; onUpdate: (service: Service) => void }) {
  if (service.management_provider === "none") return <div className="card-management-slot card-management-empty" aria-hidden="true"><span>Management not configured</span></div>;
  if (job) return (
    <div className="card-management-slot card-management-running">
      <div className="management-status-line management-checking"><span className="management-status-dot" /><strong>{job.message || "Updating…"}</strong><small>{job.progress}%</small></div>
      <div className="activity-track"><span className="activity-bar" style={{ width: `${job.progress}%` }} /></div>
    </div>
  );
  const current = state?.state ?? "unknown";
  const label = current === "current" ? "Up to date"
    : current === "available" ? "Update available"
      : current === "checking" ? "Checking for updates…"
        : current === "unavailable" ? "Update check failed"
          : current === "unconfigured" ? "Update management incomplete" : "Update status not checked";
  const version = state?.latest_version && state.latest_version !== state.current_version
    ? `${state.current_version ?? "?"} → ${state.latest_version}`
    : state?.current_version ?? null;
  return (
    <div className={`card-management-slot management-${current}`} title={state?.message ?? label}>
      <div className={`management-status-line management-${current}`}><span className="management-status-dot" /><strong>{label}</strong>{version && <small className="management-version">{version}</small>}</div>
      {current === "available" && !manageMode && <button className="card-update-action" type="button" onClick={() => onUpdate(service)}><ArrowUpCircle size={14} /> Update</button>}
    </div>
  );
}

function ServiceIcon({ service }: { service: Service }) {
  const brandedType = inferredServiceType(service);
  const entry = brandedType ? CATALOG_BY_TYPE[brandedType] : null;
  return <CatalogLogo entry={entry} fallback={service.icon ? <span className="custom-service-icon">{service.icon}</span> : <LinkIcon size={27} />} />;
}

function Dashboard({ auth, onLogout }: { auth: AuthStatus; onLogout: () => void }) {
  const [services, setServices] = useState<Service[]>([]);
  const [widgets, setWidgets] = useState<DashboardWidget[]>([]);
  const [pages, setPages] = useState<DashboardPage[]>([]);
  const [categories, setCategories] = useState<CategoryLayout[]>([]);
  const [activePageId, setActivePageId] = useState<number>(() => Number(window.localStorage.getItem("homelab-dashboard-active-page")) || 1);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Service | null | undefined>(undefined);
  const [editingPage, setEditingPage] = useState<DashboardPage | null | undefined>(undefined);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<CatalogEntry | null>(null);
  const [manageMode, setManageMode] = useState(false);
  const [statuses, setStatuses] = useState<Record<number, ServiceStatus>>({});
  const [statusLoading, setStatusLoading] = useState(false);
  const [insights, setInsights] = useState<Record<number, ServiceInsight>>({});
  const [insightLoading, setInsightLoading] = useState(false);
  const [draggingItem, setDraggingItem] = useState<{ kind: "service" | "widget"; id: number; page_id: number; category: string; favorite: boolean } | null>(null);
  const [dragOverItemKey, setDragOverItemKey] = useState<string | null>(null);
  const [draggingCategory, setDraggingCategory] = useState<string | null>(null);
  const [dragOverCategory, setDragOverCategory] = useState<string | null>(null);
  const [draggingPageId, setDraggingPageId] = useState<number | null>(null);
  const [dragOverPageId, setDragOverPageId] = useState<number | null>(null);
  const [appearance, setAppearance] = useState<AppearanceSettings>({ theme_id: "system", custom_themes: [] });
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  const [appearanceBusy, setAppearanceBusy] = useState(false);
  const [appearanceError, setAppearanceError] = useState("");
  const [connections, setConnections] = useState<ManagementConnection[]>([]);
  const [connectionsOpen, setConnectionsOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [editingWidget, setEditingWidget] = useState<DashboardWidget | null | undefined>(undefined);
  const [dashboardSettings, setDashboardSettings] = useState<DashboardSettings>({ dashboard_title: "Homelab Dashboard", show_greeting: true, telemetry_refresh_seconds: 15, update_status_refresh_seconds: 15, active_refresh_seconds: 3, update_check_interval_hours: 12 });
  const [extensions, setExtensions] = useState<ExtensionDescriptor[]>([]);
  const [updatesOpen, setUpdatesOpen] = useState(false);
  const [updateStates, setUpdateStates] = useState<Record<number, ServiceUpdateState>>({});
  const [updateJobs, setUpdateJobs] = useState<UpdateJob[]>([]);
  const [updateBusy, setUpdateBusy] = useState(false);
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState<CategoryLayout | null>(null);
  const commandBarRef = useRef<HTMLDivElement | null>(null);
  const layoutImportRef = useRef<HTMLInputElement | null>(null);

  async function loadServices() {
    setLoading(true);
    setError("");
    try {
      setServices(await api<Service[]>("/api/services/all"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard API is unavailable.");
    } finally {
      setLoading(false);
    }
  }

  async function loadWidgets() {
    try { setWidgets(await api<DashboardWidget[]>("/api/widgets")); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to load dashboard widgets."); }
  }

  async function loadSettings() {
    try { setDashboardSettings(await api<DashboardSettings>("/api/settings")); }
    catch { /* Use safe defaults if settings cannot be loaded. */ }
  }

  async function loadExtensions() {
    try { setExtensions(await api<ExtensionDescriptor[]>("/api/extensions")); }
    catch { /* Extension inventory is informational. */ }
  }

  async function saveSettings(next: DashboardSettings) {
    const saved = await api<DashboardSettings>("/api/settings", { method: "PUT", body: JSON.stringify(next) }, auth.csrf_token);
    setDashboardSettings(saved);
  }

  async function loadStructure() {
    try {
      const [pageResult, categoryResult] = await Promise.all([
        api<DashboardPage[]>("/api/pages"),
        api<CategoryLayout[]>("/api/categories"),
      ]);
      setPages(pageResult);
      setCategories(categoryResult);
      setActivePageId((current) => {
        if (pageResult.some((page) => page.id === current)) return current;
        const fallback = pageResult.find((page) => page.is_default) ?? pageResult[0];
        return fallback?.id ?? 1;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load dashboard layout.");
    }
  }

  async function loadAppearance() {
    try {
      setAppearance(await api<AppearanceSettings>("/api/appearance"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load appearance settings.");
    }
  }

  async function loadStatuses() {
    setStatusLoading(true);
    try {
      const result = await api<ServiceStatus[]>("/api/services/status");
      setStatuses(Object.fromEntries(result.map((item) => [item.id, item])));
    } catch {
      // Keep the dashboard usable if a status refresh fails.
    } finally {
      setStatusLoading(false);
    }
  }

  async function loadInsights() {
    setInsightLoading(true);
    try {
      const result = await api<ServiceInsight[]>("/api/services/insights");
      setInsights(Object.fromEntries(result.map((item) => [item.id, item])));
    } catch {
      // Rich integrations are optional; basic cards should still work.
    } finally {
      setInsightLoading(false);
    }
  }

  async function loadConnections() {
    try { setConnections(await api<ManagementConnection[]>("/api/connections")); }
    catch { /* Management connections are optional. */ }
  }

  async function loadUpdateData() {
    try {
      const [statesResult, jobsResult] = await Promise.all([
        api<ServiceUpdateState[]>("/api/updates/status"),
        api<UpdateJob[]>("/api/updates/jobs?limit=25"),
      ]);
      setUpdateStates(Object.fromEntries(statesResult.map((item) => [item.service_id, item])));
      setUpdateJobs(jobsResult);
    } catch {
      // Update management is optional.
    }
  }

  async function checkForUpdates() {
    setUpdateBusy(true);
    try {
      await api<UpdateJob>("/api/updates/check", { method: "POST" }, auth.csrf_token);
      await loadUpdateData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start update check.");
    } finally { setUpdateBusy(false); }
  }

  async function startManagedUpdate(service: Service) {
    const state = updateStates[service.id];
    const versionText = state?.latest_version ? ` to ${state.latest_version}` : "";
    if (!window.confirm(`Update ${service.name}${versionText}? The service may restart briefly.`)) return;
    setUpdateBusy(true);
    try {
      await api<UpdateJob>(`/api/services/${service.id}/update`, { method: "POST" }, auth.csrf_token);
      await loadUpdateData();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Unable to update ${service.name}.`);
    } finally { setUpdateBusy(false); }
  }

  async function updateAllAvailable() {
    const count = Object.values(updateStates).filter((item) => item.state === "available").length;
    if (!count || !window.confirm(`Update ${count} available service${count === 1 ? "" : "s"} sequentially? The batch will stop if an update fails.`)) return;
    setUpdateBusy(true);
    try {
      await api<UpdateJob>("/api/updates/update-all", { method: "POST" }, auth.csrf_token);
      await loadUpdateData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start update-all.");
    } finally { setUpdateBusy(false); }
  }

  async function refreshTelemetry() {
    await Promise.all([loadStatuses(), loadInsights()]);
  }

  useEffect(() => {
    void Promise.all([loadServices(), loadWidgets(), loadStructure(), loadAppearance(), loadConnections(), loadUpdateData(), loadSettings(), loadExtensions()]);
    void refreshTelemetry();
    const onVisible = () => { if (document.visibilityState === "visible") { void refreshTelemetry(); void loadUpdateData(); void loadWidgets(); } };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  useEffect(() => {
    const telemetryTimer = window.setInterval(() => { void refreshTelemetry(); }, Math.max(5, dashboardSettings.telemetry_refresh_seconds) * 1000);
    return () => window.clearInterval(telemetryTimer);
  }, [dashboardSettings.telemetry_refresh_seconds]);

  useEffect(() => {
    const updateTimer = window.setInterval(() => { void loadUpdateData(); }, Math.max(5, dashboardSettings.update_status_refresh_seconds) * 1000);
    return () => window.clearInterval(updateTimer);
  }, [dashboardSettings.update_status_refresh_seconds]);

  const hasActiveUpdateJob = updateJobs.some((job) => job.state === "queued" || job.state === "running");
  useEffect(() => {
    if (!hasActiveUpdateJob) return;
    const activeTimer = window.setInterval(() => { void loadUpdateData(); void refreshTelemetry(); }, Math.max(1, dashboardSettings.active_refresh_seconds) * 1000);
    return () => window.clearInterval(activeTimer);
  }, [hasActiveUpdateJob, dashboardSettings.active_refresh_seconds]);

  useEffect(() => { document.title = dashboardSettings.dashboard_title; }, [dashboardSettings.dashboard_title]);

  useEffect(() => {
    function closeMenus(event: MouseEvent) {
      if (commandBarRef.current && !commandBarRef.current.contains(event.target as Node)) { setAddMenuOpen(false); setAccountMenuOpen(false); }
    }
    function onKey(event: KeyboardEvent) { if (event.key === "Escape") { setAddMenuOpen(false); setAccountMenuOpen(false); } }
    document.addEventListener("mousedown", closeMenus);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", closeMenus); document.removeEventListener("keydown", onKey); };
  }, []);

  useEffect(() => {
    const applySelected = () => applyTheme(resolveTheme(appearance.theme_id, appearance.custom_themes), appearance.theme_id);
    applySelected();
    window.localStorage.setItem("homelab-dashboard-appearance", JSON.stringify(appearance));
    if (appearance.theme_id !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", applySelected);
    return () => media.removeEventListener("change", applySelected);
  }, [appearance]);

  useEffect(() => {
    window.localStorage.setItem("homelab-dashboard-active-page", String(activePageId));
    setQuery("");
  }, [activePageId]);

  function statusPresentation(service: Service) {
    if (!service.enabled) return { state: "disabled", label: "Disabled", title: "Service is hidden" };
    if (!service.status_check) return { state: "unchecked", label: "Not monitored", title: "Live monitoring is disabled" };
    const current = statuses[service.id];
    if (!current) return { state: "checking", label: statusLoading ? "Checking…" : "Unknown", title: "Status has not been checked yet" };
    if (current.state === "online") {
      const latency = current.latency_ms ? ` · ${current.latency_ms} ms` : "";
      return { state: "online", label: `Online${latency}`, title: `HTTP ${current.http_status ?? "OK"}` };
    }
    if (current.state === "degraded") return { state: "degraded", label: "Degraded", title: current.detail ?? `HTTP ${current.http_status ?? 500}` };
    if (current.state === "offline") return { state: "offline", label: "Offline", title: current.detail ?? "Service did not respond" };
    if (current.state === "unchecked") return { state: "unchecked", label: "Not monitored", title: current.detail ?? "Live monitoring is disabled" };
    return { state: "disabled", label: "Disabled", title: current.detail ?? "Service is hidden" };
  }

  const activePage = pages.find((page) => page.id === activePageId) ?? pages[0];

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const visible = (manageMode ? services : services.filter((service) => service.enabled))
      .filter((service) => service.page_id === activePageId);
    if (!normalized) return visible;
    return visible.filter((service) =>
      `${service.name} ${service.category} ${service.type}`.toLowerCase().includes(normalized),
    );
  }, [query, services, manageMode, activePageId]);

  const filteredWidgets = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const visible = (manageMode ? widgets : widgets.filter((widget) => widget.enabled)).filter((widget) => widget.page_id === activePageId);
    if (!normalized) return visible;
    return visible.filter((widget) => `${widget.title} ${widget.category} ${widget.type}`.toLowerCase().includes(normalized));
  }, [query, widgets, manageMode, activePageId]);

  const pageCategories = useMemo(() => {
    const layouts = categories
      .filter((category) => category.page_id === activePageId)
      .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name));
    const known = new Set(layouts.map((category) => category.name.toLowerCase()));
    const extras = Array.from(new Set([
      ...services.filter((service) => service.page_id === activePageId).map((service) => service.category),
      ...widgets.filter((widget) => widget.page_id === activePageId).map((widget) => widget.category),
    ])).filter((name) => !known.has(name.toLowerCase())).sort((a, b) => a.localeCompare(b));
    return [...layouts, ...extras.map((name, index) => ({ page_id: activePageId, name, sort_order: 100000 + index, collapsed: false, icon: null }))];
  }, [categories, services, widgets, activePageId]);

  const groups = useMemo(() => {
    type MixedItem =
      | { kind: "service"; id: number; sort_order: number; favorite: boolean; name: string; service: Service }
      | { kind: "widget"; id: number; sort_order: number; favorite: false; name: string; widget: DashboardWidget };
    const grouped: Record<string, MixedItem[]> = {};
    filtered.forEach((service) => (grouped[service.category] ??= []).push({ kind: "service", id: service.id, sort_order: service.sort_order, favorite: service.favorite, name: service.name, service }));
    filteredWidgets.forEach((widget) => (grouped[widget.category] ??= []).push({ kind: "widget", id: widget.id, sort_order: widget.sort_order, favorite: false, name: widget.title, widget }));
    Object.values(grouped).forEach((items) => items.sort((a, b) => Number(b.favorite) - Number(a.favorite) || a.sort_order - b.sort_order || a.name.localeCompare(b.name)));
    const order = new Map(pageCategories.map((category, index) => [category.name.toLowerCase(), index]));
    return Object.keys(grouped).sort((a, b) => (order.get(a.toLowerCase()) ?? 999999) - (order.get(b.toLowerCase()) ?? 999999) || a.localeCompare(b))
      .map((name) => [name, grouped[name]] as const);
  }, [filtered, filteredWidgets, pageCategories]);

  async function toggleFavorite(service: Service) {
    const next = !service.favorite;
    setServices((current) => current.map((item) => item.id === service.id ? { ...item, favorite: next } : item));
    try {
      const updated = await api<Service>(`/api/services/${service.id}/layout`, {
        method: "PATCH",
        body: JSON.stringify({ favorite: next }),
      }, auth.csrf_token);
      setServices((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (err) {
      setServices((current) => current.map((item) => item.id === service.id ? service : item));
      setError(err instanceof Error ? err.message : "Unable to update favorite.");
    }
  }

  async function dropDashboardItem(target: { kind: "service" | "widget"; id: number; page_id: number; category: string; favorite: boolean }) {
    const source = draggingItem;
    setDraggingItem(null);
    setDragOverItemKey(null);
    if (!source || source.kind === target.kind && source.id === target.id || source.page_id !== target.page_id || source.category !== target.category || source.favorite !== target.favorite || query.trim()) return;

    const mixed = [
      ...services.filter((item) => item.page_id === target.page_id && item.category === target.category).map((item) => ({ kind: "service" as const, id: item.id, sort_order: item.sort_order, favorite: item.favorite, name: item.name })),
      ...widgets.filter((item) => item.page_id === target.page_id && item.category === target.category).map((item) => ({ kind: "widget" as const, id: item.id, sort_order: item.sort_order, favorite: false, name: item.title })),
    ].sort((a, b) => Number(b.favorite) - Number(a.favorite) || a.sort_order - b.sort_order || a.name.localeCompare(b.name));

    const from = mixed.findIndex((item) => item.kind === source.kind && item.id === source.id);
    const to = mixed.findIndex((item) => item.kind === target.kind && item.id === target.id);
    if (from < 0 || to < 0) return;
    const reordered = [...mixed];
    const [moved] = reordered.splice(from, 1);
    reordered.splice(to, 0, moved);
    const serviceOrder = new Map<number, number>();
    const widgetOrder = new Map<number, number>();
    reordered.forEach((item, index) => item.kind === "service" ? serviceOrder.set(item.id, index + 1) : widgetOrder.set(item.id, index + 1));
    setServices((current) => current.map((item) => serviceOrder.has(item.id) ? { ...item, sort_order: serviceOrder.get(item.id)! } : item));
    setWidgets((current) => current.map((item) => widgetOrder.has(item.id) ? { ...item, sort_order: widgetOrder.get(item.id)! } : item));
    try {
      await api<{ ok: boolean }>("/api/dashboard-items/reorder", { method: "POST", body: JSON.stringify({ page_id: target.page_id, category: target.category, ordered_items: reordered.map((item) => ({ kind: item.kind, id: item.id })) }) }, auth.csrf_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save dashboard item order.");
      void Promise.all([loadServices(), loadWidgets()]);
    }
  }

  async function toggleCategory(categoryName: string) {
    const current = pageCategories.find((category) => category.name.toLowerCase() === categoryName.toLowerCase());
    const next = !(current?.collapsed ?? false);
    setCategories((items) => {
      const found = items.some((item) => item.page_id === activePageId && item.name.toLowerCase() === categoryName.toLowerCase());
      if (!found) return [...items, { page_id: activePageId, name: categoryName, sort_order: current?.sort_order ?? pageCategories.length + 1, collapsed: next }];
      return items.map((item) => item.page_id === activePageId && item.name.toLowerCase() === categoryName.toLowerCase() ? { ...item, collapsed: next } : item);
    });
    try {
      const updated = await api<CategoryLayout>("/api/categories/state", {
        method: "PATCH",
        body: JSON.stringify({ page_id: activePageId, name: categoryName, collapsed: next }),
      }, auth.csrf_token);
      setCategories((items) => {
        const others = items.filter((item) => !(item.page_id === updated.page_id && item.name.toLowerCase() === updated.name.toLowerCase()));
        return [...others, updated];
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save category state.");
      void loadStructure();
    }
  }

  async function dropCategory(targetName: string) {
    const sourceName = draggingCategory;
    setDraggingCategory(null);
    setDragOverCategory(null);
    if (!sourceName || sourceName === targetName || query.trim()) return;
    const ordered = pageCategories.map((category) => category.name);
    const from = ordered.findIndex((name) => name === sourceName);
    const to = ordered.findIndex((name) => name === targetName);
    if (from < 0 || to < 0) return;
    const next = [...ordered];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    const orderMap = new Map(next.map((name, index) => [name.toLowerCase(), index + 1]));
    setCategories((items) => items.map((item) => item.page_id === activePageId ? { ...item, sort_order: orderMap.get(item.name.toLowerCase()) ?? item.sort_order } : item));
    try {
      const updated = await api<CategoryLayout[]>("/api/categories/reorder", {
        method: "POST",
        body: JSON.stringify({ page_id: activePageId, ordered_names: next }),
      }, auth.csrf_token);
      setCategories((items) => [...items.filter((item) => item.page_id !== activePageId), ...updated]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save category order.");
      void loadStructure();
    }
  }

  async function dropPage(targetId: number) {
    const sourceId = draggingPageId;
    setDraggingPageId(null);
    setDragOverPageId(null);
    if (!sourceId || sourceId === targetId) return;
    const from = pages.findIndex((page) => page.id === sourceId);
    const to = pages.findIndex((page) => page.id === targetId);
    if (from < 0 || to < 0) return;
    const next = [...pages];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    setPages(next.map((page, index) => ({ ...page, sort_order: index + 1 })));
    try {
      const updated = await api<DashboardPage[]>("/api/pages/reorder", {
        method: "POST",
        body: JSON.stringify({ ordered_ids: next.map((page) => page.id) }),
      }, auth.csrf_token);
      setPages(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save page order.");
      void loadStructure();
    }
  }

  const greeting = greetingForHour(new Date().getHours());

  function beginAdd() {
    setSelectedTemplate(null);
    setCatalogOpen(true);
  }

  async function exportDashboardLayout() {
    setError("");
    try {
      const layout = await api<Record<string, unknown>>("/api/dashboard/export");
      const blob = new Blob([JSON.stringify(layout, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `homelab-dashboard-layout-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to export dashboard layout."); }
  }

  async function importDashboardLayoutFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; event.target.value = "";
    if (!file) return;
    try {
      const layout = JSON.parse(await file.text()) as Record<string, unknown>;
      if (!window.confirm("Import this dashboard layout? Imported pages are added alongside your current pages. Passwords and API keys are never imported.")) return;
      await api<DashboardPage[]>("/api/dashboard/import", { method: "POST", body: JSON.stringify(layout) }, auth.csrf_token);
      await Promise.all([loadServices(), loadWidgets(), loadStructure()]);
      setSettingsOpen(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to import dashboard layout."); }
  }

  function chooseTemplate(entry: CatalogEntry) {
    setCatalogOpen(false);
    setSelectedTemplate(entry);
    setEditing(null);
  }

  function closeEditor() {
    setEditing(undefined);
    setSelectedTemplate(null);
  }

  async function selectTheme(themeId: string) {
    setAppearanceBusy(true);
    setAppearanceError("");
    try {
      setAppearance(await api<AppearanceSettings>("/api/appearance", { method: "PUT", body: JSON.stringify({ theme_id: themeId }) }, auth.csrf_token));
      await loadExtensions();
    } catch (err) {
      setAppearanceError(err instanceof Error ? err.message : "Unable to change theme.");
    } finally {
      setAppearanceBusy(false);
    }
  }

  async function importTheme(theme: ThemePackage) {
    setAppearanceBusy(true);
    setAppearanceError("");
    try {
      setAppearance(await api<AppearanceSettings>("/api/themes", { method: "POST", body: JSON.stringify(theme) }, auth.csrf_token));
      await loadExtensions();
    } catch (err) {
      setAppearanceError(err instanceof Error ? err.message : "Unable to import theme.");
    } finally {
      setAppearanceBusy(false);
    }
  }

  async function deleteTheme(themeId: string) {
    if (!window.confirm("Delete this imported theme?")) return;
    setAppearanceBusy(true);
    setAppearanceError("");
    try {
      setAppearance(await api<AppearanceSettings>(`/api/themes/${encodeURIComponent(themeId)}`, { method: "DELETE" }, auth.csrf_token));
      await loadExtensions();
    } catch (err) {
      setAppearanceError(err instanceof Error ? err.message : "Unable to delete theme.");
    } finally {
      setAppearanceBusy(false);
    }
  }

  const pageItemCount = (pageId: number) => services.filter((service) => service.page_id === pageId).length + widgets.filter((widget) => widget.page_id === pageId).length;
  const visibleItemCount = filtered.length + filteredWidgets.length;
  const availableUpdateCount = Object.values(updateStates).filter((item) => item.state === "available").length;
  const widgetSummary = {
    totalServices: services.filter((service) => service.enabled).length,
    onlineServices: Object.values(statuses).filter((item) => item.state === "online").length,
    offlineServices: Object.values(statuses).filter((item) => item.state === "offline").length,
    updatesAvailable: availableUpdateCount,
    connections: connections.length,
    services: services.filter((service) => service.enabled).map((service) => ({ id: service.id, name: service.name, state: statuses[service.id]?.state ?? (service.status_check ? "unknown" : "unchecked"), latency: statuses[service.id]?.latency_ms ?? null })),
    updates: services.filter((service) => service.management_provider !== "none").map((service) => ({ id: service.id, name: service.name, state: updateStates[service.id]?.state ?? "unknown", current: updateStates[service.id]?.current_version ?? null, latest: updateStates[service.id]?.latest_version ?? null })),
  };

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">{dashboardSettings.dashboard_title.toUpperCase()}</p>
          <h1>{dashboardSettings.show_greeting ? `${greeting}, ${auth.username}.` : dashboardSettings.dashboard_title}</h1>
          <p className="subhead">{activePage ? `${activePage.name} · your services and tools in one place.` : "Your services and tools in one place."}</p>
        </div>
        <div className="command-bar" ref={commandBarRef}>
          <button className={`command-button updates-command ${availableUpdateCount ? "has-attention" : ""}`} type="button" title={availableUpdateCount ? `${availableUpdateCount} update${availableUpdateCount === 1 ? "" : "s"} available` : "Updates"} onClick={() => { setAddMenuOpen(false); setAccountMenuOpen(false); setUpdatesOpen(true); void loadUpdateData(); }}>
            <ArrowUpCircle size={17} /><span className="command-label">Updates</span>{availableUpdateCount > 0 && <span className="command-badge">{availableUpdateCount}</span>}
          </button>
          <button className={`command-button ${manageMode ? "active" : ""}`} type="button" title={manageMode ? "Finish arranging dashboard" : "Manage dashboard"} onClick={() => { setAddMenuOpen(false); setAccountMenuOpen(false); setManageMode((value) => !value); }}><LayoutGrid size={17} /><span className="command-label">{manageMode ? "Done" : "Manage"}</span></button>
          <div className="command-menu-wrap">
            <button className={`command-button add-command ${addMenuOpen ? "active" : ""}`} type="button" aria-haspopup="menu" aria-expanded={addMenuOpen} onClick={() => { setAddMenuOpen((value) => !value); setAccountMenuOpen(false); }}><Plus size={18} /><span className="command-label">Add</span><ChevronDown className="command-chevron" size={14} /></button>
            {addMenuOpen && <div className="command-menu" role="menu">
              <button type="button" role="menuitem" onClick={() => { setAddMenuOpen(false); beginAdd(); }}><Plus size={16} /><span><strong>Add service</strong><small>Link or integrated application</small></span></button>
              <button type="button" role="menuitem" onClick={() => { setAddMenuOpen(false); setEditingWidget(null); }}><LayoutGrid size={16} /><span><strong>Add widget</strong><small>Clock, notes, status and more</small></span></button>
              <button type="button" role="menuitem" onClick={() => { setAddMenuOpen(false); setEditingPage(null); }}><Plus size={16} /><span><strong>Add page</strong><small>Create another dashboard page</small></span></button>
            </div>}
          </div>
          <div className="command-menu-wrap">
            <button className={`command-button account-command ${accountMenuOpen ? "active" : ""}`} type="button" aria-haspopup="menu" aria-expanded={accountMenuOpen} title="Dashboard menu" onClick={() => { setAccountMenuOpen((value) => !value); setAddMenuOpen(false); }}><Settings size={17} /><span className="command-label">Menu</span><ChevronDown className="command-chevron" size={14} /></button>
            {accountMenuOpen && <div className="command-menu command-menu-right" role="menu">
              <div className="command-menu-user"><strong>{auth.username}</strong><small>Administrator</small></div>
              <button type="button" role="menuitem" onClick={() => { setAccountMenuOpen(false); setSettingsOpen(true); void loadExtensions(); }}><Settings size={16} /><span><strong>Settings</strong><small>Dashboard, monitoring and extensions</small></span></button>
              <button type="button" role="menuitem" onClick={() => { setAccountMenuOpen(false); setConnectionsOpen(true); void loadConnections(); }}><Cable size={16} /><span><strong>Connections</strong><small>TrueNAS and future controllers</small></span></button>
              <button type="button" role="menuitem" onClick={() => { setAccountMenuOpen(false); setAppearanceError(""); setAppearanceOpen(true); }}><Palette size={16} /><span><strong>Appearance</strong><small>Themes and visual editor</small></span></button>
              <div className="command-menu-separator" />
              <button className="command-menu-danger" type="button" role="menuitem" onClick={onLogout}><LogOut size={16} /><span><strong>Sign out</strong></span></button>
            </div>}
          </div>
        </div>
      </header>

      <nav className="page-tabs" aria-label="Dashboard pages">
        <div className="page-tab-scroll">
          {pages.map((page) => (
            <div
              className={`page-tab-wrap ${page.id === activePageId ? "active" : ""} ${dragOverPageId === page.id ? "drag-over" : ""}`}
              key={page.id}
              draggable={manageMode}
              onDragStart={(event) => {
                if (!manageMode) { event.preventDefault(); return; }
                setDraggingPageId(page.id);
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", `page:${page.id}`);
              }}
              onDragOver={(event) => {
                if (manageMode && draggingPageId && draggingPageId !== page.id) {
                  event.preventDefault();
                  setDragOverPageId(page.id);
                }
              }}
              onDragLeave={() => dragOverPageId === page.id && setDragOverPageId(null)}
              onDrop={(event) => { event.preventDefault(); void dropPage(page.id); }}
              onDragEnd={() => { setDraggingPageId(null); setDragOverPageId(null); }}
            >
              <button className="page-tab" type="button" onClick={() => setActivePageId(page.id)}>
                <LayoutGrid size={15} />
                <span>{page.name}</span>
                <small>{pageItemCount(page.id)}</small>
              </button>
              {manageMode && (
                <button className="page-edit" type="button" aria-label={`Edit ${page.name} page`} title={`Edit ${page.name} page`} onClick={() => setEditingPage(page)}>
                  <Pencil size={13} />
                </button>
              )}
            </div>
          ))}
        </div>
        {manageMode && <button className="add-page-button" type="button" onClick={() => setEditingPage(null)}><Plus size={15} /> Add page</button>}
      </nav>

      <section className="toolbar" aria-label="Dashboard tools">
        <Search size={18} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Search ${activePage?.name ?? "dashboard"}`} aria-label="Search dashboard" />
        <span className="service-count">{visibleItemCount} item{visibleItemCount === 1 ? "" : "s"}</span>
        <button className="refresh-button" type="button" disabled={statusLoading || insightLoading} onClick={() => void refreshTelemetry()} title="Refresh service status">
          <RefreshCw className={statusLoading || insightLoading ? "spin" : ""} size={16} />
          <span>Refresh</span>
        </button>
      </section>

      {manageMode && (
        <div className="manage-hint">
          <GripVertical size={16} />
          <span>{query.trim() ? "Clear search to reorder. Manage mode also lets you arrange pages and categories." : "Drag page tabs, category headers, and cards to arrange the dashboard. Stars pin favorite cards."}</span>
        </div>
      )}

      {error && <div className="notice">{error}</div>}

      {!loading && visibleItemCount === 0 && !error && (
        <section className="empty-state">
          <div className="empty-icon"><LayoutGrid size={28} /></div>
          <h2>{services.length === 0 && widgets.length === 0 ? "Build your dashboard" : query.trim() ? "No matching items" : `${activePage?.name ?? "This page"} is empty`}</h2>
          <p>{services.length === 0 && widgets.length === 0 ? "Add a self-hosted service or your first dashboard widget." : query.trim() ? "Try a different search or add another item." : "Add services or widgets here, or move an existing item from its edit screen."}</p>
          {!query.trim() && <div className="empty-actions"><button className="primary" type="button" onClick={beginAdd}><Plus size={18} /> Add service</button><button className="secondary" type="button" onClick={() => setEditingWidget(null)}><Plus size={18} /> Add widget</button></div>}
        </section>
      )}

      {groups.map(([category, categoryItems]) => {
        const layout = pageCategories.find((item) => item.name.toLowerCase() === category.toLowerCase());
        const collapsed = !query.trim() && (layout?.collapsed ?? false);
        return (
          <section
            key={category}
            className={`section category-section ${dragOverCategory === category ? "category-drag-over" : ""}`}
          >
            <div
              className={`section-title category-header ${manageMode ? "category-manage" : ""}`}
              draggable={manageMode && !query.trim()}
              onDragStart={(event) => {
                if (!manageMode || query.trim()) { event.preventDefault(); return; }
                setDraggingCategory(category);
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", `category:${category}`);
              }}
              onDragOver={(event) => {
                if (draggingCategory && draggingCategory !== category && !query.trim()) {
                  event.preventDefault();
                  setDragOverCategory(category);
                }
              }}
              onDragLeave={() => dragOverCategory === category && setDragOverCategory(null)}
              onDrop={(event) => { event.preventDefault(); void dropCategory(category); }}
              onDragEnd={() => { setDraggingCategory(null); setDragOverCategory(null); }}
            >
              {manageMode && <span className="category-drag-handle" title="Drag category to reorder"><GripVertical size={15} /></span>}
              <CategoryIcon icon={layout?.icon} size={18} />
              <h2>{category}</h2>
              <span className="category-count">{categoryItems.length}</span>
              {manageMode && layout && <button className="category-edit-button" type="button" onClick={() => setEditingCategory(layout)} aria-label={`Customize ${category}`} title="Rename category or change icon"><Pencil size={14} /></button>}
              <button className="collapse-button" type="button" onClick={() => void toggleCategory(category)} aria-label={`${collapsed ? "Expand" : "Collapse"} ${category}`} title={collapsed ? "Expand category" : "Collapse category"}>
                {collapsed ? <ChevronRight size={18} /> : <ChevronDown size={18} />}
              </button>
            </div>
            {!collapsed && (
              <div className="grid">
                {categoryItems.map((dashboardItem) => {
                  if (dashboardItem.kind === "widget") {
                    const widget = dashboardItem.widget;
                    const key = `widget:${widget.id}`;
                    return <WidgetCard
                      key={key}
                      widget={widget}
                      manageMode={manageMode}
                      summary={widgetSummary}
                      dragOver={dragOverItemKey === key}
                      onEdit={(item) => setEditingWidget(item)}
                      onDragStart={(event) => { if (!manageMode || query.trim()) { event.preventDefault(); return; } event.stopPropagation(); setDraggingItem({ kind: "widget", id: widget.id, page_id: widget.page_id, category: widget.category, favorite: false }); setDraggingCategory(null); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", key); }}
                      onDragOver={(event) => { if (draggingItem?.page_id === widget.page_id && draggingItem.category === widget.category && !draggingItem.favorite && !(draggingItem.kind === "widget" && draggingItem.id === widget.id) && !query.trim()) { event.preventDefault(); event.stopPropagation(); setDragOverItemKey(key); } }}
                      onDragLeave={() => dragOverItemKey === key && setDragOverItemKey(null)}
                      onDrop={(event) => { event.preventDefault(); event.stopPropagation(); void dropDashboardItem({ kind: "widget", id: widget.id, page_id: widget.page_id, category: widget.category, favorite: false }); }}
                      onDragEnd={() => { setDraggingItem(null); setDragOverItemKey(null); }}
                    />;
                  }
                  const service = dashboardItem.service;
                  const key = `service:${service.id}`;
                  const serviceStatus = statusPresentation(service);
                  const insight = insights[service.id];
                  const updateState = updateStates[service.id];
                  const updateJob = updateJobs.find((job) => (job.service_id === service.id || job.active_service_id === service.id) && (job.state === "queued" || job.state === "running"));
                  return (
                    <article
                      className={`card card-${service.card_size} ${manageMode ? "managing-card" : ""} ${service.favorite ? "favorite-card" : ""} ${!service.enabled ? "disabled-card" : ""} ${serviceStatus.state === "offline" ? "offline-card" : ""} ${dragOverItemKey === key ? "drag-over" : ""}`}
                      key={key}
                      draggable={manageMode && !query.trim()}
                      onDragStart={(event) => {
                        if (!manageMode || query.trim()) { event.preventDefault(); return; }
                        event.stopPropagation();
                        setDraggingItem({ kind: "service", id: service.id, page_id: service.page_id, category: service.category, favorite: service.favorite });
                        setDraggingCategory(null);
                        event.dataTransfer.effectAllowed = "move";
                        event.dataTransfer.setData("text/plain", key);
                      }}
                      onDragOver={(event) => {
                        if (draggingItem?.page_id === service.page_id && draggingItem.category === service.category && draggingItem.favorite === service.favorite && !(draggingItem.kind === "service" && draggingItem.id === service.id) && !query.trim()) {
                          event.preventDefault(); event.stopPropagation(); event.dataTransfer.dropEffect = "move"; setDragOverItemKey(key);
                        }
                      }}
                      onDragLeave={() => dragOverItemKey === key && setDragOverItemKey(null)}
                      onDrop={(event) => { event.preventDefault(); event.stopPropagation(); void dropDashboardItem({ kind: "service", id: service.id, page_id: service.page_id, category: service.category, favorite: service.favorite }); }}
                      onDragEnd={() => { setDraggingItem(null); setDragOverItemKey(null); }}
                    >
                      <a className="card-link" href={service.url} target="_blank" rel="noreferrer" aria-label={`Open ${service.name}`} onClick={(event) => { if (manageMode) event.preventDefault(); }}>
                        <div className="icon" aria-hidden="true"><ServiceIcon service={service} /></div>
                        <div className="card-copy"><h3>{service.name}</h3><p>{TYPE_LABELS[service.type] ?? service.type}</p></div>
                        <span className={`status status-${serviceStatus.state}`} title={serviceStatus.title}><span />{serviceStatus.label}</span>
                        <div className={`card-detail-slot ${insight && insight.state !== "none" ? "has-detail" : "empty-detail"}`}>
                          {insight && insight.state !== "none" && (
                            <div className={`insight insight-${insight.state}`}>
                              {insight.summary && <strong>{insight.summary}</strong>}
                              {insight.secondary && <span>{insight.secondary}</span>}
                              {insight.activities?.[0] && <ActivityProgress activity={insight.activities[0]} additional={Math.max(0, insight.activities.length - 1)} />}
                              {insight.items.slice(0, 2).map((item) => <span className="insight-item" key={item}>{item}</span>)}
                            </div>
                          )}
                        </div>
                        <ExternalLink className="external" size={17} />
                      </a>
                      <CardManagementStatus service={service} state={updateState} job={updateJob} manageMode={manageMode} onUpdate={(item) => void startManagedUpdate(item)} />
                      {manageMode && (
                        <div className="card-controls">
                          <span className="drag-handle" title={query.trim() ? "Clear search to reorder" : service.favorite ? "Pinned cards reorder with other pinned cards" : "Drag to reorder with services and widgets"} aria-hidden="true"><GripVertical size={15} /></span>
                          <button className={`favorite-button ${service.favorite ? "active" : ""}`} type="button" onClick={() => void toggleFavorite(service)} aria-label={`${service.favorite ? "Unpin" : "Pin"} ${service.name}`} title={service.favorite ? "Unpin favorite" : "Pin favorite"}>
                            <Star size={15} fill={service.favorite ? "currentColor" : "none"} />
                          </button>
                          <button className="edit-button" type="button" onClick={() => setEditing(service)} aria-label={`Edit ${service.name}`} title={`Edit ${service.name}`}>
                            <Pencil size={15} />
                          </button>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        );
      })}

      <input ref={layoutImportRef} className="hidden-file" type="file" accept="application/json,.json" onChange={(event) => void importDashboardLayoutFile(event)} />

      <footer className="app-footer">Homelab Dashboard v{APP_VERSION}</footer>

      {settingsOpen && (
        <SettingsModal
          settings={dashboardSettings}
          extensions={extensions}
          currentTheme={BUILTIN_THEME_BY_ID[appearance.theme_id]?.name ?? appearance.custom_themes.find((theme) => theme.id === appearance.theme_id)?.name ?? appearance.theme_id}
          importedThemeCount={appearance.custom_themes.length}
          connections={connections}
          widgetCount={widgets.length}
          appVersion={APP_VERSION}
          onClose={() => setSettingsOpen(false)}
          onSave={saveSettings}
          onOpenAppearance={() => { setAppearanceError(""); setAppearanceOpen(true); }}
          onOpenConnections={() => { setConnectionsOpen(true); void loadConnections(); }}
          onAddWidget={() => setEditingWidget(null)}
          onExportDashboard={() => void exportDashboardLayout()}
          onImportDashboard={() => layoutImportRef.current?.click()}
          onRemoveTheme={async (themeId) => { await deleteTheme(themeId); await loadExtensions(); }}
        />
      )}

      {updatesOpen && (
        <UpdateManagerModal
          services={services}
          states={updateStates}
          jobs={updateJobs}
          busy={updateBusy}
          onClose={() => setUpdatesOpen(false)}
          onCheck={() => void checkForUpdates()}
          onUpdate={(service) => void startManagedUpdate(service)}
          onUpdateAll={() => void updateAllAvailable()}
        />
      )}

      {connectionsOpen && (
        <ConnectionsModal connections={connections} csrfToken={auth.csrf_token} onClose={() => setConnectionsOpen(false)} onChanged={async () => { await loadConnections(); await loadServices(); }} />
      )}

      {appearanceOpen && (
        <AppearanceModal
          appearance={appearance}
          busy={appearanceBusy}
          error={appearanceError}
          onClose={() => setAppearanceOpen(false)}
          onSelect={selectTheme}
          onImport={importTheme}
          onDelete={deleteTheme}
        />
      )}

      {editingCategory && <CategoryEditModal category={editingCategory} csrfToken={auth.csrf_token} onClose={() => setEditingCategory(null)} onSaved={async () => { await Promise.all([loadServices(), loadWidgets(), loadStructure()]); }} />}

      {editingWidget !== undefined && <WidgetModal widget={editingWidget} pages={pages} defaultPageId={activePageId} csrfToken={auth.csrf_token} api={api} onClose={() => setEditingWidget(undefined)} onChanged={async () => { await loadWidgets(); await loadStructure(); }} />}

      {catalogOpen && <ServiceCatalogModal onClose={() => setCatalogOpen(false)} onSelect={chooseTemplate} />}

      {editing !== undefined && (
        <ServiceModal
          service={editing}
          template={selectedTemplate}
          csrfToken={auth.csrf_token}
          pages={pages}
          defaultPageId={activePageId}
          allServices={services}
          connections={connections}
          onClose={closeEditor}
          onSaved={() => { closeEditor(); void loadServices(); void loadStructure(); void loadConnections(); void refreshTelemetry(); void loadUpdateData(); }}
          onDeleted={() => { closeEditor(); void loadServices(); void loadStructure(); void refreshTelemetry(); }}
        />
      )}

      {editingPage !== undefined && (
        <PageModal
          page={editingPage}
          itemCount={editingPage ? pageItemCount(editingPage.id) : 0}
          csrfToken={auth.csrf_token}
          onClose={() => setEditingPage(undefined)}
          onSaved={(saved) => {
            setEditingPage(undefined);
            setActivePageId(saved.id);
            void loadStructure();
          }}
          onDeleted={() => {
            setEditingPage(undefined);
            void loadStructure();
          }}
        />
      )}
    </main>
  );
}

function App() {
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [fatalError, setFatalError] = useState("");

  async function loadAuth() {
    try {
      setAuth(await api<AuthStatus>("/api/auth/status"));
    } catch (err) {
      setFatalError(err instanceof Error ? err.message : "Dashboard API is unavailable.");
    }
  }

  useEffect(() => { void loadAuth(); }, []);

  async function logout() {
    try { await api<void>("/api/auth/logout", { method: "POST" }); } finally { void loadAuth(); }
  }

  if (fatalError) return <main className="auth-shell"><div className="notice">{fatalError}</div></main>;
  if (!auth) return <main className="auth-shell"><div className="loading">Loading dashboard…</div></main>;
  if (!auth.authenticated) return <AuthScreen status={auth} onAuthenticated={setAuth} />;
  return <Dashboard auth={auth} onLogout={logout} />;
}

try {
  const cached = window.localStorage.getItem("homelab-dashboard-appearance");
  if (cached) {
    const parsed = JSON.parse(cached) as AppearanceSettings;
    applyTheme(resolveTheme(parsed.theme_id, parsed.custom_themes ?? []), parsed.theme_id);
  }
} catch {
  // Ignore stale or malformed local appearance cache; authenticated state will refresh it.
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
