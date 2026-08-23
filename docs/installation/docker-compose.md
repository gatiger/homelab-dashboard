# Install with Docker Compose

This is the reference installation method.

## Requirements

- A Linux host, NAS, VM, or server with Docker Engine and Docker Compose v2.
- An unused TCP port (8080 by default).

## Install

Create a folder and save `compose.yaml` from the repository into it, then optionally copy `.env.example` to `.env`.

```bash
docker compose pull
docker compose up -d
```

Open `http://SERVER-IP:8080` and create the first Owner account.

## Change the port

In `.env`:

```env
DASHBOARD_PORT=8082
```

## Pin a release

`latest` follows the newest stable release. For predictable upgrades, pin a version:

```env
DASHBOARD_VERSION=0.20.0
```

## Optional local Docker statistics

The base installation does **not** access the Docker socket. To enable read-only local Docker container statistics through the restricted socket proxy:

```bash
docker compose -f compose.yaml -f compose.docker.yaml up -d
```

The proxy is not published to the host and POST operations are disabled.

## Update

```bash
docker compose pull
docker compose up -d
```

Never add `-v` to `docker compose down` unless you intentionally want to delete dashboard data.
