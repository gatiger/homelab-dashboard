import React, { FormEvent, useEffect, useMemo, useState } from "react";
import { ArrowUpCircle, Bookmark, CheckCircle2, Clock, FileText, Gauge, GripVertical, Pencil, Server, Plus, Trash2, X } from "lucide-react";

export type DashboardWidgetType = "clock" | "note" | "bookmarks" | "system_summary" | "service_status" | "update_overview";

export type DashboardWidget = {
  id: number;
  type: DashboardWidgetType;
  title: string;
  page_id: number;
  category: string;
  card_size: "compact" | "standard" | "wide";
  sort_order: number;
  enabled: boolean;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type DashboardPageRef = { id: number; name: string };

export type WidgetSummary = {
  totalServices: number;
  onlineServices: number;
  offlineServices: number;
  updatesAvailable: number;
  connections: number;
  services: { id: number; name: string; state: string; latency?: number | null }[];
  updates: { id: number; name: string; state: string; current?: string | null; latest?: string | null }[];
};

type WidgetForm = Omit<DashboardWidget, "id" | "created_at" | "updated_at">;

type ApiFn = <T>(path: string, options?: RequestInit, csrfToken?: string | null) => Promise<T>;

const DEFAULT_FORM: WidgetForm = {
  type: "clock",
  title: "Clock",
  page_id: 1,
  category: "Widgets",
  card_size: "standard",
  sort_order: 0,
  enabled: true,
  config: { format: "12", show_seconds: false, show_date: true, timezone: "local" },
};

export const WIDGET_TYPES: { type: DashboardWidgetType; name: string; description: string }[] = [
  { type: "clock", name: "Clock & date", description: "Local or named-time-zone clock with optional date and seconds." },
  { type: "note", name: "Note", description: "A persistent text note for reminders, status messages, or instructions." },
  { type: "bookmarks", name: "Bookmarks", description: "A compact set of quick links that opens in new tabs." },
  { type: "system_summary", name: "Dashboard summary", description: "Online/offline service counts, pending updates, and configured connections." },
  { type: "service_status", name: "Service status", description: "A live compact list of service health and latency." },
  { type: "update_overview", name: "Update overview", description: "Services with pending updates, plus optional current services." },
];

function iconFor(type: DashboardWidgetType, size = 22) {
  if (type === "clock") return <Clock size={size} />;
  if (type === "note") return <FileText size={size} />;
  if (type === "bookmarks") return <Bookmark size={size} />;
  if (type === "service_status") return <Server size={size} />;
  if (type === "update_overview") return <ArrowUpCircle size={size} />;
  return <Gauge size={size} />;
}

function defaultConfig(type: DashboardWidgetType): Record<string, unknown> {
  if (type === "clock") return { format: "12", show_seconds: false, show_date: true, timezone: "local" };
  if (type === "note") return { text: "" };
  if (type === "bookmarks") return { items: [] };
  if (type === "service_status") return { limit: 6, show_latency: true };
  if (type === "update_overview") return { limit: 6, show_current: false };
  return { show_services: true, show_updates: true, show_connections: true };
}

function parseBookmarks(text: string) {
  return text.split("\n").map((line) => line.trim()).filter(Boolean).slice(0, 12).map((line) => {
    const separator = line.indexOf("|");
    if (separator < 0) return { label: line, url: "" };
    return { label: line.slice(0, separator).trim(), url: line.slice(separator + 1).trim() };
  }).filter((item) => item.label && /^https?:\/\//i.test(item.url));
}

function bookmarkText(config: Record<string, unknown>) {
  const items = Array.isArray(config.items) ? config.items : [];
  return items.map((item) => {
    if (!item || typeof item !== "object") return "";
    const value = item as Record<string, unknown>;
    return `${String(value.label ?? "")} | ${String(value.url ?? "")}`;
  }).filter(Boolean).join("\n");
}

export function WidgetModal({
  widget,
  pages,
  defaultPageId,
  csrfToken,
  api,
  onClose,
  onChanged,
}: {
  widget: DashboardWidget | null;
  pages: DashboardPageRef[];
  defaultPageId: number;
  csrfToken?: string | null;
  api: ApiFn;
  onClose: () => void;
  onChanged: () => Promise<void> | void;
}) {
  const [form, setForm] = useState<WidgetForm>(() => widget ? {
    type: widget.type,
    title: widget.title,
    page_id: widget.page_id,
    category: widget.category,
    card_size: widget.card_size,
    sort_order: widget.sort_order,
    enabled: widget.enabled,
    config: { ...widget.config },
  } : { ...DEFAULT_FORM, page_id: defaultPageId, config: { ...DEFAULT_FORM.config } });
  const [bookmarks, setBookmarks] = useState(() => widget?.type === "bookmarks" ? bookmarkText(widget.config) : "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function changeType(type: DashboardWidgetType) {
    const template = WIDGET_TYPES.find((item) => item.type === type);
    setForm((current) => ({ ...current, type, title: widget ? current.title : template?.name ?? current.title, config: defaultConfig(type) }));
    if (type === "bookmarks") setBookmarks("");
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = { ...form, config: form.type === "bookmarks" ? { items: parseBookmarks(bookmarks) } : form.config };
      await api<DashboardWidget>(widget ? `/api/widgets/${widget.id}` : "/api/widgets", { method: widget ? "PUT" : "POST", body: JSON.stringify(payload) }, csrfToken);
      await onChanged();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save widget.");
    } finally { setBusy(false); }
  }

  async function remove() {
    if (!widget || !window.confirm(`Delete the ${widget.title} widget?`)) return;
    setBusy(true);
    try {
      await api<void>(`/api/widgets/${widget.id}`, { method: "DELETE" }, csrfToken);
      await onChanged();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete widget.");
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.currentTarget === event.target && onClose()}>
      <section className="modal widget-modal" role="dialog" aria-modal="true" aria-labelledby="widget-modal-title">
        <header className="modal-header">
          <div><p className="eyebrow">DASHBOARD WIDGET</p><h2 id="widget-modal-title">{widget ? `Edit ${widget.title}` : "Add widget"}</h2><p className="modal-subhead">Widgets live alongside service cards but do not need a service URL.</p></div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close"><X size={20} /></button>
        </header>
        <form className="form-grid" onSubmit={save}>
          <label><span>Widget type</span><select value={form.type} onChange={(event) => changeType(event.target.value as DashboardWidgetType)}>{WIDGET_TYPES.map((item) => <option key={item.type} value={item.type}>{item.name}</option>)}</select></label>
          <label><span>Title</span><input value={form.title} maxLength={80} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} required /></label>
          <label><span>Dashboard page</span><select value={form.page_id} onChange={(event) => setForm((current) => ({ ...current, page_id: Number(event.target.value) }))}>{pages.map((page) => <option key={page.id} value={page.id}>{page.name}</option>)}</select></label>
          <label><span>Category</span><input value={form.category} maxLength={80} onChange={(event) => setForm((current) => ({ ...current, category: event.target.value }))} required /></label>
          <label><span>Card size</span><select value={form.card_size} onChange={(event) => setForm((current) => ({ ...current, card_size: event.target.value as WidgetForm["card_size"] }))}><option value="compact">Compact</option><option value="standard">Standard</option><option value="wide">Wide</option></select></label>
          <label className="check-row"><input type="checkbox" checked={form.enabled} onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))} /><span>Show this widget</span></label>

          {form.type === "clock" && <>
            <label><span>Time format</span><select value={String(form.config.format ?? "12")} onChange={(event) => setForm((current) => ({ ...current, config: { ...current.config, format: event.target.value } }))}><option value="12">12-hour</option><option value="24">24-hour</option></select></label>
            <label><span>Time zone</span><input value={String(form.config.timezone ?? "local")} onChange={(event) => setForm((current) => ({ ...current, config: { ...current.config, timezone: event.target.value } }))} placeholder="local or America/New_York" /><small>Use <strong>local</strong> to follow the viewing device.</small></label>
            <label className="check-row"><input type="checkbox" checked={Boolean(form.config.show_date ?? true)} onChange={(event) => setForm((current) => ({ ...current, config: { ...current.config, show_date: event.target.checked } }))} /><span>Show date</span></label>
            <label className="check-row"><input type="checkbox" checked={Boolean(form.config.show_seconds ?? false)} onChange={(event) => setForm((current) => ({ ...current, config: { ...current.config, show_seconds: event.target.checked } }))} /><span>Show seconds</span></label>
          </>}

          {form.type === "note" && <label className="span-2"><span>Note</span><textarea rows={8} maxLength={4000} value={String(form.config.text ?? "")} onChange={(event) => setForm((current) => ({ ...current, config: { text: event.target.value } }))} placeholder="Add a reminder, instruction, or status note…" /></label>}

          {form.type === "bookmarks" && <label className="span-2"><span>Bookmarks</span><textarea rows={8} value={bookmarks} onChange={(event) => setBookmarks(event.target.value)} placeholder={"Sonarr | http://192.168.1.10:8989\nDocumentation | https://example.com"} /><small>One link per line using <strong>Label | https://address</strong>. Up to 12 links.</small></label>}

          {form.type === "system_summary" && <div className="span-2 widget-option-stack">
            <label className="check-row"><input type="checkbox" checked={Boolean(form.config.show_services ?? true)} onChange={(event) => setForm((current) => ({ ...current, config: { ...current.config, show_services: event.target.checked } }))} /><span>Show service health counts</span></label>
            <label className="check-row"><input type="checkbox" checked={Boolean(form.config.show_updates ?? true)} onChange={(event) => setForm((current) => ({ ...current, config: { ...current.config, show_updates: event.target.checked } }))} /><span>Show pending updates</span></label>
            <label className="check-row"><input type="checkbox" checked={Boolean(form.config.show_connections ?? true)} onChange={(event) => setForm((current) => ({ ...current, config: { ...current.config, show_connections: event.target.checked } }))} /><span>Show management connections</span></label>
          </div>}

          {form.type === "service_status" && <>
            <label><span>Maximum services</span><select value={Number(form.config.limit ?? 6)} onChange={(event) => setForm((current) => ({ ...current, config: { ...current.config, limit: Number(event.target.value) } }))}>{[3,4,6,8,10,12].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
            <label className="check-row"><input type="checkbox" checked={Boolean(form.config.show_latency ?? true)} onChange={(event) => setForm((current) => ({ ...current, config: { ...current.config, show_latency: event.target.checked } }))} /><span>Show response latency</span></label>
          </>}

          {form.type === "update_overview" && <>
            <label><span>Maximum services</span><select value={Number(form.config.limit ?? 6)} onChange={(event) => setForm((current) => ({ ...current, config: { ...current.config, limit: Number(event.target.value) } }))}>{[3,4,6,8,10,12].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
            <label className="check-row"><input type="checkbox" checked={Boolean(form.config.show_current ?? false)} onChange={(event) => setForm((current) => ({ ...current, config: { ...current.config, show_current: event.target.checked } }))} /><span>Also show up-to-date services</span></label>
          </>}

          {error && <div className="notice compact span-2">{error}</div>}
          <div className="modal-actions span-2">
            {widget && <button className="danger-button" type="button" disabled={busy} onClick={() => void remove()}><Trash2 size={16} /> Delete widget</button>}
            <div className="action-spacer" />
            <button className="secondary" type="button" disabled={busy} onClick={onClose}>Cancel</button>
            <button className="primary" type="submit" disabled={busy}><Plus size={16} /> {busy ? "Saving…" : widget ? "Save widget" : "Add widget"}</button>
          </div>
        </form>
      </section>
    </div>
  );
}

function formatWidgetTime(now: Date, config: Record<string, unknown>) {
  const timezone = String(config.timezone ?? "local");
  const options: Intl.DateTimeFormatOptions = {
    hour: "numeric", minute: "2-digit", second: Boolean(config.show_seconds) ? "2-digit" : undefined,
    hour12: String(config.format ?? "12") !== "24",
    timeZone: timezone === "local" ? undefined : timezone,
  };
  try { return new Intl.DateTimeFormat(undefined, options).format(now); }
  catch { return new Intl.DateTimeFormat(undefined, { ...options, timeZone: undefined }).format(now); }
}

function formatWidgetDate(now: Date, config: Record<string, unknown>) {
  const timezone = String(config.timezone ?? "local");
  const options: Intl.DateTimeFormatOptions = { weekday: "long", month: "long", day: "numeric", timeZone: timezone === "local" ? undefined : timezone };
  try { return new Intl.DateTimeFormat(undefined, options).format(now); }
  catch { return new Intl.DateTimeFormat(undefined, { ...options, timeZone: undefined }).format(now); }
}

export function WidgetCard({ widget, manageMode, summary, dragOver = false, onEdit, onDragStart, onDragOver, onDragLeave, onDrop, onDragEnd }: {
  widget: DashboardWidget;
  manageMode: boolean;
  summary: WidgetSummary;
  dragOver?: boolean;
  onEdit: (widget: DashboardWidget) => void;
  onDragStart?: (event: React.DragEvent<HTMLElement>) => void;
  onDragOver?: (event: React.DragEvent<HTMLElement>) => void;
  onDragLeave?: () => void;
  onDrop?: (event: React.DragEvent<HTMLElement>) => void;
  onDragEnd?: () => void;
}) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    if (widget.type !== "clock") return;
    const timer = window.setInterval(() => setNow(new Date()), Boolean(widget.config.show_seconds) ? 1000 : 15000);
    return () => window.clearInterval(timer);
  }, [widget.type, widget.config.show_seconds]);

  const bookmarks = useMemo(() => Array.isArray(widget.config.items) ? widget.config.items.filter((item): item is Record<string, unknown> => !!item && typeof item === "object") : [], [widget.config.items]);

  return (
    <article className={`card card-${widget.card_size} widget-card ${manageMode ? "managing-card" : ""} ${!widget.enabled ? "disabled-card" : ""} ${dragOver ? "drag-over" : ""}`} draggable={manageMode} onDragStart={onDragStart} onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop} onDragEnd={onDragEnd}>
      <div className="widget-inner">
        <div className="widget-heading"><div className="widget-icon">{iconFor(widget.type)}</div><div><h3>{widget.title}</h3><p>{WIDGET_TYPES.find((item) => item.type === widget.type)?.name}</p></div></div>
        <div className="widget-content">
          {widget.type === "clock" && <div className="clock-widget"><strong>{formatWidgetTime(now, widget.config)}</strong>{Boolean(widget.config.show_date ?? true) && <span>{formatWidgetDate(now, widget.config)}</span>}</div>}
          {widget.type === "note" && <p className="note-widget">{String(widget.config.text ?? "") || "No note text yet."}</p>}
          {widget.type === "bookmarks" && <div className="bookmark-widget">{bookmarks.length ? bookmarks.map((item, index) => <a key={`${String(item.url)}-${index}`} href={String(item.url)} target="_blank" rel="noreferrer"><Bookmark size={13} /><span>{String(item.label)}</span></a>) : <span className="widget-muted">No bookmarks configured.</span>}</div>}
          {widget.type === "system_summary" && <div className="summary-widget">
            {Boolean(widget.config.show_services ?? true) && <><div><span>Online</span><strong className="summary-good">{summary.onlineServices}</strong></div><div><span>Offline</span><strong className={summary.offlineServices ? "summary-bad" : ""}>{summary.offlineServices}</strong></div><div><span>Services</span><strong>{summary.totalServices}</strong></div></>}
            {Boolean(widget.config.show_updates ?? true) && <div><span>Updates</span><strong className={summary.updatesAvailable ? "summary-attention" : "summary-good"}>{summary.updatesAvailable}</strong></div>}
            {Boolean(widget.config.show_connections ?? true) && <div><span>Connections</span><strong>{summary.connections}</strong></div>}
          </div>}
          {widget.type === "service_status" && <div className="status-list-widget">{summary.services.slice(0, Number(widget.config.limit ?? 6)).map((service) => <div key={service.id}><span className={`mini-status-dot mini-${service.state}`} /><strong>{service.name}</strong><small>{service.state === "online" ? (Boolean(widget.config.show_latency ?? true) && service.latency ? `${service.latency} ms` : "Online") : service.state}</small></div>)}{summary.services.length === 0 && <span className="widget-muted">No services configured.</span>}</div>}
          {widget.type === "update_overview" && <div className="status-list-widget">{summary.updates.filter((item) => item.state === "available" || Boolean(widget.config.show_current ?? false) && item.state === "current").slice(0, Number(widget.config.limit ?? 6)).map((item) => <div key={item.id}><span className={`mini-status-dot ${item.state === "available" ? "mini-available" : "mini-online"}`} />{item.state === "available" ? <ArrowUpCircle size={13} /> : <CheckCircle2 size={13} />}<strong>{item.name}</strong><small>{item.state === "available" ? (item.latest && item.latest !== item.current ? `${item.current ?? "?"} → ${item.latest}` : "Update available") : "Up to date"}</small></div>)}{summary.updates.filter((item) => item.state === "available").length === 0 && !Boolean(widget.config.show_current ?? false) && <span className="widget-muted">Everything managed is up to date.</span>}</div>}
        </div>
      </div>
      {manageMode && <div className="card-controls"><span className="drag-handle" title="Drag to reorder" aria-hidden="true"><GripVertical size={15} /></span><button className="edit-button" type="button" onClick={() => onEdit(widget)} title={`Edit ${widget.title}`} aria-label={`Edit ${widget.title}`}><Pencil size={15} /></button></div>}
    </article>
  );
}
