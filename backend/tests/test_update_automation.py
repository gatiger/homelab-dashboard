from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app import main


def point_data_dir(tmp_path: Path) -> None:
    main.DATA_DIR = tmp_path
    main.DB_PATH = tmp_path / "dashboard.db"
    main.SECRET_KEY_PATH = tmp_path / "secret.key"


def create_managed_service(client: TestClient, csrf: str, *, name: str = "Lidarr", policy: str = "scheduled") -> dict:
    response = client.post(
        "/api/services",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": name,
            "type": name.lower(),
            "url": f"http://{name.lower()}.local",
            "category": "Media",
            "page_id": 1,
            "management_provider": "docker_compose",
            "management_target": f"arr-stack/{name.lower()}",
            "update_policy": policy,
            "update_release_delay_days": None,
            "update_rollback_policy": "inherit",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_maintenance_window_supports_overnight_windows() -> None:
    settings = main.DashboardSettings(
        scheduled_updates_enabled=True,
        update_maintenance_days=[6],  # Sunday
        update_maintenance_start="22:00",
        update_maintenance_end="02:00",
    )
    sunday = datetime(2026, 8, 23, 23, 30, tzinfo=timezone.utc)
    monday = datetime(2026, 8, 24, 1, 15, tzinfo=timezone.utc)
    after = datetime(2026, 8, 24, 3, 0, tzinfo=timezone.utc)

    assert main.maintenance_window_key(settings, sunday) == "2026-08-23@22:00"
    assert main.maintenance_window_key(settings, monday) == "2026-08-23@22:00"
    assert main.maintenance_window_key(settings, after) is None


def test_available_since_is_preserved_for_same_release(tmp_path: Path) -> None:
    point_data_dir(tmp_path)
    main.init_db()
    with main.db() as connection:
        now = main.iso_now()
        cursor = connection.execute(
            """INSERT INTO services (name,type,url,category,page_id,management_provider,management_target,created_at,updated_at)
               VALUES ('Test','link','http://test.local','General',1,'docker_compose','stack/test',?,?)""",
            (now, now),
        )
        service_id = int(cursor.lastrowid)

    first = "2026-08-20T12:00:00+00:00"
    second = "2026-08-21T12:00:00+00:00"
    main.save_update_state(main.ServiceUpdateState(
        service_id=service_id, provider="docker_compose", target="stack/test", state="available",
        current_version="1", latest_version="2", checked_at=first,
    ))
    # The transient checking state must not restart the release-age clock.
    main.save_update_state(main.ServiceUpdateState(
        service_id=service_id, provider="docker_compose", target="stack/test", state="checking",
        checked_at=second,
    ))
    main.save_update_state(main.ServiceUpdateState(
        service_id=service_id, provider="docker_compose", target="stack/test", state="available",
        current_version="1", latest_version="2", checked_at=second,
    ))
    with main.db() as connection:
        row = connection.execute("SELECT available_since FROM service_update_state WHERE service_id=?", (service_id,)).fetchone()
    assert row["available_since"] == first

    main.save_update_state(main.ServiceUpdateState(
        service_id=service_id, provider="docker_compose", target="stack/test", state="current",
        current_version="2", latest_version="2", checked_at=second,
    ))
    with main.db() as connection:
        row = connection.execute("SELECT available_since FROM service_update_state WHERE service_id=?", (service_id,)).fetchone()
    assert row["available_since"] is None


def test_scheduled_selection_respects_policy_and_release_delay(tmp_path: Path) -> None:
    point_data_dir(tmp_path)
    with TestClient(main.app) as client:
        auth = client.post("/api/auth/setup", json={"username": "owner", "password": "OwnerPass123!"}).json()
        csrf = auth["csrf_token"]
        scheduled = create_managed_service(client, csrf, name="Lidarr", policy="scheduled")
        manual = create_managed_service(client, csrf, name="Tdarr", policy="manual")

        old = (main.utcnow() - timedelta(days=4)).isoformat()
        for service in (scheduled, manual):
            main.save_update_state(main.ServiceUpdateState(
                service_id=service["id"], provider="docker_compose", target=service["management_target"],
                state="available", current_version="1", latest_version="2", checked_at=old, available_since=old,
            ))

        settings = main.DashboardSettings(scheduled_updates_enabled=True, update_release_delay_days=3)
        assert main.scheduled_service_ids(settings) == [scheduled["id"]]


def test_monitor_only_blocks_manual_update(tmp_path: Path, monkeypatch) -> None:
    point_data_dir(tmp_path)
    with TestClient(main.app) as client:
        auth = client.post("/api/auth/setup", json={"username": "owner", "password": "OwnerPass123!"}).json()
        csrf = auth["csrf_token"]
        service = create_managed_service(client, csrf, name="Bazarr", policy="monitor_only")
        main.save_update_state(main.ServiceUpdateState(
            service_id=service["id"], provider="docker_compose", target=service["management_target"],
            state="available", current_version="1", latest_version="2", checked_at=main.iso_now(),
        ))
        states = client.get("/api/updates/status").json()
        state = next(item for item in states if item["service_id"] == service["id"])
        assert state["can_update"] is False
        response = client.post(f"/api/services/{service['id']}/update", headers={"X-CSRF-Token": csrf})
        assert response.status_code == 400
        assert "monitoring only" in response.json()["detail"].lower()


def test_docker_post_update_verification_can_trigger_rollback(tmp_path: Path, monkeypatch) -> None:
    point_data_dir(tmp_path)
    main.init_db()
    now = main.iso_now()
    with main.db() as connection:
        cursor = connection.execute(
            """INSERT INTO services (name,type,url,category,page_id,management_provider,management_target,update_policy,update_rollback_policy,created_at,updated_at)
               VALUES ('Sonarr','sonarr','http://sonarr.local','Media',1,'docker_compose','arr-stack/sonarr','manual','automatic',?,?)""",
            (now, now),
        )
        service_id = int(cursor.lastrowid)

    monkeypatch.setattr(main, "capture_service_health_baseline", lambda service_id: main.HealthBaseline(status_state="online", integration_state=None))
    monkeypatch.setattr(main, "verify_service_health", lambda service_id, baseline: (False, "HTTP status: offline"))
    monkeypatch.setitem(
        main.MANAGEMENT_UPDATE_PERFORMERS,
        "docker_compose",
        lambda service, job_id, start, end: main.ProviderUpdateResult("1.0", "2.0", "verification_pending", "agent-1"),
    )
    calls: list[tuple[str, str, dict | None]] = []

    def fake_agent(path: str, method: str = "GET", payload: dict | None = None, timeout: float = 30):
        calls.append((path, method, payload))
        if path.endswith("/rollback"):
            return {"state": "rolled_back", "detail": "restored"}
        raise AssertionError(path)

    monkeypatch.setattr(main, "agent_request", fake_agent)
    job = main.create_update_job("update", service_id=service_id, provider="docker_compose", target="arr-stack/sonarr")
    assert main.perform_service_update(service_id, job.id) == "rolled_back"
    assert calls[0][0] == "/v1/jobs/agent-1/rollback"


def test_provider_registry_exposes_rollback_modes() -> None:
    assert main.MANAGEMENT_PROVIDERS["docker_compose"].rollback_mode == "automatic"
    assert main.MANAGEMENT_PROVIDERS["truenas_system"].rollback_mode == "manual"
    assert main.MANAGEMENT_PROVIDERS["truenas_app"].rollback_mode == "none"


def test_host_recovery_snapshot_tracks_previously_online_services(tmp_path: Path, monkeypatch) -> None:
    point_data_dir(tmp_path)
    main.init_db()
    now = main.iso_now()
    with main.db() as connection:
        host_id = int(connection.execute(
            """INSERT INTO services (name,type,url,category,page_id,management_provider,management_target,created_at,updated_at)
               VALUES ('TrueNAS','truenas','https://truenas.local','Infrastructure',1,'truenas_system','system',?,?)""",
            (now, now),
        ).lastrowid)
        sonarr_id = int(connection.execute(
            """INSERT INTO services (name,type,url,category,page_id,created_at,updated_at)
               VALUES ('Sonarr','sonarr','http://sonarr.local','Media',1,?,?)""",
            (now, now),
        ).lastrowid)
        radarr_id = int(connection.execute(
            """INSERT INTO services (name,type,url,category,page_id,created_at,updated_at)
               VALUES ('Radarr','radarr','http://radarr.local','Media',1,?,?)""",
            (now, now),
        ).lastrowid)

    monkeypatch.setattr(
        main,
        "probe_service",
        lambda service: main.ServiceStatus(id=service.id, state="online", checked_at=main.iso_now()),
    )
    snapshot = main.capture_host_recovery_snapshot(host_id)
    assert {item["id"] for item in snapshot} == {sonarr_id, radarr_id}

    job = main.create_update_job("host_update", service_id=host_id, provider="truenas_system", target="system")
    main.update_job(job.id, recovery_snapshot_json=main.json.dumps(snapshot))

    def post_reboot_probe(service):
        state = "online" if service.id == sonarr_id else "offline"
        return main.ServiceStatus(id=service.id, state=state, checked_at=main.iso_now())

    monkeypatch.setattr(main, "probe_service", post_reboot_probe)
    times = iter([0.0, 0.0, 999.0])
    monkeypatch.setattr(main.time, "time", lambda: next(times, 999.0))
    monkeypatch.setattr(main.time, "sleep", lambda _seconds: None)

    recovered, missing = main.verify_host_recovery_services(job.id)
    assert recovered == ["Sonarr"]
    assert missing == ["Radarr"]
