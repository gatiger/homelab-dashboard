from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import main


def point_data_dir(tmp_path: Path) -> None:
    main.DATA_DIR = tmp_path
    main.DB_PATH = tmp_path / "dashboard.db"
    main.SECRET_KEY_PATH = tmp_path / "secret.key"


class DummyThread:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def start(self):
        return None


def test_management_provider_registry_and_validation(tmp_path: Path, monkeypatch) -> None:
    point_data_dir(tmp_path)
    with TestClient(main.app) as client:
        auth = client.post("/api/auth/setup", json={"username": "owner", "password": "OwnerPass123!"}).json()
        csrf = auth["csrf_token"]
        assert "updates:host" in auth["permissions"]

        response = client.get("/api/management/providers")
        assert response.status_code == 200
        providers = {item["id"]: item for item in response.json()}
        assert {"docker_compose", "truenas_app", "truenas_system"} <= set(providers)
        assert "update" in providers["docker_compose"]["capabilities"]
        assert "update" in providers["truenas_app"]["capabilities"]
        assert "check" in providers["truenas_system"]["capabilities"]
        assert "update" in providers["truenas_system"]["capabilities"]
        assert providers["truenas_system"]["target_mode"] == "system"
        assert providers["truenas_system"]["update_scope"] == "host"
        assert providers["truenas_system"]["requires_reboot"] is True
        assert providers["truenas_system"]["bulk_eligible"] is False
        assert providers["truenas_system"]["requires_confirmation"] is True

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
        service_id = managed.json()["id"]

        # Save a deterministic available state before exercising the explicit host-update route.
        main.save_update_state(main.ServiceUpdateState(
            service_id=service_id,
            provider="truenas_system",
            target="system",
            state="available",
            current_version="25.10.1",
            latest_version="25.10.2",
            checked_at=main.iso_now(),
            message="Update available",
            can_update=True,
        ))

        blocked = client.post(f"/api/services/{service_id}/update", headers={"X-CSRF-Token": csrf})
        assert blocked.status_code == 400
        assert "host-update" in blocked.json()["detail"].lower()

        no_confirm = client.post(
            f"/api/services/{service_id}/host-update",
            headers={"X-CSRF-Token": csrf},
            json={"confirm": False},
        )
        assert no_confirm.status_code == 400

        monkeypatch.setattr(main.threading, "Thread", DummyThread)
        host_update = client.post(
            f"/api/services/{service_id}/host-update",
            headers={"X-CSRF-Token": csrf},
            json={"confirm": True},
        )
        assert host_update.status_code == 202, host_update.text
        assert host_update.json()["kind"] == "host_update"
        assert host_update.json()["latest_version"] == "25.10.2"

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
    assert main.management_provider_can_update("truenas_system") is True
    assert main.management_provider_bulk_eligible("truenas_system") is False
    assert main.management_provider_can_update("docker_compose") is True
    assert main.management_provider_bulk_eligible("docker_compose") is True


def test_host_update_restart_state_is_preserved_for_recovery(tmp_path: Path, monkeypatch) -> None:
    point_data_dir(tmp_path)
    main.init_db()

    host_job = main.create_update_job(
        "host_update", service_id=101, provider="truenas_system", target="system", message="Host update queued"
    )
    main.update_job(
        host_job.id,
        state="reconnecting",
        progress=90,
        current_version="25.10.1",
        latest_version="25.10.2",
        started_at=main.iso_now(),
    )
    normal_job = main.create_update_job(
        "update", service_id=102, provider="docker_compose", target="stack:service", message="Service update queued"
    )
    main.update_job(normal_job.id, state="running", progress=40, started_at=main.iso_now())

    # Simulate application startup against the same persistent database.
    main.init_db()

    with main.db() as connection:
        preserved = connection.execute("SELECT state, latest_version FROM update_jobs WHERE id = ?", (host_job.id,)).fetchone()
        interrupted = connection.execute("SELECT state, message FROM update_jobs WHERE id = ?", (normal_job.id,)).fetchone()

    assert preserved["state"] == "reconnecting"
    assert preserved["latest_version"] == "25.10.2"
    assert interrupted["state"] == "failed"
    assert "dashboard restart" in interrupted["message"].lower()

    started: list[tuple[object, tuple[object, ...]]] = []

    class CaptureThread:
        def __init__(self, *, target=None, args=(), **kwargs):
            self.target = target
            self.args = args

        def start(self):
            started.append((self.target, self.args))

    monkeypatch.setattr(main.threading, "Thread", CaptureThread)
    main.recover_host_update_jobs()

    assert len(started) == 1
    assert started[0][0] is main.resume_host_update_worker
    assert started[0][1] == (host_job.id, 101, "25.10.2")


def test_truenas_host_update_requests_reboot_then_verifies(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class FakeTrueNAS:
        def call(self, method: str, params=None):
            calls.append((method, params))
            if method == "update.status":
                return {"code": "NORMAL", "status": {"new_version": {"version": "25.10.2"}}}
            if method == "system.version_short":
                return "25.10.1"
            if method == "core.get_jobs":
                return [{"id": 77, "state": "SUCCESS", "progress": {"percent": 100, "description": "Done"}}]
            raise AssertionError(method)

        def start_job(self, method: str, params=None):
            calls.append((method, params))
            assert method == "update.run"
            return 77

    class FakeContext:
        def __enter__(self):
            return FakeTrueNAS()

        def __exit__(self, exc_type, exc, tb):
            return False

    reconnect: list[tuple[str, int, str | None]] = []
    monkeypatch.setattr(main, "truenas_client_for_managed_service", lambda service: FakeContext())
    monkeypatch.setattr(main, "update_job", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "wait_for_truenas_system_reconnect", lambda job_id, service_id, expected: reconnect.append((job_id, service_id, expected)))

    now = main.iso_now()
    service = main.Service(
        id=9,
        name="TrueNAS",
        type="truenas",
        url="https://truenas.local",
        category="Infrastructure",
        page_id=1,
        management_provider="truenas_system",
        management_target="system",
        management_connection_id=1,
        created_at=now,
        updated_at=now,
    )

    main.perform_truenas_system_update(service, "job-1")

    update_call = next(params for method, params in calls if method == "update.run")
    assert update_call == [{
        "dataset_name": None,
        "resume": False,
        "train": None,
        "version": "25.10.2",
        "reboot": True,
    }]
    assert reconnect == [("job-1", 9, "25.10.2")]


def test_truenas_rpc_start_job_captures_job_id_from_event(monkeypatch) -> None:
    sent: list[dict] = []

    class FakeSocket:
        def __init__(self):
            self.messages: list[str] = []

        def send(self, payload: str):
            message = main.json.loads(payload)
            sent.append(message)
            if message["method"] == "core.subscribe":
                self.messages.append(main.json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": "sub-1"}))
            elif message["method"] == "update.run":
                self.messages.append(main.json.dumps({
                    "jsonrpc": "2.0",
                    "method": "collection_update",
                    "params": {
                        "msg": "added",
                        "collection": "core.get_jobs",
                        "fields": {"id": 912, "message_ids": [message["id"]]},
                    },
                }))

        def recv(self):
            assert self.messages, "No fake websocket response queued"
            return self.messages.pop(0)

    rpc = main.TrueNASRPC.__new__(main.TrueNASRPC)
    rpc.ws = FakeSocket()
    rpc.sequence = 0

    job_id = rpc.start_job("update.run", [{"version": "25.10.2", "reboot": True}])

    assert job_id == 912
    assert [message["method"] for message in sent] == ["core.subscribe", "update.run"]
