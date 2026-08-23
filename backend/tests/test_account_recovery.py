from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app import main


def point_data_dir(tmp_path: Path) -> None:
    main.DATA_DIR = tmp_path
    main.DB_PATH = tmp_path / "dashboard.db"
    main.SECRET_KEY_PATH = tmp_path / "secret.key"


def test_password_change_recovery_rotation_and_session_invalidation(tmp_path: Path) -> None:
    point_data_dir(tmp_path)
    with TestClient(main.app) as primary:
        setup = primary.post("/api/auth/setup", json={"username": "admin", "password": "InitialPass123!"})
        assert setup.status_code == 201
        setup_data = setup.json()
        original_recovery = setup_data["recovery_code"]
        csrf = setup_data["csrf_token"]
        assert original_recovery.startswith("HD-")

        other = TestClient(main.app)
        assert other.post("/api/auth/login", json={"username": "admin", "password": "InitialPass123!"}).status_code == 200

        changed = primary.post(
            "/api/account/change-password",
            headers={"X-CSRF-Token": csrf},
            json={"current_password": "InitialPass123!", "new_password": "ChangedPass123!"},
        )
        assert changed.status_code == 204
        assert primary.get("/api/account").status_code == 200
        assert other.get("/api/account").status_code == 401

        rotated = primary.post(
            "/api/account/recovery-code",
            headers={"X-CSRF-Token": csrf},
            json={"current_password": "ChangedPass123!"},
        )
        assert rotated.status_code == 200
        next_recovery = rotated.json()["recovery_code"]
        assert next_recovery != original_recovery

        invalid_old = other.post(
            "/api/auth/recover",
            json={"username": "admin", "recovery_code": original_recovery, "new_password": "ShouldNotWork123!"},
        )
        assert invalid_old.status_code == 401

        primary.post("/api/auth/logout")
        recovered = primary.post(
            "/api/auth/recover",
            json={"username": "admin", "recovery_code": next_recovery, "new_password": "FinalPass123!"},
        )
        assert recovered.status_code == 200
        replacement_recovery = recovered.json()["recovery_code"]
        assert replacement_recovery != next_recovery
        assert primary.get("/api/account").status_code == 200

        account = primary.get("/api/account").json()
        events = {event["event"] for event in account["recent_events"]}
        assert "password_changed" in events
        assert "password_recovered" in events
        assert "recovery_code_rotated" in events

        assert other.post(
            "/api/auth/recover",
            json={"username": "admin", "recovery_code": next_recovery, "new_password": "StillInvalid123!"},
        ).status_code == 401


def test_v014_admin_schema_migrates_in_place(tmp_path: Path) -> None:
    point_data_dir(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(main.DB_PATH)
    connection.execute(
        "CREATE TABLE admin_users (id INTEGER PRIMARY KEY CHECK (id = 1), username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO admin_users VALUES (1, ?, ?, ?)",
        ("existing", main.hash_password("ExistingPass123!"), "2026-08-23T00:00:00+00:00"),
    )
    connection.commit()
    connection.close()

    main.init_db()

    connection = sqlite3.connect(main.DB_PATH)
    connection.row_factory = sqlite3.Row
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(admin_users)").fetchall()}
    row = connection.execute("SELECT * FROM admin_users WHERE id = 1").fetchone()
    migrated = connection.execute("SELECT * FROM dashboard_users WHERE id = 1").fetchone()
    assert row is not None
    assert row["username"] == "existing"
    assert migrated is not None
    assert migrated["username"] == "existing"
    assert migrated["role"] == "owner"
    assert bool(migrated["enabled"])
    assert {"recovery_code_hash", "recovery_generated_at", "password_changed_at"} <= columns
    assert connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='account_audit'").fetchone()
    connection.close()


def test_emergency_host_reset_rotates_credentials(tmp_path: Path, monkeypatch) -> None:
    point_data_dir(tmp_path)
    main.init_db()
    with main.db() as connection:
        now = main.iso_now()
        cursor = connection.execute(
            """INSERT INTO dashboard_users
               (username, password_hash, role, enabled, password_changed_at, created_at)
               VALUES (?, ?, 'owner', 1, ?, ?)""",
            ("admin", main.hash_password("OldPassword123!"), now, now),
        )
        user_id = int(cursor.lastrowid)
        old_recovery = main.rotate_recovery_code(connection, user_id).recovery_code
        main.create_session(connection, user_id)

    from app import admin

    answers = iter(["EmergencyPass123!", "EmergencyPass123!"])
    monkeypatch.setattr(admin.getpass, "getpass", lambda _prompt: next(answers))
    assert admin.reset_password() == 0

    with main.db() as connection:
        row = connection.execute("SELECT password_hash, recovery_code_hash FROM dashboard_users WHERE username = 'admin'").fetchone()
        assert main.verify_password("EmergencyPass123!", row["password_hash"])
        assert row["recovery_code_hash"] != main.recovery_code_digest(old_recovery)
        assert connection.execute("SELECT COUNT(*) FROM dashboard_sessions").fetchone()[0] == 0
        events = {row["event"] for row in connection.execute("SELECT event FROM account_audit").fetchall()}
        assert "emergency_password_reset" in events
