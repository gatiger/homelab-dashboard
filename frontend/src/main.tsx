import React, { FormEvent, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ExternalLink,
  GripVertical,
  Link as LinkIcon,
  LogOut,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Server,
  Settings,
  Star,
  Trash2,
  X,
} from "lucide-react";
import "./styles.css";
import { CATALOG_BY_TYPE, CATALOG_CATEGORIES, SERVICE_CATALOG, catalogSearchText, urlPlaceholder, type CatalogEntry } from "./serviceCatalog";

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
  icon?: string | null;
  enabled: boolean;
  status_check: boolean;
  favorite: boolean;
  card_size: "compact" | "standard" | "wide";
  sort_order: number;
  created_at: string;
  updated_at: string;
  has_api_key: boolean;
};

type ServiceForm = {
  name: string;
  type: string;
  url: string;
  category: string;
  icon: string;
  enabled: boolean;
  status_check: boolean;
  favorite: boolean;
  card_size: "compact" | "standard" | "wide";
  sort_order: number;
  api_key: string;
  clear_api_key: boolean;
};

type ServiceInsight = {
  id: number;
  kind: string;
  state: "ok" | "setup" | "unavailable" | "none";
  summary?: string | null;
  secondary?: string | null;
  items: string[];
};

type ServiceStatus = {
  id: number;
  state: "online" | "degraded" | "offline" | "disabled" | "unchecked";
  http_status?: number | null;
  latency_ms?: number | null;
  checked_at: string;
  detail?: string | null;
};

const APP_VERSION = "0.6.0";

const EMPTY_SERVICE: ServiceForm = {
  name: "",
  type: "link",
  url: "https://",
  category: "General",
  icon: "",
  enabled: true,
  status_check: true,
  favorite: false,
  card_size: "standard",
  sort_order: 0,
  api_key: "",
  clear_api_key: false,
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
                  {entry.integration === "jellyfin" && <small className="integration-tag">API integration</small>}
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
}: {
  service: Service | null;
  template?: CatalogEntry | null;
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
  csrfToken?: string | null;
}) {
  const initialTemplate = template ?? (service ? CATALOG_BY_TYPE[service.type] : null);
  const [form, setForm] = useState<ServiceForm>(service ? {
    name: service.name,
    type: service.type,
    url: service.url,
    category: service.category,
    icon: service.icon ?? "",
    enabled: service.enabled,
    status_check: service.status_check,
    favorite: service.favorite,
    card_size: service.card_size,
    sort_order: service.sort_order,
    api_key: "",
    clear_api_key: false,
  } : initialTemplate ? {
    name: ["link", "other"].includes(initialTemplate.type) ? "" : initialTemplate.name,
    type: initialTemplate.type,
    url: `${initialTemplate.defaultScheme ?? "http"}://`,
    category: initialTemplate.category === "Custom" ? "General" : initialTemplate.category,
    icon: "",
    enabled: true,
    status_check: true,
    favorite: false,
    card_size: "standard",
    sort_order: 0,
    api_key: "",
    clear_api_key: false,
  } : EMPTY_SERVICE);
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
      const payload = { ...form, icon: form.icon.trim() || null, api_key: form.api_key.trim() || null };
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
          {form.type === "jellyfin" && (
            <>
              <label className="span-2">
                <span>Jellyfin API key <small>optional, enables stream details</small></span>
                <input
                  type="password"
                  value={form.api_key}
                  onChange={(event) => setField("api_key", event.target.value)}
                  placeholder={service?.has_api_key ? "API key saved — leave blank to keep it" : "Paste Jellyfin API key"}
                  autoComplete="off"
                />
                <small>The key is encrypted before it is stored by the dashboard.</small>
              </label>
              {service?.has_api_key && (
                <label className="check-row span-2">
                  <input type="checkbox" checked={form.clear_api_key} onChange={(event) => setField("clear_api_key", event.target.checked)} />
                  <span>Remove the saved Jellyfin API key</span>
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
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Service | null | undefined>(undefined);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<CatalogEntry | null>(null);
  const [manageMode, setManageMode] = useState(false);
  const [statuses, setStatuses] = useState<Record<number, ServiceStatus>>({});
  const [statusLoading, setStatusLoading] = useState(false);
  const [insights, setInsights] = useState<Record<number, ServiceInsight>>({});
  const [insightLoading, setInsightLoading] = useState(false);
  const [dragging, setDragging] = useState<{ id: number; category: string; favorite: boolean } | null>(null);
  const [dragOverId, setDragOverId] = useState<number | null>(null);

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
    void loadServices();
    void refreshTelemetry();
    const timer = window.setInterval(() => { void refreshTelemetry(); }, 30000);
    return () => window.clearInterval(timer);
  }, []);

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

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const visible = manageMode ? services : services.filter((service) => service.enabled);
    if (!normalized) return visible;
    return visible.filter((service) =>
      `${service.name} ${service.category} ${service.type}`.toLowerCase().includes(normalized),
    );
  }, [query, services, manageMode]);

  const groups = useMemo(() => {
    const grouped = filtered.reduce<Record<string, Service[]>>((acc, service) => {
      (acc[service.category] ??= []).push(service);
      return acc;
    }, {});
    for (const categoryServices of Object.values(grouped)) {
      categoryServices.sort((a, b) => Number(b.favorite) - Number(a.favorite) || a.sort_order - b.sort_order || a.name.localeCompare(b.name));
    }
    return grouped;
  }, [filtered]);

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
    if (!source || source.id === target.id || source.category !== target.category || source.favorite !== target.favorite || query.trim()) return;
    const categoryItems = services
      .filter((item) => item.category === target.category)
      .sort((a, b) => Number(b.favorite) - Number(a.favorite) || a.sort_order - b.sort_order || a.name.localeCompare(b.name));
    const from = categoryItems.findIndex((item) => item.id === source.id);
    const to = categoryItems.findIndex((item) => item.id === target.id);
    if (from < 0 || to < 0) return;
    const reordered = [...categoryItems];
    const [moved] = reordered.splice(from, 1);
    reordered.splice(to, 0, moved);
    const orderMap = new Map(reordered.map((item, index) => [item.id, index + 1]));
    setServices((current) => current.map((item) => item.category === target.category ? { ...item, sort_order: orderMap.get(item.id) ?? item.sort_order } : item));
    try {
      await api<Service[]>("/api/services/reorder", {
        method: "POST",
        body: JSON.stringify({ category: target.category, ordered_ids: reordered.map((item) => item.id) }),
      }, auth.csrf_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save card order.");
      void loadServices();
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

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">SELF-HOSTED CONTROL CENTER</p>
          <h1>{greeting}, {auth.username}.</h1>
          <p className="subhead">Your services and tools in one place.</p>
        </div>
        <div className="hero-actions">
          <button className={`secondary ${manageMode ? "active" : ""}`} type="button" onClick={() => setManageMode((value) => !value)}><Settings size={17} /> {manageMode ? "Done" : "Manage"}</button>
          <button className="secondary" type="button" onClick={onLogout}><LogOut size={17} /> Sign out</button>
          <button className="primary" type="button" onClick={beginAdd}><Plus size={18} /> Add service</button>
        </div>
      </header>

      <section className="toolbar" aria-label="Dashboard tools">
        <Search size={18} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search services" aria-label="Search services" />
        <span className="service-count">{filtered.length} service{filtered.length === 1 ? "" : "s"}</span>
        <button className="refresh-button" type="button" disabled={statusLoading || insightLoading} onClick={() => void refreshTelemetry()} title="Refresh service status">
          <RefreshCw className={statusLoading || insightLoading ? "spin" : ""} size={16} />
          <span>Refresh</span>
        </button>
      </section>

      {manageMode && (
        <div className="manage-hint">
          <GripVertical size={16} />
          <span>{query.trim() ? "Clear search to drag cards. Use the star to pin favorites and the pencil to change card size." : "Drag cards to reorder within a category. Use the star to pin favorites and the pencil to change card size."}</span>
        </div>
      )}

      {error && <div className="notice">{error}</div>}

      {!loading && filtered.length === 0 && !error && (
        <section className="empty-state">
          <div className="empty-icon"><Settings size={28} /></div>
          <h2>{services.length === 0 ? "Build your dashboard" : "No matching services"}</h2>
          <p>{services.length === 0 ? "Add your first Dockge-hosted service, server tool, or generic link." : "Try a different search or add another service."}</p>
          {services.length === 0 && <button className="primary" type="button" onClick={beginAdd}><Plus size={18} /> Add first service</button>}
        </section>
      )}

      {(Object.entries(groups) as [string, Service[]][]).map(([category, categoryServices]) => (
        <section key={category} className="section">
          <div className="section-title"><Server size={18} /><h2>{category}</h2></div>
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
                    setDragging({ id: service.id, category: service.category, favorite: service.favorite });
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", String(service.id));
                  }}
                  onDragOver={(event) => {
                    if (dragging?.category === service.category && dragging.favorite === service.favorite && dragging.id !== service.id && !query.trim()) {
                      event.preventDefault();
                      event.dataTransfer.dropEffect = "move";
                      setDragOverId(service.id);
                    }
                  }}
                  onDragLeave={() => dragOverId === service.id && setDragOverId(null)}
                  onDrop={(event) => { event.preventDefault(); void dropService(service); }}
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
        </section>
      ))}

      <footer className="app-footer">Homelab Dashboard v{APP_VERSION}</footer>

      {catalogOpen && <ServiceCatalogModal onClose={() => setCatalogOpen(false)} onSelect={chooseTemplate} />}

      {editing !== undefined && (
        <ServiceModal
          service={editing}
          template={selectedTemplate}
          csrfToken={auth.csrf_token}
          onClose={closeEditor}
          onSaved={() => { closeEditor(); void loadServices(); void refreshTelemetry(); }}
          onDeleted={() => { closeEditor(); void loadServices(); void refreshTelemetry(); }}
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

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
