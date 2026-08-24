from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


AGENT_PATH = Path(__file__).resolve().parents[2] / "agent" / "app.py"
spec = importlib.util.spec_from_file_location("homelab_update_agent", AGENT_PATH)
assert spec and spec.loader
agent = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = agent
spec.loader.exec_module(agent)


def reset_agent() -> None:
    with agent.JOBS_LOCK:
        agent.JOBS.clear()
        agent.ROLLBACK_CONTEXTS.clear()


def test_commit_releases_rollback_snapshot(monkeypatch) -> None:
    reset_agent()
    job = agent.UpdateJob(
        id="job1",
        resource_id="stack/service",
        state="verification_pending",
        progress=95,
        stage="Awaiting Dashboard verification",
        rollback_available=True,
    )
    with agent.JOBS_LOCK:
        agent.JOBS[job.id] = job
        agent.ROLLBACK_CONTEXTS[job.id] = {"rollback_tag": "rollback:test"}
    removed: list[tuple[str, ...]] = []
    monkeypatch.setattr(agent, "run_best_effort", lambda *args, **kwargs: removed.append(tuple(args)))

    result = agent.commit_update(job.id)

    assert result.state == "success"
    assert result.rollback_available is False
    assert job.id not in agent.ROLLBACK_CONTEXTS
    assert removed == [("docker", "image", "rm", "rollback:test")]


def test_explicit_rollback_restores_previous_image(monkeypatch) -> None:
    reset_agent()
    job = agent.UpdateJob(
        id="job2",
        resource_id="stack/service",
        state="verification_pending",
        progress=95,
        stage="Awaiting Dashboard verification",
        rollback_available=True,
    )
    resource = agent.Resource(
        id="stack/service",
        project="stack",
        service="service",
        image="example/service:latest",
        container_names=["service"],
        working_dir="/stacks/stack",
        config_files=["/stacks/stack/compose.yaml"],
    )
    with agent.JOBS_LOCK:
        agent.JOBS[job.id] = job
        agent.ROLLBACK_CONTEXTS[job.id] = {
            "resource_id": resource.id,
            "old_image_id": "sha256:old",
            "old_version": "1.0",
            "new_version": "2.0",
            "image_ref": resource.image,
            "rollback_tag": "rollback:test",
        }
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(agent, "get_resource", lambda resource_id: resource)
    monkeypatch.setattr(agent, "compose_args", lambda resource: ["docker", "compose"])
    monkeypatch.setattr(agent, "run", lambda *args, **kwargs: calls.append(tuple(args)) or "")
    monkeypatch.setattr(agent, "run_best_effort", lambda *args, **kwargs: calls.append(tuple(args)))
    monkeypatch.setattr(agent, "wait_for_health", lambda resource: (True, "service: running"))

    result = agent.rollback_update(job.id, "HTTP status: offline")

    assert result.state == "rolled_back"
    assert result.latest_version == "1.0"
    assert result.rollback_available is False
    assert ("docker", "image", "tag", "sha256:old", "example/service:latest") in calls
    assert ("docker", "compose", "up", "-d", "--no-deps", "--force-recreate", "service") in calls
