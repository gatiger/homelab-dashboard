from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app import main


def point_data_dir(tmp_path: Path) -> None:
    main.DATA_DIR = tmp_path
    main.DB_PATH = tmp_path / "dashboard.db"
    main.SECRET_KEY_PATH = tmp_path / "secret.key"
    main._registry_cache = None


def setup_client(tmp_path: Path) -> tuple[TestClient, str]:
    point_data_dir(tmp_path)
    client = TestClient(main.app)
    client.__enter__()
    response = client.post("/api/auth/setup", json={"username": "admin", "password": "InitialPass123!"})
    assert response.status_code == 201
    return client, response.json()["csrf_token"]


def package(version: str) -> dict[str, object]:
    return {
        "format": "homelab-dashboard-extension",
        "schema_version": 1,
        "id": "community.registry-test",
        "name": "Registry Test Pack",
        "version": version,
        "author": "Registry Tester",
        "description": "Registry install/update fixture",
        "type": "page_template_pack",
        "min_dashboard_version": "0.17.0",
        "capabilities": ["page_templates"],
        "permissions": ["dashboard:register-templates"],
        "page_templates": [{"id": "registry-page", "name": "Registry Page", "services": [], "widgets": []}],
        "catalog_entries": [],
    }


def registry_for(raw_package: bytes, version: str) -> bytes:
    index = {
        "format": "homelab-dashboard-extension-registry",
        "schema_version": 1,
        "id": "test-registry",
        "name": "Test Registry",
        "description": "Unit test registry",
        "entries": [{
            "id": "community.registry-test",
            "name": "Registry Test Pack",
            "version": version,
            "author": "Registry Tester",
            "description": "Registry install/update fixture",
            "type": "page_template_pack",
            "min_dashboard_version": "0.17.0",
            "capabilities": ["page_templates"],
            "permissions": ["dashboard:register-templates"],
            "trust": "verified_community",
            "package": "packages/registry-test.json",
            "sha256": hashlib.sha256(raw_package).hexdigest(),
        }],
    }
    return json.dumps(index).encode()


def test_registry_lists_and_updates_an_installed_extension(tmp_path: Path, monkeypatch) -> None:
    client, csrf = setup_client(tmp_path)
    old_source = main.EXTENSION_REGISTRY_URL
    try:
        installed = client.post("/api/extensions/import", headers={"X-CSRF-Token": csrf}, json=package("1.0.0"))
        assert installed.status_code == 201

        next_package = json.dumps(package("1.1.0"), separators=(",", ":")).encode()
        registry_raw = registry_for(next_package, "1.1.0")
        main.EXTENSION_REGISTRY_URL = "https://registry.example/index.json"

        def fake_read(url: str, *, maximum: int) -> bytes:
            assert maximum > 0
            if url.endswith("index.json"):
                return registry_raw
            if url.endswith("packages/registry-test.json"):
                return next_package
            raise AssertionError(url)

        monkeypatch.setattr(main, "_read_limited_url", fake_read)
        main._registry_cache = None

        listing = client.get("/api/extensions/registry?refresh=true")
        assert listing.status_code == 200
        entry = listing.json()["entries"][0]
        assert entry["installed_version"] == "1.0.0"
        assert entry["update_available"] is True
        assert entry["trust"] == "verified_community"
        assert entry["compatible"] is True

        updated = client.post(
            "/api/extensions/registry/community.registry-test/install",
            headers={"X-CSRF-Token": csrf},
            json={
                "expected_version": "1.1.0",
                "expected_sha256": hashlib.sha256(next_package).hexdigest(),
                "accepted_permissions": ["dashboard:register-templates"],
            },
        )
        assert updated.status_code == 200
        assert updated.json()["version"] == "1.1.0"

        listing = client.get("/api/extensions/registry?refresh=true").json()["entries"][0]
        assert listing["installed_version"] == "1.1.0"
        assert listing["update_available"] is False
    finally:
        main.EXTENSION_REGISTRY_URL = old_source
        main._registry_cache = None
        client.__exit__(None, None, None)


def test_registry_install_requires_exact_permission_consent_and_checksum(tmp_path: Path, monkeypatch) -> None:
    client, csrf = setup_client(tmp_path)
    old_source = main.EXTENSION_REGISTRY_URL
    try:
        raw_package = json.dumps(package("1.0.0"), separators=(",", ":")).encode()
        registry_raw = registry_for(raw_package, "1.0.0")
        main.EXTENSION_REGISTRY_URL = "https://registry.example/index.json"

        monkeypatch.setattr(main, "_read_limited_url", lambda url, *, maximum: registry_raw if url.endswith("index.json") else raw_package)
        main._registry_cache = None
        entry = client.get("/api/extensions/registry?refresh=true").json()["entries"][0]

        refused = client.post(
            "/api/extensions/registry/community.registry-test/install",
            headers={"X-CSRF-Token": csrf},
            json={"expected_version": "1.0.0", "expected_sha256": entry["sha256"], "accepted_permissions": []},
        )
        assert refused.status_code == 400

        stale = client.post(
            "/api/extensions/registry/community.registry-test/install",
            headers={"X-CSRF-Token": csrf},
            json={"expected_version": "1.0.0", "expected_sha256": "0" * 64, "accepted_permissions": ["dashboard:register-templates"]},
        )
        assert stale.status_code == 409
    finally:
        main.EXTENSION_REGISTRY_URL = old_source
        main._registry_cache = None
        client.__exit__(None, None, None)
