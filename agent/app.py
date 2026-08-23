from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

AGENT_TOKEN = os.getenv("UPDATE_AGENT_TOKEN", "").strip()
STACKS_ROOT_RAW = os.getenv("UPDATE_AGENT_STACKS_ROOT", "").strip()
STACKS_ROOT = Path(STACKS_ROOT_RAW).resolve() if STACKS_ROOT_RAW else None
COMMAND_TIMEOUT = max(30, min(int(os.getenv("UPDATE_AGENT_COMMAND_TIMEOUT", "900")), 3600))
HEALTH_TIMEOUT = max(15, min(int(os.getenv("UPDATE_AGENT_HEALTH_TIMEOUT", "120")), 900))

app = FastAPI(title="Homelab Dashboard Update Agent", version="0.16.0")


class Resource(BaseModel):
    id: str
    project: str
    service: str
    image: str
    container_names: list[str] = Field(default_factory=list)
    working_dir: str
    config_files: list[str]


class ResourceRequest(BaseModel):
    resource_id: str = Field(min_length=3, max_length=300)


class UpdateJob(BaseModel):
    id: str
    resource_id: str
    state: Literal["queued", "running", "success", "failed", "rolled_back"]
    progress: int = Field(ge=0, le=100)
    stage: str
    detail: str | None = None
    current_version: str | None = None
    latest_version: str | None = None
    update_available: bool | None = None


JOBS: dict[str, UpdateJob] = {}
JOBS_LOCK = threading.Lock()


def require_token(x_agent_token: str | None) -> None:
    if not AGENT_TOKEN:
        raise HTTPException(status_code=503, detail="UPDATE_AGENT_TOKEN is not configured")
    if x_agent_token != AGENT_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid update-agent token")


def run(*args: str, timeout: int | None = None) -> str:
    completed = subprocess.run(
        list(args),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout or COMMAND_TIMEOUT,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "Command failed").strip()
        raise RuntimeError(detail[-2000:])
    return completed.stdout.strip()


def run_best_effort(*args: str, timeout: int | None = None) -> None:
    try:
        run(*args, timeout=timeout)
    except Exception:
        pass


def safe_under_root(path: str) -> Path:
    if STACKS_ROOT is None:
        raise RuntimeError("UPDATE_AGENT_STACKS_ROOT is not configured")
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(STACKS_ROOT)
    except ValueError as exc:
        raise RuntimeError(f"Compose project is outside the allowed stacks root: {resolved}") from exc
    return resolved


def docker_inspect(container_id: str) -> dict:
    raw = run("docker", "inspect", container_id)
    data = json.loads(raw)
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise RuntimeError("Unexpected Docker inspect response")
    return data[0]


def image_version(image_id_or_ref: str) -> str | None:
    try:
        raw = run("docker", "image", "inspect", image_id_or_ref)
        data = json.loads(raw)
        if not isinstance(data, list) or not data:
            return None
        config = data[0].get("Config") or {}
        labels = config.get("Labels") or {}
        for key in (
            "org.opencontainers.image.version",
            "org.label-schema.version",
            "version",
        ):
            value = labels.get(key)
            if value:
                return str(value)
        tags = data[0].get("RepoTags") or []
        if tags:
            return str(tags[0]).rsplit(":", 1)[-1]
    except Exception:
        return None
    return None


def map_compose_working_dir(project: str, label_working_dir: str) -> tuple[Path, Path]:
    """Map a Compose label path to the read-only stacks mount.

    Docker Compose records the path seen by the process that created the
    project. Dockge commonly records a path such as /opt/stacks/my-stack even
    when the host path mounted into Dockge is different. When that label path
    is not directly visible in this agent, the safe fallback is the matching
    stack-folder basename (then project name) under STACKS_ROOT. The resulting
    path is still checked against STACKS_ROOT.
    """
    label_path = Path(label_working_dir)
    try:
        return safe_under_root(str(label_path)), label_path
    except RuntimeError:
        if STACKS_ROOT is None:
            raise
        candidates = [STACKS_ROOT / label_path.name, STACKS_ROOT / project]
        for candidate in candidates:
            mapped = safe_under_root(str(candidate))
            if mapped.exists():
                return mapped, label_path
        raise RuntimeError(
            f"Compose project path {label_path} is outside the allowed stacks root and "
            f"no matching stack directory exists under {STACKS_ROOT}"
        )


def split_config_files(value: str, working_dir: Path, label_working_dir: Path) -> list[str]:
    files: list[str] = []
    for part in value.split(","):
        item = part.strip()
        if not item:
            continue
        candidate = Path(item)
        if not candidate.is_absolute():
            candidate = label_working_dir / candidate
        try:
            relative = candidate.relative_to(label_working_dir)
        except ValueError as exc:
            raise RuntimeError(f"Compose config file is outside its project directory: {candidate}") from exc
        resolved = safe_under_root(str(working_dir / relative))
        if not resolved.exists():
            raise RuntimeError(f"Compose file is not visible to update agent: {resolved}")
        files.append(str(resolved))
    if not files:
        for candidate_name in ("compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml"):
            candidate = working_dir / candidate_name
            if candidate.exists():
                files.append(str(candidate))
                break
    if not files:
        raise RuntimeError(f"No Compose file found for {working_dir}")
    return files


def list_resources_internal() -> list[Resource]:
    if STACKS_ROOT is None:
        return []
    ids = [line.strip() for line in run("docker", "ps", "-aq").splitlines() if line.strip()]
    grouped: dict[str, Resource] = {}
    for container_id in ids:
        try:
            info = docker_inspect(container_id)
            config = info.get("Config") or {}
            labels = config.get("Labels") or {}
            project = labels.get("com.docker.compose.project")
            service = labels.get("com.docker.compose.service")
            working_dir_raw = labels.get("com.docker.compose.project.working_dir")
            if not project or not service or not working_dir_raw:
                continue
            working_dir, label_working_dir = map_compose_working_dir(str(project), str(working_dir_raw))
            config_files = split_config_files(
                str(labels.get("com.docker.compose.project.config_files") or ""),
                working_dir,
                label_working_dir,
            )
            resource_id = f"{project}/{service}"
            image = str(config.get("Image") or "")
            name = str(info.get("Name") or "").lstrip("/")
            if resource_id not in grouped:
                grouped[resource_id] = Resource(
                    id=resource_id,
                    project=str(project),
                    service=str(service),
                    image=image,
                    container_names=[name] if name else [],
                    working_dir=str(working_dir),
                    config_files=config_files,
                )
            elif name and name not in grouped[resource_id].container_names:
                grouped[resource_id].container_names.append(name)
        except Exception:
            continue
    return sorted(grouped.values(), key=lambda item: (item.project.casefold(), item.service.casefold()))


def get_resource(resource_id: str) -> Resource:
    for resource in list_resources_internal():
        if resource.id == resource_id:
            return resource
    raise RuntimeError("Compose service was not found or is outside the configured stacks root")


def compose_args(resource: Resource) -> list[str]:
    args = ["docker", "compose", "--project-directory", resource.working_dir]
    for config_file in resource.config_files:
        args.extend(["-f", config_file])
    return args


def resource_containers(resource: Resource) -> list[dict]:
    result: list[dict] = []
    ids = [line.strip() for line in run(
        "docker", "ps", "-aq",
        "--filter", f"label=com.docker.compose.project={resource.project}",
        "--filter", f"label=com.docker.compose.service={resource.service}",
    ).splitlines() if line.strip()]
    for container_id in ids:
        result.append(docker_inspect(container_id))
    return result


def running_image_id(resource: Resource) -> str | None:
    containers = resource_containers(resource)
    if not containers:
        return None
    return str(containers[0].get("Image") or "") or None


def inspect_local_image_id(image_ref: str) -> str | None:
    try:
        raw = run("docker", "image", "inspect", image_ref)
        data = json.loads(raw)
        return str(data[0].get("Id") or "") or None if isinstance(data, list) and data else None
    except Exception:
        return None


def check_resource(resource: Resource) -> dict:
    before_id = running_image_id(resource)
    current_version = image_version(before_id) if before_id else None
    if not resource.image:
        raise RuntimeError("Container does not expose an image reference")
    # Pulling does not recreate a running container. It gives a registry-agnostic,
    # authentication-compatible way to discover whether a mutable image tag changed.
    run("docker", "pull", resource.image)
    latest_id = inspect_local_image_id(resource.image)
    latest_version = image_version(latest_id or resource.image)
    return {
        "resource_id": resource.id,
        "image": resource.image,
        "update_available": bool(before_id and latest_id and before_id != latest_id),
        "current_version": current_version,
        "latest_version": latest_version,
        "current_image_id": before_id,
        "latest_image_id": latest_id,
    }


def set_job(job_id: str, **changes: object) -> None:
    with JOBS_LOCK:
        current = JOBS[job_id]
        JOBS[job_id] = current.model_copy(update=changes)


def wait_for_health(resource: Resource) -> tuple[bool, str]:
    deadline = time.time() + HEALTH_TIMEOUT
    last_detail = "Waiting for container"
    running_since: float | None = None
    while time.time() < deadline:
        containers = resource_containers(resource)
        if containers:
            all_ready = True
            has_healthcheck = False
            details: list[str] = []
            for info in containers:
                state = info.get("State") or {}
                running = bool(state.get("Running"))
                health = (state.get("Health") or {}).get("Status")
                has_healthcheck = has_healthcheck or bool(health)
                name = str(info.get("Name") or "container").lstrip("/")
                if not running:
                    all_ready = False
                    details.append(f"{name}: {state.get('Status') or 'not running'}")
                elif health and health != "healthy":
                    all_ready = False
                    details.append(f"{name}: {health}")
                else:
                    details.append(f"{name}: {'healthy' if health else 'running'}")
            last_detail = " · ".join(details)
            if all_ready:
                if has_healthcheck:
                    return True, last_detail
                # Containers without Docker healthchecks must stay running for a
                # short stabilization window before the update is accepted.
                if running_since is None:
                    running_since = time.time()
                elif time.time() - running_since >= 5:
                    return True, last_detail
            else:
                running_since = None
        else:
            running_since = None
        time.sleep(2)
    return False, last_detail


def update_worker(job_id: str) -> None:
    job = JOBS[job_id]
    rollback_tag: str | None = None
    resource: Resource | None = None
    old_image_id: str | None = None
    old_version: str | None = None
    image_ref: str | None = None
    try:
        set_job(job_id, state="running", progress=5, stage="Inspecting service")
        resource = get_resource(job.resource_id)
        old_image_id = running_image_id(resource)
        old_version = image_version(old_image_id) if old_image_id else None
        image_ref = resource.image
        if not old_image_id or not image_ref:
            raise RuntimeError("Could not identify the currently running image")

        set_job(job_id, progress=15, stage="Pulling image", current_version=old_version)
        run("docker", "pull", image_ref)
        new_image_id = inspect_local_image_id(image_ref)
        new_version = image_version(new_image_id or image_ref)
        if new_image_id == old_image_id:
            set_job(job_id, state="success", progress=100, stage="Already up to date", latest_version=new_version, update_available=False)
            return

        # Keep an addressable rollback tag until health verification completes.
        rollback_tag = f"homelab-dashboard-rollback/{resource.project}-{resource.service}:{job_id[:12]}".lower().replace("_", "-")
        run("docker", "image", "tag", old_image_id, rollback_tag)
        args = compose_args(resource)

        try:
            set_job(job_id, progress=60, stage="Recreating service", latest_version=new_version, update_available=True)
            run(*args, "up", "-d", "--no-deps", resource.service)

            set_job(job_id, progress=82, stage="Waiting for health")
            healthy, detail = wait_for_health(resource)
            if not healthy:
                raise RuntimeError(f"Updated service did not become healthy: {detail}")
        except Exception as update_exc:
            # Once the image has changed, any recreate/health failure triggers a
            # best-effort restoration of the image that was running beforehand.
            set_job(job_id, progress=90, stage="Update failed — rolling back", detail=str(update_exc)[-1000:])
            try:
                run("docker", "image", "tag", old_image_id, image_ref)
                run(*args, "up", "-d", "--no-deps", "--force-recreate", resource.service)
                rollback_ok, rollback_detail = wait_for_health(resource)
                if not rollback_ok:
                    raise RuntimeError(rollback_detail)
                if rollback_tag:
                    run_best_effort("docker", "image", "rm", rollback_tag)
                set_job(
                    job_id,
                    state="rolled_back",
                    progress=100,
                    stage="Update rolled back",
                    detail=f"{str(update_exc)[-700:]} · Restored: {rollback_detail}",
                    latest_version=old_version,
                    update_available=True,
                )
                return
            except Exception as rollback_exc:
                raise RuntimeError(
                    f"Update failed ({update_exc}); rollback also failed ({rollback_exc})"
                ) from rollback_exc

        if rollback_tag:
            run_best_effort("docker", "image", "rm", rollback_tag)
        set_job(job_id, state="success", progress=100, stage="Update complete", detail=detail, latest_version=new_version, update_available=False)
    except Exception as exc:
        set_job(job_id, state="failed", progress=100, stage="Update failed", detail=str(exc)[-1200:])


@app.get("/health")
def health(x_agent_token: str | None = Header(default=None)) -> dict:
    require_token(x_agent_token)
    return {"ok": True, "stacks_root": str(STACKS_ROOT) if STACKS_ROOT else None}


@app.get("/v1/resources", response_model=list[Resource])
def resources(x_agent_token: str | None = Header(default=None)) -> list[Resource]:
    require_token(x_agent_token)
    return list_resources_internal()


@app.post("/v1/check")
def check(payload: ResourceRequest, x_agent_token: str | None = Header(default=None)) -> dict:
    require_token(x_agent_token)
    try:
        return check_resource(get_resource(payload.resource_id))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/update", response_model=UpdateJob)
def start_update(payload: ResourceRequest, x_agent_token: str | None = Header(default=None)) -> UpdateJob:
    require_token(x_agent_token)
    try:
        get_resource(payload.resource_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = UpdateJob(id=uuid.uuid4().hex, resource_id=payload.resource_id, state="queued", progress=0, stage="Queued")
    with JOBS_LOCK:
        JOBS[job.id] = job
    threading.Thread(target=update_worker, args=(job.id,), daemon=True).start()
    return job


@app.get("/v1/jobs/{job_id}", response_model=UpdateJob)
def get_job(job_id: str, x_agent_token: str | None = Header(default=None)) -> UpdateJob:
    require_token(x_agent_token)
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Update job not found")
    return job
