# Install with Dockge

Dockge is a convenient Compose UI, but it is not required by Homelab Dashboard.

## Requirements

- A working Dockge installation.
- Access to create a new Compose stack.
- An unused host port (8080 by default).

## Recommended install

1. Create a new Dockge stack named `homelab-dashboard`.
2. Paste the repository's `compose.yaml` into the stack editor.
3. If port 8080 is already in use, change `${DASHBOARD_PORT:-8080}` to another host port or add `DASHBOARD_PORT` in the stack environment.
4. Start the stack.
5. Open `http://SERVER-IP:PORT` and create the first administrator account.

Because the production Compose file uses the published GHCR image, Dockge no longer needs the repository's `backend` or `frontend` source folders.

## Enable Docker host insight

Dockge can merge the base Compose file with `compose.docker.yaml` when both files are available. If your Dockge workflow only uses one Compose editor, copy the `socket-proxy` service, `DOCKER_PROXY_URL`, and `docker-api` network sections from `compose.docker.yaml` into the stack.

Docker insight is optional. A Dockge card still works as a normal monitored link without it.

## Updating

Pull/recreate the stack using the same Compose configuration. Do not remove the `homelab-dashboard-data` volume.
