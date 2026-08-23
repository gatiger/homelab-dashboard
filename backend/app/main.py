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
from contextlib import asynccontextmanager, contextmanager
from http.cookies import SimpleCookie
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from websocket import WebSocketTimeoutException, create_connection

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

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
HOST_UPDATE_RECONNECT_TIMEOUT = max(300, min(int(os.getenv("HOST_UPDATE_RECONNECT_TIMEOUT", "1800")), 7200))
UPDATE_CHECK_INTERVAL_HOURS = max(0.0, min(float(os.getenv("UPDATE_CHECK_INTERVAL_HOURS", "12")), 168.0))
EXTENSION_REGISTRY_URL = os.getenv("EXTENSION_REGISTRY_URL", "https://raw.githubusercontent.com/gatiger/homelab-dashboard/main/registry/index.json").strip()
EXTENSION_REGISTRY_TIMEOUT = max(2.0, min(float(os.getenv("EXTENSION_REGISTRY_TIMEOUT", "8")), 30.0))
EXTENSION_REGISTRY_CACHE_SECONDS = max(30, min(int(os.getenv("EXTENSION_REGISTRY_CACHE_SECONDS", "300")), 3600))
SECRET_KEY_PATH = DATA_DIR / "secret.key"

APP_VERSION = "0.20.1"


@asynccontextmanager
async def app_lifespan(_: FastAPI):
    init_db()
    recover_host_update_jobs()
    threading.Thread(target=automatic_update_check_loop, daemon=True, name="update-check-loop").start()
    yield


app = FastAPI(title=f"{APP_NAME} API", version=APP_VERSION, lifespan=app_lifespan)

# Vite development origin. Production traffic is same-origin through nginx.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


UserRole = Literal["owner", "admin", "editor", "viewer"]

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": {
        "dashboard:view", "dashboard:edit", "services:manage", "secrets:manage",
        "updates:run", "updates:host", "connections:manage", "extensions:manage", "settings:manage",
        "users:manage",
    },
    "admin": {
        "dashboard:view", "dashboard:edit", "services:manage", "secrets:manage",
        "updates:run", "updates:host", "connections:manage", "extensions:manage", "settings:manage",
    },
    "editor": {"dashboard:view", "dashboard:edit", "services:manage"},
    "viewer": {"dashboard:view"},
}


def permissions_for_role(role: str) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["viewer"]))


class AuthStatus(BaseModel):
    setup_required: bool
    authenticated: bool
    username: str | None = None
    role: UserRole | None = None
    permissions: list[str] = Field(default_factory=list)
    csrf_token: str | None = None
    # Returned only when a new one-time recovery code has just been created.
    recovery_code: str | None = None


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


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


class RecoveryCodeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)


class PasswordRecoveryRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    recovery_code: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=10, max_length=256)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip()


class RecoveryCodeResult(BaseModel):
    recovery_code: str
    generated_at: str


class AccountAuditEvent(BaseModel):
    id: int
    event: str
    detail: str | None = None
    created_at: str


class AccountSummary(BaseModel):
    username: str
    role: UserRole
    recovery_configured: bool
    recovery_generated_at: str | None = None
    password_changed_at: str | None = None
    recent_events: list[AccountAuditEvent] = Field(default_factory=list)


class UserSummary(BaseModel):
    id: int
    username: str
    role: UserRole
    enabled: bool
    recovery_configured: bool
    password_changed_at: str | None = None
    last_login_at: str | None = None
    created_at: str


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=256)
    role: UserRole = "viewer"

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Username is required")
        return value


class UserUpdate(BaseModel):
    role: UserRole
    enabled: bool = True


class UserPasswordReset(BaseModel):
    new_password: str = Field(min_length=10, max_length=256)


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
    management_provider: str = Field(default="none", min_length=1, max_length=64)
    management_target: str | None = Field(default=None, max_length=300)
    management_controller_service_id: int | None = Field(default=None, ge=1)
    management_connection_id: int | None = Field(default=None, ge=1)

    @field_validator("management_provider")
    @classmethod
    def normalize_management_provider(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            return "none"
        if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for character in value):
            raise ValueError("Management provider may contain only letters, numbers, dots, underscores, and hyphens")
        return value

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


class ManagementConnectionBase(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    type: Literal["truenas"] = "truenas"
    url: HttpUrl
    api_key: str | None = Field(default=None, max_length=512, exclude=True)
    clear_api_key: bool = Field(default=False, exclude=True)
    auth_username: str | None = Field(default=None, max_length=256, exclude=True)
    clear_auth_username: bool = Field(default=False, exclude=True)

    @field_validator("name")
    @classmethod
    def trim_connection_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Connection name cannot be blank")
        return value


class ManagementConnectionCreate(ManagementConnectionBase):
    pass


class ManagementConnectionUpdate(ManagementConnectionBase):
    pass


class ManagementConnection(BaseModel):
    id: int
    name: str
    type: Literal["truenas"]
    url: str
    has_api_key: bool = False
    has_auth_username: bool = False
    used_by: int = 0
    created_at: str
    updated_at: str


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str


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


class PageCloneRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)

    @field_validator("name")
    @classmethod
    def trim_clone_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Page name cannot be blank")
        return value


class CategoryLayout(BaseModel):
    page_id: int
    name: str
    sort_order: int
    collapsed: bool
    icon: str | None = None


class CategoryUpdate(BaseModel):
    page_id: int = Field(ge=1)
    old_name: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    icon: str | None = Field(default=None, max_length=32)

    @field_validator("old_name", "name")
    @classmethod
    def trim_category_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Category name cannot be blank")
        return value

    @field_validator("icon")
    @classmethod
    def normalize_category_icon(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if not value:
            return None
        if not re.fullmatch(r"[a-z0-9-]{1,32}", value):
            raise ValueError("Category icon must use letters, numbers, or hyphens")
        return value


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


class DashboardSettings(BaseModel):
    dashboard_title: str = Field(default=APP_NAME, min_length=1, max_length=80)
    show_greeting: bool = True
    telemetry_refresh_seconds: int = Field(default=15, ge=5, le=300)
    update_status_refresh_seconds: int = Field(default=15, ge=5, le=300)
    active_refresh_seconds: int = Field(default=3, ge=1, le=30)
    update_check_interval_hours: float = Field(default=12, ge=0, le=168)

    @field_validator("dashboard_title")
    @classmethod
    def trim_dashboard_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Dashboard title cannot be blank")
        return value


WidgetType = Literal["clock", "note", "bookmarks", "system_summary", "service_status", "update_overview"]


class DashboardWidgetBase(BaseModel):
    type: WidgetType
    title: str = Field(min_length=1, max_length=80)
    page_id: int = Field(default=1, ge=1)
    category: str = Field(default="Widgets", min_length=1, max_length=80)
    card_size: Literal["compact", "standard", "wide"] = "standard"
    sort_order: int = Field(default=0, ge=0, le=1000000)
    enabled: bool = True
    config: dict[str, object] = Field(default_factory=dict)

    @field_validator("title", "category")
    @classmethod
    def trim_widget_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value


class DashboardWidgetCreate(DashboardWidgetBase):
    pass


class DashboardWidgetUpdate(DashboardWidgetBase):
    pass


class DashboardWidget(DashboardWidgetBase):
    id: int
    created_at: str
    updated_at: str


class WidgetLayoutUpdate(BaseModel):
    card_size: Literal["compact", "standard", "wide"] | None = None
    enabled: bool | None = None


class WidgetReorder(BaseModel):
    page_id: int = Field(default=1, ge=1)
    category: str = Field(min_length=1, max_length=80)
    ordered_ids: list[int] = Field(min_length=1, max_length=500)


class DashboardItemRef(BaseModel):
    kind: Literal["service", "widget"]
    id: int = Field(ge=1)


class DashboardItemReorder(BaseModel):
    page_id: int = Field(default=1, ge=1)
    category: str = Field(min_length=1, max_length=80)
    ordered_items: list[DashboardItemRef] = Field(min_length=1, max_length=1000)


class ExtensionDescriptor(BaseModel):
    id: str
    name: str
    type: Literal["core", "theme", "widget_pack", "page_template_pack", "catalog_pack", "bundle"]
    version: str
    author: str
    description: str
    source: Literal["built_in", "imported"]
    active: bool = True
    enabled: bool = True
    removable: bool = False
    capabilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


class ExtensionRegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=3, max_length=80)
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=5, max_length=40)
    author: str = Field(min_length=1, max_length=100)
    description: str = Field(default="Community data extension", max_length=240)
    type: Literal["page_template_pack", "catalog_pack", "bundle"]
    min_dashboard_version: str = Field(default="0.17.0", min_length=5, max_length=40)
    capabilities: list[str] = Field(default_factory=list, max_length=10)
    permissions: list[str] = Field(default_factory=list, max_length=10)
    trust: Literal["official", "verified_community", "community"] = "community"
    package: str = Field(min_length=1, max_length=240)
    sha256: str = Field(min_length=64, max_length=64)
    homepage_url: str | None = Field(default=None, max_length=500)
    repository_url: str | None = Field(default=None, max_length=500)

    @field_validator("id")
    @classmethod
    def validate_registry_id(cls, value: str) -> str:
        value = value.strip().lower()
        if not EXTENSION_ID.fullmatch(value) or value.startswith("core.") or value.startswith("theme."):
            raise ValueError("Invalid extension id")
        return value

    @field_validator("version", "min_dashboard_version")
    @classmethod
    def validate_registry_version(cls, value: str) -> str:
        value = value.strip()
        if not THEME_VERSION.fullmatch(value):
            raise ValueError("Version must look like 1.0.0")
        return value

    @field_validator("capabilities")
    @classmethod
    def validate_registry_capabilities(cls, values: list[str]) -> list[str]:
        unique = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        unknown = [value for value in unique if value not in EXTENSION_CAPABILITIES]
        if unknown:
            raise ValueError(f"Unsupported extension capabilities: {', '.join(unknown)}")
        return unique

    @field_validator("permissions")
    @classmethod
    def validate_registry_permissions(cls, values: list[str]) -> list[str]:
        unique = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        unknown = [value for value in unique if value not in EXTENSION_PERMISSIONS]
        if unknown:
            raise ValueError(f"Unsupported extension permissions: {', '.join(unknown)}")
        return unique

    @field_validator("package")
    @classmethod
    def validate_package_path(cls, value: str) -> str:
        value = value.strip()
        parsed = urlparse(value)
        if parsed.scheme or parsed.netloc or value.startswith("//") or any(part == ".." for part in value.split("/")):
            raise ValueError("Registry package must be a relative path")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("sha256 must contain 64 hexadecimal characters")
        return value


class ExtensionRegistryIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["homelab-dashboard-extension-registry"] = "homelab-dashboard-extension-registry"
    schema_version: Literal[1] = 1
    id: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="Homelab Dashboard extension registry", max_length=300)
    entries: list[ExtensionRegistryEntry] = Field(default_factory=list, max_length=2000)


class ExtensionRegistryItem(ExtensionRegistryEntry):
    installed_version: str | None = None
    installed_enabled: bool | None = None
    update_available: bool = False
    compatible: bool = True
    compatibility_message: str | None = None


class ExtensionRegistryResponse(BaseModel):
    registry_id: str
    registry_name: str
    description: str
    source_url: str
    checked_at: str
    entries: list[ExtensionRegistryItem]


class ExtensionRegistryInstallRequest(BaseModel):
    expected_version: str = Field(min_length=5, max_length=40)
    expected_sha256: str = Field(min_length=64, max_length=64)
    accepted_permissions: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("expected_version")
    @classmethod
    def validate_expected_version(cls, value: str) -> str:
        value = value.strip()
        if not THEME_VERSION.fullmatch(value):
            raise ValueError("Version must look like 1.0.0")
        return value

    @field_validator("expected_sha256")
    @classmethod
    def validate_expected_sha256(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("Invalid sha256")
        return value


EXTENSION_ID = re.compile(r"^[a-z0-9][a-z0-9.-]{2,79}$")
EXTENSION_CAPABILITIES = {"page_templates", "service_catalog"}
EXTENSION_PERMISSIONS = {"dashboard:register-templates", "catalog:register-entries"}


class ExtensionCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=80)
    icon: str | None = Field(default=None, max_length=80)
    defaultPort: int | None = Field(default=None, ge=1, le=65535)
    defaultScheme: Literal["http", "https"] | None = None
    description: str = Field(min_length=1, max_length=240)
    aliases: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("type")
    @classmethod
    def validate_catalog_type(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,79}", value):
            raise ValueError("Catalog service type must use lowercase letters, numbers, dots, underscores, or hyphens")
        return value

    @field_validator("name", "category", "description")
    @classmethod
    def trim_catalog_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, values: list[str]) -> list[str]:
        return [value.strip()[:80] for value in values if value.strip()][:20]


class PageTemplateCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    sort_order: int = Field(default=0, ge=0, le=1000)
    collapsed: bool = False
    icon: str | None = Field(default=None, max_length=32)


class PageTemplateService(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    type: str = Field(default="link", min_length=1, max_length=80)
    url: str = Field(min_length=1, max_length=1000)
    category: str = Field(default="General", min_length=1, max_length=80)
    icon: str | None = Field(default=None, max_length=32)
    enabled: bool = True
    status_check: bool = True
    favorite: bool = False
    card_size: Literal["compact", "standard", "wide"] = "standard"
    sort_order: int = Field(default=0, ge=0, le=1000000)

    @field_validator("type")
    @classmethod
    def validate_template_service_type(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", value):
            raise ValueError("Template service type must use lowercase letters, numbers, dots, underscores, or hyphens")
        return value

    @field_validator("url")
    @classmethod
    def validate_template_url(cls, value: str) -> str:
        value = value.strip()
        if urlparse(value).scheme not in {"http", "https"}:
            raise ValueError("Template service URLs must use http or https")
        return value


class PageTemplateWidget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: WidgetType
    title: str = Field(min_length=1, max_length=80)
    category: str = Field(default="Widgets", min_length=1, max_length=80)
    card_size: Literal["compact", "standard", "wide"] = "standard"
    sort_order: int = Field(default=0, ge=0, le=1000000)
    enabled: bool = True
    config: dict[str, object] = Field(default_factory=dict)


class PageTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="Reusable dashboard page template", max_length=240)
    categories: list[PageTemplateCategory] = Field(default_factory=list, max_length=100)
    services: list[PageTemplateService] = Field(default_factory=list, max_length=500)
    widgets: list[PageTemplateWidget] = Field(default_factory=list, max_length=500)

    @field_validator("id")
    @classmethod
    def validate_template_id(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,59}", value):
            raise ValueError("Template id must use lowercase letters, numbers, and hyphens")
        return value


class ExtensionPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["homelab-dashboard-extension"] = "homelab-dashboard-extension"
    schema_version: Literal[1] = 1
    id: str = Field(min_length=3, max_length=80)
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=5, max_length=40)
    author: str = Field(min_length=1, max_length=100)
    description: str = Field(default="Community data extension", max_length=240)
    type: Literal["page_template_pack", "catalog_pack", "bundle"]
    min_dashboard_version: str = Field(default="0.16.0", min_length=5, max_length=40)
    capabilities: list[str] = Field(default_factory=list, max_length=10)
    permissions: list[str] = Field(default_factory=list, max_length=10)
    page_templates: list[PageTemplate] = Field(default_factory=list, max_length=50)
    catalog_entries: list[ExtensionCatalogEntry] = Field(default_factory=list, max_length=500)

    @field_validator("id")
    @classmethod
    def validate_extension_id(cls, value: str) -> str:
        value = value.strip().lower()
        if not EXTENSION_ID.fullmatch(value):
            raise ValueError("Extension id must use lowercase letters, numbers, dots, or hyphens")
        if value.startswith("core.") or value.startswith("theme."):
            raise ValueError("Extension id uses a reserved prefix")
        return value

    @field_validator("version", "min_dashboard_version")
    @classmethod
    def validate_extension_version(cls, value: str) -> str:
        value = value.strip()
        if not THEME_VERSION.fullmatch(value):
            raise ValueError("Version must look like 1.0.0")
        return value

    @field_validator("name", "author", "description")
    @classmethod
    def trim_extension_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("capabilities")
    @classmethod
    def validate_extension_capabilities(cls, values: list[str]) -> list[str]:
        unique = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        unknown = [value for value in unique if value not in EXTENSION_CAPABILITIES]
        if unknown:
            raise ValueError(f"Unsupported extension capabilities: {', '.join(unknown)}")
        return unique

    @field_validator("permissions")
    @classmethod
    def validate_extension_permissions(cls, values: list[str]) -> list[str]:
        unique = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        unknown = [value for value in unique if value not in EXTENSION_PERMISSIONS]
        if unknown:
            raise ValueError(f"Unsupported extension permissions: {', '.join(unknown)}")
        return unique


class ExtensionStateUpdate(BaseModel):
    enabled: bool


class PageTemplateDescriptor(BaseModel):
    extension_id: str
    template_id: str
    name: str
    description: str
    author: str
    source: Literal["built_in", "imported"]


BUILTIN_PAGE_TEMPLATES: list[PageTemplate] = [
    PageTemplate(
        id="operations", name="Operations", description="At-a-glance service health and update status.",
        categories=[PageTemplateCategory(name="Overview", sort_order=1, icon="server")],
        widgets=[
            PageTemplateWidget(type="system_summary", title="Dashboard Summary", category="Overview", card_size="standard", sort_order=1, config={"show_services": True, "show_updates": True, "show_connections": True}),
            PageTemplateWidget(type="service_status", title="Service Status", category="Overview", card_size="wide", sort_order=2, config={"limit": 8, "show_latency": True}),
            PageTemplateWidget(type="update_overview", title="Updates", category="Overview", card_size="wide", sort_order=3, config={"limit": 8, "show_current": False}),
        ],
    ),
    PageTemplate(
        id="personal-start", name="Personal Start", description="Clock, quick links, and a notes area.",
        categories=[PageTemplateCategory(name="Home", sort_order=1, icon="star")],
        widgets=[
            PageTemplateWidget(type="clock", title="Clock & Date", category="Home", card_size="standard", sort_order=1, config={"format": "12", "timezone": "local", "show_date": True, "show_seconds": False}),
            PageTemplateWidget(type="bookmarks", title="Quick Links", category="Home", card_size="wide", sort_order=2, config={"items": []}),
            PageTemplateWidget(type="note", title="Notes", category="Home", card_size="wide", sort_order=3, config={"text": ""}),
        ],
    ),
]


SETTINGS_DEFAULTS: dict[str, str] = {
    "dashboard_title": APP_NAME,
    "show_greeting": "1",
    "telemetry_refresh_seconds": "15",
    "update_status_refresh_seconds": "15",
    "active_refresh_seconds": "3",
    "update_check_interval_hours": str(UPDATE_CHECK_INTERVAL_HOURS),
}


def read_dashboard_settings(connection: sqlite3.Connection | None = None) -> DashboardSettings:
    owns_connection = connection is None
    current = connection or sqlite3.connect(DB_PATH)
    if owns_connection:
        current.row_factory = sqlite3.Row
    try:
        rows = current.execute(
            "SELECT key, value FROM app_settings WHERE key IN (?, ?, ?, ?, ?, ?)",
            tuple(SETTINGS_DEFAULTS.keys()),
        ).fetchall()
        values = dict(SETTINGS_DEFAULTS)
        values.update({row["key"]: row["value"] for row in rows})
        return DashboardSettings(
            dashboard_title=values["dashboard_title"],
            show_greeting=values["show_greeting"] == "1",
            telemetry_refresh_seconds=int(float(values["telemetry_refresh_seconds"])),
            update_status_refresh_seconds=int(float(values["update_status_refresh_seconds"])),
            active_refresh_seconds=int(float(values["active_refresh_seconds"])),
            update_check_interval_hours=float(values["update_check_interval_hours"]),
        )
    finally:
        if owns_connection:
            current.close()


def save_dashboard_settings(connection: sqlite3.Connection, settings: DashboardSettings) -> None:
    values = {
        "dashboard_title": settings.dashboard_title,
        "show_greeting": "1" if settings.show_greeting else "0",
        "telemetry_refresh_seconds": str(settings.telemetry_refresh_seconds),
        "update_status_refresh_seconds": str(settings.update_status_refresh_seconds),
        "active_refresh_seconds": str(settings.active_refresh_seconds),
        "update_check_interval_hours": str(settings.update_check_interval_hours),
    }
    for key, value in values.items():
        connection.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def normalize_widget_config(widget_type: WidgetType, config: dict[str, object]) -> dict[str, object]:
    if widget_type == "clock":
        clock_format = str(config.get("format", "12"))
        if clock_format not in {"12", "24"}:
            clock_format = "12"
        timezone_name = str(config.get("timezone", "local")).strip()[:80] or "local"
        return {
            "format": clock_format,
            "show_seconds": bool(config.get("show_seconds", False)),
            "show_date": bool(config.get("show_date", True)),
            "timezone": timezone_name,
        }
    if widget_type == "note":
        return {"text": str(config.get("text", ""))[:4000]}
    if widget_type == "bookmarks":
        raw_items = config.get("items", [])
        clean_items: list[dict[str, str]] = []
        if isinstance(raw_items, list):
            for item in raw_items[:12]:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label", "")).strip()[:80]
                url = str(item.get("url", "")).strip()[:500]
                parsed = urlparse(url)
                if label and parsed.scheme in {"http", "https"} and parsed.netloc:
                    clean_items.append({"label": label, "url": url})
        return {"items": clean_items}
    if widget_type == "service_status":
        return {"limit": max(3, min(int(config.get("limit", 6) or 6), 12)), "show_latency": bool(config.get("show_latency", True))}
    if widget_type == "update_overview":
        return {"limit": max(3, min(int(config.get("limit", 6) or 6), 12)), "show_current": bool(config.get("show_current", False))}
    return {
        "show_services": bool(config.get("show_services", True)),
        "show_updates": bool(config.get("show_updates", True)),
        "show_connections": bool(config.get("show_connections", True)),
    }


def row_to_widget(row: sqlite3.Row) -> DashboardWidget:
    try:
        config = json.loads(row["config_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        config = {}
    return DashboardWidget(
        id=row["id"], type=row["type"], title=row["title"], page_id=row["page_id"], category=row["category"],
        card_size=row["card_size"], sort_order=row["sort_order"], enabled=bool(row["enabled"]),
        config=normalize_widget_config(row["type"], config if isinstance(config, dict) else {}),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


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


class ManagementProviderDescriptor(BaseModel):
    id: str
    name: str
    description: str
    capabilities: list[str] = Field(default_factory=list)
    connection_type: str | None = None
    target_label: str = "Managed resource"
    target_mode: Literal["resource", "system"] = "resource"
    update_scope: Literal["service", "host"] = "service"
    requires_reboot: bool = False
    bulk_eligible: bool = True
    requires_confirmation: bool = False
    suggested_service_types: list[str] = Field(default_factory=list)
    warning: str | None = None

    @property
    def can_check(self) -> bool:
        return "check" in self.capabilities

    @property
    def can_update(self) -> bool:
        return "update" in self.capabilities


UpdateStateName = Literal["unknown", "checking", "current", "available", "unavailable", "unconfigured"]
UpdateJobState = Literal["queued", "running", "reconnecting", "success", "failed", "rolled_back"]


class HostUpdateRequest(BaseModel):
    confirm: bool = False


class ManagedResource(BaseModel):
    id: str
    name: str
    provider: str
    current_version: str | None = None
    latest_version: str | None = None
    update_available: bool | None = None
    state: str | None = None
    detail: str | None = None


class ServiceUpdateState(BaseModel):
    service_id: int
    provider: str
    target: str | None = None
    state: UpdateStateName = "unknown"
    current_version: str | None = None
    latest_version: str | None = None
    checked_at: str | None = None
    message: str | None = None
    can_update: bool = False


class UpdateJob(BaseModel):
    id: str
    kind: Literal["check", "update", "batch", "host_update"]
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

MANAGEMENT_PROVIDERS: dict[str, ManagementProviderDescriptor] = {
    "docker_compose": ManagementProviderDescriptor(
        id="docker_compose",
        name="Docker Compose / Dockge",
        description="Discover and update allow-listed Docker Compose services through the restricted update-agent sidecar.",
        capabilities=["check", "update", "rollback", "progress"],
        target_label="Compose service",
        target_mode="resource",
        suggested_service_types=["dockge", "docker-host"],
    ),
    "truenas_app": ManagementProviderDescriptor(
        id="truenas_app",
        name="TrueNAS App",
        description="Discover and upgrade applications managed by a reusable TrueNAS connection.",
        capabilities=["check", "update", "progress"],
        connection_type="truenas",
        target_label="TrueNAS app",
        target_mode="resource",
    ),
    "truenas_system": ManagementProviderDescriptor(
        id="truenas_system",
        name="TrueNAS System",
        description="Monitor and safely install TrueNAS operating-system releases using the native TrueNAS update API.",
        capabilities=["check", "update", "reboot", "reconnect", "release_notes"],
        connection_type="truenas",
        target_label="TrueNAS system",
        target_mode="system",
        update_scope="host",
        requires_reboot=True,
        bulk_eligible=False,
        requires_confirmation=True,
        suggested_service_types=["truenas"],
        warning="Host updates require explicit confirmation and are never included in Update All. If Dashboard runs on this host, it will temporarily disconnect during the reboot.",
    ),
}


def management_provider_descriptor(provider_id: str) -> ManagementProviderDescriptor | None:
    return MANAGEMENT_PROVIDERS.get(provider_id)


def management_provider_can_update(provider_id: str) -> bool:
    descriptor = management_provider_descriptor(provider_id)
    return bool(descriptor and descriptor.can_update)


def management_provider_bulk_eligible(provider_id: str) -> bool:
    descriptor = management_provider_descriptor(provider_id)
    return bool(descriptor and descriptor.can_update and descriptor.bulk_eligible and descriptor.update_scope == "service")


def validate_management_provider_id(provider_id: str) -> None:
    if provider_id == "none":
        return
    if provider_id not in MANAGEMENT_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"Unsupported management provider: {provider_id}")


class SessionUser(BaseModel):
    user_id: int
    username: str
    role: UserRole
    permissions: list[str] = Field(default_factory=list)
    csrf_token: str
    token_hash: str

    def can(self, permission: str) -> bool:
        return permission in self.permissions


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
    if "management_connection_id" not in columns:
        connection.execute("ALTER TABLE services ADD COLUMN management_connection_id INTEGER")


def migrate_legacy_truenas_connections(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """SELECT s.id AS service_id, s.management_controller_service_id AS controller_id
           FROM services s
           WHERE s.management_provider = 'truenas_app'
             AND s.management_connection_id IS NULL
             AND s.management_controller_service_id IS NOT NULL"""
    ).fetchall()
    for item in rows:
        controller = connection.execute("SELECT * FROM services WHERE id = ?", (item["controller_id"],)).fetchone()
        if not controller or controller["type"] != "truenas":
            continue
        existing = connection.execute(
            "SELECT id FROM management_connections WHERE legacy_service_id = ?", (controller["id"],)
        ).fetchone()
        if existing:
            connection_id = int(existing["id"])
        else:
            now = iso_now()
            base_name = f"{controller['name']} connection"
            name = base_name
            suffix = 2
            while connection.execute("SELECT 1 FROM management_connections WHERE name = ? COLLATE NOCASE", (name,)).fetchone():
                name = f"{base_name} {suffix}"
                suffix += 1
            cursor = connection.execute(
                """INSERT INTO management_connections
                   (name, type, url, api_key_encrypted, auth_username_encrypted, legacy_service_id, created_at, updated_at)
                   VALUES (?, 'truenas', ?, ?, ?, ?, ?, ?)""",
                (name, controller["url"], controller["api_key_encrypted"], controller["auth_username_encrypted"], controller["id"], now, now),
            )
            connection_id = int(cursor.lastrowid)
        connection.execute("UPDATE services SET management_connection_id = ? WHERE id = ?", (connection_id, item["service_id"]))


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
                """SELECT category FROM (
                       SELECT category FROM services WHERE page_id = ?
                       UNION ALL
                       SELECT category FROM dashboard_widgets WHERE page_id = ?
                   ) GROUP BY category COLLATE NOCASE ORDER BY category COLLATE NOCASE""",
                (page_id, page_id),
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


def ensure_account_migrations(connection: sqlite3.Connection) -> None:
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(admin_users)").fetchall()}
    if "recovery_code_hash" not in columns:
        connection.execute("ALTER TABLE admin_users ADD COLUMN recovery_code_hash TEXT")
    if "recovery_generated_at" not in columns:
        connection.execute("ALTER TABLE admin_users ADD COLUMN recovery_generated_at TEXT")
    if "password_changed_at" not in columns:
        connection.execute("ALTER TABLE admin_users ADD COLUMN password_changed_at TEXT")


def ensure_multi_user_migration(connection: sqlite3.Connection) -> None:
    """Migrate the legacy single-administrator auth store without invalidating sessions."""
    if connection.execute("SELECT 1 FROM app_settings WHERE key = 'auth_v18_migrated'").fetchone():
        return
    legacy_user = connection.execute(
        "SELECT id, username, password_hash, recovery_code_hash, recovery_generated_at, password_changed_at, created_at FROM admin_users ORDER BY id LIMIT 1"
    ).fetchone()
    existing_users = int(connection.execute("SELECT COUNT(*) FROM dashboard_users").fetchone()[0])
    if existing_users == 0 and legacy_user:
        connection.execute(
            """INSERT INTO dashboard_users
               (id, username, password_hash, role, enabled, recovery_code_hash, recovery_generated_at, password_changed_at, created_at)
               VALUES (?, ?, ?, 'owner', 1, ?, ?, ?, ?)""",
            (
                legacy_user["id"],
                legacy_user["username"],
                legacy_user["password_hash"],
                legacy_user["recovery_code_hash"],
                legacy_user["recovery_generated_at"],
                legacy_user["password_changed_at"],
                legacy_user["created_at"],
            ),
        )

    # Preserve any still-valid browser sessions from v0.17 and earlier.
    if int(connection.execute("SELECT COUNT(*) FROM dashboard_sessions").fetchone()[0]) == 0:
        legacy_sessions = connection.execute(
            "SELECT token_hash, user_id, csrf_token, expires_at, created_at FROM sessions"
        ).fetchall()
        for row in legacy_sessions:
            if connection.execute("SELECT 1 FROM dashboard_users WHERE id = ?", (row["user_id"],)).fetchone():
                connection.execute(
                    """INSERT OR IGNORE INTO dashboard_sessions
                       (token_hash, user_id, csrf_token, expires_at, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (row["token_hash"], row["user_id"], row["csrf_token"], row["expires_at"], row["created_at"]),
                )
    connection.execute(
        "INSERT INTO app_settings (key, value) VALUES ('auth_v18_migrated', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (iso_now(),),
    )


def init_db() -> None:
    with db() as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                recovery_code_hash TEXT,
                recovery_generated_at TEXT,
                password_changed_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS account_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT NOT NULL,
                event TEXT NOT NULL,
                detail TEXT,
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

            CREATE TABLE IF NOT EXISTS dashboard_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer',
                enabled INTEGER NOT NULL DEFAULT 1,
                recovery_code_hash TEXT,
                recovery_generated_at TEXT,
                password_changed_at TEXT,
                last_login_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dashboard_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                csrf_token TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES dashboard_users(id) ON DELETE CASCADE
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
                icon TEXT,
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

            CREATE TABLE IF NOT EXISTS installed_extensions (
                id TEXT PRIMARY KEY,
                manifest_json TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                installed_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS management_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                type TEXT NOT NULL DEFAULT 'truenas',
                url TEXT NOT NULL,
                api_key_encrypted TEXT,
                auth_username_encrypted TEXT,
                legacy_service_id INTEGER UNIQUE,
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
                management_connection_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dashboard_widgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                page_id INTEGER NOT NULL DEFAULT 1,
                category TEXT NOT NULL DEFAULT 'Widgets',
                card_size TEXT NOT NULL DEFAULT 'standard',
                sort_order INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                config_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(page_id) REFERENCES dashboard_pages(id) ON DELETE RESTRICT
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
        ensure_account_migrations(connection)
        ensure_multi_user_migration(connection)
        ensure_service_migrations(connection)
        category_columns = {row["name"] for row in connection.execute("PRAGMA table_info(category_layouts)").fetchall()}
        if "icon" not in category_columns:
            connection.execute("ALTER TABLE category_layouts ADD COLUMN icon TEXT")
        migrate_legacy_truenas_connections(connection)
        ensure_default_page(connection)
        connection.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('theme_id', 'system')")
        for setting_key, setting_value in SETTINGS_DEFAULTS.items():
            connection.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", (setting_key, setting_value))
        ensure_category_layouts(connection)
        now = iso_now()
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        connection.execute("DELETE FROM dashboard_sessions WHERE expires_at <= ?", (now,))
        connection.execute("UPDATE update_jobs SET state = 'failed', progress = 100, message = 'Interrupted by dashboard restart', finished_at = ? WHERE state IN ('queued', 'running') AND kind != 'host_update'", (now,))
        connection.execute("UPDATE update_jobs SET state = 'failed', progress = 100, message = 'Host update was interrupted before it started', finished_at = ? WHERE state = 'queued' AND kind = 'host_update'", (now,))


def automatic_update_check_loop() -> None:
    # Give the application and optional agent time to settle after startup.
    time.sleep(60)
    last_run = 0.0
    while True:
        interval_hours = UPDATE_CHECK_INTERVAL_HOURS
        try:
            with db() as connection:
                settings = read_dashboard_settings(connection)
                interval_hours = settings.update_check_interval_hours
                active_job = connection.execute("SELECT 1 FROM update_jobs WHERE state IN ('queued', 'running', 'reconnecting') LIMIT 1").fetchone()
            now = time.monotonic()
            due = interval_hours > 0 and (last_run == 0.0 or now - last_run >= interval_hours * 3600)
            if due and not active_job:
                with db() as connection:
                    rows = connection.execute("SELECT * FROM services WHERE management_provider != 'none' ORDER BY name COLLATE NOCASE").fetchall()
                for row in rows:
                    try:
                        check_service_update(row)
                    except Exception:
                        pass
                last_run = time.monotonic()
        except Exception:
            pass
        # Short wake interval lets Settings changes take effect without a restart.
        time.sleep(300)


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


RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def normalize_recovery_code(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def generate_recovery_code() -> str:
    raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(32))
    return "HD-" + "-".join(raw[index:index + 4] for index in range(0, len(raw), 4))


def recovery_code_digest(code: str) -> str:
    normalized = normalize_recovery_code(code)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def rotate_recovery_code(connection: sqlite3.Connection, user_id: int) -> RecoveryCodeResult:
    code = generate_recovery_code()
    generated_at = iso_now()
    connection.execute(
        "UPDATE dashboard_users SET recovery_code_hash = ?, recovery_generated_at = ? WHERE id = ?",
        (recovery_code_digest(code), generated_at, user_id),
    )
    return RecoveryCodeResult(recovery_code=code, generated_at=generated_at)


def audit_account_event(connection: sqlite3.Connection, user_id: int | None, username: str, event: str, detail: str | None = None) -> None:
    connection.execute(
        "INSERT INTO account_audit (user_id, username, event, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, event, detail, iso_now()),
    )


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def admin_exists() -> bool:
    with db() as connection:
        return connection.execute("SELECT 1 FROM dashboard_users LIMIT 1").fetchone() is not None


def create_session(connection: sqlite3.Connection, user_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    now = utcnow()
    expires = now + timedelta(hours=SESSION_HOURS)
    connection.execute(
        "INSERT INTO dashboard_sessions (token_hash, user_id, csrf_token, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
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
            SELECT u.id AS user_id, u.username, u.role, u.enabled, s.token_hash, s.csrf_token, s.expires_at
            FROM dashboard_sessions s
            JOIN dashboard_users u ON u.id = s.user_id
            WHERE s.token_hash = ?
            """,
            (token_digest(session_token),),
        ).fetchone()
        if not row or not bool(row["enabled"]):
            if row:
                connection.execute("DELETE FROM dashboard_sessions WHERE token_hash = ?", (token_digest(session_token),))
            return None
        if datetime.fromisoformat(row["expires_at"]) <= utcnow():
            connection.execute("DELETE FROM dashboard_sessions WHERE token_hash = ?", (token_digest(session_token),))
            return None
        role = row["role"] if row["role"] in ROLE_PERMISSIONS else "viewer"
        return SessionUser(
            user_id=int(row["user_id"]),
            username=row["username"],
            role=role,
            permissions=permissions_for_role(role),
            csrf_token=row["csrf_token"],
            token_hash=row["token_hash"],
        )


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


def read_permission_dependency(permission: str):
    def check(user: SessionUser = Depends(require_auth)) -> SessionUser:
        if not user.can(permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission required: {permission}")
        return user
    return check


def permission_dependency(permission: str):
    def check(user: SessionUser = Depends(require_write_auth)) -> SessionUser:
        if not user.can(permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission required: {permission}")
        return user
    return check


require_connections_read = read_permission_dependency("connections:manage")
require_users_read = read_permission_dependency("users:manage")
require_dashboard_edit = permission_dependency("dashboard:edit")
require_services_manage = permission_dependency("services:manage")
require_updates_run = permission_dependency("updates:run")
require_host_updates_run = permission_dependency("updates:host")
require_connections_manage = permission_dependency("connections:manage")
require_extensions_manage = permission_dependency("extensions:manage")
require_settings_manage = permission_dependency("settings:manage")
require_users_manage = permission_dependency("users:manage")


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
        management_provider=(row["management_provider"] or "none"),
        management_target=row["management_target"],
        management_controller_service_id=None if row["management_connection_id"] else row["management_controller_service_id"],
        management_connection_id=row["management_connection_id"],
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
    keys = set(row.keys())
    return CategoryLayout(
        page_id=int(row["page_id"]),
        name=row["name"],
        sort_order=int(row["sort_order"] or 0),
        collapsed=bool(row["collapsed"]),
        icon=row["icon"] if "icon" in keys else None,
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
        headers={"User-Agent": f"HomelabDashboard/{APP_VERSION}", "Accept": "*/*"},
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
        headers={"User-Agent": f"HomelabDashboard/{APP_VERSION}", "Accept": "application/json", **(headers or {})},
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
        with TrueNASRPC(str(service.url), key, username) as client:
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
    def __init__(self, service_url: str, api_key: str, username: str | None = None):
        parsed = urlparse(str(service_url))
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

    @staticmethod
    def _error_detail(message: dict, method: str) -> RuntimeError:
        error = message.get("error") or {}
        detail = error.get("message") or (error.get("data") or {}).get("reason") or str(error)
        return RuntimeError(f"TrueNAS {method}: {detail}")

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
                raise self._error_detail(message, method)
            return message.get("result")
        raise RuntimeError(f"TrueNAS API timed out while calling {method}")

    def start_job(self, method: str, params: list[object] | None = None) -> int:
        """Start a TrueNAS job method and return its middleware job id.

        TrueNAS JSON-RPC job methods publish the job id through the
        core.get_jobs collection event. The ordinary JSON-RPC method result is
        sent only later, so waiting for it would make long-running operations
        such as update.run hit the normal RPC timeout.
        """
        self.call("core.subscribe", ["core.get_jobs"])
        self.sequence += 1
        call_id = f"hld-{self.sequence}-{uuid.uuid4().hex[:8]}"
        self.ws.send(json.dumps({"jsonrpc": "2.0", "id": call_id, "method": method, "params": params or []}))
        deadline = time.time() + max(STATUS_TIMEOUT, 30)
        direct_result_received = False
        while time.time() < deadline:
            try:
                message = json.loads(self.ws.recv())
            except WebSocketTimeoutException as exc:
                raise RuntimeError(f"TrueNAS API timed out while starting job {method}") from exc
            if not isinstance(message, dict):
                continue
            if message.get("id") == call_id:
                if "error" in message:
                    raise self._error_detail(message, method)
                direct_result_received = True
                # A fast job can finish before we observe its collection event.
                # Keep listening briefly for the event so we still capture the id.
                continue
            if message.get("method") != "collection_update":
                continue
            event = message.get("params")
            if not isinstance(event, dict) or event.get("collection") != "core.get_jobs":
                continue
            fields = event.get("fields")
            if not isinstance(fields, dict):
                continue
            message_ids = fields.get("message_ids")
            if not isinstance(message_ids, list) or call_id not in message_ids:
                continue
            job_id = fields.get("id")
            if isinstance(job_id, int) and not isinstance(job_id, bool):
                return job_id
        if direct_result_received:
            raise RuntimeError(f"TrueNAS {method} completed but its middleware job id was not reported")
        raise RuntimeError(f"TrueNAS API timed out while starting job {method}")


def truenas_client_from_row(row: sqlite3.Row) -> TrueNASRPC:
    service = row_to_service(row)
    api_key = decrypt_secret(row["api_key_encrypted"])
    username = decrypt_secret(row["auth_username_encrypted"])
    if not api_key:
        raise RuntimeError("TrueNAS controller does not have an API key saved")
    return TrueNASRPC(str(service.url), api_key, username)


def row_to_management_connection(row: sqlite3.Row, used_by: int = 0) -> ManagementConnection:
    return ManagementConnection(
        id=int(row["id"]), name=row["name"], type="truenas", url=row["url"],
        has_api_key=bool(row["api_key_encrypted"]), has_auth_username=bool(row["auth_username_encrypted"]),
        used_by=used_by, created_at=row["created_at"], updated_at=row["updated_at"],
    )


def get_management_connection_row(connection_id: int) -> sqlite3.Row:
    with db() as connection:
        row = connection.execute("SELECT * FROM management_connections WHERE id = ?", (connection_id,)).fetchone()
    if not row:
        raise RuntimeError("Management connection not found")
    return row


def truenas_client_from_connection_row(row: sqlite3.Row) -> TrueNASRPC:
    api_key = decrypt_secret(row["api_key_encrypted"])
    username = decrypt_secret(row["auth_username_encrypted"])
    if not api_key:
        raise RuntimeError("TrueNAS connection does not have an API key saved")
    return TrueNASRPC(str(row["url"]), api_key, username)


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
    provider = row["provider"] or "none"
    return ServiceUpdateState(
        service_id=int(row["service_id"]), provider=provider, target=row["target"], state=state,
        current_version=row["current_version"], latest_version=row["latest_version"], checked_at=row["checked_at"],
        message=row["message"], can_update=state == "available" and management_provider_can_update(provider),
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


def truenas_app_records(controller_row: sqlite3.Row | None = None, connection_row: sqlite3.Row | None = None) -> list[dict]:
    if connection_row is not None:
        client_context = truenas_client_from_connection_row(connection_row)
    elif controller_row is not None:
        client_context = truenas_client_from_row(controller_row)
    else:
        raise RuntimeError("TrueNAS connection is not configured")
    with client_context as client:
        raw = client.call("app.query", [[], {}])
    if not isinstance(raw, list):
        raise RuntimeError("Unexpected TrueNAS app query response")
    return [item for item in raw if isinstance(item, dict)]


def truenas_client_for_managed_service(service: Service) -> TrueNASRPC:
    if service.management_connection_id:
        return truenas_client_from_connection_row(get_management_connection_row(service.management_connection_id))
    if service.management_controller_service_id:
        return truenas_client_from_row(get_service_row(service.management_controller_service_id))
    raise RuntimeError("Choose a TrueNAS connection for this managed resource")


def truenas_system_update_status(client: TrueNASRPC) -> tuple[str | None, str | None, bool, str | None]:
    raw = client.call("update.status")
    if not isinstance(raw, dict):
        raise RuntimeError("Unexpected TrueNAS system update response")
    if str(raw.get("code") or "NORMAL").upper() == "ERROR":
        error = raw.get("error") if isinstance(raw.get("error"), dict) else {}
        raise RuntimeError(str(error.get("reason") or error.get("errname") or "TrueNAS update status is unavailable"))
    status_info = raw.get("status") if isinstance(raw.get("status"), dict) else {}
    try:
        version_raw = client.call("system.version_short")
        current_version = str(version_raw or "").strip() or None
    except Exception:
        current_info = status_info.get("current_version") if isinstance(status_info.get("current_version"), dict) else {}
        current_version = str(current_info.get("version") or current_info.get("name") or "").strip() or None
    new_version = status_info.get("new_version") if isinstance(status_info.get("new_version"), dict) else None
    latest_version = (str(new_version.get("version") or "").strip() or None) if new_version else None
    release_notes_url = (str(new_version.get("release_notes_url") or "").strip() or None) if new_version else None
    return current_version, latest_version, bool(new_version and latest_version), release_notes_url


def check_docker_compose_update(service: Service, checked_at: str) -> ServiceUpdateState:
    raw = agent_request("/v1/check", method="POST", payload={"resource_id": service.management_target}, timeout=UPDATE_JOB_TIMEOUT)
    if not isinstance(raw, dict):
        raise RuntimeError("Unexpected update-agent response")
    available = bool(raw.get("update_available"))
    return ServiceUpdateState(
        service_id=service.id, provider=service.management_provider, target=service.management_target,
        state="available" if available else "current", current_version=raw.get("current_version"),
        latest_version=raw.get("latest_version"), checked_at=checked_at,
        message="Container image update available" if available else "Container image is current",
        can_update=available,
    )


def check_truenas_app_update(service: Service, checked_at: str) -> ServiceUpdateState:
    if service.management_connection_id:
        apps = truenas_app_records(connection_row=get_management_connection_row(service.management_connection_id))
    elif service.management_controller_service_id:
        apps = truenas_app_records(controller_row=get_service_row(service.management_controller_service_id))
    else:
        raise RuntimeError("Choose a TrueNAS connection for this app")
    app_item = next((item for item in apps if str(item.get("id") or item.get("name")) == service.management_target), None)
    if not app_item:
        raise RuntimeError(f"TrueNAS app {service.management_target!r} was not found")
    available = bool(app_item.get("upgrade_available") or app_item.get("image_updates_available"))
    current_version = str(app_item.get("human_version") or app_item.get("version") or "") or None
    latest_version = str(app_item.get("latest_human_version") or app_item.get("latest_version") or "") or None
    return ServiceUpdateState(
        service_id=service.id, provider=service.management_provider, target=service.management_target,
        state="available" if available else "current", current_version=current_version,
        latest_version=latest_version, checked_at=checked_at,
        message="TrueNAS app update available" if available else "TrueNAS app is current",
        can_update=available,
    )


def check_truenas_system_update(service: Service, checked_at: str) -> ServiceUpdateState:
    with truenas_client_for_managed_service(service) as client:
        current_version, latest_version, available, release_notes_url = truenas_system_update_status(client)
    if available:
        message = "TrueNAS system update available · explicit host confirmation required"
        if release_notes_url:
            message += " · release notes available in TrueNAS"
    else:
        message = "TrueNAS system is current"
    return ServiceUpdateState(
        service_id=service.id, provider=service.management_provider, target=service.management_target,
        state="available" if available else "current", current_version=current_version,
        latest_version=latest_version, checked_at=checked_at, message=message, can_update=available,
    )


MANAGEMENT_UPDATE_CHECKERS = {
    "docker_compose": check_docker_compose_update,
    "truenas_app": check_truenas_app_update,
    "truenas_system": check_truenas_system_update,
}


def check_service_update(service_row: sqlite3.Row) -> ServiceUpdateState:
    service = row_to_service(service_row)
    provider = service.management_provider
    target = service.management_target
    checked_at = iso_now()
    if provider == "none" or not target:
        result = ServiceUpdateState(service_id=service.id, provider=provider, target=target, state="unconfigured", checked_at=checked_at, message="Update management is not configured for this service")
        save_update_state(result)
        return result
    descriptor = management_provider_descriptor(provider)
    if not descriptor:
        result = ServiceUpdateState(service_id=service.id, provider=provider, target=target, state="unavailable", checked_at=checked_at, message=f"Unsupported management provider: {provider}")
        save_update_state(result)
        return result
    save_update_state(ServiceUpdateState(
        service_id=service.id, provider=provider, target=target, state="checking", checked_at=checked_at, message=f"Checking with {descriptor.name}"
    ))
    try:
        checker = MANAGEMENT_UPDATE_CHECKERS.get(provider)
        if not checker:
            raise RuntimeError(f"{descriptor.name} does not provide update checks")
        result = checker(service, checked_at)
        result.can_update = result.state == "available" and descriptor.can_update
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
    if not service.management_target:
        raise RuntimeError("TrueNAS update target is incomplete")
    if service.management_connection_id:
        client_context = truenas_client_from_connection_row(get_management_connection_row(service.management_connection_id))
    elif service.management_controller_service_id:
        client_context = truenas_client_from_row(get_service_row(service.management_controller_service_id))
    else:
        raise RuntimeError("TrueNAS connection is not configured")
    update_job(job_id, progress=start, message="Connecting to TrueNAS")
    with client_context as client:
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


def wait_for_truenas_system_reconnect(job_id: str, service_id: int, expected_version: str | None) -> None:
    deadline = time.time() + HOST_UPDATE_RECONNECT_TIMEOUT
    last_detail = None
    while time.time() < deadline:
        try:
            service = row_to_service(get_service_row(service_id))
            with truenas_client_for_managed_service(service) as client:
                ready = bool(client.call("system.ready"))
                current_raw = client.call("system.version_short")
                current_version = str(current_raw or "").strip() or None
            if ready and (not expected_version or current_version == expected_version):
                save_update_state(ServiceUpdateState(
                    service_id=service.id, provider=service.management_provider, target=service.management_target,
                    state="current", current_version=current_version, latest_version=current_version, checked_at=iso_now(),
                    message="Host update completed and the system is ready", can_update=False,
                ))
                update_job(
                    job_id, state="success", progress=100, message="Host update completed; system is back online",
                    latest_version=current_version or expected_version, detail=None, finished_at=iso_now(), active_service_id=None,
                )
                return
            last_detail = f"System responded with version {current_version or 'unknown'} but is not ready on the expected version yet"
            update_job(job_id, state="reconnecting", progress=94, message="Waiting for the updated host to become ready", detail=last_detail)
        except Exception as exc:
            last_detail = str(exc)[:500]
            update_job(job_id, state="reconnecting", progress=92, message="Host is restarting; waiting to reconnect", detail=None)
        time.sleep(8)
    update_job(
        job_id, state="failed", progress=100, message="Host update could not be verified after restart",
        detail=(last_detail or "The managed host did not return before the reconnect timeout")[:1200], finished_at=iso_now(),
    )


def perform_truenas_system_update(service: Service, job_id: str) -> None:
    if service.management_target != "system":
        raise RuntimeError("TrueNAS system update target is incomplete")
    with truenas_client_for_managed_service(service) as client:
        current_version, latest_version, available, _ = truenas_system_update_status(client)
        if not available or not latest_version:
            raise RuntimeError("TrueNAS does not currently report a system update")
        update_job(
            job_id, state="running", progress=5, message="Starting TrueNAS system update",
            current_version=current_version, latest_version=latest_version, detail=None,
        )
        # TrueNAS update.run is a job method. Reboot is requested as part of the
        # update so the new boot environment is activated immediately.
        job_number = client.start_job("update.run", [{
            "dataset_name": None,
            "resume": False,
            "train": None,
            "version": latest_version,
            "reboot": True,
        }])
        deadline = time.time() + UPDATE_JOB_TIMEOUT
        while time.time() < deadline:
            try:
                jobs = client.call("core.get_jobs", [[["id", "=", job_number]], {}])
            except Exception:
                # A disconnect after the update job has started is expected once
                # the host begins rebooting. Verification continues below.
                break
            info = jobs[0] if isinstance(jobs, list) and jobs and isinstance(jobs[0], dict) else None
            if info:
                progress_info = info.get("progress") if isinstance(info.get("progress"), dict) else {}
                percent = float(progress_info.get("percent") or 0)
                description = str(progress_info.get("description") or "Applying TrueNAS system update")
                mapped = 10 + round(min(100.0, max(0.0, percent)) * 0.78)
                update_job(job_id, progress=min(88, mapped), message=description[:180])
                job_state = str(info.get("state") or "").upper()
                if job_state in {"FAILED", "ABORTED"}:
                    raise RuntimeError(str(info.get("error") or f"TrueNAS system update {job_state.lower()}"))
                if job_state == "SUCCESS":
                    break
            time.sleep(3)
        update_job(
            job_id, state="reconnecting", progress=90, message="Update applied; waiting for TrueNAS to reboot and reconnect",
            current_version=current_version, latest_version=latest_version, detail=None,
        )
    wait_for_truenas_system_reconnect(job_id, service.id, latest_version)


def host_update_worker(job_id: str, service_id: int) -> None:
    update_job(job_id, state="running", started_at=iso_now(), progress=1, message="Preparing host update")
    try:
        service = row_to_service(get_service_row(service_id))
        if service.management_provider != "truenas_system":
            raise RuntimeError("This host update provider is not implemented")
        perform_truenas_system_update(service, job_id)
    except Exception as exc:
        update_job(job_id, state="failed", progress=100, message="Host update failed", detail=str(exc)[:1200], finished_at=iso_now())


def resume_host_update_worker(job_id: str, service_id: int, expected_version: str | None) -> None:
    update_job(job_id, state="reconnecting", progress=91, message="Dashboard restarted during host update; verifying the managed host", detail=None)
    wait_for_truenas_system_reconnect(job_id, service_id, expected_version)


def recover_host_update_jobs() -> None:
    with db() as connection:
        rows = connection.execute(
            "SELECT id, service_id, latest_version FROM update_jobs WHERE kind = 'host_update' AND state IN ('running', 'reconnecting') ORDER BY created_at"
        ).fetchall()
    for row in rows:
        if row["service_id"] is None:
            update_job(row["id"], state="failed", progress=100, message="Host update recovery is missing a service", finished_at=iso_now())
            continue
        threading.Thread(
            target=resume_host_update_worker, args=(row["id"], int(row["service_id"]), row["latest_version"]), daemon=True,
            name=f"host-update-recovery-{row['id'][:8]}",
        ).start()


MANAGEMENT_UPDATE_PERFORMERS = {
    "docker_compose": perform_docker_update,
    "truenas_app": perform_truenas_update,
}


def perform_service_update(service_id: int, job_id: str, start: int = 5, end: int = 100) -> str:
    row = get_service_row(service_id)
    service = row_to_service(row)
    if service.management_provider == "none" or not service.management_target:
        raise RuntimeError("Update management is not configured for this service")
    descriptor = management_provider_descriptor(service.management_provider)
    if not descriptor:
        raise RuntimeError(f"Unsupported management provider: {service.management_provider}")
    if not descriptor.can_update:
        raise RuntimeError(f"{descriptor.name} supports update detection only in this dashboard version")
    if descriptor.update_scope == "host":
        raise RuntimeError(f"{descriptor.name} requires the explicit host-update workflow")
    performer = MANAGEMENT_UPDATE_PERFORMERS.get(service.management_provider)
    if not performer:
        raise RuntimeError(f"{descriptor.name} does not provide an update installer")
    update_job(job_id, active_service_id=service.id, provider=service.management_provider, target=service.management_target, progress=start, message=f"Preparing {service.name}")
    current, latest, outcome = performer(service, job_id, start, end)
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
            cached_rows = connection.execute("""SELECT s.id, s.name, s.management_provider FROM services s JOIN service_update_state u ON u.service_id=s.id
                                                WHERE u.state='available' AND s.management_provider!='none' ORDER BY s.name COLLATE NOCASE""").fetchall()
        cached = [item for item in cached_rows if management_provider_bulk_eligible(item["management_provider"] or "none")]
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


@app.get("/api/connections", response_model=list[ManagementConnection])
def list_management_connections(_: SessionUser = Depends(require_auth)) -> list[ManagementConnection]:
    with db() as connection:
        rows = connection.execute("SELECT * FROM management_connections ORDER BY name COLLATE NOCASE").fetchall()
        usage = {row["management_connection_id"]: int(row["count"]) for row in connection.execute(
            "SELECT management_connection_id, COUNT(*) AS count FROM services WHERE management_connection_id IS NOT NULL GROUP BY management_connection_id"
        ).fetchall()}
    return [row_to_management_connection(row, usage.get(row["id"], 0)) for row in rows]


@app.post("/api/connections", response_model=ManagementConnection, status_code=status.HTTP_201_CREATED)
def create_management_connection(payload: ManagementConnectionCreate, _: SessionUser = Depends(require_connections_manage)) -> ManagementConnection:
    now = iso_now()
    try:
        with db() as connection:
            cursor = connection.execute(
                """INSERT INTO management_connections (name, type, url, api_key_encrypted, auth_username_encrypted, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (payload.name, payload.type, str(payload.url), encrypt_secret(payload.api_key), encrypt_secret(payload.auth_username), now, now),
            )
            row = connection.execute("SELECT * FROM management_connections WHERE id = ?", (cursor.lastrowid,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A connection with that name already exists") from exc
    return row_to_management_connection(row)


@app.put("/api/connections/{connection_id}", response_model=ManagementConnection)
def update_management_connection(connection_id: int, payload: ManagementConnectionUpdate, _: SessionUser = Depends(require_connections_manage)) -> ManagementConnection:
    now = iso_now()
    try:
        with db() as connection:
            current = connection.execute("SELECT * FROM management_connections WHERE id = ?", (connection_id,)).fetchone()
            if not current:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
            api_key = current["api_key_encrypted"]
            username = current["auth_username_encrypted"]
            if payload.clear_api_key:
                api_key = None
            elif payload.api_key:
                api_key = encrypt_secret(payload.api_key)
            if payload.clear_auth_username:
                username = None
            elif payload.auth_username:
                username = encrypt_secret(payload.auth_username)
            connection.execute(
                "UPDATE management_connections SET name=?, type=?, url=?, api_key_encrypted=?, auth_username_encrypted=?, updated_at=? WHERE id=?",
                (payload.name, payload.type, str(payload.url), api_key, username, now, connection_id),
            )
            row = connection.execute("SELECT * FROM management_connections WHERE id = ?", (connection_id,)).fetchone()
            used_by = int(connection.execute("SELECT COUNT(*) FROM services WHERE management_connection_id = ?", (connection_id,)).fetchone()[0])
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A connection with that name already exists") from exc
    return row_to_management_connection(row, used_by)


@app.delete("/api/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_management_connection(connection_id: int, _: SessionUser = Depends(require_connections_manage)) -> Response:
    with db() as connection:
        row = connection.execute("SELECT 1 FROM management_connections WHERE id = ?", (connection_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
        used_by = int(connection.execute("SELECT COUNT(*) FROM services WHERE management_connection_id = ?", (connection_id,)).fetchone()[0])
        if used_by:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Connection is used by {used_by} managed service(s)")
        connection.execute("DELETE FROM management_connections WHERE id = ?", (connection_id,))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/connections/{connection_id}/test", response_model=ConnectionTestResult)
def test_management_connection(connection_id: int, _: SessionUser = Depends(require_connections_manage)) -> ConnectionTestResult:
    try:
        row = get_management_connection_row(connection_id)
        with truenas_client_from_connection_row(row) as client:
            apps = client.call("app.query", [[], {}])
        count = len(apps) if isinstance(apps, list) else 0
        return ConnectionTestResult(ok=True, message=f"Connected to TrueNAS · {count} app(s) found")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/api/management/providers", response_model=list[ManagementProviderDescriptor])
def list_management_providers(_: SessionUser = Depends(require_auth)) -> list[ManagementProviderDescriptor]:
    return list(MANAGEMENT_PROVIDERS.values())


@app.get("/api/management/docker/resources", response_model=list[ManagedResource])
def docker_management_resources(_: SessionUser = Depends(require_connections_read)) -> list[ManagedResource]:
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


def truenas_resources_from_apps(apps: list[dict]) -> list[ManagedResource]:
    return [ManagedResource(
        id=str(item.get("id") or item.get("name")), name=str(item.get("name") or item.get("id")), provider="truenas_app",
        current_version=str(item.get("human_version") or item.get("version") or "") or None,
        latest_version=str(item.get("latest_human_version") or item.get("latest_version") or "") or None,
        update_available=bool(item.get("upgrade_available") or item.get("image_updates_available")), state=str(item.get("state") or "") or None,
    ) for item in apps]


@app.get("/api/management/providers/{provider_id}/resources", response_model=list[ManagedResource])
def management_provider_resources(provider_id: str, connection_id: int | None = None, _: SessionUser = Depends(require_connections_read)) -> list[ManagedResource]:
    descriptor = management_provider_descriptor(provider_id)
    if not descriptor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Management provider not found")
    try:
        if provider_id == "docker_compose":
            raw = agent_request("/v1/resources", timeout=30)
            resources = raw if isinstance(raw, list) else []
            return [
                ManagedResource(
                    id=str(item.get("id")),
                    name=f"{item.get('project')} / {item.get('service')}",
                    provider=provider_id,
                    detail=str(item.get("image") or ""),
                )
                for item in resources if isinstance(item, dict)
            ]
        if descriptor.connection_type and not connection_id:
            raise RuntimeError(f"Choose a {descriptor.connection_type} connection first")
        if provider_id == "truenas_app":
            connection_row = get_management_connection_row(int(connection_id))
            if connection_row["type"] != descriptor.connection_type:
                raise RuntimeError("The selected connection type does not match this provider")
            return truenas_resources_from_apps(truenas_app_records(connection_row=connection_row))
        if provider_id == "truenas_system":
            connection_row = get_management_connection_row(int(connection_id))
            if connection_row["type"] != descriptor.connection_type:
                raise RuntimeError("The selected connection type does not match this provider")
            with truenas_client_from_connection_row(connection_row) as client:
                current_version, latest_version, available, release_notes_url = truenas_system_update_status(client)
            detail = "TrueNAS operating system"
            if release_notes_url:
                detail += " · release notes available"
            return [ManagedResource(
                id="system", name="TrueNAS System", provider=provider_id, current_version=current_version,
                latest_version=latest_version, update_available=available, state="available" if available else "current", detail=detail,
            )]
        raise RuntimeError(f"{descriptor.name} does not expose resource discovery")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/api/management/truenas/connections/{connection_id}/apps", response_model=list[ManagedResource])
def truenas_management_connection_apps(connection_id: int, _: SessionUser = Depends(require_connections_read)) -> list[ManagedResource]:
    try:
        connection_row = get_management_connection_row(connection_id)
        apps = truenas_app_records(connection_row=connection_row)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return truenas_resources_from_apps(apps)


@app.get("/api/management/truenas/{controller_service_id}/apps", response_model=list[ManagedResource])
def truenas_management_apps(controller_service_id: int, _: SessionUser = Depends(require_connections_read)) -> list[ManagedResource]:
    # Backward-compatible v0.11 route. New configurations use management connections.
    try:
        controller_row = get_service_row(controller_service_id)
        if controller_row["type"] != "truenas":
            raise RuntimeError("Selected controller service is not a TrueNAS card")
        apps = truenas_app_records(controller_row=controller_row)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return truenas_resources_from_apps(apps)


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
            provider = service["management_provider"] or "none"
            state: UpdateStateName = "unconfigured" if provider == "none" or not service["management_target"] else "unknown"
            results.append(ServiceUpdateState(service_id=service["id"], provider=provider, target=service["management_target"], state=state, can_update=False))
    return results


@app.post("/api/updates/check", response_model=UpdateJob, status_code=status.HTTP_202_ACCEPTED)
def start_update_check(_: SessionUser = Depends(require_updates_run)) -> UpdateJob:
    with db() as connection:
        active = connection.execute("SELECT 1 FROM update_jobs WHERE state IN ('queued','running','reconnecting') LIMIT 1").fetchone()
    if active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Another update job is already running")
    job = create_update_job("check", message="Update check queued")
    threading.Thread(target=check_updates_worker, args=(job.id,), daemon=True).start()
    return job


@app.post("/api/services/{service_id}/update", response_model=UpdateJob, status_code=status.HTTP_202_ACCEPTED)
def start_service_update(service_id: int, _: SessionUser = Depends(require_updates_run)) -> UpdateJob:
    try:
        row = get_service_row(service_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    service = row_to_service(row)
    if service.management_provider == "none" or not service.management_target:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Update management is not configured for this service")
    descriptor = management_provider_descriptor(service.management_provider)
    if not descriptor:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported management provider: {service.management_provider}")
    if not descriptor.can_update:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{descriptor.name} supports update detection only in this dashboard version")
    if descriptor.update_scope == "host":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{descriptor.name} requires explicit host-update confirmation")
    with db() as connection:
        active = connection.execute("SELECT 1 FROM update_jobs WHERE state IN ('queued','running','reconnecting') LIMIT 1").fetchone()
    if active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Another update job is already running")
    job = create_update_job("update", service_id=service_id, provider=service.management_provider, target=service.management_target, message=f"{service.name} update queued")
    threading.Thread(target=service_update_worker, args=(job.id, service_id), daemon=True).start()
    return job


@app.post("/api/services/{service_id}/host-update", response_model=UpdateJob, status_code=status.HTTP_202_ACCEPTED)
def start_host_update(service_id: int, payload: HostUpdateRequest, _: SessionUser = Depends(require_host_updates_run)) -> UpdateJob:
    if not payload.confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Host updates require explicit confirmation")
    try:
        row = get_service_row(service_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    service = row_to_service(row)
    descriptor = management_provider_descriptor(service.management_provider)
    if not descriptor or descriptor.update_scope != "host" or not descriptor.can_update:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This service is not configured for host-level updates")
    if not service.management_target:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Host update management is incomplete")
    with db() as connection:
        active = connection.execute("SELECT 1 FROM update_jobs WHERE state IN ('queued','running','reconnecting') LIMIT 1").fetchone()
        cached = connection.execute("SELECT * FROM service_update_state WHERE service_id = ?", (service_id,)).fetchone()
    if active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Another update job is already running")
    current_version = cached["current_version"] if cached else None
    latest_version = cached["latest_version"] if cached else None
    if not cached or cached["state"] != "available":
        checked = check_service_update(row)
        current_version = checked.current_version
        latest_version = checked.latest_version
        if checked.state != "available":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No host update is currently available")
    job = create_update_job(
        "host_update", service_id=service_id, provider=service.management_provider, target=service.management_target,
        message=f"{service.name} host update queued",
    )
    update_job(job.id, current_version=current_version, latest_version=latest_version)
    with db() as connection:
        job_row = connection.execute("SELECT * FROM update_jobs WHERE id = ?", (job.id,)).fetchone()
    threading.Thread(target=host_update_worker, args=(job.id, service_id), daemon=True, name=f"host-update-{job.id[:8]}").start()
    return row_to_update_job(job_row)


@app.post("/api/updates/update-all", response_model=UpdateJob, status_code=status.HTTP_202_ACCEPTED)
def start_update_all(_: SessionUser = Depends(require_updates_run)) -> UpdateJob:
    with db() as connection:
        active = connection.execute("SELECT 1 FROM update_jobs WHERE state IN ('queued','running','reconnecting') LIMIT 1").fetchone()
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
    return {"status": "ok", "version": APP_VERSION, "time": iso_now()}


@app.get("/api/auth/status", response_model=AuthStatus)
def auth_status(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> AuthStatus:
    setup_required = not admin_exists()
    user = None if setup_required else get_session(session_token)
    return AuthStatus(
        setup_required=setup_required,
        authenticated=user is not None,
        username=user.username if user else None,
        role=user.role if user else None,
        permissions=user.permissions if user else [],
        csrf_token=user.csrf_token if user else None,
    )


@app.post("/api/auth/setup", response_model=AuthStatus, status_code=status.HTTP_201_CREATED)
def setup_admin(credentials: Credentials, response: Response) -> AuthStatus:
    with db() as connection:
        if connection.execute("SELECT 1 FROM dashboard_users LIMIT 1").fetchone():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Owner account is already configured")
        now = iso_now()
        cursor = connection.execute(
            """INSERT INTO dashboard_users
               (username, password_hash, role, enabled, password_changed_at, last_login_at, created_at)
               VALUES (?, ?, 'owner', 1, ?, ?, ?)""",
            (credentials.username, hash_password(credentials.password), now, now, now),
        )
        user_id = int(cursor.lastrowid)
        recovery = rotate_recovery_code(connection, user_id)
        audit_account_event(connection, user_id, credentials.username, "account_created", "Owner account created")
        audit_account_event(connection, user_id, credentials.username, "recovery_code_generated", "Initial recovery code generated")
        token, csrf = create_session(connection, user_id)
    set_session_cookie(response, token)
    return AuthStatus(
        setup_required=False,
        authenticated=True,
        username=credentials.username,
        role="owner",
        permissions=permissions_for_role("owner"),
        csrf_token=csrf,
        recovery_code=recovery.recovery_code,
    )


@app.post("/api/auth/login", response_model=AuthStatus)
def login(credentials: Credentials, response: Response) -> AuthStatus:
    with db() as connection:
        user = connection.execute(
            "SELECT id, username, password_hash, role, enabled FROM dashboard_users WHERE username = ? COLLATE NOCASE",
            (credentials.username,),
        ).fetchone()
        if not user or not bool(user["enabled"]) or not verify_password(credentials.password, user["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
        role = user["role"] if user["role"] in ROLE_PERMISSIONS else "viewer"
        now = iso_now()
        connection.execute("UPDATE dashboard_users SET last_login_at = ? WHERE id = ?", (now, user["id"]))
        token, csrf = create_session(connection, user["id"])
    set_session_cookie(response, token)
    return AuthStatus(
        setup_required=False,
        authenticated=True,
        username=user["username"],
        role=role,
        permissions=permissions_for_role(role),
        csrf_token=csrf,
    )


@app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    if session_token:
        with db() as connection:
            connection.execute("DELETE FROM dashboard_sessions WHERE token_hash = ?", (token_digest(session_token),))
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@app.post("/api/auth/recover", response_model=AuthStatus)
def recover_password(payload: PasswordRecoveryRequest, response: Response) -> AuthStatus:
    # Recovery codes are deliberately high entropy and stored only as a digest.
    # Use one generic failure response so the endpoint does not confirm usernames.
    with db() as connection:
        user = connection.execute(
            "SELECT id, username, role, enabled, recovery_code_hash FROM dashboard_users WHERE username = ? COLLATE NOCASE",
            (payload.username,),
        ).fetchone()
        supplied_digest = recovery_code_digest(payload.recovery_code)
        valid = bool(user and bool(user["enabled"]) and user["recovery_code_hash"] and hmac.compare_digest(supplied_digest, user["recovery_code_hash"]))
        if not valid:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or recovery code")
        now = iso_now()
        connection.execute(
            "UPDATE dashboard_users SET password_hash = ?, password_changed_at = ? WHERE id = ?",
            (hash_password(payload.new_password), now, user["id"]),
        )
        connection.execute("DELETE FROM dashboard_sessions WHERE user_id = ?", (user["id"],))
        recovery = rotate_recovery_code(connection, int(user["id"]))
        audit_account_event(connection, int(user["id"]), user["username"], "password_recovered", "Password reset using recovery code")
        audit_account_event(connection, int(user["id"]), user["username"], "recovery_code_rotated", "Recovery code rotated after use")
        token, csrf = create_session(connection, int(user["id"]))
    set_session_cookie(response, token)
    role = user["role"] if user["role"] in ROLE_PERMISSIONS else "viewer"
    return AuthStatus(
        setup_required=False,
        authenticated=True,
        username=user["username"],
        role=role,
        permissions=permissions_for_role(role),
        csrf_token=csrf,
        recovery_code=recovery.recovery_code,
    )


@app.get("/api/account", response_model=AccountSummary)
def get_account(user: SessionUser = Depends(require_auth)) -> AccountSummary:
    with db() as connection:
        row = connection.execute(
            "SELECT username, role, recovery_code_hash, recovery_generated_at, password_changed_at FROM dashboard_users WHERE id = ?",
            (user.user_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        events = connection.execute(
            "SELECT id, event, detail, created_at FROM account_audit WHERE user_id = ? ORDER BY id DESC LIMIT 12",
            (user.user_id,),
        ).fetchall()
    return AccountSummary(
        username=row["username"],
        role=row["role"] if row["role"] in ROLE_PERMISSIONS else "viewer",
        recovery_configured=bool(row["recovery_code_hash"]),
        recovery_generated_at=row["recovery_generated_at"],
        password_changed_at=row["password_changed_at"],
        recent_events=[AccountAuditEvent(id=int(event["id"]), event=event["event"], detail=event["detail"], created_at=event["created_at"]) for event in events],
    )


@app.post("/api/account/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(payload: PasswordChangeRequest, user: SessionUser = Depends(require_write_auth)) -> Response:
    with db() as connection:
        row = connection.execute("SELECT password_hash FROM dashboard_users WHERE id = ?", (user.user_id,)).fetchone()
        if not row or not verify_password(payload.current_password, row["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")
        connection.execute(
            "UPDATE dashboard_users SET password_hash = ?, password_changed_at = ? WHERE id = ?",
            (hash_password(payload.new_password), iso_now(), user.user_id),
        )
        # Keep the browser that performed the change signed in, but invalidate all other sessions.
        connection.execute("DELETE FROM dashboard_sessions WHERE user_id = ? AND token_hash != ?", (user.user_id, user.token_hash))
        audit_account_event(connection, user.user_id, user.username, "password_changed", "Password changed from Settings; other sessions invalidated")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/account/recovery-code", response_model=RecoveryCodeResult)
def regenerate_recovery_code(payload: RecoveryCodeRequest, user: SessionUser = Depends(require_write_auth)) -> RecoveryCodeResult:
    with db() as connection:
        row = connection.execute("SELECT password_hash FROM dashboard_users WHERE id = ?", (user.user_id,)).fetchone()
        if not row or not verify_password(payload.current_password, row["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")
        result = rotate_recovery_code(connection, user.user_id)
        audit_account_event(connection, user.user_id, user.username, "recovery_code_generated", "Recovery code generated from Settings; previous code invalidated")
    return result


def row_to_user_summary(row: sqlite3.Row) -> UserSummary:
    role = row["role"] if row["role"] in ROLE_PERMISSIONS else "viewer"
    return UserSummary(
        id=int(row["id"]),
        username=row["username"],
        role=role,
        enabled=bool(row["enabled"]),
        recovery_configured=bool(row["recovery_code_hash"]),
        password_changed_at=row["password_changed_at"],
        last_login_at=row["last_login_at"],
        created_at=row["created_at"],
    )


def enabled_owner_count(connection: sqlite3.Connection) -> int:
    return int(connection.execute(
        "SELECT COUNT(*) FROM dashboard_users WHERE role = 'owner' AND enabled = 1"
    ).fetchone()[0])


@app.get("/api/users", response_model=list[UserSummary])
def list_users(_: SessionUser = Depends(require_users_read)) -> list[UserSummary]:
    with db() as connection:
        rows = connection.execute(
            "SELECT * FROM dashboard_users ORDER BY CASE role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 WHEN 'editor' THEN 2 ELSE 3 END, username COLLATE NOCASE"
        ).fetchall()
    return [row_to_user_summary(row) for row in rows]


@app.post("/api/users", response_model=UserSummary, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, actor: SessionUser = Depends(require_users_manage)) -> UserSummary:
    with db() as connection:
        if connection.execute("SELECT 1 FROM dashboard_users WHERE username = ? COLLATE NOCASE", (payload.username,)).fetchone():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
        now = iso_now()
        cursor = connection.execute(
            """INSERT INTO dashboard_users
               (username, password_hash, role, enabled, password_changed_at, created_at)
               VALUES (?, ?, ?, 1, ?, ?)""",
            (payload.username, hash_password(payload.password), payload.role, now, now),
        )
        user_id = int(cursor.lastrowid)
        audit_account_event(connection, user_id, payload.username, "account_created", f"Local account created by {actor.username} with role {payload.role}")
        row = connection.execute("SELECT * FROM dashboard_users WHERE id = ?", (user_id,)).fetchone()
    return row_to_user_summary(row)


@app.put("/api/users/{user_id}", response_model=UserSummary)
def update_user(user_id: int, payload: UserUpdate, actor: SessionUser = Depends(require_users_manage)) -> UserSummary:
    with db() as connection:
        row = connection.execute("SELECT * FROM dashboard_users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        removing_last_owner = row["role"] == "owner" and bool(row["enabled"]) and (payload.role != "owner" or not payload.enabled)
        if removing_last_owner and enabled_owner_count(connection) <= 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="At least one enabled owner account is required")
        if user_id == actor.user_id and not payload.enabled:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot disable your own account")
        if user_id == actor.user_id and payload.role != row["role"]:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Another owner must change your role")
        connection.execute("UPDATE dashboard_users SET role = ?, enabled = ? WHERE id = ?", (payload.role, int(payload.enabled), user_id))
        if not payload.enabled:
            connection.execute("DELETE FROM dashboard_sessions WHERE user_id = ?", (user_id,))
        audit_account_event(connection, user_id, row["username"], "account_updated", f"Role/enabled state changed by {actor.username}: role={payload.role}, enabled={payload.enabled}")
        updated = connection.execute("SELECT * FROM dashboard_users WHERE id = ?", (user_id,)).fetchone()
    return row_to_user_summary(updated)


@app.post("/api/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_user_password(user_id: int, payload: UserPasswordReset, actor: SessionUser = Depends(require_users_manage)) -> Response:
    with db() as connection:
        row = connection.execute("SELECT id, username FROM dashboard_users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        connection.execute(
            "UPDATE dashboard_users SET password_hash = ?, password_changed_at = ? WHERE id = ?",
            (hash_password(payload.new_password), iso_now(), user_id),
        )
        connection.execute("DELETE FROM dashboard_sessions WHERE user_id = ?", (user_id,))
        audit_account_event(connection, user_id, row["username"], "password_reset_by_owner", f"Password reset by {actor.username}; all sessions invalidated")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, actor: SessionUser = Depends(require_users_manage)) -> Response:
    with db() as connection:
        row = connection.execute("SELECT * FROM dashboard_users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if user_id == actor.user_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot delete your own account")
        if row["role"] == "owner" and bool(row["enabled"]) and enabled_owner_count(connection) <= 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="At least one enabled owner account is required")
        connection.execute("DELETE FROM dashboard_users WHERE id = ?", (user_id,))
        audit_account_event(connection, None, row["username"], "account_deleted", f"Local account deleted by {actor.username}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
def update_appearance(payload: AppearanceUpdate, _: SessionUser = Depends(require_settings_manage)) -> AppearanceSettings:
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
def import_theme(payload: ThemePackage, _: SessionUser = Depends(require_settings_manage)) -> AppearanceSettings:
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
def delete_theme(theme_id: str, _: SessionUser = Depends(require_settings_manage)) -> AppearanceSettings:
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


@app.get("/api/settings", response_model=DashboardSettings)
def get_dashboard_settings(_: SessionUser = Depends(require_auth)) -> DashboardSettings:
    with db() as connection:
        return read_dashboard_settings(connection)


@app.put("/api/settings", response_model=DashboardSettings)
def update_dashboard_settings(payload: DashboardSettings, _: SessionUser = Depends(require_settings_manage)) -> DashboardSettings:
    with db() as connection:
        save_dashboard_settings(connection, payload)
        return read_dashboard_settings(connection)


@app.get("/api/widgets", response_model=list[DashboardWidget])
def list_widgets(_: SessionUser = Depends(require_auth)) -> list[DashboardWidget]:
    with db() as connection:
        rows = connection.execute(
            "SELECT * FROM dashboard_widgets ORDER BY page_id, category COLLATE NOCASE, sort_order, title COLLATE NOCASE"
        ).fetchall()
    return [row_to_widget(row) for row in rows]


@app.post("/api/widgets", response_model=DashboardWidget, status_code=status.HTTP_201_CREATED)
def create_widget(payload: DashboardWidgetCreate, _: SessionUser = Depends(require_dashboard_edit)) -> DashboardWidget:
    now = iso_now()
    with db() as connection:
        require_page(connection, payload.page_id)
        ensure_category_layout(connection, payload.page_id, payload.category)
        sort_order = payload.sort_order or int(connection.execute(
            """SELECT COALESCE(MAX(sort_order), 0) + 1 FROM (
                   SELECT sort_order FROM services WHERE page_id = ? AND category = ? COLLATE NOCASE
                   UNION ALL SELECT sort_order FROM dashboard_widgets WHERE page_id = ? AND category = ? COLLATE NOCASE
               )""",
            (payload.page_id, payload.category, payload.page_id, payload.category),
        ).fetchone()[0])
        config = normalize_widget_config(payload.type, payload.config)
        cursor = connection.execute(
            """INSERT INTO dashboard_widgets
               (type, title, page_id, category, card_size, sort_order, enabled, config_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (payload.type, payload.title, payload.page_id, payload.category, payload.card_size, sort_order, int(payload.enabled), json.dumps(config, separators=(",", ":")), now, now),
        )
        row = connection.execute("SELECT * FROM dashboard_widgets WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_widget(row)


@app.put("/api/widgets/{widget_id}", response_model=DashboardWidget)
def update_widget(widget_id: int, payload: DashboardWidgetUpdate, _: SessionUser = Depends(require_dashboard_edit)) -> DashboardWidget:
    with db() as connection:
        current = connection.execute("SELECT page_id, category, sort_order FROM dashboard_widgets WHERE id = ?", (widget_id,)).fetchone()
        if not current:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget not found")
        require_page(connection, payload.page_id)
        ensure_category_layout(connection, payload.page_id, payload.category)
        config = normalize_widget_config(payload.type, payload.config)
        sort_order = payload.sort_order
        if payload.page_id != current["page_id"] or payload.category.casefold() != str(current["category"]).casefold():
            sort_order = int(connection.execute("""SELECT COALESCE(MAX(sort_order), 0) + 1 FROM (SELECT sort_order FROM services WHERE page_id = ? AND category = ? COLLATE NOCASE UNION ALL SELECT sort_order FROM dashboard_widgets WHERE page_id = ? AND category = ? COLLATE NOCASE)""", (payload.page_id, payload.category, payload.page_id, payload.category)).fetchone()[0])
        connection.execute(
            """UPDATE dashboard_widgets SET type = ?, title = ?, page_id = ?, category = ?, card_size = ?,
               sort_order = ?, enabled = ?, config_json = ?, updated_at = ? WHERE id = ?""",
            (payload.type, payload.title, payload.page_id, payload.category, payload.card_size, sort_order, int(payload.enabled), json.dumps(config, separators=(",", ":")), iso_now(), widget_id),
        )
        row = connection.execute("SELECT * FROM dashboard_widgets WHERE id = ?", (widget_id,)).fetchone()
    return row_to_widget(row)


@app.patch("/api/widgets/{widget_id}/layout", response_model=DashboardWidget)
def update_widget_layout(widget_id: int, payload: WidgetLayoutUpdate, _: SessionUser = Depends(require_dashboard_edit)) -> DashboardWidget:
    with db() as connection:
        row = connection.execute("SELECT * FROM dashboard_widgets WHERE id = ?", (widget_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget not found")
        connection.execute(
            "UPDATE dashboard_widgets SET card_size = ?, enabled = ?, updated_at = ? WHERE id = ?",
            (payload.card_size or row["card_size"], int(payload.enabled) if payload.enabled is not None else row["enabled"], iso_now(), widget_id),
        )
        row = connection.execute("SELECT * FROM dashboard_widgets WHERE id = ?", (widget_id,)).fetchone()
    return row_to_widget(row)


@app.post("/api/widgets/reorder", response_model=list[DashboardWidget])
def reorder_widgets(payload: WidgetReorder, _: SessionUser = Depends(require_dashboard_edit)) -> list[DashboardWidget]:
    if len(payload.ordered_ids) != len(set(payload.ordered_ids)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate widget ids in reorder request")
    with db() as connection:
        existing = [row["id"] for row in connection.execute(
            "SELECT id FROM dashboard_widgets WHERE page_id = ? AND category = ? COLLATE NOCASE ORDER BY sort_order, id",
            (payload.page_id, payload.category),
        ).fetchall()]
        if set(existing) != set(payload.ordered_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Widget reorder must include every widget in the category")
        for position, widget_id in enumerate(payload.ordered_ids, start=1):
            connection.execute("UPDATE dashboard_widgets SET sort_order = ?, updated_at = ? WHERE id = ?", (position, iso_now(), widget_id))
        rows = connection.execute(
            "SELECT * FROM dashboard_widgets WHERE page_id = ? AND category = ? COLLATE NOCASE ORDER BY sort_order, title COLLATE NOCASE",
            (payload.page_id, payload.category),
        ).fetchall()
    return [row_to_widget(row) for row in rows]


@app.delete("/api/widgets/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_widget(widget_id: int, _: SessionUser = Depends(require_dashboard_edit)) -> Response:
    with db() as connection:
        cursor = connection.execute("DELETE FROM dashboard_widgets WHERE id = ?", (widget_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def extension_version_tuple(value: str) -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value)
    return tuple(int(part) for part in match.groups()) if match else (0, 0, 0)


def validate_extension_package_content(package: ExtensionPackage) -> None:
    if extension_version_tuple(package.min_dashboard_version) > extension_version_tuple(APP_VERSION):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extension requires Homelab Dashboard {package.min_dashboard_version} or newer",
        )
    template_ids = [template.id for template in package.page_templates]
    if len(template_ids) != len(set(template_ids)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Extension contains duplicate page-template ids")
    catalog_types = [entry.type for entry in package.catalog_entries]
    if len(catalog_types) != len(set(catalog_types)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Extension contains duplicate service catalog types")
    needs_templates = bool(package.page_templates)
    needs_catalog = bool(package.catalog_entries)
    if needs_templates and "page_templates" not in package.capabilities:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Page-template packages must declare the page_templates capability")
    if needs_templates and "dashboard:register-templates" not in package.permissions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Page-template packages must request dashboard:register-templates")
    if needs_catalog and "service_catalog" not in package.capabilities:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Catalog packages must declare the service_catalog capability")
    if needs_catalog and "catalog:register-entries" not in package.permissions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Catalog packages must request catalog:register-entries")
    if package.type == "page_template_pack" and (not needs_templates or needs_catalog):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="page_template_pack must contain templates only")
    if package.type == "catalog_pack" and (not needs_catalog or needs_templates):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="catalog_pack must contain catalog entries only")
    if package.type == "bundle" and not (needs_templates or needs_catalog):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="bundle must contain at least one supported data capability")


def installed_extension_rows(connection: sqlite3.Connection, *, enabled_only: bool = False) -> list[tuple[ExtensionPackage, bool]]:
    query = "SELECT * FROM installed_extensions"
    if enabled_only:
        query += " WHERE enabled = 1"
    query += " ORDER BY id COLLATE NOCASE"
    result: list[tuple[ExtensionPackage, bool]] = []
    for row in connection.execute(query).fetchall():
        try:
            package = ExtensionPackage.model_validate_json(row["manifest_json"])
            validate_extension_package_content(package)
            result.append((package, bool(row["enabled"])))
        except (ValueError, HTTPException):
            continue
    return result


def extension_descriptor(package: ExtensionPackage, enabled: bool) -> ExtensionDescriptor:
    return ExtensionDescriptor(
        id=package.id,
        name=package.name,
        type=package.type,
        version=package.version,
        author=package.author,
        description=package.description,
        source="imported",
        active=enabled,
        enabled=enabled,
        removable=True,
        capabilities=package.capabilities,
        permissions=package.permissions,
    )


def export_page_payload(connection: sqlite3.Connection, page_id: int) -> dict[str, object]:
    page = require_page(connection, page_id)
    categories = [
        dict(name=row["name"], sort_order=row["sort_order"], collapsed=bool(row["collapsed"]), icon=row["icon"] if "icon" in row.keys() else None)
        for row in connection.execute("SELECT * FROM category_layouts WHERE page_id = ? ORDER BY sort_order, name COLLATE NOCASE", (page_id,)).fetchall()
    ]
    services_out: list[dict[str, object]] = []
    for row in connection.execute("SELECT * FROM services WHERE page_id = ? ORDER BY category COLLATE NOCASE, sort_order, id", (page_id,)).fetchall():
        services_out.append({
            "name": row["name"], "type": row["type"], "url": row["url"], "category": row["category"], "icon": row["icon"],
            "enabled": bool(row["enabled"]), "status_check": bool(row["status_check"]), "favorite": bool(row["favorite"]),
            "card_size": row["card_size"], "sort_order": row["sort_order"],
        })
    widgets_out: list[dict[str, object]] = []
    for row in connection.execute("SELECT * FROM dashboard_widgets WHERE page_id = ? ORDER BY category COLLATE NOCASE, sort_order, id", (page_id,)).fetchall():
        try:
            config = json.loads(row["config_json"] or "{}")
        except json.JSONDecodeError:
            config = {}
        widgets_out.append({
            "type": row["type"], "title": row["title"], "category": row["category"], "card_size": row["card_size"],
            "sort_order": row["sort_order"], "enabled": bool(row["enabled"]), "config": config,
        })
    return {"name": page["name"], "categories": categories, "services": services_out, "widgets": widgets_out}


def unique_page_name(connection: sqlite3.Connection, requested_name: str) -> str:
    base_name = requested_name.strip()[:60] or "New page"
    name = base_name
    suffix = 2
    while connection.execute("SELECT 1 FROM dashboard_pages WHERE name = ? COLLATE NOCASE", (name,)).fetchone():
        tail = f" {suffix}"
        name = f"{base_name[:60-len(tail)]}{tail}"
        suffix += 1
    return name


def create_page_from_template(connection: sqlite3.Connection, template: PageTemplate, requested_name: str) -> DashboardPage:
    now = iso_now()
    name = unique_page_name(connection, requested_name)
    page_order = int(connection.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM dashboard_pages").fetchone()[0])
    cursor = connection.execute(
        "INSERT INTO dashboard_pages (name, sort_order, is_default, created_at, updated_at) VALUES (?, ?, 0, ?, ?)",
        (name, page_order, now, now),
    )
    page_id = int(cursor.lastrowid)
    for index, category in enumerate(template.categories, start=1):
        icon = category.icon.strip().lower() if category.icon else None
        if icon and not re.fullmatch(r"[a-z0-9-]{1,32}", icon):
            icon = None
        connection.execute(
            "INSERT OR IGNORE INTO category_layouts (page_id, name, sort_order, collapsed, icon) VALUES (?, ?, ?, ?, ?)",
            (page_id, category.name, category.sort_order or index, int(category.collapsed), icon),
        )
    for index, service in enumerate(template.services, start=1):
        ensure_category_layout(connection, page_id, service.category)
        connection.execute(
            """INSERT INTO services (name,type,url,category,page_id,icon,enabled,status_check,favorite,card_size,sort_order,management_provider,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (service.name, service.type, service.url, service.category, page_id, service.icon, int(service.enabled), int(service.status_check),
             int(service.favorite), service.card_size, service.sort_order or index, "none", now, now),
        )
    for index, widget in enumerate(template.widgets, start=1):
        ensure_category_layout(connection, page_id, widget.category)
        config = normalize_widget_config(widget.type, widget.config)
        connection.execute(
            """INSERT INTO dashboard_widgets (type,title,page_id,category,card_size,sort_order,enabled,config_json,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (widget.type, widget.title, page_id, widget.category, widget.card_size, widget.sort_order or index, int(widget.enabled),
             json.dumps(config, separators=(",", ":")), now, now),
        )
    row = connection.execute("SELECT * FROM dashboard_pages WHERE id = ?", (page_id,)).fetchone()
    return row_to_page(row)


_registry_cache_lock = threading.Lock()
_registry_cache: tuple[float, ExtensionRegistryIndex] | None = None


def _registry_source_url() -> str:
    value = EXTENSION_REGISTRY_URL.strip()
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Extension registry URL must use HTTPS")
    return value


def _read_limited_url(url: str, *, maximum: int) -> bytes:
    request = Request(url, headers={"User-Agent": f"Homelab-Dashboard/{APP_VERSION}", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=EXTENSION_REGISTRY_TIMEOUT) as response:
            requested = urlparse(url)
            final = urlparse(response.geturl())
            if final.scheme != "https" or final.netloc != requested.netloc:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Registry download redirected outside its HTTPS origin")
            content_type = response.headers.get("Content-Type", "").lower()
            if "json" not in content_type and "text/plain" not in content_type and "octet-stream" not in content_type:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Registry returned an unsupported content type")
            data = response.read(maximum + 1)
    except HTTPException:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Unable to reach extension registry: {exc}") from exc
    if len(data) > maximum:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Registry response is too large")
    return data


def load_extension_registry(*, refresh: bool = False) -> ExtensionRegistryIndex:
    global _registry_cache
    now = time.time()
    with _registry_cache_lock:
        if not refresh and _registry_cache and now - _registry_cache[0] < EXTENSION_REGISTRY_CACHE_SECONDS:
            return _registry_cache[1]
    source = _registry_source_url()
    raw = _read_limited_url(source, maximum=2_000_000)
    try:
        registry = ExtensionRegistryIndex.model_validate_json(raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Extension registry is invalid: {exc}") from exc
    ids = [entry.id for entry in registry.entries]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Extension registry contains duplicate extension ids")
    with _registry_cache_lock:
        _registry_cache = (now, registry)
    return registry


def registry_package_url(entry: ExtensionRegistryEntry) -> str:
    source = _registry_source_url()
    package_url = urljoin(source, entry.package)
    source_parts = urlparse(source)
    package_parts = urlparse(package_url)
    if package_parts.scheme != "https" or package_parts.netloc != source_parts.netloc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Registry package must stay on the registry HTTPS origin")
    return package_url


def registry_response(*, refresh: bool = False) -> ExtensionRegistryResponse:
    registry = load_extension_registry(refresh=refresh)
    with db() as connection:
        installed_rows = {row["id"]: row for row in connection.execute("SELECT * FROM installed_extensions").fetchall()}
    entries: list[ExtensionRegistryItem] = []
    for entry in registry.entries:
        installed_version = None
        installed_enabled = None
        row = installed_rows.get(entry.id)
        if row:
            try:
                package = ExtensionPackage.model_validate_json(row["manifest_json"])
                installed_version = package.version
                installed_enabled = bool(row["enabled"])
            except ValueError:
                pass
        compatible = extension_version_tuple(entry.min_dashboard_version) <= extension_version_tuple(APP_VERSION)
        entries.append(ExtensionRegistryItem(
            **entry.model_dump(),
            installed_version=installed_version,
            installed_enabled=installed_enabled,
            update_available=bool(installed_version and extension_version_tuple(entry.version) > extension_version_tuple(installed_version)),
            compatible=compatible,
            compatibility_message=None if compatible else f"Requires Homelab Dashboard {entry.min_dashboard_version} or newer",
        ))
    return ExtensionRegistryResponse(
        registry_id=registry.id,
        registry_name=registry.name,
        description=registry.description,
        source_url=_registry_source_url(),
        checked_at=iso_now(),
        entries=entries,
    )


@app.get("/api/extensions/registry", response_model=ExtensionRegistryResponse)
def get_extension_registry(refresh: bool = False, _: SessionUser = Depends(require_auth)) -> ExtensionRegistryResponse:
    return registry_response(refresh=refresh)


@app.post("/api/extensions/registry/{extension_id}/install", response_model=ExtensionDescriptor)
def install_registry_extension(extension_id: str, payload: ExtensionRegistryInstallRequest, _: SessionUser = Depends(require_extensions_manage)) -> ExtensionDescriptor:
    registry = load_extension_registry(refresh=True)
    entry = next((item for item in registry.entries if item.id == extension_id), None)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Extension is not present in the configured registry")
    if payload.expected_version != entry.version or payload.expected_sha256.lower() != entry.sha256:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Registry entry changed; refresh the registry before installing")
    if sorted(set(payload.accepted_permissions)) != sorted(set(entry.permissions)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Accepted permissions do not match the registry package")
    if extension_version_tuple(entry.min_dashboard_version) > extension_version_tuple(APP_VERSION):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Extension requires Homelab Dashboard {entry.min_dashboard_version} or newer")
    package_url = registry_package_url(entry)
    raw = _read_limited_url(package_url, maximum=4_000_000)
    digest = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(digest, entry.sha256):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Extension package checksum does not match the registry")
    try:
        package = ExtensionPackage.model_validate_json(raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Extension package is invalid: {exc}") from exc
    validate_extension_package_content(package)
    if package.id != entry.id or package.version != entry.version:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Extension package identity/version does not match the registry")
    if sorted(package.permissions) != sorted(entry.permissions) or sorted(package.capabilities) != sorted(entry.capabilities):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Extension package capabilities/permissions do not match the registry")
    now = iso_now()
    with db() as connection:
        existing = connection.execute("SELECT * FROM installed_extensions WHERE id = ?", (package.id,)).fetchone()
        if existing:
            current = ExtensionPackage.model_validate_json(existing["manifest_json"])
            if extension_version_tuple(package.version) <= extension_version_tuple(current.version):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The installed extension is already this version or newer")
            enabled = bool(existing["enabled"])
            connection.execute("UPDATE installed_extensions SET manifest_json = ?, updated_at = ? WHERE id = ?", (package.model_dump_json(), now, package.id))
        else:
            enabled = True
            connection.execute(
                "INSERT INTO installed_extensions (id, manifest_json, enabled, installed_at, updated_at) VALUES (?, ?, 1, ?, ?)",
                (package.id, package.model_dump_json(), now, now),
            )
    return extension_descriptor(package, enabled)


@app.get("/api/extensions", response_model=list[ExtensionDescriptor])
def list_extensions(_: SessionUser = Depends(require_auth)) -> list[ExtensionDescriptor]:
    built_in = [
        ExtensionDescriptor(id="core.theme-engine", name="Theme Engine", type="core", version=APP_VERSION, author="Homelab Dashboard", description="Built-in appearance engine and validated data-only theme packages.", source="built_in", active=True, enabled=True, removable=False),
        ExtensionDescriptor(id="core.widgets", name="Built-in Widget Pack", type="widget_pack", version=APP_VERSION, author="Homelab Dashboard", description="Clock, note, bookmarks, dashboard-summary, service-status, and update-overview widgets.", source="built_in", active=True, enabled=True, removable=False),
        ExtensionDescriptor(id="core.update-manager", name="Update Manager", type="core", version=APP_VERSION, author="Homelab Dashboard", description="Management providers, update discovery, progress, health verification, and history.", source="built_in", active=True, enabled=True, removable=False),
        ExtensionDescriptor(id="core.page-templates", name="Starter Page Templates", type="page_template_pack", version=APP_VERSION, author="Homelab Dashboard", description="Built-in reusable Operations and Personal Start dashboard pages.", source="built_in", active=True, enabled=True, removable=False, capabilities=["page_templates"], permissions=[]),
    ]
    with db() as connection:
        selected = connection.execute("SELECT value FROM app_settings WHERE key = 'theme_id'").fetchone()
        selected_id = selected["value"] if selected else "system"
        themes = list_theme_rows(connection)
        packages = installed_extension_rows(connection)
    imported_themes = [
        ExtensionDescriptor(
            id=f"theme.{theme.id}", name=theme.name, type="theme", version=theme.version, author=theme.author,
            description=theme.description or "Imported visual theme", source="imported", active=selected_id == theme.id, enabled=True, removable=True,
            capabilities=["appearance"], permissions=[],
        ) for theme in themes
    ]
    return built_in + imported_themes + [extension_descriptor(package, enabled) for package, enabled in packages]


@app.post("/api/extensions/import", response_model=ExtensionDescriptor, status_code=status.HTTP_201_CREATED)
def import_extension(payload: ExtensionPackage, _: SessionUser = Depends(require_extensions_manage)) -> ExtensionDescriptor:
    validate_extension_package_content(payload)
    now = iso_now()
    with db() as connection:
        if connection.execute("SELECT 1 FROM installed_extensions WHERE id = ?", (payload.id,)).fetchone():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An extension with that id is already installed")
        connection.execute(
            "INSERT INTO installed_extensions (id, manifest_json, enabled, installed_at, updated_at) VALUES (?, ?, 1, ?, ?)",
            (payload.id, payload.model_dump_json(), now, now),
        )
    return extension_descriptor(payload, True)


@app.patch("/api/extensions/{extension_id}", response_model=ExtensionDescriptor)
def set_extension_state(extension_id: str, payload: ExtensionStateUpdate, _: SessionUser = Depends(require_extensions_manage)) -> ExtensionDescriptor:
    with db() as connection:
        row = connection.execute("SELECT * FROM installed_extensions WHERE id = ?", (extension_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Extension not found")
        package = ExtensionPackage.model_validate_json(row["manifest_json"])
        connection.execute("UPDATE installed_extensions SET enabled = ?, updated_at = ? WHERE id = ?", (int(payload.enabled), iso_now(), extension_id))
    return extension_descriptor(package, payload.enabled)


@app.delete("/api/extensions/{extension_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_extension(extension_id: str, _: SessionUser = Depends(require_extensions_manage)) -> Response:
    with db() as connection:
        cursor = connection.execute("DELETE FROM installed_extensions WHERE id = ?", (extension_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Extension not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/catalog/extensions", response_model=list[ExtensionCatalogEntry])
def extension_catalog_entries(_: SessionUser = Depends(require_auth)) -> list[ExtensionCatalogEntry]:
    entries: list[ExtensionCatalogEntry] = []
    seen: set[str] = set()
    with db() as connection:
        packages = installed_extension_rows(connection, enabled_only=True)
    for package, _enabled in packages:
        for entry in package.catalog_entries:
            if entry.type in seen:
                continue
            seen.add(entry.type)
            entries.append(entry)
    return entries


@app.get("/api/page-templates", response_model=list[PageTemplateDescriptor])
def list_page_templates(_: SessionUser = Depends(require_auth)) -> list[PageTemplateDescriptor]:
    result = [
        PageTemplateDescriptor(extension_id="core.page-templates", template_id=template.id, name=template.name, description=template.description, author="Homelab Dashboard", source="built_in")
        for template in BUILTIN_PAGE_TEMPLATES
    ]
    with db() as connection:
        packages = installed_extension_rows(connection, enabled_only=True)
    for package, _enabled in packages:
        for template in package.page_templates:
            result.append(PageTemplateDescriptor(extension_id=package.id, template_id=template.id, name=template.name, description=template.description, author=package.author, source="imported"))
    return result


def resolve_page_template(connection: sqlite3.Connection, extension_id: str, template_id: str) -> PageTemplate:
    if extension_id == "core.page-templates":
        for template in BUILTIN_PAGE_TEMPLATES:
            if template.id == template_id:
                return template
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page template not found")
    row = connection.execute("SELECT * FROM installed_extensions WHERE id = ? AND enabled = 1", (extension_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enabled extension not found")
    package = ExtensionPackage.model_validate_json(row["manifest_json"])
    validate_extension_package_content(package)
    for template in package.page_templates:
        if template.id == template_id:
            return template
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page template not found")


@app.post("/api/page-templates/{extension_id}/{template_id}/instantiate", response_model=DashboardPage, status_code=status.HTTP_201_CREATED)
def instantiate_page_template(extension_id: str, template_id: str, payload: PageCloneRequest, _: SessionUser = Depends(require_dashboard_edit)) -> DashboardPage:
    with db() as connection:
        template = resolve_page_template(connection, extension_id, template_id)
        return create_page_from_template(connection, template, payload.name)


@app.get("/api/pages/{page_id}/template-package", response_model=ExtensionPackage)
def export_page_template_package(page_id: int, _: SessionUser = Depends(require_auth)) -> ExtensionPackage:
    with db() as connection:
        page = export_page_payload(connection, page_id)
    slug = re.sub(r"[^a-z0-9]+", "-", str(page["name"]).lower()).strip("-")[:48] or "page"
    template = PageTemplate(
        id=slug,
        name=str(page["name"]),
        description=f"Reusable template exported from the {page['name']} dashboard page.",
        categories=[PageTemplateCategory.model_validate(item) for item in page["categories"]],
        services=[PageTemplateService.model_validate(item) for item in page["services"]],
        widgets=[PageTemplateWidget.model_validate(item) for item in page["widgets"]],
    )
    return ExtensionPackage(
        id=f"local.{slug}-templates",
        name=f"{page['name']} Page Template",
        version="1.0.0",
        author="Homelab Dashboard User",
        description="Shareable page-template package. API keys, passwords, and management links are excluded.",
        type="page_template_pack",
        min_dashboard_version="0.16.0",
        capabilities=["page_templates"],
        permissions=["dashboard:register-templates"],
        page_templates=[template],
    )


@app.get("/api/dashboard/export")
def export_dashboard_structure(_: SessionUser = Depends(require_auth)) -> dict[str, object]:
    with db() as connection:
        page_rows = connection.execute("SELECT * FROM dashboard_pages ORDER BY sort_order, id").fetchall()
        exported_pages: list[dict[str, object]] = []
        for page in page_rows:
            categories = [dict(name=row["name"], sort_order=row["sort_order"], collapsed=bool(row["collapsed"]), icon=row["icon"] if "icon" in row.keys() else None) for row in connection.execute("SELECT * FROM category_layouts WHERE page_id = ? ORDER BY sort_order, name COLLATE NOCASE", (page["id"],)).fetchall()]
            services_out = []
            for row in connection.execute("SELECT * FROM services WHERE page_id = ? ORDER BY category COLLATE NOCASE, sort_order, id", (page["id"],)).fetchall():
                services_out.append({"name": row["name"], "type": row["type"], "url": row["url"], "category": row["category"], "icon": row["icon"], "enabled": bool(row["enabled"]), "status_check": bool(row["status_check"]), "favorite": bool(row["favorite"]), "card_size": row["card_size"], "sort_order": row["sort_order"]})
            widgets_out = []
            for row in connection.execute("SELECT * FROM dashboard_widgets WHERE page_id = ? ORDER BY category COLLATE NOCASE, sort_order, id", (page["id"],)).fetchall():
                try: config = json.loads(row["config_json"] or "{}")
                except json.JSONDecodeError: config = {}
                widgets_out.append({"type": row["type"], "title": row["title"], "category": row["category"], "card_size": row["card_size"], "sort_order": row["sort_order"], "enabled": bool(row["enabled"]), "config": config})
            exported_pages.append({"name": page["name"], "is_default": bool(page["is_default"]), "categories": categories, "services": services_out, "widgets": widgets_out})
    return {"format": "homelab-dashboard-layout", "schema_version": 1, "exported_at": iso_now(), "contains_secrets": False, "pages": exported_pages}


@app.post("/api/dashboard/import", response_model=list[DashboardPage])
def import_dashboard_structure(payload: dict[str, object], _: SessionUser = Depends(require_dashboard_edit)) -> list[DashboardPage]:
    if payload.get("format") != "homelab-dashboard-layout" or payload.get("schema_version") != 1 or not isinstance(payload.get("pages"), list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported dashboard layout file")
    now = iso_now()
    with db() as connection:
        for raw_page in payload["pages"][:50]:
            if not isinstance(raw_page, dict):
                continue
            base_name = str(raw_page.get("name", "Imported page")).strip()[:60] or "Imported page"
            name = base_name
            suffix = 2
            while connection.execute("SELECT 1 FROM dashboard_pages WHERE name = ? COLLATE NOCASE", (name,)).fetchone():
                tail = f" {suffix}"
                name = f"{base_name[:60-len(tail)]}{tail}"
                suffix += 1
            page_order = int(connection.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM dashboard_pages").fetchone()[0])
            cursor = connection.execute("INSERT INTO dashboard_pages (name, sort_order, is_default, created_at, updated_at) VALUES (?, ?, 0, ?, ?)", (name, page_order, now, now))
            page_id = int(cursor.lastrowid)
            raw_categories = raw_page.get("categories", [])
            if isinstance(raw_categories, list):
                for index, raw_cat in enumerate(raw_categories[:100], start=1):
                    if not isinstance(raw_cat, dict): continue
                    cat_name = str(raw_cat.get("name", "General")).strip()[:80] or "General"
                    icon = str(raw_cat.get("icon") or "").strip().lower()[:32] or None
                    if icon and not re.fullmatch(r"[a-z0-9-]{1,32}", icon): icon = None
                    connection.execute("INSERT OR IGNORE INTO category_layouts (page_id, name, sort_order, collapsed, icon) VALUES (?, ?, ?, ?, ?)", (page_id, cat_name, int(raw_cat.get("sort_order") or index), int(bool(raw_cat.get("collapsed", False))), icon))
            raw_services = raw_page.get("services", [])
            if isinstance(raw_services, list):
                for index, raw in enumerate(raw_services[:1000], start=1):
                    if not isinstance(raw, dict): continue
                    name_value = str(raw.get("name", "Service")).strip()[:80] or "Service"
                    type_value = str(raw.get("type", "link")).strip().lower()[:80] or "link"
                    if not re.fullmatch(r"[a-z0-9._-]+", type_value):
                        type_value = "link"
                    url_value = str(raw.get("url", "https://")).strip()[:1000]
                    parsed = urlparse(url_value)
                    if parsed.scheme not in {"http", "https"}: continue
                    category = str(raw.get("category", "General")).strip()[:80] or "General"
                    ensure_category_layout(connection, page_id, category)
                    connection.execute("""INSERT INTO services (name,type,url,category,page_id,icon,enabled,status_check,favorite,card_size,sort_order,management_provider,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (name_value, type_value, url_value, category, page_id, (str(raw.get("icon") or "").strip()[:32] or None), int(bool(raw.get("enabled", True))), int(bool(raw.get("status_check", True))), int(bool(raw.get("favorite", False))), raw.get("card_size") if raw.get("card_size") in {"compact","standard","wide"} else "standard", int(raw.get("sort_order") or index), "none", now, now))
            raw_widgets = raw_page.get("widgets", [])
            if isinstance(raw_widgets, list):
                for index, raw in enumerate(raw_widgets[:1000], start=1):
                    if not isinstance(raw, dict): continue
                    widget_type = str(raw.get("type", "note"))
                    if widget_type not in {"clock","note","bookmarks","system_summary","service_status","update_overview"}: continue
                    title = str(raw.get("title", "Widget")).strip()[:80] or "Widget"
                    category = str(raw.get("category", "Widgets")).strip()[:80] or "Widgets"
                    ensure_category_layout(connection, page_id, category)
                    config = normalize_widget_config(widget_type, raw.get("config") if isinstance(raw.get("config"), dict) else {})
                    connection.execute("""INSERT INTO dashboard_widgets (type,title,page_id,category,card_size,sort_order,enabled,config_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)""", (widget_type, title, page_id, category, raw.get("card_size") if raw.get("card_size") in {"compact","standard","wide"} else "standard", int(raw.get("sort_order") or index), int(bool(raw.get("enabled", True))), json.dumps(config,separators=(",",":")), now, now))
        rows = connection.execute("SELECT * FROM dashboard_pages ORDER BY sort_order, id").fetchall()
    return [row_to_page(row) for row in rows]


@app.get("/api/pages", response_model=list[DashboardPage])
def list_pages(_: SessionUser = Depends(require_auth)) -> list[DashboardPage]:
    with db() as connection:
        rows = connection.execute(
            "SELECT * FROM dashboard_pages ORDER BY sort_order, id"
        ).fetchall()
    return [row_to_page(row) for row in rows]


@app.post("/api/pages", response_model=DashboardPage, status_code=status.HTTP_201_CREATED)
def create_page(payload: DashboardPageCreate, _: SessionUser = Depends(require_dashboard_edit)) -> DashboardPage:
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
def update_page(page_id: int, payload: DashboardPageUpdate, _: SessionUser = Depends(require_dashboard_edit)) -> DashboardPage:
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


@app.post("/api/pages/{page_id}/clone", response_model=DashboardPage, status_code=status.HTTP_201_CREATED)
def clone_page(page_id: int, payload: PageCloneRequest, _: SessionUser = Depends(require_dashboard_edit)) -> DashboardPage:
    now = iso_now()
    with db() as connection:
        require_page(connection, page_id)
        sort_order = int(connection.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM dashboard_pages").fetchone()[0])
        try:
            cursor = connection.execute("INSERT INTO dashboard_pages (name, sort_order, is_default, created_at, updated_at) VALUES (?, ?, 0, ?, ?)", (payload.name, sort_order, now, now))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A page with that name already exists") from exc
        new_page_id = int(cursor.lastrowid)
        for category in connection.execute("SELECT * FROM category_layouts WHERE page_id = ? ORDER BY sort_order, name COLLATE NOCASE", (page_id,)).fetchall():
            connection.execute("INSERT INTO category_layouts (page_id, name, sort_order, collapsed, icon) VALUES (?, ?, ?, ?, ?)", (new_page_id, category["name"], category["sort_order"], category["collapsed"], category["icon"] if "icon" in category.keys() else None))
        for service in connection.execute("SELECT * FROM services WHERE page_id = ? ORDER BY category COLLATE NOCASE, sort_order, id", (page_id,)).fetchall():
            connection.execute(
                """INSERT INTO services (name, type, url, category, page_id, icon, enabled, status_check, favorite, card_size, sort_order, api_key_encrypted, auth_username_encrypted, auth_password_encrypted, management_provider, management_target, management_controller_service_id, management_connection_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (service["name"], service["type"], service["url"], service["category"], new_page_id, service["icon"], service["enabled"], service["status_check"], service["favorite"], service["card_size"], service["sort_order"], service["api_key_encrypted"], service["auth_username_encrypted"], service["auth_password_encrypted"], service["management_provider"], service["management_target"], service["management_controller_service_id"], service["management_connection_id"], now, now),
            )
        for widget in connection.execute("SELECT * FROM dashboard_widgets WHERE page_id = ? ORDER BY category COLLATE NOCASE, sort_order, id", (page_id,)).fetchall():
            connection.execute("""INSERT INTO dashboard_widgets (type, title, page_id, category, card_size, sort_order, enabled, config_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (widget["type"], widget["title"], new_page_id, widget["category"], widget["card_size"], widget["sort_order"], widget["enabled"], widget["config_json"], now, now))
        row = connection.execute("SELECT * FROM dashboard_pages WHERE id = ?", (new_page_id,)).fetchone()
    return row_to_page(row)


@app.post("/api/pages/reorder", response_model=list[DashboardPage])
def reorder_pages(payload: PageReorder, _: SessionUser = Depends(require_dashboard_edit)) -> list[DashboardPage]:
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
def delete_page(page_id: int, _: SessionUser = Depends(require_dashboard_edit)) -> Response:
    with db() as connection:
        page = require_page(connection, page_id)
        if page["is_default"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The default Home page cannot be deleted")
        service_count = int(connection.execute("SELECT COUNT(*) FROM services WHERE page_id = ?", (page_id,)).fetchone()[0])
        widget_count = int(connection.execute("SELECT COUNT(*) FROM dashboard_widgets WHERE page_id = ?", (page_id,)).fetchone()[0])
        if service_count or widget_count:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Move or remove services and widgets from this page before deleting it")
        connection.execute("DELETE FROM dashboard_pages WHERE id = ?", (page_id,))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/categories", response_model=list[CategoryLayout])
def list_categories(_: SessionUser = Depends(require_auth)) -> list[CategoryLayout]:
    with db() as connection:
        ensure_category_layouts(connection)
        rows = connection.execute(
            """
            SELECT c.page_id, c.name, c.sort_order, c.collapsed, c.icon
            FROM category_layouts c
            WHERE EXISTS (
                SELECT 1 FROM services s
                WHERE s.page_id = c.page_id AND s.category = c.name COLLATE NOCASE
            ) OR EXISTS (
                SELECT 1 FROM dashboard_widgets w
                WHERE w.page_id = c.page_id AND w.category = c.name COLLATE NOCASE
            )
            ORDER BY c.page_id, c.sort_order, c.name COLLATE NOCASE
            """
        ).fetchall()
    return [row_to_category(row) for row in rows]


@app.put("/api/categories/configure", response_model=CategoryLayout)
def configure_category(payload: CategoryUpdate, _: SessionUser = Depends(require_dashboard_edit)) -> CategoryLayout:
    with db() as connection:
        require_page(connection, payload.page_id)
        ensure_category_layout(connection, payload.page_id, payload.old_name)
        current = connection.execute(
            "SELECT * FROM category_layouts WHERE page_id = ? AND name = ? COLLATE NOCASE",
            (payload.page_id, payload.old_name),
        ).fetchone()
        if not current:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
        if payload.name != payload.old_name:
            conflict = None
            if payload.name.casefold() != payload.old_name.casefold():
                conflict = connection.execute(
                    "SELECT 1 FROM category_layouts WHERE page_id = ? AND name = ? COLLATE NOCASE",
                    (payload.page_id, payload.name),
                ).fetchone()
            if conflict:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A category with that name already exists on this page")
            connection.execute("UPDATE services SET category = ?, updated_at = ? WHERE page_id = ? AND category = ? COLLATE NOCASE", (payload.name, iso_now(), payload.page_id, payload.old_name))
            connection.execute("UPDATE dashboard_widgets SET category = ?, updated_at = ? WHERE page_id = ? AND category = ? COLLATE NOCASE", (payload.name, iso_now(), payload.page_id, payload.old_name))
            connection.execute("UPDATE category_layouts SET name = ?, icon = ? WHERE page_id = ? AND name = ? COLLATE NOCASE", (payload.name, payload.icon, payload.page_id, payload.old_name))
        else:
            connection.execute("UPDATE category_layouts SET icon = ? WHERE page_id = ? AND name = ? COLLATE NOCASE", (payload.icon, payload.page_id, payload.old_name))
        row = connection.execute("SELECT * FROM category_layouts WHERE page_id = ? AND name = ? COLLATE NOCASE", (payload.page_id, payload.name)).fetchone()
    return row_to_category(row)


@app.patch("/api/categories/state", response_model=CategoryLayout)
def update_category_state(payload: CategoryStateUpdate, _: SessionUser = Depends(require_dashboard_edit)) -> CategoryLayout:
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
def reorder_categories(payload: CategoryReorder, _: SessionUser = Depends(require_dashboard_edit)) -> list[CategoryLayout]:
    if len(payload.ordered_names) != len(set(name.casefold() for name in payload.ordered_names)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate category names in reorder request")
    with db() as connection:
        require_page(connection, payload.page_id)
        ensure_category_layouts(connection)
        current = [
            row["category"]
            for row in connection.execute(
                """SELECT category FROM (
                       SELECT category FROM services WHERE page_id = ?
                       UNION ALL
                       SELECT category FROM dashboard_widgets WHERE page_id = ?
                   ) GROUP BY category COLLATE NOCASE ORDER BY category COLLATE NOCASE""",
                (payload.page_id, payload.page_id),
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
            SELECT c.page_id, c.name, c.sort_order, c.collapsed, c.icon
            FROM category_layouts c
            WHERE c.page_id = ? AND (EXISTS (
                SELECT 1 FROM services s WHERE s.page_id = c.page_id AND s.category = c.name COLLATE NOCASE
            ) OR EXISTS (
                SELECT 1 FROM dashboard_widgets w WHERE w.page_id = c.page_id AND w.category = c.name COLLATE NOCASE
            ))
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
def create_service(service: ServiceCreate, user: SessionUser = Depends(require_services_manage)) -> Service:
    validate_management_provider_id(service.management_provider)
    if not user.can("secrets:manage") and (
        service.api_key or service.auth_username or service.auth_password or service.clear_api_key
        or service.clear_auth_credentials or service.management_provider != "none"
        or service.management_target or service.management_controller_service_id or service.management_connection_id
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Editors cannot configure credentials or management providers")
    now = iso_now()
    with db() as connection:
        require_page(connection, service.page_id)
        ensure_category_layout(connection, service.page_id, service.category)
        cursor = connection.execute(
            """
            INSERT INTO services (name, type, url, category, page_id, icon, enabled, status_check, favorite, card_size, sort_order, api_key_encrypted, auth_username_encrypted, auth_password_encrypted, management_provider, management_target, management_controller_service_id, management_connection_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                int(connection.execute("""SELECT COALESCE(MAX(sort_order), 0) + 1 FROM (SELECT sort_order FROM services WHERE page_id = ? AND category = ? COLLATE NOCASE UNION ALL SELECT sort_order FROM dashboard_widgets WHERE page_id = ? AND category = ? COLLATE NOCASE)""", (service.page_id, service.category, service.page_id, service.category)).fetchone()[0]),
                encrypt_secret(service.api_key),
                encrypt_secret(service.auth_username),
                encrypt_secret(service.auth_password),
                service.management_provider,
                service.management_target,
                service.management_controller_service_id,
                service.management_connection_id,
                now,
                now,
            ),
        )
        row = connection.execute("SELECT * FROM services WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_service(row)


@app.put("/api/services/{service_id}", response_model=Service)
def update_service(service_id: int, service: ServiceUpdate, user: SessionUser = Depends(require_services_manage)) -> Service:
    validate_management_provider_id(service.management_provider)
    now = iso_now()
    with db() as connection:
        current = connection.execute("SELECT category, page_id, sort_order, api_key_encrypted, auth_username_encrypted, auth_password_encrypted, management_provider, management_target, management_controller_service_id, management_connection_id FROM services WHERE id = ?", (service_id,)).fetchone()
        if not current:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
        if not user.can("secrets:manage"):
            sensitive_change = bool(
                service.api_key or service.auth_username or service.auth_password
                or service.clear_api_key or service.clear_auth_credentials
                or service.management_provider != current["management_provider"]
                or service.management_target != current["management_target"]
                or service.management_controller_service_id != current["management_controller_service_id"]
                or service.management_connection_id != current["management_connection_id"]
            )
            if sensitive_change:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Editors cannot change credentials or management providers")
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
                """SELECT COALESCE(MAX(sort_order), 0) + 1 FROM (SELECT sort_order FROM services WHERE page_id = ? AND category = ? COLLATE NOCASE UNION ALL SELECT sort_order FROM dashboard_widgets WHERE page_id = ? AND category = ? COLLATE NOCASE)""",
                (service.page_id, service.category, service.page_id, service.category),
            ).fetchone()[0])
        connection.execute(
            """
            UPDATE services
            SET name = ?, type = ?, url = ?, category = ?, page_id = ?, icon = ?, enabled = ?, status_check = ?, favorite = ?, card_size = ?, sort_order = ?, api_key_encrypted = ?, auth_username_encrypted = ?, auth_password_encrypted = ?, management_provider = ?, management_target = ?, management_controller_service_id = ?, management_connection_id = ?, updated_at = ?
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
                service.management_connection_id,
                now,
                service_id,
            ),
        )
        if (service.management_provider != current["management_provider"] or service.management_target != current["management_target"] or service.management_controller_service_id != current["management_controller_service_id"] or service.management_connection_id != current["management_connection_id"]):
            connection.execute("DELETE FROM service_update_state WHERE service_id = ?", (service_id,))
        row = connection.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone()
    return row_to_service(row)


@app.patch("/api/services/{service_id}/layout", response_model=Service)
def update_service_layout(service_id: int, layout: ServiceLayoutUpdate, _: SessionUser = Depends(require_dashboard_edit)) -> Service:
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
def reorder_services(payload: ServiceReorder, _: SessionUser = Depends(require_dashboard_edit)) -> list[Service]:
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


@app.post("/api/dashboard-items/reorder")
def reorder_dashboard_items(payload: DashboardItemReorder, _: SessionUser = Depends(require_dashboard_edit)) -> dict[str, bool]:
    keys = [(item.kind, item.id) for item in payload.ordered_items]
    if len(keys) != len(set(keys)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate dashboard items in reorder request")
    with db() as connection:
        service_rows = connection.execute("SELECT id FROM services WHERE page_id = ? AND category = ? COLLATE NOCASE", (payload.page_id, payload.category)).fetchall()
        widget_rows = connection.execute("SELECT id FROM dashboard_widgets WHERE page_id = ? AND category = ? COLLATE NOCASE", (payload.page_id, payload.category)).fetchall()
        expected = {("service", int(row["id"])) for row in service_rows} | {("widget", int(row["id"])) for row in widget_rows}
        if set(keys) != expected:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dashboard reorder must include every service and widget in the category")
        now = iso_now()
        for position, item in enumerate(payload.ordered_items, start=1):
            table = "services" if item.kind == "service" else "dashboard_widgets"
            connection.execute(f"UPDATE {table} SET sort_order = ?, updated_at = ? WHERE id = ?", (position, now, item.id))
    return {"ok": True}


@app.delete("/api/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(service_id: int, _: SessionUser = Depends(require_services_manage)) -> Response:
    with db() as connection:
        cursor = connection.execute("DELETE FROM services WHERE id = ?", (service_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
