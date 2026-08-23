from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sqlite3
import ssl
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from http.cookies import SimpleCookie
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from websocket import WebSocketTimeoutException, create_connection

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl, field_validator

APP_NAME = os.getenv("APP_NAME", "Homelab Dashboard")
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DB_PATH = DATA_DIR / "dashboard.db"
SESSION_COOKIE = "homelab_dashboard_session"
SESSION_HOURS = int(os.getenv("SESSION_HOURS", "168"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() in {"1", "true", "yes", "on"}
STATUS_TIMEOUT = max(1.0, min(float(os.getenv("STATUS_TIMEOUT", "4")), 15.0))
STATUS_WORKERS = max(1, min(int(os.getenv("STATUS_WORKERS", "8")), 32))
DOCKER_PROXY_URL = os.getenv("DOCKER_PROXY_URL", "").strip().rstrip("/")
UPDATE_AGENT_URL = os.getenv("UPDATE_AGENT_URL", "").strip().rstrip("/")
UPDATE_AGENT_TOKEN = os.getenv("UPDATE_AGENT_TOKEN", "").strip()
UPDATE_JOB_TIMEOUT = max(60, min(int(os.getenv("UPDATE_JOB_TIMEOUT", "900")), 3600))
UPDATE_CHECK_INTERVAL_HOURS = max(0.0, min(float(os.getenv("UPDATE_CHECK_INTERVAL_HOURS", "12")), 168.0))
SECRET_KEY_PATH = DATA_DIR / "secret.key"

app = FastAPI(title=f"{APP_NAME} API", version="0.11.0")

# Vite development origin. Production traffic is same-origin through nginx.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthStatus(BaseModel):
    setup_required: bool
    authenticated: bool
    username: str | None = None
    csrf_token: str | None = None


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=256)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Username is required")
        return value


# Service type identifiers are intentionally open-ended. The frontend ships a
# curated catalog, while API clients and future plugins may register additional
# identifiers without requiring a backend release.

class ServiceBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: str = Field(default="link", min_length=1, max_length=64)
    url: HttpUrl
    category: str = Field(default="General", min_length=1, max_length=80)
    page_id: int = Field(default=1, ge=1)
    icon: str | None = Field(default=None, max_length=32)
    enabled: bool = True
    status_check: bool = True
    favorite: bool = False
    card_size: Literal["compact", "standard", "wide"] = "standard"
    sort_order: int = Field(default=0, ge=0, le=1000000)
    api_key: str | None = Field(default=None, max_length=512, exclude=True)
    clear_api_key: bool = Field(default=False, exclude=True)
    auth_username: str | None = Field(default=None, max_length=256, exclude=True)
    auth_password: str | None = Field(default=None, max_length=512, exclude=True)
    clear_auth_credentials: bool = Field(default=False, exclude=True)
    management_provider: Literal["none", "docker_compose", "truenas_app"] = "none"
    management_target: str | None = Field(default=None, max_length=300)
    management_controller_service_id: int | None = Field(default=None, ge=1)

    @field_validator("management_target")
    @classmethod
    def trim_management_target(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("name", "category")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value

    @field_validator("type")
    @classmethod
    def normalize_service_type(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("Service type cannot be blank")
        if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for character in value):
            raise ValueError("Service type may contain only letters, numbers, dots, underscores, and hyphens")
        return value

    @field_validator("icon")
    @classmethod
    def trim_icon(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(ServiceBase):
    pass


class Service(ServiceBase):
    id: int
    has_api_key: bool = False
    has_auth_username: bool = False
    has_auth_credentials: bool = False
    created_at: str
    updated_at: str


class ServiceLayoutUpdate(BaseModel):
    favorite: bool | None = None
    card_size: Literal["compact", "standard", "wide"] | None = None


class ServiceReorder(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    page_id: int = Field(default=1, ge=1)
    ordered_ids: list[int] = Field(min_length=1, max_length=500)

    @field_validator("category")
    @classmethod
    def trim_category(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Category cannot be blank")
        return value


class DashboardPageBase(BaseModel):
    name: str = Field(min_length=1, max_length=60)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Page name cannot be blank")
        return value


class DashboardPageCreate(DashboardPageBase):
    pass


class DashboardPageUpdate(DashboardPageBase):
    pass


class DashboardPage(DashboardPageBase):
    id: int
    sort_order: int
    is_default: bool
    created_at: str
    updated_at: str


class PageReorder(BaseModel):
    ordered_ids: list[int] = Field(min_length=1, max_length=50)


class CategoryLayout(BaseModel):
    page_id: int
    name: str
    sort_order: int
    collapsed: bool


class CategoryStateUpdate(BaseModel):
    page_id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=80)
    collapsed: bool

    @field_validator("name")
    @classmethod
    def trim_category_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Category cannot be blank")
        return value


class CategoryReorder(BaseModel):
    page_id: int = Field(ge=1)
    ordered_names: list[str] = Field(min_length=1, max_length=100)

    @field_validator("ordered_names")
    @classmethod
    def validate_names(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("Category names cannot be blank")
        return cleaned


HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
THEME_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
THEME_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")
BUILTIN_THEME_IDS = {"system", "dark", "light", "slate", "ocean", "forest", "violet", "amber"}


class ThemeColors(BaseModel):
    background: str
    backgroundAccent: str
    surface: str
    surfaceAlt: str
    surfaceHover: str
    surfaceInset: str
    border: str
    borderSoft: str
    borderStrong: str
    text: str
    textSecondary: str
    muted: str
    subtle: str
    accent: str
    accentHover: str
    accentStrong: str
    accentSoft: str
    accentLight: str
    accentText: str

    @field_validator("*", mode="before")
    @classmethod
    def validate_color(cls, value: str) -> str:
        if not isinstance(value, str) or not HEX_COLOR.fullmatch(value.strip()):
            raise ValueError("Theme colors must use six-digit hex values such as #3b82f6")
        return value.strip().lower()


class ThemePackage(BaseModel):
    format: Literal["homelab-dashboard-theme"] = "homelab-dashboard-theme"
    schema_version: Literal[1] = 1
    id: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=5, max_length=40)
    author: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=240)
    mode: Literal["dark", "light"]
    colors: ThemeColors

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        value = value.strip().lower()
        if not THEME_ID.fullmatch(value):
            raise ValueError("Theme id must use lowercase letters, numbers, and hyphens")
        if value in BUILTIN_THEME_IDS:
            raise ValueError("Theme id conflicts with a built-in theme")
        return value

    @field_validator("name", "author")
    @classmethod
    def trim_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        value = value.strip()
        if not THEME_VERSION.fullmatch(value):
            raise ValueError("Theme version must look like 1.0.0")
        return value

    @field_validator("description")
    @classmethod
    def trim_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class AppearanceUpdate(BaseModel):
    theme_id: str = Field(min_length=2, max_length=40)

    @field_validator("theme_id")
    @classmethod
    def normalize_theme_id(cls, value: str) -> str:
        return value.strip().lower()


class AppearanceSettings(BaseModel):
    theme_id: str
    custom_themes: list[ThemePackage] = Field(default_factory=list)


StatusState = Literal["online", "degraded", "offline", "disabled", "unchecked"]


class ServiceStatus(BaseModel):
    id: int
    state: StatusState
    http_status: int | None = None
    latency_ms: int | None = None
    checked_at: str
    detail: str | None = None


class ServiceActivity(BaseModel):
    operation: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=300)
    progress: float | None = Field(default=None, ge=0, le=100)
    transferred_bytes: int | None = Field(default=None, ge=0)
    total_bytes: int | None = Field(default=None, ge=0)
    speed_bps: int | None = Field(default=None, ge=0)
    eta_seconds: int | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, max_length=80)
    detail: str | None = Field(default=None, max_length=200)


class ServiceInsight(BaseModel):
    id: int
    kind: str
    state: Literal["ok", "setup", "unavailable", "none"] = "none"
    summary: str | None = None
    secondary: str | None = None
    items: list[str] = Field(default_factory=list)
    activities: list[ServiceActivity] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class IntegrationDescriptor(BaseModel):
    type: str
    name: str
    auth: Literal["none", "api_key", "username_password", "docker_proxy"]
    capabilities: list[str] = Field(default_factory=list)


UpdateStateName = Literal["unknown", "checking", "current", "available", "unavailable", "unconfigured"]
UpdateJobState = Literal["queued", "running", "success", "failed", "rolled_back"]


class ManagedResource(BaseModel):
    id: str
    name: str
    provider: Literal["docker_compose", "truenas_app"]
    current_version: str | None = None
    latest_version: str | None = None
    update_available: bool | None = None
    state: str | None = None
    detail: str | None = None


class ServiceUpdateState(BaseModel):
    service_id: int
    provider: Literal["none", "docker_compose", "truenas_app"]
    target: str | None = None
    state: UpdateStateName = "unknown"
    current_version: str | None = None
    latest_version: str | None = None
    checked_at: str | None = None
    message: str | None = None
    can_update: bool = False


class UpdateJob(BaseModel):
    id: str
    kind: Literal["check", "update", "batch"]
    service_id: int | None = None
    active_service_id: int | None = None
    provider: str | None = None
    target: str | None = None
    state: UpdateJobState
    progress: int = Field(ge=0, le=100)
    message: str
    current_version: str | None = None
    latest_version: str | None = None
    detail: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


INTEGRATIONS: dict[str, IntegrationDescriptor] = {
    "jellyfin": IntegrationDescriptor(type="jellyfin", name="Jellyfin", auth="api_key", capabilities=["health", "sessions"]),
    "sonarr": IntegrationDescriptor(type="sonarr", name="Sonarr", auth="api_key", capabilities=["health", "activity", "progress", "queue", "upcoming"]),
    "radarr": IntegrationDescriptor(type="radarr", name="Radarr", auth="api_key", capabilities=["health", "activity", "progress", "queue", "upcoming"]),
    "prowlarr": IntegrationDescriptor(type="prowlarr", name="Prowlarr", auth="api_key", capabilities=["health", "indexers"]),
    "qbittorrent": IntegrationDescriptor(type="qbittorrent", name="qBittorrent", auth="username_password", capabilities=["health", "activity", "progress", "queue", "transfer_speed", "eta"]),
    "sabnzbd": IntegrationDescriptor(type="sabnzbd", name="SABnzbd", auth="api_key", capabilities=["health", "activity", "progress", "queue", "transfer_speed", "eta"]),
    "immich": IntegrationDescriptor(type="immich", name="Immich", auth="api_key", capabilities=["health", "server_info", "storage"]),
    "truenas": IntegrationDescriptor(type="truenas", name="TrueNAS", auth="api_key", capabilities=["health", "storage", "activity", "progress", "alerts"]),
    "dockge": IntegrationDescriptor(type="dockge", name="Dockge", auth="docker_proxy", capabilities=["health", "containers", "stacks"]),
    "docker-host": IntegrationDescriptor(type="docker-host", name="Docker Host", auth="docker_proxy", capabilities=["health", "containers", "stacks"]),
}


class SessionUser(BaseModel):
    username: str
    csrf_token: str


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utcnow().isoformat()


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def ensure_service_migrations(connection: sqlite3.Connection) -> None:
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(services)").fetchall()}
    if "status_check" not in columns:
        connection.execute("ALTER TABLE services ADD COLUMN status_check INTEGER NOT NULL DEFAULT 1")
    if "api_key_encrypted" not in columns:
        connection.execute("ALTER TABLE services ADD COLUMN api_key_encrypted TEXT")
    if "favorite" not in columns:
        connection.execute("ALTER TABLE services ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0")
    if "card_size" not in columns:
        connection.execute("ALTER TABLE services ADD COLUMN card_size TEXT NOT NULL DEFAULT 'standard'")
    if "sort_order" not in columns:
        connection.execute("ALTER TABLE services ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
        connection.execute("UPDATE services SET sort_order = id WHERE sort_order = 0")
    if "page_id" not in columns:
        connection.execute("ALTER TABLE services ADD COLUMN page_id INTEGER NOT NULL DEFAULT 1")
    if "auth_username_encrypted" not in columns:
        connection.execute("ALTER TABLE services ADD COLUMN auth_username_encrypted TEXT")
    if "auth_password_encrypted" not in columns:
        connection.execute("ALTER TABLE services ADD COLUMN auth_password_encrypted TEXT")
    if "management_provider" not in columns:
        connection.execute("ALTER TABLE services ADD COLUMN management_provider TEXT NOT NULL DEFAULT 'none'")
    if "management_target" not in columns:
        connection.execute("ALTER TABLE services ADD COLUMN management_target TEXT")
    if "management_controller_service_id" not in columns:
        connection.execute("ALTER TABLE services ADD COLUMN management_controller_service_id INTEGER")


def ensure_default_page(connection: sqlite3.Connection) -> None:
    now = iso_now()
    connection.execute(
        """
        INSERT OR IGNORE INTO dashboard_pages (id, name, sort_order, is_default, created_at, updated_at)
        VALUES (1, 'Home', 1, 1, ?, ?)
        """,
        (now, now),
    )


def ensure_category_layouts(connection: sqlite3.Connection) -> None:
    page_ids = [row["id"] for row in connection.execute("SELECT id FROM dashboard_pages").fetchall()]
    for page_id in page_ids:
        existing = {
            row["name"].casefold()
            for row in connection.execute("SELECT name FROM category_layouts WHERE page_id = ?", (page_id,)).fetchall()
        }
        categories = [
            row["category"]
            for row in connection.execute(
                "SELECT category FROM services WHERE page_id = ? GROUP BY category COLLATE NOCASE ORDER BY category COLLATE NOCASE",
                (page_id,),
            ).fetchall()
        ]
        next_order = int(connection.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM category_layouts WHERE page_id = ?",
            (page_id,),
        ).fetchone()[0])
        for category in categories:
            if category.casefold() in existing:
                continue
            connection.execute(
                "INSERT INTO category_layouts (page_id, name, sort_order, collapsed) VALUES (?, ?, ?, 0)",
                (page_id, category, next_order),
            )
            next_order += 1


def ensure_category_layout(connection: sqlite3.Connection, page_id: int, category: str) -> None:
    existing = connection.execute(
        "SELECT 1 FROM category_layouts WHERE page_id = ? AND name = ?",
        (page_id, category),
    ).fetchone()
    if existing:
        return
    sort_order = int(connection.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM category_layouts WHERE page_id = ?",
        (page_id,),
    ).fetchone()[0])
    connection.execute(
        "INSERT INTO category_layouts (page_id, name, sort_order, collapsed) VALUES (?, ?, ?, 0)",
        (page_id, category, sort_order),
    )


def require_page(connection: sqlite3.Connection, page_id: int) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM dashboard_pages WHERE id = ?", (page_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard page not found")
    return row


def init_db() -> None:
    with db() as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                csrf_token TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES admin_users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS dashboard_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS category_layouts (
                page_id INTEGER NOT NULL,
                name TEXT NOT NULL COLLATE NOCASE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                collapsed INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (page_id, name),
                FOREIGN KEY(page_id) REFERENCES dashboard_pages(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS custom_themes (
                id TEXT PRIMARY KEY,
                manifest_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'link',
                url TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'General',
                page_id INTEGER NOT NULL DEFAULT 1,
                icon TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                status_check INTEGER NOT NULL DEFAULT 1,
                favorite INTEGER NOT NULL DEFAULT 0,
                card_size TEXT NOT NULL DEFAULT 'standard',
                sort_order INTEGER NOT NULL DEFAULT 0,
                api_key_encrypted TEXT,
                auth_username_encrypted TEXT,
                auth_password_encrypted TEXT,
                management_provider TEXT NOT NULL DEFAULT 'none',
                management_target TEXT,
                management_controller_service_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS service_update_state (
                service_id INTEGER PRIMARY KEY,
                provider TEXT NOT NULL DEFAULT 'none',
                target TEXT,
                state TEXT NOT NULL DEFAULT 'unknown',
                current_version TEXT,
                latest_version TEXT,
                checked_at TEXT,
                message TEXT,
                FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS update_jobs (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                service_id INTEGER,
                active_service_id INTEGER,
                provider TEXT,
                target TEXT,
                state TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL,
                current_version TEXT,
                latest_version TEXT,
                detail TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            );
            """
        )
        ensure_service_migrations(connection)
        ensure_default_page(connection)
        connection.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('theme_id', 'system')")
        ensure_category_layouts(connection)
        now = iso_now()
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        connection.execute("UPDATE update_jobs SET state = 'failed', progress = 100, message = 'Interrupted by dashboard restart', finished_at = ? WHERE state IN ('queued', 'running')", (now,))


def automatic_update_check_loop() -> None:
    # Give the application and optional agent time to settle after startup.
    time.sleep(60)
    while UPDATE_CHECK_INTERVAL_HOURS > 0:
        try:
            with db() as connection:
                active_job = connection.execute("SELECT 1 FROM update_jobs WHERE state IN ('queued', 'running') LIMIT 1").fetchone()
                rows = [] if active_job else connection.execute("SELECT * FROM services WHERE management_provider != 'none' ORDER BY name COLLATE NOCASE").fetchall()
            for row in rows:
                try:
                    check_service_update(row)
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(max(3600, UPDATE_CHECK_INTERVAL_HOURS * 3600))


@app.on_event("startup")
def startup() -> None:
    init_db()
    if UPDATE_CHECK_INTERVAL_HOURS > 0:
        threading.Thread(target=automatic_update_check_loop, daemon=True, name="update-check-loop").start()


def get_fernet() -> Fernet:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SECRET_KEY_PATH.exists():
        SECRET_KEY_PATH.write_bytes(Fernet.generate_key())
        try:
            SECRET_KEY_PATH.chmod(0o600)
        except OSError:
            pass
    key = SECRET_KEY_PATH.read_bytes().strip()
    return Fernet(key)


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    return get_fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return get_fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=64)
    return f"scrypt${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_hex, digest_hex = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=2**14,
            r=8,
            p=1,
            dklen=64,
        )
        return hmac.compare_digest(derived.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def admin_exists() -> bool:
    with db() as connection:
        return connection.execute("SELECT 1 FROM admin_users LIMIT 1").fetchone() is not None


def create_session(connection: sqlite3.Connection, user_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    now = utcnow()
    expires = now + timedelta(hours=SESSION_HOURS)
    connection.execute(
        "INSERT INTO sessions (token_hash, user_id, csrf_token, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
        (token_digest(token), user_id, csrf_token, expires.isoformat(), now.isoformat()),
    )
    return token, csrf_token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_HOURS * 3600,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def get_session(session_token: str | None) -> SessionUser | None:
    if not session_token:
        return None
    with db() as connection:
        row = connection.execute(
            """
            SELECT u.username, s.csrf_token, s.expires_at
            FROM sessions s
            JOIN admin_users u ON u.id = s.user_id
            WHERE s.token_hash = ?
            """,
            (token_digest(session_token),),
        ).fetchone()
        if not row:
            return None
        if datetime.fromisoformat(row["expires_at"]) <= utcnow():
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_digest(session_token),))
            return None
        return SessionUser(username=row["username"], csrf_token=row["csrf_token"])


def require_auth(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> SessionUser:
    user = get_session(session_token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user


def require_write_auth(
    user: SessionUser = Depends(require_auth),
    x_csrf_token: str | None = Header(default=None),
) -> SessionUser:
    if not x_csrf_token or not hmac.compare_digest(x_csrf_token, user.csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
    return user


def row_to_service(row: sqlite3.Row) -> Service:
    return Service(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        url=row["url"],
        category=row["category"],
        page_id=int(row["page_id"] or 1),
        icon=row["icon"],
        enabled=bool(row["enabled"]),
        status_check=bool(row["status_check"]),
        favorite=bool(row["favorite"]),
        card_size=row["card_size"] if row["card_size"] in {"compact", "standard", "wide"} else "standard",
        sort_order=int(row["sort_order"] or 0),
        api_key=None,
        clear_api_key=False,
        auth_username=None,
        auth_password=None,
        clear_auth_credentials=False,
        management_provider=row["management_provider"] if row["management_provider"] in {"none", "docker_compose", "truenas_app"} else "none",
        management_target=row["management_target"],
        management_controller_service_id=row["management_controller_service_id"],
        has_api_key=bool(row["api_key_encrypted"]),
        has_auth_username=bool(row["auth_username_encrypted"]),
        has_auth_credentials=bool(row["auth_username_encrypted"] and row["auth_password_encrypted"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def row_to_page(row: sqlite3.Row) -> DashboardPage:
    return DashboardPage(
        id=row["id"],
        name=row["name"],
        sort_order=int(row["sort_order"] or 0),
        is_default=bool(row["is_default"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def row_to_category(row: sqlite3.Row) -> CategoryLayout:
    return CategoryLayout(
        page_id=int(row["page_id"]),
        name=row["name"],
        sort_order=int(row["sort_order"] or 0),
        collapsed=bool(row["collapsed"]),
    )


def row_to_theme(row: sqlite3.Row) -> ThemePackage:
    try:
        return ThemePackage.model_validate_json(row["manifest_json"])
    except Exception as exc:  # noqa: BLE001 - invalid stored extensions should not crash unrelated routes.
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Stored theme {row['id']} is invalid") from exc


def list_theme_rows(connection: sqlite3.Connection) -> list[ThemePackage]:
    rows = connection.execute("SELECT * FROM custom_themes ORDER BY id COLLATE NOCASE").fetchall()
    return [row_to_theme(row) for row in rows]


def theme_exists(connection: sqlite3.Connection, theme_id: str) -> bool:
    if theme_id in BUILTIN_THEME_IDS:
        return True
    return connection.execute("SELECT 1 FROM custom_themes WHERE id = ?", (theme_id,)).fetchone() is not None


def is_private_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    lowered = hostname.lower().rstrip(".")
    if lowered in {"localhost", "host.docker.internal"} or lowered.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(lowered)
        return address.is_private or address.is_loopback or address.is_link_local
    except ValueError:
        return False


def perform_probe(url: str, method: str, verify_tls: bool = True) -> tuple[int, int]:
    request = Request(
        url,
        method=method,
        headers={"User-Agent": "HomelabDashboard/0.11.0", "Accept": "*/*"},
    )
    context = None if verify_tls else ssl._create_unverified_context()
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=STATUS_TIMEOUT, context=context) as response:
            code = int(response.getcode() or 200)
    except HTTPError as exc:
        code = int(exc.code)
    latency_ms = max(1, round((time.perf_counter() - started) * 1000))
    return code, latency_ms


def probe_service(service: Service) -> ServiceStatus:
    checked_at = iso_now()
    if not service.enabled:
        return ServiceStatus(id=service.id, state="disabled", checked_at=checked_at, detail="Service is hidden")
    if not service.status_check:
        return ServiceStatus(id=service.id, state="unchecked", checked_at=checked_at, detail="Status monitoring is off")

    url = str(service.url)
    hostname = urlparse(url).hostname

    try:
        try:
            code, latency = perform_probe(url, "HEAD")
            if code in {405, 501}:
                code, latency = perform_probe(url, "GET")
        except URLError as exc:
            # Private homelabs commonly use self-signed certificates. Retry only private/local
            # destinations without certificate verification; public hosts remain fully verified.
            reason = exc.reason
            if is_private_hostname(hostname) and isinstance(reason, (ssl.SSLCertVerificationError, ssl.SSLError)):
                code, latency = perform_probe(url, "HEAD", verify_tls=False)
                if code in {405, 501}:
                    code, latency = perform_probe(url, "GET", verify_tls=False)
            else:
                raise

        state: StatusState = "online" if code < 500 else "degraded"
        detail = None if state == "online" else f"HTTP {code}"
        return ServiceStatus(
            id=service.id,
            state=state,
            http_status=code,
            latency_ms=latency,
            checked_at=checked_at,
            detail=detail,
        )
    except Exception as exc:  # noqa: BLE001 - status checks must never break the dashboard endpoint.
        detail = str(getattr(exc, "reason", exc)) or exc.__class__.__name__
        if len(detail) > 160:
            detail = detail[:157] + "..."
        return ServiceStatus(id=service.id, state="offline", checked_at=checked_at, detail=detail)


def request_raw(
    url: str,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    data: bytes | None = None,
    verify_tls: bool = True,
) -> tuple[bytes, object]:
    request = Request(
        url,
        method=method,
        data=data,
        headers={"User-Agent": "HomelabDashboard/0.11.0", "Accept": "application/json", **(headers or {})},
    )
    context = None if verify_tls else ssl._create_unverified_context()
    with urlopen(request, timeout=STATUS_TIMEOUT, context=context) as response:
        return response.read(), response.headers


def request_raw_local_retry(
    url: str,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    data: bytes | None = None,
) -> tuple[bytes, object]:
    hostname = urlparse(url).hostname
    try:
        return request_raw(url, headers=headers, method=method, data=data)
    except URLError as exc:
        reason = exc.reason
        if is_private_hostname(hostname) and isinstance(reason, (ssl.SSLCertVerificationError, ssl.SSLError)):
            return request_raw(url, headers=headers, method=method, data=data, verify_tls=False)
        raise


def request_json(url: str, headers: dict[str, str] | None = None, verify_tls: bool = True) -> object:
    body, _ = request_raw(url, headers=headers, verify_tls=verify_tls)
    return json.loads(body.decode("utf-8"))


def service_json(service: Service, path: str, headers: dict[str, str] | None = None) -> object:
    base = str(service.url).rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    body, _ = request_raw_local_retry(url, headers=headers)
    return json.loads(body.decode("utf-8"))


def clamp_progress(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return round(max(0.0, min(number, 100.0)), 1)


def progress_from_remaining(total: object, remaining: object) -> float | None:
    try:
        total_number = float(total)  # type: ignore[arg-type]
        remaining_number = float(remaining)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if total_number <= 0:
        return None
    return clamp_progress(((total_number - max(0.0, remaining_number)) / total_number) * 100.0)


def safe_int(value: object) -> int | None:
    try:
        number = int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return max(0, number)


def parse_duration_seconds(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value).strip()
    if not text or text.lower() in {"unknown", "infinite", "∞", "none"}:
        return None
    parts = text.split(":")
    if not (1 <= len(parts) <= 3):
        return None
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        return None
    if any(number < 0 for number in numbers):
        return None
    if len(numbers) == 3:
        return int(numbers[0] * 3600 + numbers[1] * 60 + numbers[2])
    if len(numbers) == 2:
        return int(numbers[0] * 60 + numbers[1])
    return int(numbers[0])


def seconds_until(value: object) -> int | None:
    if not value:
        return None
    try:
        text = str(value).strip().replace("Z", "+00:00")
        target = datetime.fromisoformat(text)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        return max(0, int((target.astimezone(timezone.utc) - utcnow()).total_seconds()))
    except (TypeError, ValueError):
        return None


def human_bytes(value: int | None) -> str | None:
    if value is None:
        return None
    size = float(value)
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    unit = units[0]
    for unit in units:
        if abs(size) < 1024.0 or unit == units[-1]:
            break
        size /= 1024.0
    precision = 0 if size >= 100 else 1
    return f"{size:.{precision}f} {unit}"


def setup_api_key_insight(service: Service, label: str, capabilities: list[str]) -> ServiceInsight:
    return ServiceInsight(
        id=service.id,
        kind=service.type,
        state="setup",
        summary=f"Add {label} API key",
        secondary="Edit this card to enable live integration details",
        capabilities=capabilities,
    )


def integration_capabilities(kind: str) -> list[str]:
    descriptor = INTEGRATIONS.get(kind)
    return list(descriptor.capabilities) if descriptor else []


def jellyfin_insight(service: Service, encrypted_key: str | None) -> ServiceInsight:
    capabilities = integration_capabilities("jellyfin")
    key = decrypt_secret(encrypted_key)
    if not key:
        return setup_api_key_insight(service, "Jellyfin", capabilities)
    headers = {"X-Emby-Token": key}
    try:
        info = service_json(service, "/System/Info", headers=headers)
        sessions = service_json(service, "/Sessions", headers=headers)
        if not isinstance(info, dict) or not isinstance(sessions, list):
            raise ValueError("Unexpected Jellyfin response")
        active = []
        paused = 0
        transcoding = 0
        for session in sessions:
            if not isinstance(session, dict) or not session.get("NowPlayingItem"):
                continue
            active.append(session)
            if (session.get("PlayState") or {}).get("IsPaused"):
                paused += 1
            if session.get("TranscodingInfo"):
                transcoding += 1
        items: list[str] = []
        for session in active[:2]:
            item = session.get("NowPlayingItem") or {}
            title = item.get("SeriesName") or item.get("Name") or "Playing media"
            if item.get("SeriesName") and item.get("Name"):
                title = f"{item.get('SeriesName')} — {item.get('Name')}"
            user = session.get("UserName") or session.get("Client") or "User"
            items.append(f"{user}: {title}")
        count = len(active)
        summary = f"{count} active stream{'s' if count != 1 else ''}" if count else "No active streams"
        extras = []
        if paused:
            extras.append(f"{paused} paused")
        if transcoding:
            extras.append(f"{transcoding} transcoding")
        secondary = f"Jellyfin {info.get('Version', 'server')}"
        if extras:
            secondary += " · " + " · ".join(extras)
        return ServiceInsight(id=service.id, kind="jellyfin", state="ok", summary=summary, secondary=secondary, items=items, capabilities=capabilities)
    except Exception as exc:  # noqa: BLE001
        detail = str(getattr(exc, "reason", exc)) or exc.__class__.__name__
        return ServiceInsight(id=service.id, kind="jellyfin", state="unavailable", summary="Jellyfin integration unavailable", secondary=detail[:120], capabilities=capabilities)


def paged_records(value: object) -> tuple[list[dict], int]:
    if isinstance(value, list):
        records = [item for item in value if isinstance(item, dict)]
        return records, len(records)
    if isinstance(value, dict):
        raw = value.get("records") or []
        records = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
        total = safe_int(value.get("totalRecords"))
        return records, total if total is not None else len(records)
    return [], 0


def servarr_queue_title(kind: str, record: dict) -> str:
    if kind == "sonarr":
        series = record.get("series") if isinstance(record.get("series"), dict) else {}
        episode = record.get("episode") if isinstance(record.get("episode"), dict) else {}
        series_title = series.get("title")
        season = safe_int(episode.get("seasonNumber"))
        number = safe_int(episode.get("episodeNumber"))
        episode_title = episode.get("title")
        if series_title and season is not None and number is not None:
            title = f"{series_title} S{season:02d}E{number:02d}"
            if episode_title:
                title += f" — {episode_title}"
            return title
    if kind == "radarr":
        movie = record.get("movie") if isinstance(record.get("movie"), dict) else {}
        if movie.get("title"):
            year = movie.get("year")
            return f"{movie.get('title')} ({year})" if year else str(movie.get("title"))
    return str(record.get("title") or record.get("downloadId") or "Queued download")


def servarr_queue_activity(kind: str, record: dict) -> ServiceActivity:
    total = safe_int(record.get("size"))
    remaining = safe_int(record.get("sizeleft") if "sizeleft" in record else record.get("sizeLeft"))
    transferred = max(0, total - remaining) if total is not None and remaining is not None else None
    eta = parse_duration_seconds(record.get("timeleft") if "timeleft" in record else record.get("timeLeft"))
    if eta is None:
        eta = seconds_until(record.get("estimatedCompletionTime"))
    status_text = str(record.get("status") or record.get("trackedDownloadStatus") or "Downloading")
    return ServiceActivity(
        operation="download",
        title=servarr_queue_title(kind, record),
        progress=progress_from_remaining(total, remaining),
        transferred_bytes=transferred,
        total_bytes=total,
        eta_seconds=eta,
        status=status_text,
    )


def servarr_upcoming(kind: str, calendar: object) -> str | None:
    if not isinstance(calendar, list):
        return None
    candidates: list[tuple[str, str]] = []
    for raw in calendar:
        if not isinstance(raw, dict):
            continue
        if kind == "sonarr":
            date = raw.get("airDateUtc") or raw.get("airDate")
            series = raw.get("series") if isinstance(raw.get("series"), dict) else {}
            season = safe_int(raw.get("seasonNumber"))
            number = safe_int(raw.get("episodeNumber"))
            title = series.get("title") or raw.get("title")
            if title and season is not None and number is not None:
                title = f"{title} S{season:02d}E{number:02d}"
        else:
            date = raw.get("digitalRelease") or raw.get("physicalRelease") or raw.get("inCinemas") or raw.get("minimumAvailability")
            title = raw.get("title")
        if date and title:
            candidates.append((str(date), str(title)))
    if not candidates:
        return None
    date, title = min(candidates, key=lambda item: item[0])
    return f"Upcoming: {title} · {date[:10]}"


def servarr_insight(service: Service, encrypted_key: str | None, kind: Literal["sonarr", "radarr"]) -> ServiceInsight:
    capabilities = integration_capabilities(kind)
    key = decrypt_secret(encrypted_key)
    if not key:
        return setup_api_key_insight(service, "Sonarr" if kind == "sonarr" else "Radarr", capabilities)
    headers = {"X-Api-Key": key}
    try:
        system_info = service_json(service, "/api/v3/system/status", headers=headers)
        health = service_json(service, "/api/v3/health", headers=headers)
        queue_path = "/api/v3/queue?page=1&pageSize=50&sortDirection=ascending&sortKey=timeleft"
        if kind == "sonarr":
            queue_path += "&includeUnknownSeriesItems=true&includeSeries=true&includeEpisode=true"
        else:
            queue_path += "&includeUnknownMovieItems=true&includeMovie=true"
        queue = service_json(service, queue_path, headers=headers)
        records, queue_total = paged_records(queue)
        activities = [servarr_queue_activity(kind, record) for record in records[:5]]

        now = utcnow()
        calendar_params = {"start": now.isoformat(), "end": (now + timedelta(days=7)).isoformat()}
        if kind == "sonarr":
            calendar_params["includeSeries"] = "true"
        params = urlencode(calendar_params)
        try:
            calendar = service_json(service, f"/api/v3/calendar?{params}", headers=headers)
            upcoming = servarr_upcoming(kind, calendar)
        except Exception:  # noqa: BLE001 - calendar is supplemental; queue/health still provide useful insight.
            upcoming = None

        health_items = []
        if isinstance(health, list):
            for item in health:
                if isinstance(item, dict) and item.get("message"):
                    health_items.append(str(item.get("message")))
        name = "Sonarr" if kind == "sonarr" else "Radarr"
        version = system_info.get("version") if isinstance(system_info, dict) else None
        summary = f"{queue_total} item{'s' if queue_total != 1 else ''} in queue" if queue_total else "Queue empty"
        secondary = f"{name} {version}" if version else name
        items = health_items[:2]
        if upcoming and len(items) < 2:
            items.append(upcoming)
        if health_items:
            secondary += f" · {len(health_items)} health warning{'s' if len(health_items) != 1 else ''}"
        return ServiceInsight(id=service.id, kind=kind, state="ok", summary=summary, secondary=secondary, items=items, activities=activities, capabilities=capabilities)
    except Exception as exc:  # noqa: BLE001
        detail = str(getattr(exc, "reason", exc)) or exc.__class__.__name__
        return ServiceInsight(id=service.id, kind=kind, state="unavailable", summary=f"{kind.title()} integration unavailable", secondary=detail[:120], capabilities=capabilities)


def prowlarr_insight(service: Service, encrypted_key: str | None) -> ServiceInsight:
    capabilities = integration_capabilities("prowlarr")
    key = decrypt_secret(encrypted_key)
    if not key:
        return setup_api_key_insight(service, "Prowlarr", capabilities)
    headers = {"X-Api-Key": key}
    try:
        system_info = service_json(service, "/api/v1/system/status", headers=headers)
        health = service_json(service, "/api/v1/health", headers=headers)
        indexers = service_json(service, "/api/v1/indexer", headers=headers)
        health_items = [str(item.get("message")) for item in health if isinstance(item, dict) and item.get("message")] if isinstance(health, list) else []
        indexer_list = [item for item in indexers if isinstance(item, dict)] if isinstance(indexers, list) else []
        enabled = sum(1 for item in indexer_list if item.get("enable", True))
        version = system_info.get("version") if isinstance(system_info, dict) else None
        if health_items:
            summary = f"{len(health_items)} health warning{'s' if len(health_items) != 1 else ''}"
        else:
            summary = "Healthy"
        secondary = f"{enabled}/{len(indexer_list)} indexers enabled" if indexer_list else "Indexer health available"
        if version:
            secondary += f" · v{version}"
        return ServiceInsight(id=service.id, kind="prowlarr", state="ok", summary=summary, secondary=secondary, items=health_items[:2], capabilities=capabilities)
    except Exception as exc:  # noqa: BLE001
        detail = str(getattr(exc, "reason", exc)) or exc.__class__.__name__
        return ServiceInsight(id=service.id, kind="prowlarr", state="unavailable", summary="Prowlarr integration unavailable", secondary=detail[:120], capabilities=capabilities)


def qbittorrent_insight(service: Service, encrypted_username: str | None, encrypted_password: str | None) -> ServiceInsight:
    capabilities = integration_capabilities("qbittorrent")
    username = decrypt_secret(encrypted_username)
    password = decrypt_secret(encrypted_password)
    if not username or not password:
        return ServiceInsight(
            id=service.id,
            kind="qbittorrent",
            state="setup",
            summary="Add qBittorrent WebUI credentials",
            secondary="Edit this card to enable queue and transfer activity",
            capabilities=capabilities,
        )
    base = str(service.url).rstrip("/")
    try:
        login_body = urlencode({"username": username, "password": password}).encode("utf-8")
        login_raw, login_headers = request_raw_local_retry(
            f"{base}/api/v2/auth/login",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": f"{base}/"},
            method="POST",
            data=login_body,
        )
        if login_raw.decode("utf-8", errors="replace").strip() != "Ok.":
            raise ValueError("qBittorrent rejected the saved WebUI credentials")
        cookies = SimpleCookie()
        get_all = getattr(login_headers, "get_all", None)
        cookie_headers = get_all("Set-Cookie") if callable(get_all) else []
        for cookie_header in cookie_headers or []:
            cookies.load(cookie_header)
        sid = cookies.get("SID")
        auth_headers = {"Referer": f"{base}/"}
        if sid:
            auth_headers["Cookie"] = f"SID={sid.value}"

        torrents_raw, _ = request_raw_local_retry(f"{base}/api/v2/torrents/info", headers=auth_headers)
        transfer_raw, _ = request_raw_local_retry(f"{base}/api/v2/transfer/info", headers=auth_headers)
        version_raw, _ = request_raw_local_retry(f"{base}/api/v2/app/version", headers=auth_headers)
        torrents = json.loads(torrents_raw.decode("utf-8"))
        transfer = json.loads(transfer_raw.decode("utf-8"))
        if not isinstance(torrents, list) or not isinstance(transfer, dict):
            raise ValueError("Unexpected qBittorrent response")

        download_states = {"downloading", "forcedDL", "stalledDL", "queuedDL", "metaDL", "checkingDL", "allocating"}
        downloading = [item for item in torrents if isinstance(item, dict) and str(item.get("state")) in download_states and float(item.get("progress") or 0) < 1]
        downloading.sort(key=lambda item: (safe_int(item.get("dlspeed")) or 0, float(item.get("progress") or 0)), reverse=True)
        activities: list[ServiceActivity] = []
        for item in downloading[:5]:
            total = safe_int(item.get("size") or item.get("total_size"))
            downloaded = safe_int(item.get("downloaded"))
            progress = clamp_progress(float(item.get("progress") or 0) * 100)
            eta = safe_int(item.get("eta"))
            if eta is not None and eta >= 8_640_000:
                eta = None
            activities.append(ServiceActivity(
                operation="download",
                title=str(item.get("name") or "Torrent download"),
                progress=progress,
                transferred_bytes=downloaded,
                total_bytes=total,
                speed_bps=safe_int(item.get("dlspeed")),
                eta_seconds=eta,
                status=str(item.get("state") or "Downloading"),
            ))
        global_speed = safe_int(transfer.get("dl_info_speed")) or 0
        summary = f"{len(downloading)} download{'s' if len(downloading) != 1 else ''} active" if downloading else "No active downloads"
        speed_text = human_bytes(global_speed)
        secondary = f"qBittorrent {version_raw.decode('utf-8', errors='replace').strip()}"
        if speed_text and global_speed:
            secondary += f" · ↓ {speed_text}/s"
        return ServiceInsight(id=service.id, kind="qbittorrent", state="ok", summary=summary, secondary=secondary, activities=activities, capabilities=capabilities)
    except Exception as exc:  # noqa: BLE001
        detail = str(getattr(exc, "reason", exc)) or exc.__class__.__name__
        return ServiceInsight(id=service.id, kind="qbittorrent", state="unavailable", summary="qBittorrent integration unavailable", secondary=detail[:120], capabilities=capabilities)


def sabnzbd_insight(service: Service, encrypted_key: str | None) -> ServiceInsight:
    capabilities = integration_capabilities("sabnzbd")
    key = decrypt_secret(encrypted_key)
    if not key:
        return setup_api_key_insight(service, "SABnzbd", capabilities)
    try:
        query = urlencode({"mode": "queue", "output": "json", "apikey": key})
        payload = service_json(service, f"/api?{query}")
        queue = payload.get("queue") if isinstance(payload, dict) else None
        if not isinstance(queue, dict):
            raise ValueError("Unexpected SABnzbd response")
        slots = [item for item in (queue.get("slots") or []) if isinstance(item, dict)] if isinstance(queue.get("slots"), list) else []
        speed_kb = safe_int(queue.get("kbpersec")) or 0
        speed_bps = speed_kb * 1024
        activities: list[ServiceActivity] = []
        for index, item in enumerate(slots[:5]):
            total_mb = safe_int(item.get("mb"))
            left_mb = safe_int(item.get("mbleft"))
            total = total_mb * 1024 * 1024 if total_mb is not None else None
            remaining = left_mb * 1024 * 1024 if left_mb is not None else None
            transferred = max(0, total - remaining) if total is not None and remaining is not None else None
            activities.append(ServiceActivity(
                operation="download",
                title=str(item.get("filename") or item.get("name") or "Usenet download"),
                progress=clamp_progress(item.get("percentage")),
                transferred_bytes=transferred,
                total_bytes=total,
                speed_bps=speed_bps if index == 0 and speed_bps else None,
                eta_seconds=parse_duration_seconds(item.get("timeleft")),
                status=str(item.get("status") or "Queued"),
            ))
        count = safe_int(queue.get("noofslots"))
        count = count if count is not None else len(slots)
        summary = f"{count} item{'s' if count != 1 else ''} in queue" if count else "Queue empty"
        secondary = str(queue.get("status") or "SABnzbd")
        speed_text = human_bytes(speed_bps)
        if speed_text and speed_bps:
            secondary += f" · ↓ {speed_text}/s"
        return ServiceInsight(id=service.id, kind="sabnzbd", state="ok", summary=summary, secondary=secondary, activities=activities, capabilities=capabilities)
    except Exception as exc:  # noqa: BLE001
        detail = str(getattr(exc, "reason", exc)) or exc.__class__.__name__
        return ServiceInsight(id=service.id, kind="sabnzbd", state="unavailable", summary="SABnzbd integration unavailable", secondary=detail[:120], capabilities=capabilities)


def immich_insight(service: Service, encrypted_key: str | None) -> ServiceInsight:
    capabilities = integration_capabilities("immich")
    key = decrypt_secret(encrypted_key)
    if not key:
        return setup_api_key_insight(service, "Immich", capabilities)
    headers = {"x-api-key": key}
    try:
        about = service_json(service, "/api/server/about", headers=headers)
        if not isinstance(about, dict):
            raise ValueError("Unexpected Immich response")
        stats: dict = {}
        stats_error = None
        try:
            raw_stats = service_json(service, "/api/server/statistics", headers=headers)
            if isinstance(raw_stats, dict):
                stats = raw_stats
        except Exception as exc:  # noqa: BLE001 - about/version still provides useful data when stats permission is absent.
            stats_error = str(getattr(exc, "reason", exc)) or exc.__class__.__name__
        photos = safe_int(stats.get("photos")) or 0
        videos = safe_int(stats.get("videos")) or 0
        usage = safe_int(stats.get("usage"))
        asset_count = photos + videos
        summary = f"{asset_count:,} assets" if stats else "Server connected"
        version = str(about.get("version") or "server")
        secondary = f"Immich {version}"
        if usage is not None:
            usage_text = human_bytes(usage)
            if usage_text:
                secondary += f" · {usage_text} used"
        items = [f"{photos:,} photos · {videos:,} videos"] if stats else []
        if stats_error:
            items.append("Server statistics permission not available")
        return ServiceInsight(id=service.id, kind="immich", state="ok", summary=summary, secondary=secondary, items=items[:2], capabilities=capabilities)
    except Exception as exc:  # noqa: BLE001
        detail = str(getattr(exc, "reason", exc)) or exc.__class__.__name__
        return ServiceInsight(id=service.id, kind="immich", state="unavailable", summary="Immich integration unavailable", secondary=detail[:120], capabilities=capabilities)


def truenas_insight(service: Service, encrypted_key: str | None, encrypted_username: str | None = None) -> ServiceInsight:
    capabilities = integration_capabilities("truenas")
    key = decrypt_secret(encrypted_key)
    if not key:
        return setup_api_key_insight(service, "TrueNAS", capabilities)
    username = decrypt_secret(encrypted_username)
    headers = {"Authorization": f"Bearer {key}"}
    try:
        # TrueNAS 25.04+ uses the versioned JSON-RPC WebSocket API. Try it first
        # so the integration also works on TrueNAS 26+, where the old REST API
        # has been removed. The REST path below remains as a compatibility fallback.
        with TrueNASRPC(service, key, username) as client:
            pools_raw = client.call("pool.query", [[], {}])
            alerts_ws = None
            try:
                alerts_ws = client.call("alert.list", [])
            except Exception:
                alerts_ws = None
        if not isinstance(pools_raw, list):
            raise ValueError("Unexpected TrueNAS pool response")
        pools = [pool for pool in pools_raw if isinstance(pool, dict)]
        total_size = sum(safe_int(pool.get("size")) or 0 for pool in pools)
        total_allocated = sum(safe_int(pool.get("allocated")) or 0 for pool in pools)
        unhealthy = [pool for pool in pools if str(pool.get("status") or "").upper() not in {"ONLINE", "HEALTHY"} or pool.get("healthy") is False]
        activities: list[ServiceActivity] = []
        for pool in pools:
            pool_name = str(pool.get("name") or "Pool")
            scan = pool.get("scan") if isinstance(pool.get("scan"), dict) else None
            if scan and str(scan.get("state") or "").upper() not in {"FINISHED", "CANCELED", "CANCELLED", "NONE"}:
                operation = str(scan.get("function") or "scan").lower()
                activities.append(ServiceActivity(operation=operation, title=f"{pool_name} {operation}", progress=clamp_progress(scan.get("percentage")), transferred_bytes=safe_int(scan.get("bytes_processed")), total_bytes=safe_int(scan.get("bytes_to_process")), eta_seconds=safe_int(scan.get("total_secs_left")), status=str(scan.get("state") or "Running")))
        alert_count = sum(1 for alert in alerts_ws if isinstance(alert, dict) and not alert.get("dismissed")) if isinstance(alerts_ws, list) else 0
        summary = "All pools healthy" if not unhealthy else f"{len(unhealthy)} pool{'s' if len(unhealthy) != 1 else ''} need attention"
        if not pools:
            summary = "No pools returned"
        secondary_parts = []
        if total_size:
            used_percent = round(total_allocated / total_size * 100)
            secondary_parts.append(f"{human_bytes(total_allocated)} / {human_bytes(total_size)} used ({used_percent}%)")
        secondary_parts.append(f"{len(pools)} pool{'s' if len(pools) != 1 else ''}")
        if alert_count:
            secondary_parts.append(f"{alert_count} active alert{'s' if alert_count != 1 else ''}")
        items = [f"{pool.get('name')}: {pool.get('status')}" for pool in unhealthy[:2]]
        return ServiceInsight(id=service.id, kind="truenas", state="ok", summary=summary, secondary=" · ".join(secondary_parts), items=items, activities=activities[:5], capabilities=capabilities)
    except Exception:
        pass
    try:
        pools_raw = service_json(service, "/api/v2.0/pool", headers=headers)
        if not isinstance(pools_raw, list):
            raise ValueError("Unexpected TrueNAS pool response")
        pools = [pool for pool in pools_raw if isinstance(pool, dict)]
        total_size = sum(safe_int(pool.get("size")) or 0 for pool in pools)
        total_allocated = sum(safe_int(pool.get("allocated")) or 0 for pool in pools)
        unhealthy = [pool for pool in pools if str(pool.get("status") or "").upper() not in {"ONLINE", "HEALTHY"} or pool.get("healthy") is False]
        activities: list[ServiceActivity] = []
        for pool in pools:
            pool_name = str(pool.get("name") or "Pool")
            scan = pool.get("scan") if isinstance(pool.get("scan"), dict) else None
            if scan and str(scan.get("state") or "").upper() not in {"FINISHED", "CANCELED", "CANCELLED", "NONE"}:
                operation = str(scan.get("function") or "scan").lower()
                activities.append(ServiceActivity(
                    operation=operation,
                    title=f"{pool_name} {operation}",
                    progress=clamp_progress(scan.get("percentage")),
                    transferred_bytes=safe_int(scan.get("bytes_processed")),
                    total_bytes=safe_int(scan.get("bytes_to_process")),
                    eta_seconds=safe_int(scan.get("total_secs_left")),
                    status=str(scan.get("state") or "Running"),
                ))
            expand = pool.get("expand") if isinstance(pool.get("expand"), dict) else None
            if expand and str(expand.get("state") or "").upper() not in {"FINISHED", "CANCELED", "CANCELLED", "NONE"}:
                activities.append(ServiceActivity(
                    operation="expand",
                    title=f"{pool_name} expansion",
                    progress=clamp_progress(expand.get("percentage")),
                    transferred_bytes=safe_int(expand.get("bytes_reflowed")),
                    total_bytes=safe_int(expand.get("bytes_to_reflow")),
                    eta_seconds=safe_int(expand.get("total_secs_left")),
                    status=str(expand.get("state") or "Running"),
                ))
        alert_count = 0
        try:
            alerts_raw = service_json(service, "/api/v2.0/alert/list", headers=headers)
            if isinstance(alerts_raw, list):
                alert_count = sum(1 for alert in alerts_raw if isinstance(alert, dict) and not alert.get("dismissed"))
        except Exception:  # noqa: BLE001 - alert permission is supplemental to pool monitoring.
            alert_count = 0

        summary = "All pools healthy" if not unhealthy else f"{len(unhealthy)} pool{'s' if len(unhealthy) != 1 else ''} need attention"
        if not pools:
            summary = "No pools returned"
        secondary_parts = []
        if total_size:
            used_percent = round(total_allocated / total_size * 100)
            allocated_text = human_bytes(total_allocated)
            size_text = human_bytes(total_size)
            secondary_parts.append(f"{allocated_text} / {size_text} used ({used_percent}%)")
        secondary_parts.append(f"{len(pools)} pool{'s' if len(pools) != 1 else ''}")
        if alert_count:
            secondary_parts.append(f"{alert_count} active alert{'s' if alert_count != 1 else ''}")
        items = [f"{pool.get('name')}: {pool.get('status')}" for pool in unhealthy[:2]]
        return ServiceInsight(id=service.id, kind="truenas", state="ok", summary=summary, secondary=" · ".join(secondary_parts), items=items, activities=activities[:5], capabilities=capabilities)
    except Exception as exc:  # noqa: BLE001
        detail = str(getattr(exc, "reason", exc)) or exc.__class__.__name__
        if isinstance(exc, HTTPError) and exc.code in {401, 403}:
            detail = "API key was rejected. TrueNAS REST compatibility may require an appropriately privileged API key."
        return ServiceInsight(id=service.id, kind="truenas", state="unavailable", summary="TrueNAS integration unavailable", secondary=detail[:160], capabilities=capabilities)


def docker_host_insight(service_id: int, kind: str = "docker-host") -> ServiceInsight:
    capabilities = integration_capabilities(kind)
    if not DOCKER_PROXY_URL:
        return ServiceInsight(
            id=service_id,
            kind=kind,
            state="setup",
            summary="Docker host integration not enabled",
            secondary="Enable the optional Docker socket proxy to show local container statistics",
            capabilities=capabilities,
        )
    try:
        data = request_json(f"{DOCKER_PROXY_URL}/containers/json?all=1")
        if not isinstance(data, list):
            raise ValueError("Unexpected Docker response")
        total = len(data)
        running = sum(1 for container in data if isinstance(container, dict) and container.get("State") == "running")
        stopped_names: list[str] = []
        projects = set()
        for container in data:
            if not isinstance(container, dict):
                continue
            labels = container.get("Labels") or {}
            project = labels.get("com.docker.compose.project") if isinstance(labels, dict) else None
            if project:
                projects.add(project)
            if container.get("State") != "running":
                names = container.get("Names") or []
                if names:
                    stopped_names.append(str(names[0]).lstrip("/"))
        stopped = max(0, total - running)
        secondary = "All containers running" if stopped == 0 else f"{stopped} container{'s' if stopped != 1 else ''} stopped"
        return ServiceInsight(
            id=service_id,
            kind=kind,
            state="ok",
            summary=f"{len(projects)} stack{'s' if len(projects) != 1 else ''} · {running}/{total} containers running",
            secondary=secondary,
            items=[f"Stopped: {name}" for name in stopped_names[:2]],
            capabilities=capabilities,
        )
    except Exception as exc:  # noqa: BLE001
        detail = str(getattr(exc, "reason", exc)) or exc.__class__.__name__
        return ServiceInsight(id=service_id, kind=kind, state="unavailable", summary="Docker host stats unavailable", secondary=detail[:120], capabilities=capabilities)


def insight_for_row(row: sqlite3.Row) -> ServiceInsight:
    service = row_to_service(row)
    if not service.enabled:
        return ServiceInsight(id=service.id, kind=service.type, state="none")
    if service.type == "jellyfin":
        return jellyfin_insight(service, row["api_key_encrypted"])
    if service.type in {"sonarr", "radarr"}:
        return servarr_insight(service, row["api_key_encrypted"], service.type)
    if service.type == "prowlarr":
        return prowlarr_insight(service, row["api_key_encrypted"])
    if service.type == "qbittorrent":
        return qbittorrent_insight(service, row["auth_username_encrypted"], row["auth_password_encrypted"])
    if service.type == "sabnzbd":
        return sabnzbd_insight(service, row["api_key_encrypted"])
    if service.type == "immich":
        return immich_insight(service, row["api_key_encrypted"])
    if service.type == "truenas":
        return truenas_insight(service, row["api_key_encrypted"], row["auth_username_encrypted"])
    if service.type in {"dockge", "docker-host"}:
        return docker_host_insight(service.id, service.type)
    return ServiceInsight(id=service.id, kind=service.type, state="none")



class TrueNASRPC:
    def __init__(self, service: Service, api_key: str, username: str | None = None):
        parsed = urlparse(str(service.url))
        if parsed.scheme.lower() != "https":
            raise RuntimeError("TrueNAS API-key management requires an HTTPS service URL")
        if not parsed.hostname:
            raise RuntimeError("TrueNAS URL has no hostname")
        self.hostname = parsed.hostname
        self.ws_url = f"wss://{parsed.netloc}/api/current"
        sslopt = None
        if is_private_hostname(parsed.hostname):
            sslopt = {"cert_reqs": ssl.CERT_NONE, "check_hostname": False}
        self.ws = create_connection(self.ws_url, timeout=max(STATUS_TIMEOUT, 10), sslopt=sslopt or {})
        self.sequence = 0
        try:
            authenticated = False
            if username:
                try:
                    result = self.call("auth.login_ex", [{"mechanism": "API_KEY_PLAIN", "username": username, "api_key": api_key, "login_options": {"user_info": False}}])
                    authenticated = isinstance(result, dict) and result.get("response_type") == "SUCCESS"
                except Exception:
                    authenticated = False
            if not authenticated:
                result = self.call("auth.login_with_api_key", [api_key])
                authenticated = result is True or (isinstance(result, dict) and result.get("response_type") == "SUCCESS")
            if not authenticated:
                raise RuntimeError("TrueNAS API key authentication failed")
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass

    def __enter__(self) -> "TrueNASRPC":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def call(self, method: str, params: list[object] | None = None) -> object:
        self.sequence += 1
        call_id = f"hld-{self.sequence}-{uuid.uuid4().hex[:8]}"
        self.ws.send(json.dumps({"jsonrpc": "2.0", "id": call_id, "method": method, "params": params or []}))
        deadline = time.time() + max(STATUS_TIMEOUT, 15)
        while time.time() < deadline:
            try:
                message = json.loads(self.ws.recv())
            except WebSocketTimeoutException as exc:
                raise RuntimeError(f"TrueNAS API timed out while calling {method}") from exc
            if not isinstance(message, dict) or message.get("id") != call_id:
                continue
            if "error" in message:
                error = message.get("error") or {}
                detail = error.get("message") or (error.get("data") or {}).get("reason") or str(error)
                raise RuntimeError(f"TrueNAS {method}: {detail}")
            return message.get("result")
        raise RuntimeError(f"TrueNAS API timed out while calling {method}")


def truenas_client_from_row(row: sqlite3.Row) -> TrueNASRPC:
    service = row_to_service(row)
    api_key = decrypt_secret(row["api_key_encrypted"])
    username = decrypt_secret(row["auth_username_encrypted"])
    if not api_key:
        raise RuntimeError("TrueNAS controller does not have an API key saved")
    return TrueNASRPC(service, api_key, username)


def agent_request(path: str, method: str = "GET", payload: dict | None = None, timeout: float = 30) -> object:
    if not UPDATE_AGENT_URL:
        raise RuntimeError("Docker update agent is not enabled")
    headers = {"Accept": "application/json"}
    if UPDATE_AGENT_TOKEN:
        headers["X-Agent-Token"] = UPDATE_AGENT_TOKEN
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = Request(f"{UPDATE_AGENT_URL}{path}", method=method, headers=headers, data=data)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
            detail = body.get("detail") if isinstance(body, dict) else None
        except Exception:
            detail = None
        raise RuntimeError(detail or f"Update agent returned HTTP {exc.code}") from exc


def row_to_update_state(row: sqlite3.Row) -> ServiceUpdateState:
    state = row["state"] if row["state"] in {"unknown", "checking", "current", "available", "unavailable", "unconfigured"} else "unknown"
    provider = row["provider"] if row["provider"] in {"none", "docker_compose", "truenas_app"} else "none"
    return ServiceUpdateState(
        service_id=int(row["service_id"]), provider=provider, target=row["target"], state=state,
        current_version=row["current_version"], latest_version=row["latest_version"], checked_at=row["checked_at"],
        message=row["message"], can_update=state == "available",
    )


def row_to_update_job(row: sqlite3.Row) -> UpdateJob:
    return UpdateJob(
        id=row["id"], kind=row["kind"], service_id=row["service_id"], active_service_id=row["active_service_id"],
        provider=row["provider"], target=row["target"], state=row["state"], progress=int(row["progress"] or 0),
        message=row["message"], current_version=row["current_version"], latest_version=row["latest_version"], detail=row["detail"],
        created_at=row["created_at"], started_at=row["started_at"], finished_at=row["finished_at"],
    )


def save_update_state(state_obj: ServiceUpdateState) -> None:
    with db() as connection:
        connection.execute(
            """INSERT INTO service_update_state (service_id, provider, target, state, current_version, latest_version, checked_at, message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(service_id) DO UPDATE SET provider=excluded.provider, target=excluded.target, state=excluded.state,
               current_version=excluded.current_version, latest_version=excluded.latest_version, checked_at=excluded.checked_at, message=excluded.message""",
            (state_obj.service_id, state_obj.provider, state_obj.target, state_obj.state, state_obj.current_version, state_obj.latest_version, state_obj.checked_at, state_obj.message),
        )


def create_update_job(kind: str, service_id: int | None = None, provider: str | None = None, target: str | None = None, message: str = "Queued") -> UpdateJob:
    job_id = uuid.uuid4().hex
    now = iso_now()
    with db() as connection:
        connection.execute(
            "INSERT INTO update_jobs (id, kind, service_id, active_service_id, provider, target, state, progress, message, created_at) VALUES (?, ?, ?, ?, ?, ?, 'queued', 0, ?, ?)",
            (job_id, kind, service_id, service_id, provider, target, message, now),
        )
        row = connection.execute("SELECT * FROM update_jobs WHERE id = ?", (job_id,)).fetchone()
    return row_to_update_job(row)


def update_job(job_id: str, **changes: object) -> None:
    if not changes:
        return
    allowed = {"active_service_id", "state", "progress", "message", "current_version", "latest_version", "detail", "started_at", "finished_at", "provider", "target"}
    parts: list[str] = []
    values: list[object] = []
    for key, value in changes.items():
        if key not in allowed:
            continue
        parts.append(f"{key} = ?")
        values.append(value)
    if not parts:
        return
    values.append(job_id)
    with db() as connection:
        connection.execute(f"UPDATE update_jobs SET {', '.join(parts)} WHERE id = ?", tuple(values))


def get_service_row(service_id: int) -> sqlite3.Row:
    with db() as connection:
        row = connection.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone()
    if not row:
        raise RuntimeError("Service not found")
    return row


def truenas_app_records(controller_row: sqlite3.Row) -> list[dict]:
    with truenas_client_from_row(controller_row) as client:
        raw = client.call("app.query", [[], {}])
    if not isinstance(raw, list):
        raise RuntimeError("Unexpected TrueNAS app query response")
    return [item for item in raw if isinstance(item, dict)]


def check_service_update(service_row: sqlite3.Row) -> ServiceUpdateState:
    service = row_to_service(service_row)
    provider = service.management_provider
    target = service.management_target
    checked_at = iso_now()
    if provider == "none" or not target:
        result = ServiceUpdateState(service_id=service.id, provider=provider, target=target, state="unconfigured", checked_at=checked_at, message="Update management is not configured for this service")
        save_update_state(result)
        return result
    try:
        if provider == "docker_compose":
            raw = agent_request("/v1/check", method="POST", payload={"resource_id": target}, timeout=UPDATE_JOB_TIMEOUT)
            if not isinstance(raw, dict):
                raise RuntimeError("Unexpected update-agent response")
            available = bool(raw.get("update_available"))
            result = ServiceUpdateState(
                service_id=service.id, provider=provider, target=target, state="available" if available else "current",
                current_version=raw.get("current_version"), latest_version=raw.get("latest_version"), checked_at=checked_at,
                message="Container image update available" if available else "Container image is current",
            )
        elif provider == "truenas_app":
            controller_id = service.management_controller_service_id
            if not controller_id:
                raise RuntimeError("Choose a TrueNAS controller card for this app")
            controller_row = get_service_row(controller_id)
            apps = truenas_app_records(controller_row)
            app_item = next((item for item in apps if str(item.get("id") or item.get("name")) == target), None)
            if not app_item:
                raise RuntimeError(f"TrueNAS app {target!r} was not found")
            available = bool(app_item.get("upgrade_available") or app_item.get("image_updates_available"))
            current_version = str(app_item.get("human_version") or app_item.get("version") or "") or None
            latest_version = str(app_item.get("latest_human_version") or app_item.get("latest_version") or "") or None
            result = ServiceUpdateState(
                service_id=service.id, provider=provider, target=target, state="available" if available else "current",
                current_version=current_version, latest_version=latest_version, checked_at=checked_at,
                message="TrueNAS app update available" if available else "TrueNAS app is current",
            )
        else:
            raise RuntimeError("Unsupported management provider")
    except Exception as exc:
        result = ServiceUpdateState(service_id=service.id, provider=provider, target=target, state="unavailable", checked_at=checked_at, message=str(exc)[:240])
    save_update_state(result)
    return result


def check_updates_worker(job_id: str) -> None:
    update_job(job_id, state="running", progress=1, message="Checking configured services", started_at=iso_now())
    try:
        with db() as connection:
            rows = connection.execute("SELECT * FROM services WHERE management_provider != 'none' ORDER BY name COLLATE NOCASE").fetchall()
        if not rows:
            update_job(job_id, state="success", progress=100, message="No managed services configured", finished_at=iso_now())
            return
        for index, row in enumerate(rows, start=1):
            service = row_to_service(row)
            update_job(job_id, active_service_id=service.id, progress=max(1, round((index - 1) / len(rows) * 100)), message=f"Checking {service.name}")
            check_service_update(row)
        update_job(job_id, active_service_id=None, state="success", progress=100, message="Update check complete", finished_at=iso_now())
    except Exception as exc:
        update_job(job_id, state="failed", progress=100, message="Update check failed", detail=str(exc)[:1000], finished_at=iso_now())


def perform_docker_update(service: Service, job_id: str, start: int = 5, end: int = 100) -> tuple[str | None, str | None, str]:
    raw = agent_request("/v1/update", method="POST", payload={"resource_id": service.management_target}, timeout=30)
    if not isinstance(raw, dict) or not raw.get("id"):
        raise RuntimeError("Update agent did not return a job id")
    agent_job_id = str(raw["id"])
    deadline = time.time() + UPDATE_JOB_TIMEOUT
    while time.time() < deadline:
        status_raw = agent_request(f"/v1/jobs/{agent_job_id}", timeout=30)
        if not isinstance(status_raw, dict):
            raise RuntimeError("Unexpected update-agent job response")
        agent_progress = int(status_raw.get("progress") or 0)
        mapped = start + round((end - start) * agent_progress / 100)
        update_job(job_id, progress=min(end, mapped), message=str(status_raw.get("stage") or "Updating container"), current_version=status_raw.get("current_version"), latest_version=status_raw.get("latest_version"), detail=status_raw.get("detail"))
        state = status_raw.get("state")
        if state == "success":
            return status_raw.get("current_version"), status_raw.get("latest_version"), "success"
        if state == "rolled_back":
            return status_raw.get("current_version"), status_raw.get("latest_version"), "rolled_back"
        if state == "failed":
            raise RuntimeError(str(status_raw.get("detail") or "Docker update failed"))
        time.sleep(1.5)
    raise RuntimeError("Docker update timed out")


def perform_truenas_update(service: Service, job_id: str, start: int = 5, end: int = 100) -> tuple[str | None, str | None, str]:
    if not service.management_controller_service_id or not service.management_target:
        raise RuntimeError("TrueNAS update target is incomplete")
    controller_row = get_service_row(service.management_controller_service_id)
    update_job(job_id, progress=start, message="Connecting to TrueNAS")
    with truenas_client_from_row(controller_row) as client:
        before_raw = client.call("app.query", [[["id", "=", service.management_target]], {"get": True}])
        before = before_raw if isinstance(before_raw, dict) else {}
        current_version = str(before.get("human_version") or before.get("version") or "") or None
        latest_version = str(before.get("latest_human_version") or before.get("latest_version") or "") or None
        update_job(job_id, progress=start + 10, message="Starting TrueNAS app upgrade", current_version=current_version, latest_version=latest_version)
        result = client.call("app.upgrade", [service.management_target, {"app_version": "latest", "values": {}, "snapshot_hostpaths": False}])
        job_number = result if isinstance(result, int) else None
        deadline = time.time() + UPDATE_JOB_TIMEOUT
        while time.time() < deadline:
            percent = None
            description = "TrueNAS is upgrading the app"
            state = None
            error = None
            if job_number is not None:
                jobs = client.call("core.get_jobs", [[["id", "=", job_number]], {}])
                job_info = jobs[0] if isinstance(jobs, list) and jobs and isinstance(jobs[0], dict) else None
                if job_info:
                    progress_info = job_info.get("progress") if isinstance(job_info.get("progress"), dict) else {}
                    percent = progress_info.get("percent")
                    description = str(progress_info.get("description") or description)
                    state = str(job_info.get("state") or "")
                    error = job_info.get("error")
            app_now_raw = client.call("app.query", [[["id", "=", service.management_target]], {"get": True}])
            app_now = app_now_raw if isinstance(app_now_raw, dict) else {}
            if percent is None:
                percent = 85 if str(app_now.get("state") or "").upper() in {"DEPLOYING", "STOPPING"} else 70
            mapped = start + round((end - start) * min(100, max(0, float(percent))) / 100)
            update_job(job_id, progress=min(end - 2, mapped), message=description[:180])
            if state in {"FAILED", "ABORTED"}:
                raise RuntimeError(str(error or f"TrueNAS app upgrade {state.lower()}"))
            if state == "SUCCESS" or (str(app_now.get("state") or "").upper() == "RUNNING" and not bool(app_now.get("upgrade_available") or app_now.get("image_updates_available"))):
                final_version = str(app_now.get("human_version") or app_now.get("version") or latest_version or "") or latest_version
                return current_version, final_version, "success"
            time.sleep(2)
        raise RuntimeError("TrueNAS app upgrade timed out")


def perform_service_update(service_id: int, job_id: str, start: int = 5, end: int = 100) -> str:
    row = get_service_row(service_id)
    service = row_to_service(row)
    if service.management_provider == "none" or not service.management_target:
        raise RuntimeError("Update management is not configured for this service")
    update_job(job_id, active_service_id=service.id, provider=service.management_provider, target=service.management_target, progress=start, message=f"Preparing {service.name}")
    if service.management_provider == "docker_compose":
        current, latest, outcome = perform_docker_update(service, job_id, start, end)
    elif service.management_provider == "truenas_app":
        current, latest, outcome = perform_truenas_update(service, job_id, start, end)
    else:
        raise RuntimeError("Unsupported management provider")
    if outcome == "rolled_back":
        save_update_state(ServiceUpdateState(service_id=service.id, provider=service.management_provider, target=service.management_target, state="available", current_version=latest or current, latest_version=None, checked_at=iso_now(), message="Update failed and the previous image was restored"))
        return "rolled_back"
    state = check_service_update(get_service_row(service.id))
    update_job(job_id, current_version=current, latest_version=state.current_version or latest)
    return "success"


def service_update_worker(job_id: str, service_id: int) -> None:
    update_job(job_id, state="running", started_at=iso_now(), progress=1, message="Starting update")
    try:
        outcome = perform_service_update(service_id, job_id)
        if outcome == "rolled_back":
            update_job(job_id, state="rolled_back", progress=100, message="Update failed; previous container image restored", finished_at=iso_now())
        else:
            update_job(job_id, state="success", progress=100, message="Update complete", finished_at=iso_now(), active_service_id=None)
    except Exception as exc:
        update_job(job_id, state="failed", progress=100, message="Update failed", detail=str(exc)[:1200], finished_at=iso_now())


def batch_update_worker(job_id: str) -> None:
    update_job(job_id, state="running", started_at=iso_now(), progress=1, message="Preparing update queue")
    try:
        with db() as connection:
            cached = connection.execute("""SELECT s.id, s.name FROM services s JOIN service_update_state u ON u.service_id=s.id
                                           WHERE u.state='available' AND s.management_provider!='none' ORDER BY s.name COLLATE NOCASE""").fetchall()
        if not cached:
            update_job(job_id, state="success", progress=100, message="No available updates", finished_at=iso_now(), active_service_id=None)
            return
        total = len(cached)
        for index, item in enumerate(cached):
            segment_start = round(index / total * 100)
            segment_end = round((index + 1) / total * 100)
            update_job(job_id, active_service_id=int(item["id"]), message=f"Updating {item['name']}", progress=segment_start)
            outcome = perform_service_update(int(item["id"]), job_id, max(1, segment_start), max(segment_start + 1, segment_end))
            if outcome == "rolled_back":
                raise RuntimeError(f"{item['name']} failed its health check and was rolled back; batch stopped")
        update_job(job_id, active_service_id=None, state="success", progress=100, message="All available updates completed", finished_at=iso_now())
    except Exception as exc:
        update_job(job_id, state="failed", progress=100, message="Update-all stopped", detail=str(exc)[:1200], finished_at=iso_now())


@app.get("/api/management/docker/resources", response_model=list[ManagedResource])
def docker_management_resources(_: SessionUser = Depends(require_auth)) -> list[ManagedResource]:
    try:
        raw = agent_request("/v1/resources", timeout=30)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    resources = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        resources.append(ManagedResource(id=str(item.get("id")), name=f"{item.get('project')} / {item.get('service')}", provider="docker_compose", detail=str(item.get("image") or "")))
    return resources


@app.get("/api/management/truenas/{controller_service_id}/apps", response_model=list[ManagedResource])
def truenas_management_apps(controller_service_id: int, _: SessionUser = Depends(require_auth)) -> list[ManagedResource]:
    try:
        controller_row = get_service_row(controller_service_id)
        if controller_row["type"] != "truenas":
            raise RuntimeError("Selected controller service is not a TrueNAS card")
        apps = truenas_app_records(controller_row)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return [ManagedResource(
        id=str(item.get("id") or item.get("name")), name=str(item.get("name") or item.get("id")), provider="truenas_app",
        current_version=str(item.get("human_version") or item.get("version") or "") or None,
        latest_version=str(item.get("latest_human_version") or item.get("latest_version") or "") or None,
        update_available=bool(item.get("upgrade_available") or item.get("image_updates_available")), state=str(item.get("state") or "") or None,
    ) for item in apps]


@app.get("/api/updates/status", response_model=list[ServiceUpdateState])
def update_statuses(_: SessionUser = Depends(require_auth)) -> list[ServiceUpdateState]:
    with db() as connection:
        services = connection.execute("SELECT id, management_provider, management_target FROM services ORDER BY id").fetchall()
        cached = {row["service_id"]: row for row in connection.execute("SELECT * FROM service_update_state").fetchall()}
    results: list[ServiceUpdateState] = []
    for service in services:
        row = cached.get(service["id"])
        if row:
            results.append(row_to_update_state(row))
        else:
            provider = service["management_provider"] if service["management_provider"] in {"none", "docker_compose", "truenas_app"} else "none"
            state: UpdateStateName = "unconfigured" if provider == "none" or not service["management_target"] else "unknown"
            results.append(ServiceUpdateState(service_id=service["id"], provider=provider, target=service["management_target"], state=state, can_update=False))
    return results


@app.post("/api/updates/check", response_model=UpdateJob, status_code=status.HTTP_202_ACCEPTED)
def start_update_check(_: SessionUser = Depends(require_write_auth)) -> UpdateJob:
    with db() as connection:
        active = connection.execute("SELECT 1 FROM update_jobs WHERE state IN ('queued','running') LIMIT 1").fetchone()
    if active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Another update job is already running")
    job = create_update_job("check", message="Update check queued")
    threading.Thread(target=check_updates_worker, args=(job.id,), daemon=True).start()
    return job


@app.post("/api/services/{service_id}/update", response_model=UpdateJob, status_code=status.HTTP_202_ACCEPTED)
def start_service_update(service_id: int, _: SessionUser = Depends(require_write_auth)) -> UpdateJob:
    try:
        row = get_service_row(service_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    service = row_to_service(row)
    if service.management_provider == "none" or not service.management_target:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Update management is not configured for this service")
    with db() as connection:
        active = connection.execute("SELECT 1 FROM update_jobs WHERE state IN ('queued','running') LIMIT 1").fetchone()
    if active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Another update job is already running")
    job = create_update_job("update", service_id=service_id, provider=service.management_provider, target=service.management_target, message=f"{service.name} update queued")
    threading.Thread(target=service_update_worker, args=(job.id, service_id), daemon=True).start()
    return job


@app.post("/api/updates/update-all", response_model=UpdateJob, status_code=status.HTTP_202_ACCEPTED)
def start_update_all(_: SessionUser = Depends(require_write_auth)) -> UpdateJob:
    with db() as connection:
        active = connection.execute("SELECT 1 FROM update_jobs WHERE state IN ('queued','running') LIMIT 1").fetchone()
    if active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Another update job is already running")
    job = create_update_job("batch", message="Update-all queued")
    threading.Thread(target=batch_update_worker, args=(job.id,), daemon=True).start()
    return job


@app.get("/api/updates/jobs", response_model=list[UpdateJob])
def list_update_jobs(limit: int = 25, _: SessionUser = Depends(require_auth)) -> list[UpdateJob]:
    limit = max(1, min(limit, 100))
    with db() as connection:
        rows = connection.execute("SELECT * FROM update_jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [row_to_update_job(row) for row in rows]


@app.get("/api/updates/jobs/{job_id}", response_model=UpdateJob)
def get_update_job(job_id: str, _: SessionUser = Depends(require_auth)) -> UpdateJob:
    with db() as connection:
        row = connection.execute("SELECT * FROM update_jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Update job not found")
    return row_to_update_job(row)


@app.get("/api/integrations", response_model=list[IntegrationDescriptor])
def integration_descriptors(_: SessionUser = Depends(require_auth)) -> list[IntegrationDescriptor]:
    return list(INTEGRATIONS.values())


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.11.0", "time": iso_now()}


@app.get("/api/auth/status", response_model=AuthStatus)
def auth_status(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> AuthStatus:
    setup_required = not admin_exists()
    user = None if setup_required else get_session(session_token)
    return AuthStatus(
        setup_required=setup_required,
        authenticated=user is not None,
        username=user.username if user else None,
        csrf_token=user.csrf_token if user else None,
    )


@app.post("/api/auth/setup", response_model=AuthStatus, status_code=status.HTTP_201_CREATED)
def setup_admin(credentials: Credentials, response: Response) -> AuthStatus:
    with db() as connection:
        if connection.execute("SELECT 1 FROM admin_users LIMIT 1").fetchone():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Administrator is already configured")
        cursor = connection.execute(
            "INSERT INTO admin_users (id, username, password_hash, created_at) VALUES (1, ?, ?, ?)",
            (credentials.username, hash_password(credentials.password), iso_now()),
        )
        token, csrf = create_session(connection, cursor.lastrowid or 1)
    set_session_cookie(response, token)
    return AuthStatus(setup_required=False, authenticated=True, username=credentials.username, csrf_token=csrf)


@app.post("/api/auth/login", response_model=AuthStatus)
def login(credentials: Credentials, response: Response) -> AuthStatus:
    with db() as connection:
        user = connection.execute(
            "SELECT id, username, password_hash FROM admin_users WHERE username = ? COLLATE NOCASE",
            (credentials.username,),
        ).fetchone()
        if not user or not verify_password(credentials.password, user["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
        token, csrf = create_session(connection, user["id"])
    set_session_cookie(response, token)
    return AuthStatus(setup_required=False, authenticated=True, username=user["username"], csrf_token=csrf)


@app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    if session_token:
        with db() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_digest(session_token),))
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@app.get("/api/appearance", response_model=AppearanceSettings)
def get_appearance(_: SessionUser = Depends(require_auth)) -> AppearanceSettings:
    with db() as connection:
        row = connection.execute("SELECT value FROM app_settings WHERE key = 'theme_id'").fetchone()
        theme_id = row["value"] if row else "system"
        if not theme_exists(connection, theme_id):
            theme_id = "system"
            connection.execute("INSERT INTO app_settings (key, value) VALUES ('theme_id', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (theme_id,))
        custom_themes = list_theme_rows(connection)
    return AppearanceSettings(theme_id=theme_id, custom_themes=custom_themes)


@app.put("/api/appearance", response_model=AppearanceSettings)
def update_appearance(payload: AppearanceUpdate, _: SessionUser = Depends(require_write_auth)) -> AppearanceSettings:
    with db() as connection:
        if not theme_exists(connection, payload.theme_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme not found")
        connection.execute(
            "INSERT INTO app_settings (key, value) VALUES ('theme_id', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (payload.theme_id,),
        )
        custom_themes = list_theme_rows(connection)
    return AppearanceSettings(theme_id=payload.theme_id, custom_themes=custom_themes)


@app.post("/api/themes", response_model=AppearanceSettings, status_code=status.HTTP_201_CREATED)
def import_theme(payload: ThemePackage, _: SessionUser = Depends(require_write_auth)) -> AppearanceSettings:
    now = iso_now()
    with db() as connection:
        if connection.execute("SELECT 1 FROM custom_themes WHERE id = ?", (payload.id,)).fetchone():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A custom theme with that id already exists")
        connection.execute(
            "INSERT INTO custom_themes (id, manifest_json, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (payload.id, payload.model_dump_json(), now, now),
        )
        row = connection.execute("SELECT value FROM app_settings WHERE key = 'theme_id'").fetchone()
        theme_id = row["value"] if row else "system"
        custom_themes = list_theme_rows(connection)
    return AppearanceSettings(theme_id=theme_id, custom_themes=custom_themes)


@app.delete("/api/themes/{theme_id}", response_model=AppearanceSettings)
def delete_theme(theme_id: str, _: SessionUser = Depends(require_write_auth)) -> AppearanceSettings:
    theme_id = theme_id.strip().lower()
    if theme_id in BUILTIN_THEME_IDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Built-in themes cannot be deleted")
    with db() as connection:
        result = connection.execute("DELETE FROM custom_themes WHERE id = ?", (theme_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme not found")
        row = connection.execute("SELECT value FROM app_settings WHERE key = 'theme_id'").fetchone()
        selected = row["value"] if row else "system"
        if selected == theme_id:
            selected = "system"
            connection.execute(
                "INSERT INTO app_settings (key, value) VALUES ('theme_id', 'system') ON CONFLICT(key) DO UPDATE SET value = excluded.value"
            )
        custom_themes = list_theme_rows(connection)
    return AppearanceSettings(theme_id=selected, custom_themes=custom_themes)


@app.get("/api/pages", response_model=list[DashboardPage])
def list_pages(_: SessionUser = Depends(require_auth)) -> list[DashboardPage]:
    with db() as connection:
        rows = connection.execute(
            "SELECT * FROM dashboard_pages ORDER BY sort_order, id"
        ).fetchall()
    return [row_to_page(row) for row in rows]


@app.post("/api/pages", response_model=DashboardPage, status_code=status.HTTP_201_CREATED)
def create_page(payload: DashboardPageCreate, _: SessionUser = Depends(require_write_auth)) -> DashboardPage:
    now = iso_now()
    with db() as connection:
        sort_order = int(connection.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM dashboard_pages"
        ).fetchone()[0])
        try:
            cursor = connection.execute(
                "INSERT INTO dashboard_pages (name, sort_order, is_default, created_at, updated_at) VALUES (?, ?, 0, ?, ?)",
                (payload.name, sort_order, now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A page with that name already exists") from exc
        row = connection.execute("SELECT * FROM dashboard_pages WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_page(row)


@app.put("/api/pages/{page_id}", response_model=DashboardPage)
def update_page(page_id: int, payload: DashboardPageUpdate, _: SessionUser = Depends(require_write_auth)) -> DashboardPage:
    with db() as connection:
        require_page(connection, page_id)
        try:
            connection.execute(
                "UPDATE dashboard_pages SET name = ?, updated_at = ? WHERE id = ?",
                (payload.name, iso_now(), page_id),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A page with that name already exists") from exc
        row = connection.execute("SELECT * FROM dashboard_pages WHERE id = ?", (page_id,)).fetchone()
    return row_to_page(row)


@app.post("/api/pages/reorder", response_model=list[DashboardPage])
def reorder_pages(payload: PageReorder, _: SessionUser = Depends(require_write_auth)) -> list[DashboardPage]:
    if len(payload.ordered_ids) != len(set(payload.ordered_ids)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate page ids in reorder request")
    with db() as connection:
        existing_ids = [row["id"] for row in connection.execute("SELECT id FROM dashboard_pages ORDER BY id").fetchall()]
        if set(existing_ids) != set(payload.ordered_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Page reorder must include every dashboard page")
        now = iso_now()
        for position, page_id in enumerate(payload.ordered_ids, start=1):
            connection.execute(
                "UPDATE dashboard_pages SET sort_order = ?, updated_at = ? WHERE id = ?",
                (position, now, page_id),
            )
        rows = connection.execute("SELECT * FROM dashboard_pages ORDER BY sort_order, id").fetchall()
    return [row_to_page(row) for row in rows]


@app.delete("/api/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_page(page_id: int, _: SessionUser = Depends(require_write_auth)) -> Response:
    with db() as connection:
        page = require_page(connection, page_id)
        if page["is_default"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The default Home page cannot be deleted")
        service_count = int(connection.execute("SELECT COUNT(*) FROM services WHERE page_id = ?", (page_id,)).fetchone()[0])
        if service_count:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Move or remove services from this page before deleting it")
        connection.execute("DELETE FROM dashboard_pages WHERE id = ?", (page_id,))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/categories", response_model=list[CategoryLayout])
def list_categories(_: SessionUser = Depends(require_auth)) -> list[CategoryLayout]:
    with db() as connection:
        ensure_category_layouts(connection)
        rows = connection.execute(
            """
            SELECT c.page_id, c.name, c.sort_order, c.collapsed
            FROM category_layouts c
            WHERE EXISTS (
                SELECT 1 FROM services s
                WHERE s.page_id = c.page_id AND s.category = c.name COLLATE NOCASE
            )
            ORDER BY c.page_id, c.sort_order, c.name COLLATE NOCASE
            """
        ).fetchall()
    return [row_to_category(row) for row in rows]


@app.patch("/api/categories/state", response_model=CategoryLayout)
def update_category_state(payload: CategoryStateUpdate, _: SessionUser = Depends(require_write_auth)) -> CategoryLayout:
    with db() as connection:
        require_page(connection, payload.page_id)
        ensure_category_layout(connection, payload.page_id, payload.name)
        connection.execute(
            "UPDATE category_layouts SET collapsed = ? WHERE page_id = ? AND name = ?",
            (int(payload.collapsed), payload.page_id, payload.name),
        )
        row = connection.execute(
            "SELECT * FROM category_layouts WHERE page_id = ? AND name = ?",
            (payload.page_id, payload.name),
        ).fetchone()
    return row_to_category(row)


@app.post("/api/categories/reorder", response_model=list[CategoryLayout])
def reorder_categories(payload: CategoryReorder, _: SessionUser = Depends(require_write_auth)) -> list[CategoryLayout]:
    if len(payload.ordered_names) != len(set(name.casefold() for name in payload.ordered_names)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate category names in reorder request")
    with db() as connection:
        require_page(connection, payload.page_id)
        ensure_category_layouts(connection)
        current = [
            row["category"]
            for row in connection.execute(
                "SELECT category FROM services WHERE page_id = ? GROUP BY category COLLATE NOCASE ORDER BY category COLLATE NOCASE",
                (payload.page_id,),
            ).fetchall()
        ]
        if {name.casefold() for name in current} != {name.casefold() for name in payload.ordered_names}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category reorder must include every category on the page")
        for position, name in enumerate(payload.ordered_names, start=1):
            ensure_category_layout(connection, payload.page_id, name)
            connection.execute(
                "UPDATE category_layouts SET sort_order = ? WHERE page_id = ? AND name = ? COLLATE NOCASE",
                (position, payload.page_id, name),
            )
        rows = connection.execute(
            """
            SELECT c.page_id, c.name, c.sort_order, c.collapsed
            FROM category_layouts c
            WHERE c.page_id = ? AND EXISTS (
                SELECT 1 FROM services s WHERE s.page_id = c.page_id AND s.category = c.name COLLATE NOCASE
            )
            ORDER BY c.sort_order, c.name COLLATE NOCASE
            """,
            (payload.page_id,),
        ).fetchall()
    return [row_to_category(row) for row in rows]


@app.get("/api/services", response_model=list[Service])
def list_services(_: SessionUser = Depends(require_auth)) -> list[Service]:
    with db() as connection:
        rows = connection.execute(
            "SELECT * FROM services WHERE enabled = 1 ORDER BY page_id, category COLLATE NOCASE, sort_order, name COLLATE NOCASE"
        ).fetchall()
    return [row_to_service(row) for row in rows]


@app.get("/api/services/all", response_model=list[Service])
def list_all_services(_: SessionUser = Depends(require_auth)) -> list[Service]:
    with db() as connection:
        rows = connection.execute(
            "SELECT * FROM services ORDER BY page_id, category COLLATE NOCASE, sort_order, name COLLATE NOCASE"
        ).fetchall()
    return [row_to_service(row) for row in rows]


@app.get("/api/services/status", response_model=list[ServiceStatus])
def service_statuses(_: SessionUser = Depends(require_auth)) -> list[ServiceStatus]:
    with db() as connection:
        rows = connection.execute(
            "SELECT * FROM services ORDER BY page_id, category COLLATE NOCASE, sort_order, name COLLATE NOCASE"
        ).fetchall()
    services = [row_to_service(row) for row in rows]
    if not services:
        return []

    results: dict[int, ServiceStatus] = {}
    with ThreadPoolExecutor(max_workers=min(STATUS_WORKERS, len(services))) as executor:
        futures = {executor.submit(probe_service, service): service.id for service in services}
        for future in as_completed(futures):
            service_id = futures[future]
            try:
                results[service_id] = future.result()
            except Exception as exc:  # pragma: no cover - defensive fallback
                results[service_id] = ServiceStatus(
                    id=service_id,
                    state="offline",
                    checked_at=iso_now(),
                    detail=str(exc)[:160],
                )
    return [results[service.id] for service in services]


@app.get("/api/services/insights", response_model=list[ServiceInsight])
def service_insights(_: SessionUser = Depends(require_auth)) -> list[ServiceInsight]:
    with db() as connection:
        rows = connection.execute(
            "SELECT * FROM services ORDER BY page_id, category COLLATE NOCASE, sort_order, name COLLATE NOCASE"
        ).fetchall()
    relevant = [row for row in rows if row["type"] in INTEGRATIONS]
    if not relevant:
        return []
    results: dict[int, ServiceInsight] = {}
    with ThreadPoolExecutor(max_workers=min(STATUS_WORKERS, len(relevant))) as executor:
        futures = {executor.submit(insight_for_row, row): row["id"] for row in relevant}
        for future in as_completed(futures):
            service_id = futures[future]
            try:
                results[service_id] = future.result()
            except Exception as exc:  # pragma: no cover
                results[service_id] = ServiceInsight(id=service_id, kind="unknown", state="unavailable", summary="Integration unavailable", secondary=str(exc)[:120])
    return [results[row["id"]] for row in relevant]


@app.post("/api/services", response_model=Service, status_code=status.HTTP_201_CREATED)
def create_service(service: ServiceCreate, _: SessionUser = Depends(require_write_auth)) -> Service:
    now = iso_now()
    with db() as connection:
        require_page(connection, service.page_id)
        ensure_category_layout(connection, service.page_id, service.category)
        cursor = connection.execute(
            """
            INSERT INTO services (name, type, url, category, page_id, icon, enabled, status_check, favorite, card_size, sort_order, api_key_encrypted, auth_username_encrypted, auth_password_encrypted, management_provider, management_target, management_controller_service_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                service.name,
                service.type,
                str(service.url),
                service.category,
                service.page_id,
                service.icon,
                int(service.enabled),
                int(service.status_check),
                int(service.favorite),
                service.card_size,
                int(connection.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM services WHERE page_id = ? AND category = ?", (service.page_id, service.category)).fetchone()[0]),
                encrypt_secret(service.api_key),
                encrypt_secret(service.auth_username),
                encrypt_secret(service.auth_password),
                service.management_provider,
                service.management_target,
                service.management_controller_service_id,
                now,
                now,
            ),
        )
        row = connection.execute("SELECT * FROM services WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_service(row)


@app.put("/api/services/{service_id}", response_model=Service)
def update_service(service_id: int, service: ServiceUpdate, _: SessionUser = Depends(require_write_auth)) -> Service:
    now = iso_now()
    with db() as connection:
        current = connection.execute("SELECT category, page_id, sort_order, api_key_encrypted, auth_username_encrypted, auth_password_encrypted, management_provider, management_target, management_controller_service_id FROM services WHERE id = ?", (service_id,)).fetchone()
        if not current:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
        require_page(connection, service.page_id)
        ensure_category_layout(connection, service.page_id, service.category)
        api_key_encrypted = current["api_key_encrypted"]
        if service.clear_api_key:
            api_key_encrypted = None
        elif service.api_key:
            api_key_encrypted = encrypt_secret(service.api_key)
        auth_username_encrypted = current["auth_username_encrypted"]
        auth_password_encrypted = current["auth_password_encrypted"]
        if service.clear_auth_credentials:
            auth_username_encrypted = None
            auth_password_encrypted = None
        else:
            if service.auth_username:
                auth_username_encrypted = encrypt_secret(service.auth_username)
            if service.auth_password:
                auth_password_encrypted = encrypt_secret(service.auth_password)
        sort_order = service.sort_order
        if service.category != current["category"] or service.page_id != current["page_id"]:
            sort_order = int(connection.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM services WHERE page_id = ? AND category = ?",
                (service.page_id, service.category),
            ).fetchone()[0])
        connection.execute(
            """
            UPDATE services
            SET name = ?, type = ?, url = ?, category = ?, page_id = ?, icon = ?, enabled = ?, status_check = ?, favorite = ?, card_size = ?, sort_order = ?, api_key_encrypted = ?, auth_username_encrypted = ?, auth_password_encrypted = ?, management_provider = ?, management_target = ?, management_controller_service_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                service.name,
                service.type,
                str(service.url),
                service.category,
                service.page_id,
                service.icon,
                int(service.enabled),
                int(service.status_check),
                int(service.favorite),
                service.card_size,
                sort_order,
                api_key_encrypted,
                auth_username_encrypted,
                auth_password_encrypted,
                service.management_provider,
                service.management_target,
                service.management_controller_service_id,
                now,
                service_id,
            ),
        )
        if (service.management_provider != current["management_provider"] or service.management_target != current["management_target"] or service.management_controller_service_id != current["management_controller_service_id"]):
            connection.execute("DELETE FROM service_update_state WHERE service_id = ?", (service_id,))
        row = connection.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone()
    return row_to_service(row)


@app.patch("/api/services/{service_id}/layout", response_model=Service)
def update_service_layout(service_id: int, layout: ServiceLayoutUpdate, _: SessionUser = Depends(require_write_auth)) -> Service:
    updates: list[str] = []
    values: list[object] = []
    if layout.favorite is not None:
        updates.append("favorite = ?")
        values.append(int(layout.favorite))
    if layout.card_size is not None:
        updates.append("card_size = ?")
        values.append(layout.card_size)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No layout changes supplied")
    updates.append("updated_at = ?")
    values.append(iso_now())
    values.append(service_id)
    with db() as connection:
        existing = connection.execute("SELECT 1 FROM services WHERE id = ?", (service_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
        connection.execute(f"UPDATE services SET {', '.join(updates)} WHERE id = ?", tuple(values))
        row = connection.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone()
    return row_to_service(row)


@app.post("/api/services/reorder", response_model=list[Service])
def reorder_services(payload: ServiceReorder, _: SessionUser = Depends(require_write_auth)) -> list[Service]:
    if len(payload.ordered_ids) != len(set(payload.ordered_ids)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate service ids in reorder request")
    with db() as connection:
        placeholders = ",".join("?" for _ in payload.ordered_ids)
        rows = connection.execute(
            f"SELECT id, category, page_id FROM services WHERE id IN ({placeholders})",
            tuple(payload.ordered_ids),
        ).fetchall()
        if len(rows) != len(payload.ordered_ids):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more services were not found")
        if any(row["category"] != payload.category or row["page_id"] != payload.page_id for row in rows):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Services can only be reordered within the same page and category")
        now = iso_now()
        for position, service_id in enumerate(payload.ordered_ids, start=1):
            connection.execute(
                "UPDATE services SET sort_order = ?, updated_at = ? WHERE id = ?",
                (position, now, service_id),
            )
        ordered_rows = connection.execute(
            "SELECT * FROM services WHERE page_id = ? AND category = ? ORDER BY sort_order, name COLLATE NOCASE",
            (payload.page_id, payload.category),
        ).fetchall()
    return [row_to_service(row) for row in ordered_rows]


@app.delete("/api/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(service_id: int, _: SessionUser = Depends(require_write_auth)) -> Response:
    with db() as connection:
        cursor = connection.execute("DELETE FROM services WHERE id = ?", (service_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
