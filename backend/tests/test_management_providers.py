from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import main


def point_data_dir(tmp_path: Path) -> None:
    main.DATA_DIR = tmp_path
    main.DB_PATH = tmp_path / "dashboard.db"
    main.SECRET_KEY_PATH = tmp_path / "secret.key"


def test_management_provider_registry_and_validation(tmp_path: Path, monkeypatch) -> None:
    point_data_dir(tmp_path)
    with TestClient(main.app) as client:
        auth = client.post("/api/auth/setup", json={"username": "owner", "password": "OwnerPass123!"}).json()
        csrf = auth["csrf_token"]

        response = client.get("/api/management/providers")
        assert response.status_code == 200
        providers = {item["id"]: item for item in response.json()}
        assert {"docker_compose", "truenas_app", "truenas_system"} <= set(providers)
        assert "update" in providers["docker_compose"]["capabilities"]
        assert "update" in providers["truenas_app"]["capabilities"]
        assert "check" in providers["truenas_system"]["capabilities"]
        assert "update" not in providers["truenas_system"]["capabilities"]
        assert providers["truenas_system"]["target_mode"] == "system"

        connection = client.post(
            "/api/connections",
            headers={"X-CSRF-Token": csrf},
            json={"name": "Test TrueNAS", "type": "truenas", "url": "https://truenas.local", "api_key": "test-api-key"},
        )
        assert connection.status_code == 201, connection.text

        class FakeTrueNAS:
            def call(self, method: str, params=None):
                if method == "update.status":
                    return {"code": "NORMAL", "status": {"new_version": {"version": "25.10.2"}}}
                if method == "system.version_short":
                    return "25.10.1"
                raise AssertionError(method)

        class FakeContext:
            def __enter__(self):
                return FakeTrueNAS()

            def __exit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr(main, "truenas_client_from_connection_row", lambda row: FakeContext())
        resources = client.get(f"/api/management/providers/truenas_system/resources?connection_id={connection.json()['id']}")
        assert resources.status_code == 200, resources.text
        assert resources.json()[0]["id"] == "system"
        assert resources.json()[0]["current_version"] == "25.10.1"
        assert resources.json()[0]["latest_version"] == "25.10.2"
        assert resources.json()[0]["update_available"] is True

        managed = client.post(
            "/api/services",
            headers={"X-CSRF-Token": csrf},
            json={
                "name": "TrueNAS",
                "type": "truenas",
                "url": "https://truenas.local",
                "category": "Infrastructure",
                "page_id": 1,
                "management_provider": "truenas_system",
                "management_target": "system",
                "management_connection_id": connection.json()["id"],
            },
        )
        assert managed.status_code == 201, managed.text
        blocked = client.post(f"/api/services/{managed.json()['id']}/update", headers={"X-CSRF-Token": csrf})
        assert blocked.status_code == 400
        assert "detection only" in blocked.json()["detail"].lower()

        rejected = client.post(
            "/api/services",
            headers={"X-CSRF-Token": csrf},
            json={
                "name": "Unknown manager",
                "type": "link",
                "url": "https://example.local",
                "category": "General",
                "page_id": 1,
                "management_provider": "unknown_provider",
            },
        )
        assert rejected.status_code == 422


def test_truenas_system_status_parser_and_capability_gate() -> None:
    class FakeTrueNAS:
        def call(self, method: str, params=None):
            if method == "update.status":
                return {
                    "code": "NORMAL",
                    "status": {
                        "new_version": {
                            "version": "25.10.2",
                            "release_notes_url": "https://example.invalid/release-notes",
                        }
                    },
                }
            if method == "system.version_short":
                return "25.10.1"
            raise AssertionError(method)

    current, latest, available, notes = main.truenas_system_update_status(FakeTrueNAS())
    assert current == "25.10.1"
    assert latest == "25.10.2"
    assert available is True
    assert notes == "https://example.invalid/release-notes"
    assert main.management_provider_can_update("truenas_system") is False
    assert main.management_provider_can_update("docker_compose") is True
