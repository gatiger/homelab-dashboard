from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import main


def point_data_dir(tmp_path: Path) -> None:
    main.DATA_DIR = tmp_path
    main.DB_PATH = tmp_path / "dashboard.db"
    main.SECRET_KEY_PATH = tmp_path / "secret.key"


def setup_client(tmp_path: Path) -> tuple[TestClient, str]:
    point_data_dir(tmp_path)
    client = TestClient(main.app)
    client.__enter__()
    response = client.post("/api/auth/setup", json={"username": "admin", "password": "InitialPass123!"})
    assert response.status_code == 201
    return client, response.json()["csrf_token"]


def test_data_extension_install_toggle_and_template_instantiation(tmp_path: Path) -> None:
    client, csrf = setup_client(tmp_path)
    try:
        package = {
            "format": "homelab-dashboard-extension",
            "schema_version": 1,
            "id": "community.lab-pack",
            "name": "Lab Pack",
            "version": "1.0.0",
            "author": "Community Tester",
            "description": "Safe data-only extension test",
            "type": "bundle",
            "min_dashboard_version": "0.16.0",
            "capabilities": ["page_templates", "service_catalog"],
            "permissions": ["dashboard:register-templates", "catalog:register-entries"],
            "page_templates": [
                {
                    "id": "lab-start",
                    "name": "Lab Start",
                    "description": "Starter lab page",
                    "categories": [{"name": "Lab", "sort_order": 1, "icon": "server"}],
                    "services": [],
                    "widgets": [{"type": "note", "title": "Lab Notes", "category": "Lab", "config": {"text": "hello"}}],
                }
            ],
            "catalog_entries": [
                {
                    "type": "community-app",
                    "name": "Community App",
                    "category": "Custom",
                    "description": "A community catalog definition",
                    "defaultPort": 4321,
                    "defaultScheme": "http",
                    "aliases": ["community"],
                }
            ],
        }
        installed = client.post("/api/extensions/import", headers={"X-CSRF-Token": csrf}, json=package)
        assert installed.status_code == 201
        assert installed.json()["enabled"] is True
        assert installed.json()["permissions"] == ["dashboard:register-templates", "catalog:register-entries"]

        catalog = client.get("/api/catalog/extensions")
        assert catalog.status_code == 200
        assert [entry["type"] for entry in catalog.json()] == ["community-app"]

        templates = client.get("/api/page-templates")
        assert templates.status_code == 200
        assert any(item["extension_id"] == "community.lab-pack" and item["template_id"] == "lab-start" for item in templates.json())

        created = client.post(
            "/api/page-templates/community.lab-pack/lab-start/instantiate",
            headers={"X-CSRF-Token": csrf},
            json={"name": "My Lab"},
        )
        assert created.status_code == 201
        page_id = created.json()["id"]
        widgets = client.get("/api/widgets").json()
        assert any(widget["page_id"] == page_id and widget["title"] == "Lab Notes" for widget in widgets)

        disabled = client.patch(
            "/api/extensions/community.lab-pack",
            headers={"X-CSRF-Token": csrf},
            json={"enabled": False},
        )
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False
        assert client.get("/api/catalog/extensions").json() == []
        assert not any(item["extension_id"] == "community.lab-pack" for item in client.get("/api/page-templates").json())

        # Content created from an extension is deliberately not deleted when the package is disabled/removed.
        assert any(widget["page_id"] == page_id for widget in client.get("/api/widgets").json())
    finally:
        client.__exit__(None, None, None)


def test_page_template_export_excludes_service_secrets_and_management_links(tmp_path: Path) -> None:
    client, csrf = setup_client(tmp_path)
    try:
        created = client.post("/api/pages", headers={"X-CSRF-Token": csrf}, json={"name": "Share Me"})
        assert created.status_code == 201
        page_id = created.json()["id"]
        with main.db() as connection:
            now = main.iso_now()
            connection.execute(
                """INSERT INTO services
                   (name,type,url,category,page_id,icon,enabled,status_check,favorite,card_size,sort_order,
                    api_key_encrypted,auth_username_encrypted,auth_password_encrypted,management_provider,management_target,
                    management_connection_id,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "Secret Service", "link", "https://service.local", "General", page_id, None, 1, 1, 0, "standard", 1,
                    main.encrypt_secret("api-secret"), main.encrypt_secret("user"), main.encrypt_secret("password"),
                    "truenas_app", "secret-target", 999, now, now,
                ),
            )

        response = client.get(f"/api/pages/{page_id}/template-package")
        assert response.status_code == 200
        payload = response.json()
        raw = response.text
        assert payload["format"] == "homelab-dashboard-extension"
        assert payload["type"] == "page_template_pack"
        assert payload["permissions"] == ["dashboard:register-templates"]
        assert "api-secret" not in raw
        assert "secret-target" not in raw
        service = payload["page_templates"][0]["services"][0]
        assert set(service) <= {"name", "type", "url", "category", "icon", "enabled", "status_check", "favorite", "card_size", "sort_order"}
        assert not ({"api_key", "api_key_encrypted", "auth_username", "auth_password", "management_provider", "management_target", "management_connection_id"} & set(service))
    finally:
        client.__exit__(None, None, None)


def test_extension_rejects_dangerous_or_unknown_permissions(tmp_path: Path) -> None:
    client, csrf = setup_client(tmp_path)
    try:
        package = {
            "format": "homelab-dashboard-extension",
            "schema_version": 1,
            "id": "community.bad-pack",
            "name": "Bad Pack",
            "version": "1.0.0",
            "author": "Tester",
            "description": "Should be rejected",
            "type": "page_template_pack",
            "min_dashboard_version": "0.16.0",
            "capabilities": ["page_templates"],
            "permissions": ["docker:write"],
            "page_templates": [{"id": "bad", "name": "Bad", "services": [], "widgets": []}],
        }
        response = client.post("/api/extensions/import", headers={"X-CSRF-Token": csrf}, json=package)
        assert response.status_code == 422

        package["permissions"] = ["dashboard:register-templates"]
        package["script"] = "fetch('/api/secrets')"
        response = client.post("/api/extensions/import", headers={"X-CSRF-Token": csrf}, json=package)
        assert response.status_code == 422
    finally:
        client.__exit__(None, None, None)


def test_v015_database_adds_extension_table_without_touching_dashboard_content(tmp_path: Path) -> None:
    point_data_dir(tmp_path)
    main.init_db()
    with main.db() as connection:
        connection.execute("DROP TABLE installed_extensions")
        now = main.iso_now()
        connection.execute(
            "INSERT INTO services (name,type,url,category,page_id,enabled,status_check,favorite,card_size,sort_order,management_provider,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("Existing Service", "link", "https://existing.local", "General", 1, 1, 1, 0, "standard", 1, "none", now, now),
        )

    main.init_db()

    with main.db() as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='installed_extensions'").fetchone()
        row = connection.execute("SELECT name,url FROM services WHERE name='Existing Service'").fetchone()
        assert row is not None
        assert row["url"] == "https://existing.local"
