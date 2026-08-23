import React, { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ChevronDown,
  ChevronRight,
  Download,
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
  has_auth_credentials: boolean;
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

type ServiceStatus = {
  id: number;
  state: "online" | "degraded" | "offline" | "disabled" | "unchecked";
  http_status?: number | null;
  latency_ms?: number | null;
  checked_at: string;
  detail?: string | null;
};

const APP_VERSION = "0.10.0";

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
}: {
  service: Service | null;
  template?: CatalogEntry | null;
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
  csrfToken?: string | null;
  pages: DashboardPage[];
  defaultPageId: number;
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
  } : { ...EMPTY_SERVICE, page_id: defaultPageId });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const selectedCatalogEntry = CATALOG_BY_TYPE[form.type];

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
  serviceCount,
  onClose,
  onSaved,
  onDeleted,
  csrfToken,
}: {
  page: DashboardPage | null;
  serviceCount: number;
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
          {page && !page.is_default && serviceCount > 0 && <small>Move or remove the {serviceCount} service{serviceCount === 1 ? "" : "s"} on this page before deleting it.</small>}
          {error && <div className="notice compact">{error}</div>}
          <div className="modal-actions">
            {page && !page.is_default && (
              <button className="danger-button" disabled={busy || serviceCount > 0} type="button" onClick={() => void remove()}>
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
          <button className="secondary" type="button" disabled={busy} onClick={() => fileInput.current?.click()}><Upload size={16} /> Import theme</button>
          <button className="secondary" type="button" onClick={downloadTemplate}><Download size={16} /> Theme template</button>
          <input ref={fileInput} className="hidden-file" type="file" accept="application/json,.json" onChange={(event) => void importFile(event)} />
          <span>Community theme format v1 · colors only · no CSS or JavaScript</span>
        </div>

        {error && <div className="notice appearance-error">{error}</div>}

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

function ServiceIcon({ service }: { service: Service }) {
  const brandedType = inferredServiceType(service);
  const entry = brandedType ? CATALOG_BY_TYPE[brandedType] : null;
  return <CatalogLogo entry={entry} fallback={service.icon ? <span className="custom-service-icon">{service.icon}</span> : <LinkIcon size={27} />} />;
}

function Dashboard({ auth, onLogout }: { auth: AuthStatus; onLogout: () => void }) {
  const [services, setServices] = useState<Service[]>([]);
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
  const [dragging, setDragging] = useState<{ id: number; page_id: number; category: string; favorite: boolean } | null>(null);
  const [dragOverId, setDragOverId] = useState<number | null>(null);
  const [draggingCategory, setDraggingCategory] = useState<string | null>(null);
  const [dragOverCategory, setDragOverCategory] = useState<string | null>(null);
  const [draggingPageId, setDraggingPageId] = useState<number | null>(null);
  const [dragOverPageId, setDragOverPageId] = useState<number | null>(null);
  const [appearance, setAppearance] = useState<AppearanceSettings>({ theme_id: "system", custom_themes: [] });
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  const [appearanceBusy, setAppearanceBusy] = useState(false);
  const [appearanceError, setAppearanceError] = useState("");

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

  async function refreshTelemetry() {
    await Promise.all([loadStatuses(), loadInsights()]);
  }

  useEffect(() => {
    void Promise.all([loadServices(), loadStructure(), loadAppearance()]);
    void refreshTelemetry();
    const timer = window.setInterval(() => { void refreshTelemetry(); }, 30000);
    return () => window.clearInterval(timer);
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

  const pageCategories = useMemo(() => {
    const layouts = categories
      .filter((category) => category.page_id === activePageId)
      .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name));
    const known = new Set(layouts.map((category) => category.name.toLowerCase()));
    const extras = Array.from(new Set(
      services.filter((service) => service.page_id === activePageId).map((service) => service.category),
    )).filter((name) => !known.has(name.toLowerCase())).sort((a, b) => a.localeCompare(b));
    return [...layouts, ...extras.map((name, index) => ({ page_id: activePageId, name, sort_order: 100000 + index, collapsed: false }))];
  }, [categories, services, activePageId]);

  const groups = useMemo(() => {
    const grouped = filtered.reduce<Record<string, Service[]>>((acc, service) => {
      (acc[service.category] ??= []).push(service);
      return acc;
    }, {});
    for (const categoryServices of Object.values(grouped)) {
      categoryServices.sort((a, b) => Number(b.favorite) - Number(a.favorite) || a.sort_order - b.sort_order || a.name.localeCompare(b.name));
    }
    const order = new Map(pageCategories.map((category, index) => [category.name.toLowerCase(), index]));
    return (Object.entries(grouped) as [string, Service[]][]).sort(([nameA], [nameB]) =>
      (order.get(nameA.toLowerCase()) ?? 999999) - (order.get(nameB.toLowerCase()) ?? 999999) || nameA.localeCompare(nameB),
    );
  }, [filtered, pageCategories]);

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

  async function dropService(target: Service) {
    const source = dragging;
    setDragging(null);
    setDragOverId(null);
    if (!source || source.id === target.id || source.page_id !== target.page_id || source.category !== target.category || source.favorite !== target.favorite || query.trim()) return;
    const categoryItems = services
      .filter((item) => item.page_id === target.page_id && item.category === target.category)
      .sort((a, b) => Number(b.favorite) - Number(a.favorite) || a.sort_order - b.sort_order || a.name.localeCompare(b.name));
    const from = categoryItems.findIndex((item) => item.id === source.id);
    const to = categoryItems.findIndex((item) => item.id === target.id);
    if (from < 0 || to < 0) return;
    const reordered = [...categoryItems];
    const [moved] = reordered.splice(from, 1);
    reordered.splice(to, 0, moved);
    const orderMap = new Map(reordered.map((item, index) => [item.id, index + 1]));
    setServices((current) => current.map((item) => item.page_id === target.page_id && item.category === target.category ? { ...item, sort_order: orderMap.get(item.id) ?? item.sort_order } : item));
    try {
      await api<Service[]>("/api/services/reorder", {
        method: "POST",
        body: JSON.stringify({ page_id: target.page_id, category: target.category, ordered_ids: reordered.map((item) => item.id) }),
      }, auth.csrf_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save card order.");
      void loadServices();
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
    } catch (err) {
      setAppearanceError(err instanceof Error ? err.message : "Unable to delete theme.");
    } finally {
      setAppearanceBusy(false);
    }
  }

  const pageServiceCount = (pageId: number) => services.filter((service) => service.page_id === pageId).length;

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">SELF-HOSTED CONTROL CENTER</p>
          <h1>{greeting}, {auth.username}.</h1>
          <p className="subhead">{activePage ? `${activePage.name} · your services and tools in one place.` : "Your services and tools in one place."}</p>
        </div>
        <div className="hero-actions">
          <button className="secondary" type="button" onClick={() => { setAppearanceError(""); setAppearanceOpen(true); }}><Palette size={17} /> Appearance</button>
          <button className={`secondary ${manageMode ? "active" : ""}`} type="button" onClick={() => setManageMode((value) => !value)}><Settings size={17} /> {manageMode ? "Done" : "Manage"}</button>
          <button className="secondary" type="button" onClick={onLogout}><LogOut size={17} /> Sign out</button>
          <button className="primary" type="button" onClick={beginAdd}><Plus size={18} /> Add service</button>
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
                <small>{pageServiceCount(page.id)}</small>
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
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Search ${activePage?.name ?? "services"}`} aria-label="Search services" />
        <span className="service-count">{filtered.length} service{filtered.length === 1 ? "" : "s"}</span>
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

      {!loading && filtered.length === 0 && !error && (
        <section className="empty-state">
          <div className="empty-icon"><LayoutGrid size={28} /></div>
          <h2>{services.length === 0 ? "Build your dashboard" : query.trim() ? "No matching services" : `${activePage?.name ?? "This page"} is empty`}</h2>
          <p>{services.length === 0 ? "Add your first self-hosted service, server tool, or generic link." : query.trim() ? "Try a different search or add another service." : "Add services here or move an existing card to this page from its edit screen."}</p>
          {!query.trim() && <button className="primary" type="button" onClick={beginAdd}><Plus size={18} /> Add service</button>}
        </section>
      )}

      {groups.map(([category, categoryServices]) => {
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
              <Server size={18} />
              <h2>{category}</h2>
              <span className="category-count">{categoryServices.length}</span>
              <button className="collapse-button" type="button" onClick={() => void toggleCategory(category)} aria-label={`${collapsed ? "Expand" : "Collapse"} ${category}`} title={collapsed ? "Expand category" : "Collapse category"}>
                {collapsed ? <ChevronRight size={18} /> : <ChevronDown size={18} />}
              </button>
            </div>
            {!collapsed && (
              <div className="grid">
                {categoryServices.map((service) => {
                  const serviceStatus = statusPresentation(service);
                  const insight = insights[service.id];
                  return (
                    <article
                      className={`card card-${service.card_size} ${manageMode ? "managing-card" : ""} ${service.favorite ? "favorite-card" : ""} ${!service.enabled ? "disabled-card" : ""} ${serviceStatus.state === "offline" ? "offline-card" : ""} ${dragOverId === service.id ? "drag-over" : ""}`}
                      key={service.id}
                      draggable={manageMode && !query.trim()}
                      onDragStart={(event) => {
                        if (!manageMode || query.trim()) { event.preventDefault(); return; }
                        event.stopPropagation();
                        setDragging({ id: service.id, page_id: service.page_id, category: service.category, favorite: service.favorite });
                        setDraggingCategory(null);
                        event.dataTransfer.effectAllowed = "move";
                        event.dataTransfer.setData("text/plain", String(service.id));
                      }}
                      onDragOver={(event) => {
                        if (dragging?.page_id === service.page_id && dragging.category === service.category && dragging.favorite === service.favorite && dragging.id !== service.id && !query.trim()) {
                          event.preventDefault();
                          event.stopPropagation();
                          event.dataTransfer.dropEffect = "move";
                          setDragOverId(service.id);
                        }
                      }}
                      onDragLeave={() => dragOverId === service.id && setDragOverId(null)}
                      onDrop={(event) => { event.preventDefault(); event.stopPropagation(); void dropService(service); }}
                      onDragEnd={() => { setDragging(null); setDragOverId(null); }}
                    >
                      <a className="card-link" href={service.url} target="_blank" rel="noreferrer" aria-label={`Open ${service.name}`} onClick={(event) => { if (manageMode) event.preventDefault(); }}>
                        <div className="icon" aria-hidden="true"><ServiceIcon service={service} /></div>
                        <div className="card-copy"><h3>{service.name}</h3><p>{TYPE_LABELS[service.type] ?? service.type}</p></div>
                        <span className={`status status-${serviceStatus.state}`} title={serviceStatus.title}><span />{serviceStatus.label}</span>
                        {insight && insight.state !== "none" && (
                          <div className={`insight insight-${insight.state}`}>
                            {insight.summary && <strong>{insight.summary}</strong>}
                            {insight.secondary && <span>{insight.secondary}</span>}
                            {insight.activities?.[0] && <ActivityProgress activity={insight.activities[0]} additional={Math.max(0, insight.activities.length - 1)} />}
                            {insight.items.slice(0, 2).map((item) => <span className="insight-item" key={item}>{item}</span>)}
                          </div>
                        )}
                        <ExternalLink className="external" size={17} />
                      </a>
                      {manageMode && (
                        <div className="card-controls">
                          <span className="drag-handle" title={query.trim() ? "Clear search to reorder" : "Drag to reorder"} aria-hidden="true"><GripVertical size={15} /></span>
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

      <footer className="app-footer">Homelab Dashboard v{APP_VERSION}</footer>

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

      {catalogOpen && <ServiceCatalogModal onClose={() => setCatalogOpen(false)} onSelect={chooseTemplate} />}

      {editing !== undefined && (
        <ServiceModal
          service={editing}
          template={selectedTemplate}
          csrfToken={auth.csrf_token}
          pages={pages}
          defaultPageId={activePageId}
          onClose={closeEditor}
          onSaved={() => { closeEditor(); void loadServices(); void loadStructure(); void refreshTelemetry(); }}
          onDeleted={() => { closeEditor(); void loadServices(); void loadStructure(); void refreshTelemetry(); }}
        />
      )}

      {editingPage !== undefined && (
        <PageModal
          page={editingPage}
          serviceCount={editingPage ? pageServiceCount(editingPage.id) : 0}
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
