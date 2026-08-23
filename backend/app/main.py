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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

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
SECRET_KEY_PATH = DATA_DIR / "secret.key"

app = FastAPI(title=f"{APP_NAME} API", version="0.9.0")

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


class ServiceInsight(BaseModel):
    id: int
    kind: str
    state: Literal["ok", "setup", "unavailable", "none"] = "none"
    summary: str | None = None
    secondary: str | None = None
    items: list[str] = Field(default_factory=list)


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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        ensure_service_migrations(connection)
        ensure_default_page(connection)
        connection.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('theme_id', 'system')")
        ensure_category_layouts(connection)
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (iso_now(),))


@app.on_event("startup")
def startup() -> None:
    init_db()


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
        has_api_key=bool(row["api_key_encrypted"]),
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
        headers={"User-Agent": "HomelabDashboard/0.9.0", "Accept": "*/*"},
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


def request_json(url: str, headers: dict[str, str] | None = None, verify_tls: bool = True) -> object:
    request = Request(url, method="GET", headers={"User-Agent": "HomelabDashboard/0.9.0", "Accept": "application/json", **(headers or {})})
    context = None if verify_tls else ssl._create_unverified_context()
    with urlopen(request, timeout=STATUS_TIMEOUT, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def service_json(service: Service, path: str, headers: dict[str, str] | None = None) -> object:
    base = str(service.url).rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    hostname = urlparse(url).hostname
    try:
        return request_json(url, headers=headers)
    except URLError as exc:
        reason = exc.reason
        if is_private_hostname(hostname) and isinstance(reason, (ssl.SSLCertVerificationError, ssl.SSLError)):
            return request_json(url, headers=headers, verify_tls=False)
        raise


def jellyfin_insight(service: Service, encrypted_key: str | None) -> ServiceInsight:
    key = decrypt_secret(encrypted_key)
    if not key:
        return ServiceInsight(
            id=service.id,
            kind="jellyfin",
            state="setup",
            summary="Add API key for stream details",
            secondary="Edit this card to enable Jellyfin integration",
        )
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
        summary = f"{count} active stream{'s' if count != 1 else ''}"
        if count == 0:
            summary = "No active streams"
        extras = []
        if paused:
            extras.append(f"{paused} paused")
        if transcoding:
            extras.append(f"{transcoding} transcoding")
        secondary = f"Jellyfin {info.get('Version', 'server')}"
        if extras:
            secondary += " · " + " · ".join(extras)
        return ServiceInsight(id=service.id, kind="jellyfin", state="ok", summary=summary, secondary=secondary, items=items)
    except Exception as exc:  # noqa: BLE001
        detail = str(getattr(exc, "reason", exc)) or exc.__class__.__name__
        return ServiceInsight(id=service.id, kind="jellyfin", state="unavailable", summary="Jellyfin integration unavailable", secondary=detail[:120])


def docker_host_insight(service_id: int, kind: str = "docker-host") -> ServiceInsight:
    if not DOCKER_PROXY_URL:
        return ServiceInsight(
            id=service_id,
            kind=kind,
            state="setup",
            summary="Docker host integration not enabled",
            secondary="Enable the optional Docker socket proxy to show local container statistics",
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
        )
    except Exception as exc:  # noqa: BLE001
        detail = str(getattr(exc, "reason", exc)) or exc.__class__.__name__
        return ServiceInsight(id=service_id, kind=kind, state="unavailable", summary="Docker host stats unavailable", secondary=detail[:120])


def insight_for_row(row: sqlite3.Row) -> ServiceInsight:
    service = row_to_service(row)
    if not service.enabled:
        return ServiceInsight(id=service.id, kind=service.type, state="none")
    if service.type == "jellyfin":
        return jellyfin_insight(service, row["api_key_encrypted"])
    if service.type in {"dockge", "docker-host"}:
        return docker_host_insight(service.id, service.type)
    return ServiceInsight(id=service.id, kind=service.type, state="none")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.9.0", "time": iso_now()}


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
    relevant = [row for row in rows if row["type"] in {"jellyfin", "dockge", "docker-host"}]
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
            INSERT INTO services (name, type, url, category, page_id, icon, enabled, status_check, favorite, card_size, sort_order, api_key_encrypted, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        current = connection.execute("SELECT category, page_id, sort_order, api_key_encrypted FROM services WHERE id = ?", (service_id,)).fetchone()
        if not current:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
        require_page(connection, service.page_id)
        ensure_category_layout(connection, service.page_id, service.category)
        api_key_encrypted = current["api_key_encrypted"]
        if service.clear_api_key:
            api_key_encrypted = None
        elif service.api_key:
            api_key_encrypted = encrypt_secret(service.api_key)
        sort_order = service.sort_order
        if service.category != current["category"] or service.page_id != current["page_id"]:
            sort_order = int(connection.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM services WHERE page_id = ? AND category = ?",
                (service.page_id, service.category),
            ).fetchone()[0])
        connection.execute(
            """
            UPDATE services
            SET name = ?, type = ?, url = ?, category = ?, page_id = ?, icon = ?, enabled = ?, status_check = ?, favorite = ?, card_size = ?, sort_order = ?, api_key_encrypted = ?, updated_at = ?
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
                now,
                service_id,
            ),
        )
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
