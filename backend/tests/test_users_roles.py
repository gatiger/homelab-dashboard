from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import main


def point_data_dir(tmp_path: Path) -> None:
    main.DATA_DIR = tmp_path
    main.DB_PATH = tmp_path / "dashboard.db"
    main.SECRET_KEY_PATH = tmp_path / "secret.key"


def login(client: TestClient, username: str, password: str) -> dict:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def test_owner_creates_users_and_roles_enforce_capabilities(tmp_path: Path) -> None:
    point_data_dir(tmp_path)
    with TestClient(main.app) as owner:
        setup = owner.post("/api/auth/setup", json={"username": "owner", "password": "OwnerPass123!"})
        assert setup.status_code == 201
        auth = setup.json()
        assert auth["role"] == "owner"
        assert "users:manage" in auth["permissions"]
        csrf = auth["csrf_token"]

        for username, role in [("viewer", "viewer"), ("editor", "editor"), ("admin", "admin")]:
            created = owner.post(
                "/api/users",
                headers={"X-CSRF-Token": csrf},
                json={"username": username, "password": f"{username.title()}Pass123!", "role": role},
            )
            assert created.status_code == 201, created.text
            assert created.json()["role"] == role

        users = owner.get("/api/users")
        assert users.status_code == 200
        assert {item["username"] for item in users.json()} == {"owner", "viewer", "editor", "admin"}

        # A single enabled owner cannot demote itself.
        owner_id = next(item["id"] for item in users.json() if item["username"] == "owner")
        cannot_demote = owner.put(
            f"/api/users/{owner_id}",
            headers={"X-CSRF-Token": csrf},
            json={"role": "admin", "enabled": True},
        )
        assert cannot_demote.status_code == 409

    with TestClient(main.app) as viewer:
        viewer_auth = login(viewer, "viewer", "ViewerPass123!")
        assert viewer_auth["role"] == "viewer"
        assert viewer.get("/api/services").status_code == 200
        assert viewer.get("/api/users").status_code == 403
        denied = viewer.post(
            "/api/widgets",
            headers={"X-CSRF-Token": viewer_auth["csrf_token"]},
            json={"type": "note", "title": "Nope", "page_id": 1, "category": "Widgets", "card_size": "standard", "enabled": True, "config": {"text": "x"}},
        )
        assert denied.status_code == 403

    with TestClient(main.app) as editor:
        editor_auth = login(editor, "editor", "EditorPass123!")
        csrf = editor_auth["csrf_token"]
        created = editor.post(
            "/api/services",
            headers={"X-CSRF-Token": csrf},
            json={"name": "Editable link", "type": "link", "url": "http://example.local", "category": "General", "page_id": 1},
        )
        assert created.status_code == 201, created.text
        secret_denied = editor.post(
            "/api/services",
            headers={"X-CSRF-Token": csrf},
            json={"name": "Secret link", "type": "sonarr", "url": "http://sonarr.local", "category": "General", "page_id": 1, "api_key": "secret"},
        )
        assert secret_denied.status_code == 403
        assert editor.post("/api/updates/check", headers={"X-CSRF-Token": csrf}).status_code == 403

    with TestClient(main.app) as admin:
        admin_auth = login(admin, "admin", "AdminPass123!")
        csrf = admin_auth["csrf_token"]
        assert "users:manage" not in admin_auth["permissions"]
        settings = admin.get("/api/settings").json()
        settings["dashboard_title"] = "Admin changed this"
        assert admin.put("/api/settings", headers={"X-CSRF-Token": csrf}, json=settings).status_code == 200
        assert admin.get("/api/users").status_code == 403


def test_disabling_user_invalidates_sessions(tmp_path: Path) -> None:
    point_data_dir(tmp_path)
    with TestClient(main.app) as owner:
        setup = owner.post("/api/auth/setup", json={"username": "owner", "password": "OwnerPass123!"}).json()
        csrf = setup["csrf_token"]
        created = owner.post(
            "/api/users",
            headers={"X-CSRF-Token": csrf},
            json={"username": "guest", "password": "GuestPass123!", "role": "viewer"},
        ).json()

        guest = TestClient(main.app)
        assert login(guest, "guest", "GuestPass123!")["authenticated"] is True
        assert guest.get("/api/services").status_code == 200

        disabled = owner.put(
            f"/api/users/{created['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"role": "viewer", "enabled": False},
        )
        assert disabled.status_code == 200
        assert guest.get("/api/services").status_code == 401
        assert guest.post("/api/auth/login", json={"username": "guest", "password": "GuestPass123!"}).status_code == 401


def test_legacy_admin_and_session_migrate_to_owner(tmp_path: Path) -> None:
    point_data_dir(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    import sqlite3
    from datetime import timedelta

    connection = sqlite3.connect(main.DB_PATH)
    connection.execute(
        "CREATE TABLE admin_users (id INTEGER PRIMARY KEY CHECK (id = 1), username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, recovery_code_hash TEXT, recovery_generated_at TEXT, password_changed_at TEXT, created_at TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, csrf_token TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    now = main.utcnow()
    connection.execute(
        "INSERT INTO admin_users VALUES (1, ?, ?, NULL, NULL, ?, ?)",
        ("legacy", main.hash_password("LegacyPass123!"), now.isoformat(), now.isoformat()),
    )
    raw_token = "legacy-session-token"
    connection.execute(
        "INSERT INTO sessions VALUES (?, 1, ?, ?, ?)",
        (main.token_digest(raw_token), "legacy-csrf", (now + timedelta(hours=4)).isoformat(), now.isoformat()),
    )
    connection.commit()
    connection.close()

    main.init_db()

    with main.db() as migrated:
        user = migrated.execute("SELECT * FROM dashboard_users WHERE username = 'legacy'").fetchone()
        assert user is not None
        assert user["role"] == "owner"
        assert migrated.execute("SELECT COUNT(*) FROM dashboard_sessions").fetchone()[0] == 1

    session = main.get_session(raw_token)
    assert session is not None
    assert session.username == "legacy"
    assert session.role == "owner"
    assert "users:manage" in session.permissions


def test_legacy_sessions_are_not_reimported_after_migration(tmp_path: Path) -> None:
    point_data_dir(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    import sqlite3
    from datetime import timedelta

    connection = sqlite3.connect(main.DB_PATH)
    connection.execute(
        "CREATE TABLE admin_users (id INTEGER PRIMARY KEY CHECK (id = 1), username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, recovery_code_hash TEXT, recovery_generated_at TEXT, password_changed_at TEXT, created_at TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, csrf_token TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    now = main.utcnow()
    connection.execute(
        "INSERT INTO admin_users VALUES (1, ?, ?, NULL, NULL, ?, ?)",
        ("legacy", main.hash_password("LegacyPass123!"), now.isoformat(), now.isoformat()),
    )
    connection.execute(
        "INSERT INTO sessions VALUES (?, 1, ?, ?, ?)",
        (main.token_digest("old-token"), "csrf", (now + timedelta(hours=4)).isoformat(), now.isoformat()),
    )
    connection.commit(); connection.close()

    main.init_db()
    with main.db() as migrated:
        assert migrated.execute("SELECT COUNT(*) FROM dashboard_sessions").fetchone()[0] == 1
        migrated.execute("DELETE FROM dashboard_sessions")

    main.init_db()
    with main.db() as migrated:
        assert migrated.execute("SELECT COUNT(*) FROM dashboard_sessions").fetchone()[0] == 0
        assert migrated.execute("SELECT 1 FROM app_settings WHERE key = 'auth_v18_migrated'").fetchone()
