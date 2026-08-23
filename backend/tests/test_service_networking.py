from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import main


def point_data_dir(tmp_path: Path) -> None:
    main.DATA_DIR = tmp_path
    main.DB_PATH = tmp_path / "dashboard.db"
    main.SECRET_KEY_PATH = tmp_path / "secret.key"


def service(now: str, **overrides) -> main.Service:
    values = {
        "id": 1,
        "name": "Sonarr",
        "type": "sonarr",
        "url": "https://sonarr.example.test/",
        "internal_url": None,
        "category": "Media",
        "page_id": 1,
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return main.Service(**values)


def test_internal_url_is_persisted_without_changing_browser_url(tmp_path: Path) -> None:
    point_data_dir(tmp_path)
    with TestClient(main.app) as client:
        auth = client.post("/api/auth/setup", json={"username": "owner", "password": "OwnerPass123!"}).json()
        response = client.post(
            "/api/services",
            headers={"X-CSRF-Token": auth["csrf_token"]},
            json={
                "name": "Sonarr",
                "type": "sonarr",
                "url": "https://sonarr.example.test/",
                "internal_url": "http://192.168.1.20:8989/",
                "category": "Media",
                "page_id": 1,
            },
        )
        assert response.status_code == 201, response.text
        saved = response.json()
        assert saved["url"] == "https://sonarr.example.test/"
        assert saved["internal_url"] == "http://192.168.1.20:8989/"

        with main.db() as connection:
            stored = connection.execute("SELECT url, internal_url FROM services WHERE id = ?", (saved["id"],)).fetchone()
        assert stored["url"] == "https://sonarr.example.test/"
        assert stored["internal_url"] == "http://192.168.1.20:8989/"


def test_probe_prefers_internal_url_and_falls_back_to_browser_url(monkeypatch) -> None:
    captured: list[str] = []

    def fake_probe(url: str, method: str, verify_tls: bool = True):
        captured.append(url)
        return 200, 5

    monkeypatch.setattr(main, "perform_probe", fake_probe)
    now = main.iso_now()

    internal = service(now, internal_url="http://192.168.1.20:8989/")
    result = main.probe_service(internal)
    assert result.state == "online"
    assert captured[-1] == "http://192.168.1.20:8989/"

    fallback = service(now, id=2, internal_url=None)
    result = main.probe_service(fallback)
    assert result.state == "online"
    assert captured[-1] == "https://sonarr.example.test/"


def test_rich_integration_requests_use_internal_url(monkeypatch) -> None:
    requested: list[str] = []

    def fake_request(url: str, headers=None, method="GET", data=None):
        requested.append(url)
        return b'{}', {}

    monkeypatch.setattr(main, "request_raw_local_retry", fake_request)
    now = main.iso_now()
    target = service(now, internal_url="http://sonarr:8989/")

    assert main.service_json(target, "/api/v3/system/status") == {}
    assert requested == ["http://sonarr:8989/api/v3/system/status"]
